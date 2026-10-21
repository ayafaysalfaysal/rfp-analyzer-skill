"""AI-first man-day estimation arithmetic and resource-aware scheduling.

Claude supplies the judgment for each work package (Likely effort or an effort
breakdown by component, optional Low/High, AI suitability, confidence). This
module applies the configured team profile and calibration, rounds, derives
ranges, applies contingency once per item, rolls up totals and builds a
dependency- and capacity-aware calendar estimate.
"""
from __future__ import annotations

import csv
import heapq
from collections import OrderedDict

from .state import active, audit, next_id, phases
from .util import (RfpError, add_working_days, id_parts, now_iso, parse_date, r2,
                   round_to, round_up_to, stable_hash)

OPEN_Q = ("Open", "Sent")


# --------------------------------------------------------------------------- inputs
def inputs_hash(state, config) -> str:
    """Fingerprint of everything an estimate depends on (to detect stale estimates)."""
    wbs = [{k: w.get(k) for k in ("id", "module", "activity", "role", "phase", "requirements",
                                  "depends_on", "components", "low_md", "likely_md", "high_md",
                                  "ai_suitability", "confidence", "assumptions", "provisional",
                                  "scheduling", "elapsed_days", "max_people", "status",
                                  "workstream")}
           for w in state["wbs"]]
    qs = [{k: q.get(k) for k in ("id", "priority", "status", "requirements")}
          for q in state["clarifications"]]
    asm = [{k: a.get(k) for k in ("id", "status")} for a in state["assumptions"]]
    cfg = {k: config.get(k) for k in ("estimation", "team", "timeline")}
    return stable_hash({"wbs": wbs, "q": qs, "asm": asm, "cfg": cfg,
                        "cal": state.get("calibration"), "phases": state["project"].get("phases")})


def is_stale(state, config) -> bool:
    return bool(state["wbs"]) and state.get("estimate_inputs_hash") != inputs_hash(state, config)


def calibration_factors(state, config):
    cal = state.get("calibration") or {}
    if cal.get("factors"):
        return cal["factors"], f"historical data: {cal.get('source', 'unspecified')}"
    f = float(config["estimation"]["ai_first"].get("calibration_factor") or 1.0)
    src = config["estimation"]["ai_first"].get("calibration_source") or (
        "none (factor 1.0, no historical data provided)" if f == 1.0 else "config")
    return {"High": f, "Medium": f, "Low": f}, src


def provisional_reasons(state, w) -> list:
    reasons = []
    if w.get("provisional"):
        reasons.append("flagged provisional by estimator")
    reqs = set(w.get("requirements", []))
    for q in state["clarifications"]:
        if q.get("priority") == "Critical" and q.get("status") in OPEN_Q and reqs & set(q.get("requirements", [])):
            reasons.append(f"depends on open critical clarification {q['id']}")
    asm_by_id = {a["id"]: a for a in state["assumptions"]}
    for aid in w.get("assumptions", []):
        a = asm_by_id.get(aid)
        if a and a.get("status") == "Invalidated":
            reasons.append(f"based on invalidated assumption {aid}")
    return reasons


def contingency_percent(config, confidence, provisional) -> float:
    c = config["estimation"]["contingency"]
    if c["method"] == "none":
        return 0.0
    if c["method"] == "flat":
        pct = float(c.get("flat_percent", 0))
    else:
        pct = float(c["by_confidence"].get(confidence, c["by_confidence"].get("Medium", 10)))
    if provisional:
        pct += float(c.get("provisional_extra_percent", 0))
    return min(pct, float(c.get("max_percent", 100)))


