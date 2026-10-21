"""Change impact analysis: show, propose (what-if), approve, reject.

A proposal never modifies the working scope. It is evaluated on a copy of the
state, recorded as CHG-xxx with before/after values, and only applied after an
explicit approval naming the approver.
"""
from __future__ import annotations

from .estimate import compute, inputs_hash
from .state import SPECS, audit, get, next_id, paths, upsert
from .trace import related
from .util import RfpError, as_list, deepcopy, now_iso, r2, today, write_json

SOW_SECTIONS = {
    "scope": ["5. Scope of Work", "6. Detailed Modules and Functionality"],
    "technical": ["7. Technical Scope"],
    "deliverables": ["8. Deliverables", "19. Acceptance Criteria"],
    "milestones": ["11. Milestones"],
    "effort": ["12. Estimated Man-Days"],
    "timeline": ["13. Estimated Timeline"],
    "assumptions": ["17. Assumptions"],
    "exclusions": ["18. Exclusions"],
}
NEW_KEY = "__change_new_requirement__"


def show(state, req_id) -> dict:
    r = get(state, req_id)
    if not r or not req_id.startswith("REQ-"):
        raise RfpError(f"Requirement {req_id} not found.")
    rel = related(state, req_id)
    sections = list(SOW_SECTIONS["scope"])
    if rel["deliverables"]:
        sections += SOW_SECTIONS["deliverables"]
    if rel["estimates"]:
        sections += SOW_SECTIONS["effort"] + SOW_SECTIONS["timeline"]
    if [a for a in rel["assumptions"] if a.get("client_facing", True)]:
        sections += SOW_SECTIONS["assumptions"]
    if rel["exclusions"]:
        sections += SOW_SECTIONS["exclusions"]
    return {
        "requirement": r, **rel,
        "effort": {"likely": r2(sum(e["likely"] for e in rel["estimates"])),
                   "total_md": r2(sum(e["total_md"] for e in rel["estimates"])),
                   "low": r2(sum(e["low"] for e in rel["estimates"])),
                   "high": r2(sum(e["high"] for e in rel["estimates"]))},
        "sow_sections": sections,
        "changes": [c for c in state["changes"] if c.get("target") == req_id],
        "shared_wbs_note": [w["id"] for w in rel["wbs"] if len(w.get("requirements", [])) > 1],
    }


def _batch_from_spec(spec, chg_id) -> dict:
    target = spec["target"]
    batch = {"reason": f"{chg_id}: {spec.get('description', '')}"}
    sub = lambda v: NEW_KEY if v == "NEW" else v  # noqa: E731

    reqs = []
    if target == "NEW":
        if not spec.get("requirement"):
            raise RfpError("A NEW requirement change needs a 'requirement' object.")
        reqs.append({**spec["requirement"], "key": NEW_KEY})
    elif spec.get("requirement"):
        reqs.append({**spec["requirement"], "id": target})
    reqs += [dict(x) for x in spec.get("requirements", [])]
    if reqs:
        batch["requirements"] = reqs
    wbs = []
    for item in spec.get("wbs", []):
        item = dict(item)
        if "requirements" in item:
            item["requirements"] = [sub(x) for x in as_list(item["requirements"])]
        wbs.append(item)
    wbs += [{"id": w, "status": "Removed"} for w in spec.get("remove_wbs", [])]
    if wbs:
        batch["wbs"] = wbs
    asm = [dict(a) for a in spec.get("assumptions", [])]
    for a in asm:
        if "requirements" in a:
            a["requirements"] = [sub(x) for x in as_list(a["requirements"])]
    asm += [{"id": a, "status": "Invalidated"} for a in spec.get("invalidates_assumptions", [])]
    if asm:
        batch["assumptions"] = asm
    for coll in ("deliverables", "exclusions", "risks", "milestones"):
        if spec.get(coll):
            items = [dict(x) for x in spec[coll]]
            for x in items:
                if "requirements" in x:
                    x["requirements"] = [sub(v) for v in as_list(x["requirements"])]
            batch[coll] = items
    return batch


def _apply(state, spec, chg_id):
    work, res = upsert(state, _batch_from_spec(spec, chg_id), allow_locked=True,
                       actor=f"change {chg_id}")
    return work, res


def _phase_map(timeline):
    return {p["phase"]: p for p in (timeline or {}).get("phases", [])}


