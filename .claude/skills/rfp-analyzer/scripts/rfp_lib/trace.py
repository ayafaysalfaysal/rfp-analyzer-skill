"""Traceability matrix and coverage / consistency validation."""
from __future__ import annotations

import re
from pathlib import Path

from .estimate import OPEN_Q, is_stale, rollup, totals
from .state import SPECS, active, is_active, paths
from .util import as_list, r2

SEVERITY_ORDER = {"ERROR": 0, "WARNING": 1, "INFO": 2}
SUMMARY_HEADINGS = ["Project Overview", "Proposed Solution", "Functional Scope", "Technical Scope",
                    "Delivery Expectations", "Important Findings", "What the Client Actually Wants"]
CONTINGENCY_WORDS = re.compile(
    r"\bcontingency\b|^\s*(schedule\s+|effort\s+|estimate\s+)?buffer\b|\b(risk|management)\s+reserve\b",
    re.I)


# --------------------------------------------------------------------------- matrix
def build_links(state) -> list:
    """Flat many-to-many edge list: (from, relation, to)."""
    links = []
    add = lambda a, rel, b: links.append({"from": a, "relation": rel, "to": b})  # noqa: E731
    for q in state["clarifications"]:
        for r in q.get("requirements", []):
            add(r, "clarified by", q["id"])
    for w in active(state, "wbs"):
        for r in w.get("requirements", []):
            add(r, "implemented by", w["id"])
        if w.get("estimate_id"):
            add(w["id"], "estimated by", w["estimate_id"])
        for a in w.get("assumptions", []):
            add(w["id"], "assumes", a)
        for k in w.get("risks", []):
            add(w["id"], "exposed to", k)
        for d in w.get("deliverables", []):
            add(w["id"], "produces", d)
        for d in w.get("depends_on", []):
            add(w["id"], "depends on", d)
    for a in state["assumptions"]:
        for r in a.get("requirements", []):
            add(r, "assumes", a["id"])
        for w in a.get("wbs", []):
            add(w, "assumes", a["id"])
    for k in state["risks"]:
        for r in k.get("requirements", []):
            add(r, "exposed to", k["id"])
        for w in k.get("wbs", []):
            add(w, "exposed to", k["id"])
    for d in active(state, "deliverables"):
        for r in d.get("requirements", []):
            add(r, "delivered in", d["id"])
        for w in d.get("wbs", []):
            add(w, "produces", d["id"])
    for d in state["decisions"]:
        for r in d.get("requirements", []):
            add(r, "decided by", d["id"])
    # De-duplicate while preserving order.
    seen, out = set(), []
    for l in links:
        k = (l["from"], l["relation"], l["to"])
        if k not in seen:
            seen.add(k)
            out.append(l)
    return out


def related(state, req_id) -> dict:
    """Everything linked to one requirement (directly or through its WBS items)."""
    wbs = [w for w in active(state, "wbs") if req_id in w.get("requirements", [])]
    wbs_ids = {w["id"] for w in wbs}
    est = [e for e in state.get("estimates", []) if e["wbs"] in wbs_ids]
    qs = [q for q in state["clarifications"] if req_id in q.get("requirements", [])]
    asm_ids = {a for w in wbs for a in w.get("assumptions", [])}
    asm = [a for a in state["assumptions"]
           if a["id"] in asm_ids or req_id in a.get("requirements", []) or wbs_ids & set(a.get("wbs", []))]
    risk_ids = {k for w in wbs for k in w.get("risks", [])}
    risks = [k for k in state["risks"]
             if k["id"] in risk_ids or req_id in k.get("requirements", []) or wbs_ids & set(k.get("wbs", []))]
    del_ids = {d for w in wbs for d in w.get("deliverables", [])}
    dels = [d for d in active(state, "deliverables")
            if d["id"] in del_ids or req_id in d.get("requirements", []) or wbs_ids & set(d.get("wbs", []))]
    decs = [d for d in state["decisions"] if req_id in d.get("requirements", [])]
    excl = [x for x in active(state, "exclusions") if req_id in x.get("requirements", [])]
    deps = [d for d in state["dependencies"]
            if req_id in d.get("requirements", []) or wbs_ids & set(d.get("wbs", []))]
    return {"wbs": wbs, "estimates": est, "clarifications": qs, "assumptions": asm,
            "risks": risks, "deliverables": dels, "decisions": decs, "exclusions": excl,
            "dependencies": deps}