# --------------------------------------------------------------------------- per item
def compute_item(w, config, factors, reasons):
    est = config["estimation"]
    inc = est.get("rounding_increment") or 0
    comps = w.get("components") or {}
    raw_likely = sum(float(v) for v in comps.values()) if comps else w.get("likely_md")
    if raw_likely is None:
        return None
    suit = w.get("ai_suitability", "Medium")
    profile = est["ai_first"]["profiles"][est["ai_first"]["team_profile"]]
    multiplier = float(profile.get(suit, 1.0)) * float(factors.get(suit, 1.0))
    adj = float(raw_likely) * multiplier
    likely = round_to(adj, inc)
    if adj > 0 and likely == 0:
        likely = float(inc or adj)
    rm = est["range_multipliers"].get(w.get("confidence", "Medium"), {"low": 0.75, "high": 1.5})
    low = round_to(float(w["low_md"]) * multiplier, inc) if w.get("low_md") is not None \
        else round_to(adj * float(rm["low"]), inc)
    high = round_to(float(w["high_md"]) * multiplier, inc) if w.get("high_md") is not None \
        else round_to(adj * float(rm["high"]), inc)
    low, high = min(low, likely), max(high, likely)
    provisional = bool(reasons)
    pct = contingency_percent(config, w.get("confidence", "Medium"), provisional)
    cont = r2(likely * pct / 100)
    total = r2(likely + cont)
    return {
        "id": w["estimate_id"], "wbs": w["id"], "module": w["module"], "activity": w["activity"],
        "role": w["role"], "phase": w.get("phase", ""), "workstream": w.get("workstream") or w["module"],
        "ai_suitability": suit, "confidence": w.get("confidence", "Medium"),
        "complexity": w.get("complexity", "Medium"),
        "raw_likely": r2(raw_likely), "multiplier": round(multiplier, 4),
        "low": low, "likely": likely, "high": high,
        "expected": r2((low + 4 * likely + high) / 6),
        "contingency_pct": pct, "contingency_md": cont, "total_md": total,
        "hours": r2(total * float(est["hours_per_man_day"])),
        "provisional": provisional, "provisional_reasons": reasons,
        "components": {k: float(v) for k, v in comps.items()},
        "range_source": "explicit" if w.get("low_md") is not None or w.get("high_md") is not None
        else f"confidence multipliers ({w.get('confidence', 'Medium')})",
    }


# --------------------------------------------------------------------------- rollups
SUM_FIELDS = ("low", "likely", "high", "expected", "contingency_md", "total_md", "hours")


def rollup(estimates, key) -> "OrderedDict":
    out = OrderedDict()
    for e in estimates:
        g = out.setdefault(e[key] or "(unassigned)", {f: 0.0 for f in SUM_FIELDS} | {"count": 0})
        for f in SUM_FIELDS:
            g[f] += e[f]
        g["count"] += 1
    for g in out.values():
        for f in SUM_FIELDS:
            g[f] = r2(g[f])
    return out


def totals(estimates) -> dict:
    t = {f: r2(sum(e[f] for e in estimates)) for f in SUM_FIELDS}
    t["base_md"] = t["likely"]
    t["effective_contingency_pct"] = r2(t["contingency_md"] / t["likely"] * 100) if t["likely"] else 0.0
    t["provisional_md"] = r2(sum(e["total_md"] for e in estimates if e["provisional"]))
    t["count"] = len(estimates)
    return t


