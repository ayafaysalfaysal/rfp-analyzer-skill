"""Baseline management: Draft -> Reviewed -> Approved Baseline, with snapshots and diffs."""
from __future__ import annotations

from .estimate import compute, is_stale
from .state import SPECS, audit, next_id, paths
from .trace import validate
from .util import RfpError, deepcopy, now_iso, r2, read_json, today, write_json

SNAPSHOT_EXCLUDE = ("audit_log", "baselines")
STATUSES = ("Draft", "Reviewed", "Approved Baseline")


def snapshot(state) -> dict:
    return {k: deepcopy(v) for k, v in state.items() if k not in SNAPSHOT_EXCLUDE}


def diff(old: dict, new: dict) -> dict:
    """Entity-level diff between two snapshots (added / removed / changed fields)."""
    out = {"entities": {}, "totals": {}}
    for name in SPECS:
        if name in ("changes",):
            continue
        a = {i["id"]: i for i in old.get(name, [])}
        b = {i["id"]: i for i in new.get(name, [])}
        changed = {}
        for i in sorted(set(a) & set(b)):
            fields = {f: {"old": a[i].get(f), "new": b[i].get(f)}
                      for f in sorted(set(a[i]) | set(b[i]))
                      if f not in ("history", "updated", "created") and a[i].get(f) != b[i].get(f)}
            if fields:
                changed[i] = fields
        entry = {"added": sorted(set(b) - set(a)), "removed": sorted(set(a) - set(b)),
                 "changed": changed}
        if entry["added"] or entry["removed"] or entry["changed"]:
            out["entities"][name] = entry
    ta = (old.get("estimation_summary") or {}).get("totals", {})
    tb = (new.get("estimation_summary") or {}).get("totals", {})
    for k in ("likely", "contingency_md", "total_md", "low", "high"):
        if k in ta or k in tb:
            out["totals"][k] = {"old": ta.get(k), "new": tb.get(k),
                                "delta": r2((tb.get(k) or 0) - (ta.get(k) or 0))}
    out["timeline_days"] = {"old": (old.get("timeline") or {}).get("working_days"),
                            "new": (new.get("timeline") or {}).get("working_days")}
    return out


def approve(state, config, analysis_dir, by, accept_risks="", notes=""):
    """Approve the current scope/assumptions/estimates as a new baseline.

    Refuses when validation reports errors, unless the PM explicitly accepts the
    risks with a written statement (recorded in the baseline and decision log).
    """
    if not by:
        raise RfpError("Baseline approval requires --by <name of the approving PM>.")
    if is_stale(state, config) or not state.get("estimates"):
        compute(state, config)
    report = validate(state, config, analysis_dir)
    # An out-of-date SOW is resolved *by* re-baselining and regenerating, so it cannot block it.
    errors = [f for f in report["findings"]
              if f["severity"] == "ERROR" and f["check"] != "sow-out-of-sync"]
    if errors and not accept_risks:
        lines = "\n  - ".join(f"[{f['check']}] {f['message']}" for f in errors)
        raise RfpError(f"Baseline NOT approved: {len(errors)} unresolved error(s):\n  - {lines}\n"
                       "Resolve them, or re-run with --accept-risks \"<statement>\" to approve "
                       "with documented, PM-accepted risks.")
    version = (state["project"].get("baseline_version") or 0) + 1
    snap = snapshot(state)
    p = paths(analysis_dir)
    fname = p["baselines"] / f"baseline-v{version}.json"
    prev = state["baselines"][-1] if state["baselines"] else None
    changes = diff(read_json(p["root"] / prev["file"]), snap) if prev else None
    snap["project"] = {**snap["project"], "status": "Approved Baseline", "baseline_version": version}
    write_json(fname, snap)
    totals = state["estimation_summary"]["totals"]
    dec = deepcopy(SPECS["decisions"]["defaults"])
    dec.update({
        "id": next_id(state, "decisions"),
        "description": f"Approve baseline v{version} (scope, assumptions and estimates)",
        "status": "Approved", "owner": by, "date": today(),
        "scope_impact": f"{report['coverage']['in_scope']} in-scope requirements",
        "estimate_impact": f"{totals['total_md']} MD total (base {totals['likely']})",
        "timeline_impact": f"{state['timeline'].get('working_days')} working days",
        "rationale": notes + (f" Accepted risks: {accept_risks}" if accept_risks else ""),
        "created": now_iso(), "updated": now_iso(), "history": [],
    })
    state["decisions"].append(dec)
    record = {
        "version": version, "approved_by": by, "date": now_iso(),
        "file": str(fname.relative_to(p["root"])).replace("\\", "/"),
        "totals": {k: totals[k] for k in ("low", "likely", "high", "contingency_md", "total_md")},
        "timeline_days": state["timeline"].get("working_days"),
        "accepted_risks": accept_risks, "accepted_findings": errors if accept_risks else [],
        "open_warnings": sum(1 for f in report["findings"] if f["severity"] == "WARNING"),
        "notes": notes, "decision": dec["id"],
        "diff_from_previous": changes,
    }
    state["baselines"].append(record)
    state["project"]["status"] = "Approved Baseline"
    state["project"]["baseline_version"] = version
    audit(state, "baseline-approved", f"v{version} by {by}" +
          (f"; accepted {len(errors)} error(s)" if accept_risks else ""), actor=by)
    return record


def set_status(state, status, reason, by=""):
    if status not in ("Draft", "Reviewed"):
        raise RfpError("Use `baseline approve` to approve a baseline; set-status accepts Draft or "
                       "Reviewed.")
    if not reason:
        raise RfpError("A --reason is required to change status.")
    old = state["project"].get("status")
    state["project"]["status"] = status
    audit(state, "status", f"{old} -> {status}: {reason}", actor=by or "pm")
    return old


def baseline_diff(state, analysis_dir, v_old=None, v_new=None):
    p = paths(analysis_dir)
    bl = {b["version"]: b for b in state["baselines"]}
    if not bl:
        raise RfpError("No approved baselines yet.")
    v_old = int(v_old) if v_old else max(bl)
    old = read_json(p["root"] / bl[v_old]["file"])
    if v_new:
        new = read_json(p["root"] / bl[int(v_new)]["file"])
    else:
        new = snapshot(state)
    return diff(old, new)