def matrix(state) -> list:
    rows = []
    for r in state["requirements"]:
        rel = related(state, r["id"])
        in_scope = r.get("scope") == "In Scope" and is_active(r)
        prov = any(e["provisional"] for e in rel["estimates"])
        if not is_active(r):
            status = "Removed"
        elif not in_scope:
            status = r.get("scope")
        elif r.get("classification") == "Assumption":
            status = "Assumption (no build)"
        elif not rel["wbs"]:
            status = "GAP: no WBS"
        elif not rel["estimates"]:
            status = "GAP: no estimate"
        elif not rel["deliverables"]:
            status = "GAP: no deliverable"
        elif prov:
            status = "Traced (provisional)"
        else:
            status = "Traced"
        rows.append({
            "requirement": r["id"], "description": r["description"], "module": r["module"],
            "scope": r.get("scope"), "classification": r.get("classification"),
            "clarifications": [q["id"] for q in rel["clarifications"]],
            "wbs": [w["id"] for w in rel["wbs"]],
            "estimates": [e["id"] for e in rel["estimates"]],
            "effort_md": r2(sum(e["total_md"] for e in rel["estimates"])),
            "assumptions": [a["id"] for a in rel["assumptions"]],
            "risks": [k["id"] for k in rel["risks"]],
            "deliverables": [d["id"] for d in rel["deliverables"]],
            "decisions": [d["id"] for d in rel["decisions"]],
            "status": status,
        })
    return rows


# --------------------------------------------------------------------------- validation
def _f(findings, check, severity, message, ids=()):
    findings.append({"check": check, "severity": severity, "message": message, "ids": list(ids)})