# --------------------------------------------------------------------------- scheduling
def schedule(state, config, estimates, basis="total_md") -> dict:
    team = config["team"]
    roles = team.get("roles") or {}
    tl = config["timeline"]
    loe_roles = set(tl.get("level_of_effort_roles") or [])
    wdpw = int(team.get("working_days_per_week", 5))
    wbs = {w["id"]: w for w in active(state, "wbs")}
    est = {e["wbs"]: e for e in estimates}
    warnings = []
    is_loe = lambda w: w.get("scheduling") == "level_of_effort" or w["role"] in loe_roles  # noqa: E731
    tasks = {wid for wid in est if wid in wbs and not is_loe(wbs[wid])}
    loe = [wid for wid in est if wid in wbs and is_loe(wbs[wid])]
    order_phases = phases(state)
    rank = {p: i for i, p in enumerate(order_phases)}

    # Kahn topological order, prioritised by (phase rank, numeric id).
    deps = {}
    for wid in tasks:
        ds = []
        for d in wbs[wid].get("depends_on", []):
            if d in tasks:
                ds.append(d)
            elif d not in wbs:
                warnings.append(f"{wid} depends on {d}, which is removed/unknown; dependency ignored.")
        deps[wid] = ds
    indeg = {wid: len(ds) for wid, ds in deps.items()}
    children = {wid: [] for wid in tasks}
    for wid, ds in deps.items():
        for d in ds:
            children[d].append(wid)
    key = lambda wid: (rank.get(wbs[wid].get("phase"), 999), id_parts(wid)[1])  # noqa: E731
    heap = [(key(w), w) for w in tasks if indeg[w] == 0]
    heapq.heapify(heap)
    order = []
    while heap:
        _, wid = heapq.heappop(heap)
        order.append(wid)
        for c in children[wid]:
            indeg[c] -= 1
            if indeg[c] == 0:
                heapq.heappush(heap, (key(c), c))
    if len(order) != len(tasks):
        cyc = sorted(set(tasks) - set(order))
        raise RfpError(f"Dependency cycle among work packages: {', '.join(cyc)}")

    pools, alloc = {}, {}
    for role in {wbs[w]["role"] for w in tasks}:
        cfg = roles.get(role) or {}
        count = int(cfg.get("count") or 0)
        a = float(cfg.get("allocation") or 1.0)
        if count <= 0:
            warnings.append(f"No capacity configured for role '{role}' (team.roles); assumed 1 "
                            "person at 100% for scheduling. Update the config.")
            count, a = 1, 1.0
        pools[role] = [[0.0, None] for _ in range(count)]
        alloc[role] = a

    default_k = int(team.get("max_people_per_item") or 1)
    review = float(tl.get("client_review_days") or 0)
    gating = bool(tl.get("phase_gating"))
    sched = OrderedDict()
    for wid in order:
        w, e = wbs[wid], est[wid]
        effort = float(e[basis])
        dep_finish, dep_driver = 0.0, None
        for d in deps[wid]:
            if sched[d]["finish"] > dep_finish:
                dep_finish, dep_driver = sched[d]["finish"], d
        gate = 0.0
        if gating:
            r = rank.get(w.get("phase"), 999)
            prior = [s["finish"] for s in sched.values() if rank.get(s["phase"], 999) < r]
            if prior:
                gate = max(prior) + review
        pool = pools[w["role"]]
        k = max(1, min(int(w.get("max_people") or default_k), len(pool)))
        chosen = sorted(range(len(pool)), key=lambda i: pool[i][0])[:k]
        res_free = max(pool[i][0] for i in chosen)
        blocker = max((pool[i] for i in chosen), key=lambda m: m[0])[1]
        start = max(dep_finish, gate, res_free)
        duration = effort / (k * alloc[w["role"]]) if effort > 0 else 0.0
        if w.get("elapsed_days"):
            duration = max(duration, float(w["elapsed_days"]))
        duration = round_up_to(duration, 0.5)
        finish = start + duration
        for i in chosen:
            pool[i] = [finish, wid]
        if start == 0:
            driver = None
        elif dep_driver and dep_finish >= max(gate, res_free):
            driver = dep_driver
        elif gate >= res_free:
            driver = "phase gate"
        else:
            driver = blocker
        sched[wid] = {"wbs": wid, "phase": w.get("phase", ""), "role": w["role"],
                      "workstream": w.get("workstream") or w["module"], "effort": effort,
                      "people": k, "start": start, "finish": finish, "duration": duration,
                      "driver": driver}

    dev_finish = max((s["finish"] for s in sched.values()), default=0.0)
    phase_rows, last_accept = [], 0.0
    for ph in order_phases:
        rows = [s for s in sched.values() if s["phase"] == ph]
        if not rows:
            continue
        start = min(s["start"] for s in rows)
        finish = max(s["finish"] for s in rows)
        accept = finish + review
        last_accept = max(last_accept, accept)
        phase_rows.append({"phase": ph, "start": start, "finish": finish,
                           "review_days": review, "acceptance": accept})
    end = (last_accept if phase_rows else dev_finish) + float(tl.get("deployment_buffer_days") or 0)
    if not sched:
        end = 0.0

    for role in sorted({wbs[w]["role"] for w in loe}):
        effort = sum(est[w][basis] for w in loe if wbs[w]["role"] == role)
        cfg = roles.get(role) or {}
        capacity = end * int(cfg.get("count") or 0) * float(cfg.get("allocation") or 0)
        if effort > capacity + 1e-6:
            warnings.append(f"{role} level-of-effort ({r2(effort)} MD) exceeds configured capacity "
                            f"over the {r2(end)}-day timeline ({r2(capacity)} MD). Increase "
                            "allocation or expect a longer timeline.")

    # Critical chain: walk back from the latest-finishing task via its drivers.
    path = []
    if sched:
        cur = max(sched.values(), key=lambda s: s["finish"])["wbs"]
        seen = set()
        while cur and cur in sched and cur not in seen:
            seen.add(cur)
            path.append(cur)
            cur = sched[cur]["driver"] if sched[cur]["driver"] in sched else None
        path.reverse()

    streams = OrderedDict()
    for s in sched.values():
        st = streams.setdefault(s["workstream"], {"workstream": s["workstream"], "start": s["start"],
                                                  "finish": s["finish"], "effort": 0.0, "items": []})
        st["start"], st["finish"] = min(st["start"], s["start"]), max(st["finish"], s["finish"])
        st["effort"] = r2(st["effort"] + s["effort"])
        st["items"].append(s["wbs"])
    events = sorted([(s["start"], 1) for s in sched.values() if s["duration"] > 0] +
                    [(s["finish"], -1) for s in sched.values() if s["duration"] > 0],
                    key=lambda x: (x[0], x[1]))
    conc = peak = 0
    for _, delta in events:
        conc += delta
        peak = max(peak, conc)

    start_date = parse_date(team.get("start_date"))
    result = {
        "basis": basis, "working_days": r2(end), "weeks": r2(end / wdpw) if wdpw else None,
        "development_finish_day": r2(dev_finish), "phases": phase_rows,
        "tasks": list(sched.values()), "critical_path": path,
        "workstreams": list(streams.values()), "max_parallel_tasks": peak,
        "level_of_effort": loe, "warnings": warnings,
        "assumptions": [
            f"{wdpw} working days per week; public holidays and leave are not modelled.",
            f"{r2(review)} working days of client review after each phase milestone.",
            f"{tl.get('deployment_buffer_days', 0)} working days for go-live after final acceptance.",
            "Team capacity per role as configured in team.roles.",
        ],
        "start_date": team.get("start_date") or "",
        "end_date": add_working_days(start_date, end, wdpw).isoformat() if start_date and end else "",
    }
    if start_date:
        for p in phase_rows:
            p["finish_date"] = add_working_days(start_date, p["finish"], wdpw).isoformat()
            p["acceptance_date"] = add_working_days(start_date, p["acceptance"], wdpw).isoformat()
    return result