def propose(state, config, spec, analysis_dir=None) -> dict:
    """Evaluate a proposed change without altering the working scope."""
    target = spec.get("target")
    if not target:
        raise RfpError("Change spec needs 'target' (a REQ-xxx ID or 'NEW').")
    if target != "NEW" and (not get(state, target) or not target.startswith("REQ-")):
        raise RfpError(f"Target requirement {target} not found.")
    if not spec.get("description"):
        raise RfpError("Change spec needs a 'description' of the proposed change.")
    chg_id = next_id(state, "changes")

    before = deepcopy(state)
    compute(before, config)
    after, res = _apply(deepcopy(before), spec, chg_id)
    compute(after, config)
    new_req = (after.get("keys", {}).get("requirements", {}) or {}).get(NEW_KEY)
    target_after = new_req if target == "NEW" else target

    tb, ta = before["estimation_summary"]["totals"], after["estimation_summary"]["totals"]
    mods_b, mods_a = before["estimation_summary"]["by_module"], after["estimation_summary"]["by_module"]
    module_delta = {m: r2(mods_a.get(m, {}).get("total_md", 0) - mods_b.get(m, {}).get("total_md", 0))
                    for m in sorted(set(mods_b) | set(mods_a))}
    module_delta = {m: d for m, d in module_delta.items() if d}

    est_b = {e["wbs"]: e for e in before["estimates"]}
    est_a = {e["wbs"]: e for e in after["estimates"]}
    touched = set(res["created"]) | set(res["updated"])
    wbs_changes = []
    for wid in sorted(w for w in touched if w.startswith("WBS-")):
        b, a = est_b.get(wid), est_a.get(wid)
        wbs_changes.append({"wbs": wid, "before_md": b["total_md"] if b else 0.0,
                            "after_md": a["total_md"] if a else 0.0,
                            "delta_md": r2((a["total_md"] if a else 0) - (b["total_md"] if b else 0)),
                            "action": "added" if wid in res["created"] else
                            ("removed" if not a else "updated")})
    affected_reqs = {target_after} if target_after else set()
    for wid in touched:
        if wid.startswith("WBS-"):
            for st in (before, after):
                w = get(st, wid)
                if w:
                    affected_reqs.update(w.get("requirements", []))

    pb, pa = _phase_map(before["timeline"]), _phase_map(after["timeline"])
    milestone_shift = []
    for ph in sorted(set(pb) | set(pa)):
        d = r2(pa.get(ph, {}).get("acceptance", 0) - pb.get(ph, {}).get("acceptance", 0))
        if d:
            ms = [m["id"] for m in after["milestones"] if m.get("phase") == ph]
            milestone_shift.append({"phase": ph, "shift_days": d, "milestones": ms})
    tl_delta = r2(after["timeline"]["working_days"] - before["timeline"]["working_days"])

    rel_before = related(before, target) if target != "NEW" else {"assumptions": [], "wbs": []}
    review_asm = sorted({a["id"] for a in rel_before["assumptions"]
                         if a["status"] not in ("Invalidated", "Superseded")}
                        - set(spec.get("invalidates_assumptions", [])))

    sections = set()
    req_fields = set((spec.get("requirement") or {}).keys())
    if target == "NEW" or req_fields & {"description", "module", "type", "scope", "classification",
                                        "phase", "status"} or spec.get("requirements"):
        sections.update(SOW_SECTIONS["scope"])
    if req_fields & {"type"}:
        sections.update(SOW_SECTIONS["technical"])
    if (spec.get("requirement") or {}).get("scope") in ("Out of Scope", "Deferred") or spec.get("exclusions"):
        sections.update(SOW_SECTIONS["exclusions"])
    if abs(ta["total_md"] - tb["total_md"]) > 0.001:
        sections.update(SOW_SECTIONS["effort"])
    if tl_delta:
        sections.update(SOW_SECTIONS["timeline"])
    if milestone_shift:
        sections.update(SOW_SECTIONS["milestones"])
    if spec.get("assumptions") or spec.get("invalidates_assumptions"):
        sections.update(SOW_SECTIONS["assumptions"])
    if spec.get("deliverables"):
        sections.update(SOW_SECTIONS["deliverables"])

    threshold = float(config["estimation"].get("material_change_md", 2))
    delta_total = r2(ta["total_md"] - tb["total_md"])
    material = abs(delta_total) >= threshold or target == "NEW" or "scope" in req_fields or \
        bool(spec.get("remove_wbs")) or bool(milestone_shift)
    prev_items = {}
    for ident in [target] + [w["wbs"] for w in wbs_changes] + list(spec.get("invalidates_assumptions", [])):
        item = get(before, ident) if ident != "NEW" else None
        if item:
            prev_items[ident] = {k: v for k, v in item.items() if k != "history"}
    summary = (f"{chg_id} — {spec['description']}. Effort {tb['total_md']} → {ta['total_md']} MD "
               f"({'+' if delta_total >= 0 else ''}{delta_total}); timeline "
               f"{before['timeline']['working_days']} → {after['timeline']['working_days']} working days "
               f"({'+' if tl_delta >= 0 else ''}{tl_delta}). Affects {len(affected_reqs)} requirement(s)"
               f"{', SOW sections ' + ', '.join(sorted(sections)) if sections else ''}. "
               f"{'Material change: approval required.' if material else 'Minor change: approval still recorded.'}")
    record = {
        "id": chg_id, "target": target, "description": spec["description"],
        "requested_by": spec.get("requested_by", ""), "source": spec.get("source", ""),
        "created": now_iso(), "spec": spec, "previous_state": prev_items,
        "proposed_state": {k: v for k, v in spec.items() if k not in ("description", "target")},
        "affected_requirements": sorted(a for a in affected_reqs if a),
        "effort_before": {"likely": tb["likely"], "total_md": tb["total_md"]},
        "effort_after": {"likely": ta["likely"], "total_md": ta["total_md"]},
        "effort_delta_md": delta_total, "module_delta": module_delta, "wbs_changes": wbs_changes,
        "timeline_before_days": before["timeline"]["working_days"],
        "timeline_after_days": after["timeline"]["working_days"], "timeline_delta_days": tl_delta,
        "milestone_shift": milestone_shift, "sow_sections": sorted(sections),
        "assumptions_invalidated": list(spec.get("invalidates_assumptions", [])),
        "assumptions_to_review": review_asm, "material": material,
        "approval_required": True, "approval_status": "Pending", "applied": False,
        "baseline_version_at_proposal": state["project"].get("baseline_version"),
        "base_hash": inputs_hash(before, config), "summary": summary,
        "decided_by": "", "decided_at": "", "decision": None, "note": "",
    }
    state["changes"].append(record)
    audit(state, "change-proposed", summary)
    if analysis_dir:
        write_json(paths(analysis_dir)["changes"] / f"{chg_id}.json", record)
    return record