def validate(state, config, analysis_dir=None) -> dict:
    F = []
    reqs = {r["id"]: r for r in state["requirements"]}
    wbs_all = {w["id"]: w for w in state["wbs"]}
    wbs = {w["id"]: w for w in active(state, "wbs")}
    est = {e["wbs"]: e for e in state.get("estimates", [])}
    asm = {a["id"]: a for a in state["assumptions"]}
    in_scope = [r for r in state["requirements"]
                if is_active(r) and r.get("scope") == "In Scope" and r.get("classification") != "Assumption"]

    # 0. Referential integrity.
    ids_seen = {}
    for name in SPECS:
        for item in state.get(name, []):
            if item.get("id") in ids_seen:
                _f(F, "integrity", "ERROR", f"Duplicate ID {item['id']}.", [item["id"]])
            ids_seen[item.get("id")] = name
    all_ids = set(ids_seen) | {e["id"] for e in state.get("estimates", [])}
    for name, spec in SPECS.items():
        for item in state.get(name, []):
            for field in spec["refs"]:
                for ref in as_list(item.get(field)):
                    if ref not in all_ids:
                        _f(F, "integrity", "ERROR", f"{item['id']}.{field} references unknown {ref}.",
                           [item["id"]])
    for r in state["requirements"]:
        for s in r.get("sources", []):
            if s.get("doc") not in all_ids:
                _f(F, "integrity", "ERROR", f"{r['id']} cites unknown document {s.get('doc')}.", [r["id"]])

    # 1-2. Requirements -> WBS -> estimates.
    for r in in_scope:
        linked = [w for w in wbs.values() if r["id"] in w.get("requirements", [])]
        if not linked:
            _f(F, "req-without-wbs", "ERROR", f"{r['id']} ({r['module']}) is in scope but has no "
               "WBS activity.", [r["id"]])
        elif not any(w["id"] in est for w in linked):
            _f(F, "req-without-estimate", "ERROR", f"{r['id']} has WBS activities but no estimate.",
               [r["id"]])
    # 3. WBS without estimate.
    for w in wbs.values():
        if w["id"] not in est:
            _f(F, "wbs-without-estimate", "ERROR", f"{w['id']} '{w['activity']}' has no estimate "
               "(set likely_md or components, then run `estimate`).", [w["id"]])
    if is_stale(state, config):
        _f(F, "stale-estimates", "ERROR", "WBS, clarifications or configuration changed since the "
           "last estimate. Run `rfp.py estimate`.")
    # 4. Orphaned WBS.
    for w in wbs.values():
        if not w.get("requirements") and not w.get("cross_cutting"):
            _f(F, "orphan-wbs", "WARNING", f"{w['id']} '{w['activity']}' is linked to no requirement "
               "(set cross_cutting=true for PM/architecture/QA-type activities).", [w["id"]])
    # 5. Justification.
    for w in wbs.values():
        if not (w.get("effort_drivers") or w.get("estimation_notes") or w.get("components")
                or w.get("assumptions")):
            _f(F, "unjustified-estimate", "WARNING", f"{w['id']} has no effort drivers, component "
               "breakdown, notes or assumptions to justify its estimate.", [w["id"]])
        if w.get("components") and w.get("likely_md") is not None and \
                abs(sum(w["components"].values()) - w["likely_md"]) > 0.01:
            _f(F, "component-mismatch", "ERROR", f"{w['id']}: components sum to "
               f"{sum(w['components'].values())} but likely_md is {w['likely_md']}. Components win; "
               "remove or correct likely_md.", [w["id"]])
        if w.get("needs_review"):
            _f(F, "needs-review", "WARNING", f"{w['id']} is flagged for re-estimation after a "
               "clarification answer or change.", [w["id"]])
    # 6-7. Deliverables.
    for d in active(state, "deliverables"):
        if not d.get("requirements") and not d.get("wbs") and \
                not any(d["id"] in w.get("deliverables", []) for w in wbs.values()):
            _f(F, "orphan-deliverable", "WARNING", f"{d['id']} '{d['name']}' is linked to no "
               "requirement or WBS activity.", [d["id"]])
        if d.get("client_facing", True) and not d.get("acceptance_criteria"):
            _f(F, "deliverable-acceptance", "WARNING", f"{d['id']} '{d['name']}' has no acceptance "
               "criteria.", [d["id"]])
    for r in in_scope:
        rel_del = related(state, r["id"])["deliverables"]
        if not rel_del:
            _f(F, "req-without-deliverable", "WARNING", f"{r['id']} is not mapped to any SOW "
               "deliverable.", [r["id"]])
    # 8. Critical clarifications.
    for q in state["clarifications"]:
        if q.get("priority") == "Critical" and q.get("status") in OPEN_Q:
            _f(F, "open-critical-question", "ERROR", f"{q['id']} (Critical, {q['audience']}) is "
               f"unresolved: {q['question'][:120]}", [q["id"]] + q.get("requirements", []))
        if q.get("needs_review"):
            _f(F, "answer-needs-review", "WARNING", f"{q['id']} was answered; review linked "
               "requirements, assumptions and estimates.", [q["id"]])
    for r in in_scope:
        if r.get("clarification_required") and not any(
                r["id"] in q.get("requirements", []) for q in state["clarifications"]):
            _f(F, "clarification-missing", "WARNING", f"{r['id']} is marked clarification_required "
               "but no question references it.", [r["id"]])
    # 9. Assumptions.
    for w in wbs.values():
        for aid in w.get("assumptions", []):
            a = asm.get(aid)
            if not a:
                continue
            if a["status"] == "Invalidated":
                _f(F, "invalid-assumption", "ERROR", f"{w['id']} relies on invalidated assumption "
                   f"{aid}; re-estimate.", [w["id"], aid])
            elif a["status"] == "Proposed":
                _f(F, "unapproved-assumption", "WARNING", f"{w['id']} relies on unapproved "
                   f"assumption {aid}.", [w["id"], aid])
    for a in state["assumptions"]:
        if a["status"] not in ("Invalidated", "Superseded") and not a.get("if_wrong"):
            _f(F, "assumption-impact", "WARNING", f"{a['id']} does not state what happens if it "
               "proves incorrect.", [a["id"]])
        if not a.get("requirements") and not a.get("wbs") and \
                not any(a["id"] in w.get("assumptions", []) for w in wbs.values()):
            _f(F, "assumption-unlinked", "INFO", f"{a['id']} is not linked to any requirement or "
               "estimate.", [a["id"]])
    # 10. Estimates vs scope.
    for w in wbs.values():
        linked = [reqs[r] for r in w.get("requirements", []) if r in reqs]
        if linked and all(not is_active(r) or r.get("scope") != "In Scope" for r in linked):
            _f(F, "estimate-out-of-scope", "ERROR", f"{w['id']} is estimated but all its "
               "requirements are out of scope/deferred/removed.", [w["id"]])
    # 11-13. Arithmetic.
    estimates = state.get("estimates", [])
    if estimates:
        t = totals(estimates)
        for key in ("module", "role", "phase"):
            s = r2(sum(g["total_md"] for g in rollup(estimates, key).values()))
            if abs(s - t["total_md"]) > 0.011:
                _f(F, "rollup-mismatch", "ERROR", f"Sum by {key} ({s}) != overall total "
                   f"({t['total_md']}).")
        if abs(r2(t["likely"] + t["contingency_md"]) - t["total_md"]) > 0.011:
            _f(F, "contingency-arithmetic", "ERROR", "Base + contingency != total.")
        hpd = float(config["estimation"]["hours_per_man_day"])
        for e in estimates:
            if not e["low"] <= e["likely"] <= e["high"]:
                _f(F, "range-order", "ERROR", f"{e['id']} violates Low <= Likely <= High.", [e["wbs"]])
            if abs(e["hours"] - r2(e["total_md"] * hpd)) > 0.011:
                _f(F, "hours-arithmetic", "ERROR", f"{e['id']} hours != man-days x {hpd}.", [e["wbs"]])
        summary_total = (state.get("estimation_summary") or {}).get("totals", {}).get("total_md")
        if summary_total is not None and abs(summary_total - t["total_md"]) > 0.011:
            _f(F, "summary-mismatch", "ERROR", "Stored estimation summary disagrees with item totals.")
    for w in wbs.values():
        if CONTINGENCY_WORDS.search(f"{w['activity']} {w.get('workstream', '')}") or \
                any(CONTINGENCY_WORDS.search(k) for k in (w.get("components") or {})):
            _f(F, "double-contingency", "ERROR", f"{w['id']} looks like a contingency/buffer line. "
               "Contingency is applied separately; remove it from the WBS.", [w["id"]])
    for msg in (state.get("estimation_summary") or {}).get("sanity_warnings", []):
        _f(F, "effort-balance", "WARNING", msg)
    # 14. Decisions applied consistently.
    for d in state["decisions"]:
        if d.get("status") != "Approved":
            continue
        for rid, expected in (d.get("effect") or {}).items():
            r = reqs.get(rid)
            if not r:
                continue
            for field, value in (expected or {}).items():
                if r.get(field) != value:
                    _f(F, "decision-not-applied", "ERROR", f"{d['id']} (Approved) sets {rid}.{field}"
                       f"='{value}' but it is '{r.get(field)}'.", [d["id"], rid])
    # 15-16. Out-of-scope documentation and mandatory deferrals.
    ss = state.get("scope_strategy") or {}
    deferral_reqs = {}
    for entry in ss.get("deferrals", []) or []:
        for rid in entry.get("requirements", []):
            deferral_reqs[rid] = entry
    excluded = {rid for x in active(state, "exclusions") for rid in x.get("requirements", [])}
    for r in state["requirements"]:
        if not is_active(r) or r.get("scope") == "In Scope":
            continue
        if r["id"] not in excluded and r["id"] not in deferral_reqs:
            _f(F, "undocumented-exclusion", "WARNING", f"{r['id']} is {r['scope']} but not listed "
               "in exclusions or scope deferrals.", [r["id"]])
        if r.get("classification") == "Mandatory":
            entry = deferral_reqs.get(r["id"], {})
            has_decision = any(r["id"] in d.get("requirements", []) and d.get("status") == "Approved"
                               for d in state["decisions"])
            if not entry.get("compliance_impact") or not has_decision:
                _f(F, "mandatory-descoped", "ERROR", f"Mandatory {r['id']} is {r['scope']} without "
                   "a stated RFP-compliance impact and an Approved decision.", [r["id"]])
    # 17. Sources and priorities.
    for r in in_scope:
        if not r.get("sources") and r.get("classification") not in ("Proposed Improvement", "Assumption"):
            _f(F, "untraced-source", "WARNING", f"{r['id']} has no source reference.", [r["id"]])
        if r.get("priority_source") == "Client" and not r.get("sources"):
            _f(F, "unsupported-priority", "WARNING", f"{r['id']} claims a client-confirmed priority "
               "without a source reference.", [r["id"]])
    # 18. Modules covered.
    for module in sorted({r["module"] for r in in_scope}):
        if not any(w["module"] == module or set(w.get("requirements", [])) &
                   {r["id"] for r in in_scope if r["module"] == module} for w in wbs.values()):
            _f(F, "module-missing", "ERROR", f"Module '{module}' has in-scope requirements but no "
               "WBS work.")
    # 19. Timeline realism.
    tl = state.get("timeline") or {}
    for msg in tl.get("warnings", []):
        _f(F, "timeline", "WARNING", msg)
    if (config.get("timeline") or {}).get("client_review_days", 0) <= 0 and tl.get("phases"):
        _f(F, "timeline", "WARNING", "No client review time is planned at milestones.")
    for wid in wbs:
        if wbs[wid]["role"] not in (config["team"].get("roles") or {}):
            _f(F, "unknown-role", "WARNING", f"{wid} uses role '{wbs[wid]['role']}' not defined in "
               "team.roles.", [wid])
    for m in active(state, "milestones"):
        if tl.get("phases") and m.get("phase") not in {p["phase"] for p in tl["phases"]}:
            _f(F, "milestone-phase", "WARNING", f"{m['id']} '{m['name']}' is in phase "
               f"'{m.get('phase')}', which has no scheduled work.", [m["id"]])
    # 20. Changes.
    for c in state["changes"]:
        if c.get("approval_status") == "Pending":
            _f(F, "pending-change", "INFO", f"{c['id']} ({c['target']}) awaits approval: "
               f"{c['description'][:100]}", [c["id"]])
        if c.get("approval_status") == "Approved" and not c.get("applied"):
            _f(F, "change-not-applied", "ERROR", f"{c['id']} is approved but not applied.", [c["id"]])
    # 21. Documents.
    for d in state["documents"]:
        if d["status"] in ("Unreadable", "Unsupported", "Needs Vision/OCR", "Partial") and \
                not d.get("reviewed_manually"):
            _f(F, "document-unprocessed", "WARNING", f"{d['id']} `{d['path']}` is {d['status']}; "
               "review it (Claude Read tool / OCR) and set reviewed_manually=true.", [d["id"]])
    for m in state.get("missing_documents", []):
        if m.get("status") in ("Unconfirmed", "Missing", "Requested"):
            _f(F, "missing-document", "WARNING", f"Referenced document '{m['reference']}' "
               f"({m.get('referenced_in')}) is {m['status'].lower()}.")
    # 22. SOW in sync with baseline.
    sow = state.get("sow", {})
    last = (sow.get("versions") or [None])[-1]
    if last and last.get("status") == "Final":
        if last.get("baseline_version") != state["project"].get("baseline_version") or \
                state["project"].get("status") != "Approved Baseline":
            _f(F, "sow-out-of-sync", "ERROR", f"Final SOW v{last['version']} was generated from "
               f"baseline v{last.get('baseline_version')}; scope/estimates have changed since. "
               "Re-approve the baseline and regenerate the SOW.")
    if (config.get("company") or {}).get("name") in ("", "Your Company"):
        _f(F, "config-company", "INFO", "company.name is still the sample value; set it before "
           "generating a client SOW.")
    # 23. Executive summary present and complete.
    if analysis_dir:
        es = Path(analysis_dir) / "01-executive-summary.md"
        if not es.exists():
            _f(F, "summary-missing", "WARNING", "01-executive-summary.md has not been written.")
        else:
            text = es.read_text(encoding="utf-8")
            missing = [h for h in SUMMARY_HEADINGS if h.lower() not in text.lower()]
            if missing:
                _f(F, "summary-incomplete", "WARNING", f"Executive summary lacks sections: {missing}.")

    F.sort(key=lambda f: (SEVERITY_ORDER[f["severity"]], f["check"]))
    counts = {s: sum(1 for f in F if f["severity"] == s) for s in SEVERITY_ORDER}
    if not state["requirements"]:
        readiness = "NOT STARTED"
    elif counts["ERROR"]:
        readiness = "NOT READY"
    elif counts["WARNING"]:
        readiness = "READY WITH WARNINGS"
    else:
        readiness = "READY"
    rows = matrix(state)
    coverage = {
        "requirements_total": len(state["requirements"]),
        "in_scope": len(in_scope),
        "traced": sum(1 for r in rows if r["status"].startswith("Traced")),
        "gaps": sum(1 for r in rows if r["status"].startswith("GAP")),
        "out_of_scope": sum(1 for r in rows if r["status"] in ("Out of Scope", "Deferred")),
        "wbs_active": len(wbs), "wbs_estimated": sum(1 for w in wbs if w in est),
        "open_critical_questions": sum(1 for q in state["clarifications"]
                                       if q["priority"] == "Critical" and q["status"] in OPEN_Q),
        "provisional_estimates": sum(1 for e in estimates if e["provisional"]),
        "pending_changes": sum(1 for c in state["changes"] if c.get("approval_status") == "Pending"),
    }
    return {"findings": F, "counts": counts, "readiness": readiness, "coverage": coverage,
            "removed_wbs": [w for w in wbs_all if w not in wbs]}


def outputs_present(analysis_dir) -> dict:
    names = ["01-executive-summary.md", "02-requirements-matrix.xlsx", "03-client-clarifications.xlsx",
             "04-wbs-estimation.xlsx", "05-risks-and-assumptions.md", "06-scope-recommendations.md",
             "07-statement-of-work.docx", "08-decision-log.md", "09-requirements-traceability.xlsx",
             "10-change-impact-register.xlsx", "11-scope-coverage-report.md"]
    root = paths(analysis_dir)["root"]
    return {n: (root / n).exists() for n in names}