# --------------------------------------------------------------------------- main entry
def compute(state, config) -> dict:
    """Recompute every estimate, rollup and timeline. Mutates state; returns the summary."""
    factors, cal_source = calibration_factors(state, config)
    estimates, missing = [], []
    for w in active(state, "wbs"):
        if not w.get("estimate_id"):
            w["estimate_id"] = next_id(state, "estimates")
        e = compute_item(w, config, factors, provisional_reasons(state, w))
        if e is None:
            missing.append(w["id"])
        else:
            estimates.append(e)
    t = totals(estimates)
    est_cfg = config["estimation"]
    role_sum = rollup(estimates, "role")
    pm_md = sum(g["likely"] for r, g in role_sum.items() if r.upper() in ("PM", "PROJECT MANAGER"))
    qa_md = sum(g["likely"] for r, g in role_sum.items() if r.upper().startswith("QA"))
    checks = []
    if t["likely"]:
        sc = est_cfg.get("sanity_checks", {})
        pm_pct, qa_pct = pm_md / t["likely"] * 100, qa_md / t["likely"] * 100
        if pm_pct < sc.get("pm_percent_min", 0) or pm_pct > sc.get("pm_percent_max", 100):
            checks.append(f"PM effort is {pm_pct:.1f}% of base effort (expected "
                          f"{sc.get('pm_percent_min')}–{sc.get('pm_percent_max')}%).")
        if qa_pct < sc.get("qa_percent_min", 0):
            checks.append(f"QA effort is {qa_pct:.1f}% of base effort (minimum "
                          f"{sc.get('qa_percent_min')}%).")
    summary = {
        "computed": now_iso(),
        "team_profile": est_cfg["ai_first"]["team_profile"],
        "calibration": {"factors": factors, "source": cal_source},
        "hours_per_man_day": est_cfg["hours_per_man_day"],
        "rounding_increment": est_cfg.get("rounding_increment"),
        "contingency_method": est_cfg["contingency"]["method"],
        "totals": t,
        "by_module": rollup(estimates, "module"),
        "by_role": role_sum,
        "by_phase": rollup(estimates, "phase"),
        "by_ai_suitability": rollup(estimates, "ai_suitability"),
        "missing_estimates": missing,
        "provisional": [e["wbs"] for e in estimates if e["provisional"]],
        "sanity_warnings": checks,
    }
    state["estimates"] = estimates
    state["estimation_summary"] = summary
    state["timeline"] = schedule(state, config, estimates, "total_md")
    state["timeline_base"] = {k: v for k, v in schedule(state, config, estimates, "likely").items()
                              if k in ("working_days", "weeks", "phases", "critical_path")}
    state["estimate_inputs_hash"] = inputs_hash(state, config)
    audit(state, "estimate", f"{len(estimates)} items; total {t['total_md']} MD "
                             f"(base {t['likely']} + contingency {t['contingency_md']})")
    return summary