def _decision(state, description, status, by, reqs, record, note):
    dec = deepcopy(SPECS["decisions"]["defaults"])
    dec.update({
        "id": next_id(state, "decisions"), "description": description, "status": status,
        "owner": by, "date": today(), "requirements": sorted(reqs),
        "scope_impact": ", ".join(record.get("sow_sections", [])) or "None",
        "estimate_impact": f"{'+' if record['effort_delta_md'] >= 0 else ''}{record['effort_delta_md']} MD",
        "timeline_impact": f"{'+' if record['timeline_delta_days'] >= 0 else ''}"
                           f"{record['timeline_delta_days']} working days",
        "rationale": note, "created": now_iso(), "updated": now_iso(), "history": [],
        "change": record["id"],
    })
    state["decisions"].append(dec)
    return dec["id"]


def _find(state, chg_id):
    for c in state["changes"]:
        if c["id"] == chg_id:
            return c
    raise RfpError(f"Change {chg_id} not found.")


def approve(state, config, chg_id, by, note="", force=False):
    if not by:
        raise RfpError("Approval requires --by <name of the approver>.")
    c = _find(state, chg_id)
    if c["approval_status"] != "Pending":
        raise RfpError(f"{chg_id} is already {c['approval_status']}.")
    check = deepcopy(state)
    compute(check, config)
    if inputs_hash(check, config) != c["base_hash"] and not force:
        raise RfpError(f"Scope or estimates changed since {chg_id} was assessed. Re-run the impact "
                       "assessment (new proposal) or pass --force to apply anyway.")
    new_state, _ = _apply(state, c["spec"], chg_id)
    compute(new_state, config)
    c = _find(new_state, chg_id)
    new_req = (new_state.get("keys", {}).get("requirements", {}) or {}).get(NEW_KEY)
    if c["target"] == "NEW" and new_req:
        c["created_requirement"] = new_req
        new_state["keys"]["requirements"].pop(NEW_KEY, None)
        new_state["keys"]["requirements"][f"{chg_id}-new"] = new_req
        c["affected_requirements"] = sorted(set(c["affected_requirements"]) | {new_req})
    c.update({"approval_status": "Approved", "applied": True, "decided_by": by,
              "decided_at": now_iso(), "note": note,
              "effort_after_actual": new_state["estimation_summary"]["totals"]["total_md"]})
    c["decision"] = _decision(new_state, f"Approve change {chg_id}: {c['description']}", "Approved",
                              by, c["affected_requirements"], c, note)
    proj = new_state["project"]
    if proj.get("status") == "Approved Baseline":
        proj["status"] = "Reviewed"
        proj["notes"] = (f"Baseline v{proj['baseline_version']} superseded by approved change "
                         f"{chg_id}; re-approve the baseline before issuing a final SOW.")
    audit(new_state, "change-approved", f"{chg_id} by {by}", actor=by)
    return new_state, c


def reject(state, chg_id, by, note=""):
    if not by:
        raise RfpError("Rejection requires --by <name>.")
    c = _find(state, chg_id)
    if c["approval_status"] != "Pending":
        raise RfpError(f"{chg_id} is already {c['approval_status']}.")
    c.update({"approval_status": "Rejected", "decided_by": by, "decided_at": now_iso(), "note": note})
    c["decision"] = _decision(state, f"Reject change {chg_id}: {c['description']}", "Rejected", by,
                              c["affected_requirements"], c, note)
    audit(state, "change-rejected", f"{chg_id} by {by}", actor=by)
    return state, c