# --------------------------------------------------------------------------- calibration
def calibrate(state, csv_path, min_rows=3) -> dict:
    """Derive actual/estimate ratios per AI-suitability class from historical data.

    CSV columns (header names case-insensitive): ai_suitability, estimated_md, actual_md.
    Optional: project, activity. Only real historical data should be used.
    """
    with open(csv_path, newline="", encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
    if not rows:
        raise RfpError("Calibration CSV is empty.")
    norm = [{(k or "").strip().lower(): (v or "").strip() for k, v in r.items()} for r in rows]
    for col in ("ai_suitability", "estimated_md", "actual_md"):
        if col not in norm[0]:
            raise RfpError(f"Calibration CSV needs column '{col}'.")
    sums = {"High": [0.0, 0.0, 0], "Medium": [0.0, 0.0, 0], "Low": [0.0, 0.0, 0]}
    skipped = 0
    for r in norm:
        suit = r["ai_suitability"].title()
        try:
            e, a = float(r["estimated_md"]), float(r["actual_md"])
        except ValueError:
            skipped += 1
            continue
        if suit not in sums or e <= 0 or a < 0:
            skipped += 1
            continue
        sums[suit][0] += e
        sums[suit][1] += a
        sums[suit][2] += 1
    tot_e = sum(v[0] for v in sums.values())
    tot_a = sum(v[1] for v in sums.values())
    if tot_e <= 0:
        raise RfpError("No usable rows in calibration CSV.")
    overall = round(tot_a / tot_e, 3)
    factors, detail = {}, {}
    for suit, (e, a, n) in sums.items():
        if n >= min_rows:
            factors[suit] = round(a / e, 3)
            detail[suit] = f"{n} rows, ratio {factors[suit]}"
        else:
            factors[suit] = overall
            detail[suit] = f"{n} rows (< {min_rows}); using overall ratio {overall}"
    state["calibration"] = {"factors": factors, "overall": overall, "detail": detail,
                            "rows_used": sum(v[2] for v in sums.values()), "rows_skipped": skipped,
                            "source": str(csv_path), "date": now_iso()}
    audit(state, "calibrate", f"factors={factors} from {csv_path}")
    return state["calibration"]
