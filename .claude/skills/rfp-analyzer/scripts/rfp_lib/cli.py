"""Command-line interface: python scripts/rfp.py <command> [...]"""
from __future__ import annotations

import argparse
import csv
import datetime as _dt
import json
import shutil
import sys
from pathlib import Path

from . import __version__
from .config import load_config
from .state import (SPECS, active, audit, entity_of, get, load_state, new_state, paths, save_state,
                    upsert)
from .util import RfpError, fmt_num, now_iso, read_json, today

RENDER_TARGETS = {
    "requirements": "02-requirements-matrix.xlsx",
    "clarifications": "03-client-clarifications.xlsx",
    "estimation": "04-wbs-estimation.xlsx",
    "risks": "05-risks-and-assumptions.md",
    "scope": "06-scope-recommendations.md",
    "decisions": "08-decision-log.md",
    "traceability": "09-requirements-traceability.xlsx",
    "changes": "10-change-impact-register.xlsx",
    "coverage": "11-scope-coverage-report.md",
}


def _out(obj):
    print(json.dumps(obj, indent=2, ensure_ascii=False, default=str))


def _ctx(args, need_state=True):
    adir = Path(args.dir)
    config = load_config(args.config, adir)
    state = load_state(adir) if need_state else None
    return adir, config, state


def _archive(adir, name):
    """Copy an existing deliverable into history before it is overwritten."""
    src = Path(adir) / name
    if src.exists():
        stamp = _dt.datetime.now().strftime("%Y%m%d-%H%M%S")
        dst = paths(adir)["history"] / "deliverables" / stamp
        dst.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst / name)


# --------------------------------------------------------------------------- commands
def cmd_ingest(args):
    adir = Path(args.dir)
    config = load_config(args.config, adir)
    p = paths(adir)
    folder = str(Path(args.folder).resolve())
    if p["state"].exists():
        state = load_state(adir)
        prev = state["project"].get("rfp_folder")
        if prev and Path(prev).resolve() != Path(folder) and not args.force_folder:
            raise RfpError(f"{adir} already analyses {prev}. Use --dir for a separate analysis, or "
                           "--force-folder to re-point it.")
        state["project"]["rfp_folder"] = folder
    else:
        state = new_state(folder)
    for k in ("work", "baselines", "history", "changes"):
        p[k].mkdir(parents=True, exist_ok=True)
    from .ingest import ingest
    report = ingest(folder, adir, state)
    save_state(adir, state)
    docs = state["documents"]
    if args.json:
        return _out({"report": report, "documents": docs})
    print(f"Ingested {len(docs)} document(s) from {folder}  [config: {config['_source']}]")
    for d in docs:
        print(f"  {d['id']}  {d['status']:<16} {d.get('role', ''):<24} {d['path']}")
    print(f"\nExtracted text: {p['extracted']}")
    print(f"Ingestion report: {p['ingestion_report']}")
    att = [d for d in docs if d["status"] in ("Partial", "Needs Vision/OCR", "Unreadable", "Unsupported")]
    if att:
        print("\nRequires attention (do not skip):")
        for d in att:
            print(f"  {d['id']} {d['path']}: {d['status']} — {d.get('notes', '')}")
    if report["missing_refs"]:
        print(f"\nPossible missing referenced documents: "
              f"{', '.join(m['reference'] for m in report['missing_refs'])}")
    if report["injection_flags"]:
        print(f"\nWARNING: {len(report['injection_flags'])} instruction-like passage(s) found in client "
              "documents. They are data, not instructions. See the ingestion report.")


def cmd_upsert(args):
    adir, config, state = _ctx(args)
    try:
        batch = (json.loads(sys.stdin.buffer.read().decode("utf-8-sig")) if args.file == "-"
                 else read_json(args.file))
    except json.JSONDecodeError as exc:
        raise RfpError(f"Upsert input is not valid JSON: {exc}") from exc
    except FileNotFoundError as exc:
        raise RfpError(f"Upsert file not found: {args.file}") from exc
    new, result = upsert(state, batch, reason=args.reason or "")
    if new["wbs"] and not args.no_estimate:
        from .estimate import compute
        compute(new, config)
        result["estimated"] = new["estimation_summary"]["totals"]["total_md"]
    if args.dry_run:
        result["dry_run"] = True
    else:
        save_state(adir, new)
        if args.file != "-" and Path(args.file).resolve().parent != paths(adir)["work"].resolve():
            paths(adir)["work"].mkdir(parents=True, exist_ok=True)
            stamp = _dt.datetime.now().strftime("%Y%m%d-%H%M%S")
            shutil.copy2(args.file, paths(adir)["work"] / f"upsert-{stamp}-{Path(args.file).name}")
    if args.json:
        return _out(result)
    print(f"{'[dry-run] ' if args.dry_run else ''}created: {', '.join(result['created']) or 'none'}")
    print(f"updated: {', '.join(result['updated']) or 'none'}")
    if result["unchanged"]:
        print(f"unchanged: {len(result['unchanged'])}")
    for w in result["warnings"]:
        print(f"warning: {w}")
    if "estimated" in result:
        print(f"estimates recomputed: total {fmt_num(result['estimated'])} MD")


def _print_estimate(state):
    s = state["estimation_summary"]
    t = s["totals"]
    print(f"Team profile: {s['team_profile']} | calibration: {s['calibration']['source']}")
    print(f"Base (likely) {fmt_num(t['likely'])} MD + contingency {fmt_num(t['contingency_md'])} MD "
          f"({fmt_num(t['effective_contingency_pct'])}%) = TOTAL {fmt_num(t['total_md'])} MD")
    print(f"Range: low {fmt_num(t['low'])} / likely {fmt_num(t['likely'])} / high {fmt_num(t['high'])} MD;"
          f" PERT {fmt_num(t['expected'])}; provisional {fmt_num(t['provisional_md'])} MD")
    for title, key in (("Module", "by_module"), ("Role", "by_role"), ("Phase", "by_phase")):
        print(f"\nBy {title.lower()}:")
        for k, g in s[key].items():
            print(f"  {k:<32} {fmt_num(g['likely']):>8} likely  {fmt_num(g['total_md']):>8} total")
    tl = state["timeline"]
    print(f"\nTimeline: {fmt_num(tl['working_days'])} working days (~{fmt_num(tl['weeks'])} weeks) incl. "
          f"contingency; {fmt_num(state['timeline_base']['working_days'])} without.")
    print(f"Critical path: {' -> '.join(tl['critical_path']) or 'n/a'}")
    for w in tl["warnings"] + s["sanity_warnings"]:
        print(f"warning: {w}")
    if s["missing_estimates"]:
        print(f"MISSING estimates: {', '.join(s['missing_estimates'])}")


def cmd_estimate(args):
    adir, config, state = _ctx(args)
    from .estimate import compute
    compute(state, config)
    save_state(adir, state)
    if args.json:
        return _out({"summary": state["estimation_summary"], "timeline": state["timeline"]})
    _print_estimate(state)


def _render(adir, config, state, targets):
    from . import render_md, render_xlsx
    from .estimate import compute, is_stale
    if state["wbs"] and is_stale(state, config):
        compute(state, config)
    written = []
    for t in targets:
        name = RENDER_TARGETS[t]
        path = Path(adir) / name
        if t == "estimation" and not state.get("estimates"):
            print(f"skip {name}: no estimates yet")
            continue
        _archive(adir, name)
        if t == "requirements":
            render_xlsx.requirements_matrix(state, config, path)
        elif t == "clarifications":
            copy = Path(adir) / "03-client-clarifications-CLIENT-COPY.xlsx" \
                if config["outputs"].get("client_copy_clarifications", True) else None
            if copy:
                _archive(adir, copy.name)
            render_xlsx.clarifications(state, config, path, copy)
            if copy:
                written.append(str(copy))
        elif t == "estimation":
            render_xlsx.estimation(state, config, path)
        elif t == "traceability":
            render_xlsx.traceability(state, config, path, adir)
        elif t == "changes":
            render_xlsx.change_register(state, config, path)
        elif t == "risks":
            path.write_text(render_md.risks_and_assumptions(state, config), encoding="utf-8")
        elif t == "scope":
            path.write_text(render_md.scope_recommendations(state, config), encoding="utf-8")
        elif t == "decisions":
            path.write_text(render_md.decision_log(state, config), encoding="utf-8")
        elif t == "coverage":
            path.write_text(render_md.coverage_report(state, config, adir), encoding="utf-8")
        written.append(str(path))
    audit(state, "render", ", ".join(targets))
    return written


def cmd_render(args):
    adir, config, state = _ctx(args)
    targets = list(RENDER_TARGETS) if not args.targets or "all" in args.targets else args.targets
    bad = [t for t in targets if t not in RENDER_TARGETS]
    if bad:
        raise RfpError(f"Unknown render target(s) {bad}. Choose from: all, {', '.join(RENDER_TARGETS)}")
    written = _render(adir, config, state, targets)
    save_state(adir, state)
    for w in written:
        print(f"wrote {w}")


def cmd_sow(args):
    adir, config, state = _ctx(args)
    from .estimate import compute, is_stale
    if is_stale(state, config):
        compute(state, config)
    if args.markdown:
        from .render_docx import check_final_gate, sow_markdown
        if not args.draft:
            check_final_gate(state)
        out = Path(adir) / "07-statement-of-work.md"
        out.write_text(sow_markdown(state, config), encoding="utf-8")
        print(f"wrote {out} (Markdown fallback)")
        return
    from .render_docx import build_sow
    res = build_sow(state, config, adir, draft=args.draft, force=args.force, pdf=args.pdf)
    _render(adir, config, state, ["decisions"])
    save_state(adir, state)
    print(f"wrote {res['path']} — {res['record']['status']} v{res['record']['version']}, "
          f"total {fmt_num(res['record']['total_md'])} man-days")
    for w in res["warnings"]:
        print(f"warning: {w}")
    if res["pdf"]:
        print(f"pdf: {res['pdf']}")


def cmd_validate(args):
    adir, config, state = _ctx(args)
    from .estimate import compute, is_stale
    from .render_md import coverage_report
    from .trace import validate
    if state["wbs"] and is_stale(state, config) and not args.no_recompute:
        compute(state, config)
        save_state(adir, state)
    rep = validate(state, config, adir)
    _archive(adir, RENDER_TARGETS["coverage"])
    (Path(adir) / RENDER_TARGETS["coverage"]).write_text(coverage_report(state, config, adir),
                                                          encoding="utf-8")
    if args.json:
        _out(rep)
    else:
        print(f"Readiness: {rep['readiness']}  (errors {rep['counts']['ERROR']}, warnings "
              f"{rep['counts']['WARNING']}, info {rep['counts']['INFO']})")
        for f in rep["findings"]:
            print(f"  {f['severity']:<7} [{f['check']}] {f['message']}")
        print(f"\nwrote {Path(adir) / RENDER_TARGETS['coverage']}")
    if args.strict and rep["counts"]["ERROR"]:
        sys.exit(1)


def cmd_trace(args):
    adir, config, state = _ctx(args)
    from .trace import matrix
    rows = matrix(state)
    if args.id:
        rows = [r for r in rows if r["requirement"] == args.id]
    if args.json:
        return _out(rows)
    for r in rows:
        print(f"{r['requirement']} [{r['status']}] Q:{','.join(r['clarifications']) or '-'} "
              f"WBS:{','.join(r['wbs']) or '-'} EST:{','.join(r['estimates']) or '-'} "
              f"ASM:{','.join(r['assumptions']) or '-'} RSK:{','.join(r['risks']) or '-'} "
              f"DEL:{','.join(r['deliverables']) or '-'} ({fmt_num(r['effort_md'])} MD)")


def cmd_impact(args):
    adir, config, state = _ctx(args)
    from . import impact
    if args.propose:
        spec = read_json(args.propose)
        spec.setdefault("target", args.req)
        if spec["target"] != args.req:
            raise RfpError(f"Spec target {spec['target']} does not match {args.req}.")
        rec = impact.propose(state, config, spec, adir)
        _render(adir, config, state, ["changes"])
        save_state(adir, state)
        if args.json:
            return _out(rec)
        print(rec["summary"])
        print(f"Module deltas: {rec['module_delta'] or 'none'}")
        for w in rec["wbs_changes"]:
            print(f"  {w['wbs']} {w['action']}: {fmt_num(w['before_md'])} -> {fmt_num(w['after_md'])} MD")
        for m in rec["milestone_shift"]:
            print(f"  milestone shift: {m['phase']} {'+' if m['shift_days'] >= 0 else ''}"
                  f"{fmt_num(m['shift_days'])} days {m['milestones']}")
        if rec["assumptions_invalidated"]:
            print(f"Assumptions to invalidate: {', '.join(rec['assumptions_invalidated'])}")
        if rec["assumptions_to_review"]:
            print(f"Assumptions to re-check: {', '.join(rec['assumptions_to_review'])}")
        print(f"\nStatus: PENDING APPROVAL. Approve with: rfp.py change approve {rec['id']} --by \"<name>\"")
        return
    if args.req == "NEW":
        raise RfpError("For a new requirement, pass --propose <spec.json> with target NEW.")
    info = impact.show(state, args.req)
    if args.json:
        return _out(info)
    r = info["requirement"]
    print(f"1. Requirement {r['id']} [{r['module']}] ({r.get('classification')}, {r.get('scope')}, "
          f"{r.get('status')})\n   {r['description']}")
    print(f"2. Clarifications: " + ("; ".join(f"{q['id']} ({q['priority']}, {q['status']})"
                                            for q in info["clarifications"]) or "none"))
    print("3. WBS activities: " + ("; ".join(f"{w['id']} {w['activity']}" for w in info["wbs"]) or "none"))
    e = info["effort"]
    print(f"4. Current effort: {fmt_num(e['total_md'])} MD total ({fmt_num(e['likely'])} likely; range "
          f"{fmt_num(e['low'])}–{fmt_num(e['high'])})")
    if info["shared_wbs_note"]:
        print(f"   note: {', '.join(info['shared_wbs_note'])} also serve other requirements")
    print("5. Assumptions: " + ("; ".join(f"{a['id']} ({a['status']})" for a in info["assumptions"]) or "none"))
    print("6. Risks: " + ("; ".join(f"{k['id']} ({k['probability']}/{k['impact']})" for k in info["risks"])
                          or "none"))
    print("7. SOW deliverables: " + ("; ".join(f"{d['id']} {d['name']}" for d in info["deliverables"])
                                     or "none") + f" | SOW sections: {', '.join(info['sow_sections'])}")
    if info["changes"]:
        print("Change history: " + "; ".join(f"{c['id']} {c['approval_status']}" for c in info["changes"]))
    print("\nTo assess a change (items 8-12), write a change spec and run:\n"
          f"  rfp.py impact {args.req} --propose <spec.json>")


def cmd_change(args):
    adir, config, state = _ctx(args)
    from . import impact
    if args.action == "approve":
        state, rec = impact.approve(state, config, args.chg, args.by, args.note or "", args.force)
    else:
        state, rec = impact.reject(state, args.chg, args.by, args.note or "")
    _render(adir, config, state, ["changes", "decisions"])
    save_state(adir, state)
    print(f"{rec['id']} {rec['approval_status']} by {rec['decided_by']} (decision {rec['decision']}).")
    if rec["approval_status"] == "Approved":
        print(f"Applied. Total now {fmt_num(state['estimation_summary']['totals']['total_md'])} MD. "
              f"Project status: {state['project']['status']}.")
        if state["project"]["status"] != "Approved Baseline" and state["baselines"]:
            print("Re-approve the baseline before issuing a final SOW.")


def cmd_answer(args):
    adir, config, state = _ctx(args)
    q = get(state, args.qid)
    if not q or not args.qid.startswith("Q-"):
        raise RfpError(f"Clarification {args.qid} not found.")
    q.update({"answer": args.answer, "answer_source": args.source or "", "answered_date": today(),
              "status": "Closed" if args.close else "Answered", "needs_review": True,
              "updated": now_iso()})
    flagged = []
    for w in active(state, "wbs"):
        if set(w.get("requirements", [])) & set(q.get("requirements", [])):
            w["needs_review"] = True
            flagged.append(w["id"])
    audit(state, "answer", f"{args.qid} answered (source: {args.source or 'n/a'}); no approval implied")
    from .estimate import compute
    if state["wbs"]:
        compute(state, config)
    save_state(adir, state)
    print(f"{args.qid} marked {q['status']}. This records the client's answer only; it does NOT "
          "approve scope or estimates.")
    print(f"Review: requirements {', '.join(q.get('requirements', [])) or 'none'}; "
          f"assumptions {', '.join(q.get('assumptions', [])) or 'none'}; WBS flagged {', '.join(flagged) or 'none'}.")
    print("After updating them, clear the flags via upsert (needs_review=false).")


def cmd_baseline(args):
    adir, config, state = _ctx(args)
    from . import baseline
    if args.action == "approve":
        rec = baseline.approve(state, config, adir, args.by, args.accept_risks or "", args.notes or "")
        _render(adir, config, state, ["decisions", "coverage"])
        save_state(adir, state)
        print(f"Baseline v{rec['version']} approved by {rec['approved_by']}: {fmt_num(rec['totals']['total_md'])} "
              f"MD, {fmt_num(rec['timeline_days'])} working days. Snapshot: {rec['file']}")
        if rec["accepted_risks"]:
            print(f"Accepted risks recorded ({len(rec['accepted_findings'])} unresolved error(s)).")
    elif args.action == "list":
        for b in state["baselines"]:
            print(f"v{b['version']} {b['date'][:10]} by {b['approved_by']}: {fmt_num(b['totals']['total_md'])} MD"
                  f"{' [accepted risks]' if b.get('accepted_risks') else ''}")
        if not state["baselines"]:
            print("No baselines approved yet.")
    else:
        _out(baseline.baseline_diff(state, adir, args.from_v, args.to_v))


def cmd_set_status(args):
    adir, config, state = _ctx(args)
    from .baseline import set_status
    old = set_status(state, args.status, args.reason, args.by or "")
    _render(adir, config, state, ["decisions"])
    save_state(adir, state)
    print(f"Status {old} -> {args.status}.")


def cmd_calibrate(args):
    adir, config, state = _ctx(args)
    from .estimate import calibrate, compute
    cal = calibrate(state, args.csv)
    if state["wbs"]:
        compute(state, config)
    save_state(adir, state)
    _out(cal)


def cmd_get(args):
    adir, config, state = _ctx(args)
    item = get(state, args.id)
    if not item:
        raise RfpError(f"{args.id} not found.")
    _out(item)


def cmd_list(args):
    adir, config, state = _ctx(args)
    if args.entity not in list(SPECS) + ["estimates"]:
        raise RfpError(f"Unknown entity '{args.entity}'. Choose from {list(SPECS) + ['estimates']}")
    items = state.get(args.entity, [])
    for cond in args.where or []:
        k, _, v = cond.partition("=")
        items = [i for i in items if str(i.get(k)) == v or (isinstance(i.get(k), list) and v in i.get(k))]
    if args.json:
        return _out(items)
    for i in items:
        label = i.get("description") or i.get("question") or i.get("activity") or i.get("name") or i.get("path")
        print(f"{i['id']}  {i.get('status', '')}  {str(label)[:110]}")


def cmd_export_csv(args):
    adir, config, state = _ctx(args)
    from .trace import matrix
    out = paths(adir)["root"] / "csv"
    out.mkdir(exist_ok=True)

    def dump(name, rows):
        if not rows:
            return
        with open(out / name, "w", newline="", encoding="utf-8-sig") as f:
            wr = csv.DictWriter(f, fieldnames=list(rows[0].keys()), extrasaction="ignore")
            wr.writeheader()
            for r in rows:
                wr.writerow({k: (", ".join(map(str, v)) if isinstance(v, list) else v) for k, v in r.items()})
    dump("requirements.csv", state["requirements"])
    dump("clarifications.csv", state["clarifications"])
    dump("wbs.csv", state["wbs"])
    dump("estimates.csv", state.get("estimates", []))
    dump("traceability.csv", matrix(state))
    dump("changes.csv", [{k: v for k, v in c.items() if k not in ("spec", "previous_state")}
                         for c in state["changes"]])
    print(f"wrote CSV files to {out}")


STAGES = [
    ("1. Analyze", "Read documents and write 01-executive-summary.md"),
    ("2. Clarify", "Requirements matrix (02) and clarification register (03)"),
    ("3. Estimate", "WBS and AI-first estimates (04)"),
    ("4. Review", "Risks/assumptions (05), scope strategy (06), traceability (09), coverage (11)"),
    ("5. Approve", "PM approves baseline"),
    ("6. Generate SOW", "Final client SOW (07) from the approved baseline"),
]


def stage_progress(state, config, adir):
    from .estimate import is_stale
    root = Path(adir)
    has = lambda n: (root / n).exists()  # noqa: E731
    sow_final = [v for v in state["sow"].get("versions", []) if v["status"] == "Final"
                 and v.get("baseline_version") == state["project"].get("baseline_version")]
    done = [
        bool(state["documents"]) and has("01-executive-summary.md"),
        bool(state["requirements"]) and bool(state["clarifications"]) and has(RENDER_TARGETS["requirements"])
        and has(RENDER_TARGETS["clarifications"]),
        bool(state.get("estimates")) and not is_stale(state, config) and has(RENDER_TARGETS["estimation"]),
        bool(state["risks"] or state["assumptions"]) and bool(state.get("scope_strategy"))
        and has(RENDER_TARGETS["risks"]) and has(RENDER_TARGETS["scope"]),
        state["project"]["status"] == "Approved Baseline",
        bool(sow_final) and state["project"]["status"] == "Approved Baseline",
    ]
    return done


def cmd_status(args):
    adir, config, state = _ctx(args)
    from .trace import validate
    done = stage_progress(state, config, adir)
    rep = validate(state, config, adir)
    p = state["project"]
    info = {
        "project": p.get("name") or "(not set)", "client": p.get("client") or "(not set)",
        "rfp_folder": p.get("rfp_folder"), "status": p["status"], "baseline": p.get("baseline_version"),
        "documents": {s: sum(1 for d in state["documents"] if d["status"] == s)
                      for s in sorted({d["status"] for d in state["documents"]})},
        "requirements": len(state["requirements"]),
        "open_questions": {pr: sum(1 for q in state["clarifications"]
                                   if q["priority"] == pr and q["status"] in ("Open", "Sent"))
                           for pr in ("Critical", "Important", "Optional")},
        "wbs": len(active(state, "wbs")),
        "total_md": (state.get("estimation_summary") or {}).get("totals", {}).get("total_md"),
        "pending_changes": [c["id"] for c in state["changes"] if c["approval_status"] == "Pending"],
        "readiness": rep["readiness"], "errors": rep["counts"]["ERROR"],
        "warnings": rep["counts"]["WARNING"],
        "stages": [{"stage": s, "what": w, "done": d} for (s, w), d in zip(STAGES, done)],
        "next": next((s for (s, _), d in zip(STAGES, done) if not d), "All stages complete"),
        "last_activity": (state.get("audit_log") or [{}])[-1],
    }
    if args.json:
        return _out(info)
    print(f"Project: {info['project']} | Client: {info['client']} | Status: {info['status']}"
          f"{' v' + str(info['baseline']) if info['baseline'] else ''}")
    print(f"RFP folder: {info['rfp_folder']}")
    print(f"Documents: {info['documents']} | Requirements: {info['requirements']} | WBS: {info['wbs']} | "
          f"Total: {fmt_num(info['total_md']) if info['total_md'] is not None else '-'} MD")
    print(f"Open questions: {info['open_questions']} | Pending changes: {info['pending_changes'] or 'none'}")
    print(f"Readiness: {info['readiness']} ({info['errors']} errors, {info['warnings']} warnings)")
    for s in info["stages"]:
        print(f"  [{'x' if s['done'] else ' '}] {s['stage']}: {s['what']}")
    print(f"Next: {info['next']}")
    la = info["last_activity"]
    if la:
        print(f"Last activity: {la.get('ts')} {la.get('action')} — {la.get('detail')}")


# --------------------------------------------------------------------------- parser
def build_parser():
    ap = argparse.ArgumentParser(prog="rfp.py", description="rfp-analyzer deterministic toolkit")
    ap.add_argument("--version", action="version", version=__version__)
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--dir", default="rfp-analysis", help="analysis directory (default ./rfp-analysis)")
    common.add_argument("--config", help="path to a config YAML")
    common.add_argument("--json", action="store_true", help="machine-readable output")
    sub = ap.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("ingest", parents=[common], help="discover and extract RFP documents")
    s.add_argument("folder")
    s.add_argument("--force-folder", action="store_true")
    s.set_defaults(fn=cmd_ingest)
    s = sub.add_parser("upsert", parents=[common], help="create/update entities from a JSON batch")
    s.add_argument("file", help="JSON batch file, or - for stdin")
    s.add_argument("--reason")
    s.add_argument("--dry-run", action="store_true")
    s.add_argument("--no-estimate", action="store_true")
    s.set_defaults(fn=cmd_upsert)
    s = sub.add_parser("estimate", parents=[common], help="recompute estimates, rollups and timeline")
    s.set_defaults(fn=cmd_estimate)
    s = sub.add_parser("render", parents=[common], help="render deliverables")
    s.add_argument("targets", nargs="*", help=f"all | {' | '.join(RENDER_TARGETS)}")
    s.set_defaults(fn=cmd_render)
    s = sub.add_parser("sow", parents=[common], help="generate the Statement of Work")
    s.add_argument("--draft", action="store_true")
    s.add_argument("--force", action="store_true", help="supersede an existing FINAL SOW (archived)")
    s.add_argument("--pdf", action="store_true")
    s.add_argument("--markdown", action="store_true", help="Markdown fallback (no python-docx)")
    s.set_defaults(fn=cmd_sow)
    s = sub.add_parser("validate", parents=[common], help="coverage & consistency validation")
    s.add_argument("--strict", action="store_true", help="exit 1 when errors exist")
    s.add_argument("--no-recompute", action="store_true")
    s.set_defaults(fn=cmd_validate)
    s = sub.add_parser("trace", parents=[common], help="print traceability")
    s.add_argument("id", nargs="?")
    s.set_defaults(fn=cmd_trace)
    s = sub.add_parser("impact", parents=[common], help="show or assess a requirement change")
    s.add_argument("req")
    s.add_argument("--propose", help="change spec JSON")
    s.set_defaults(fn=cmd_impact)
    s = sub.add_parser("change", parents=[common], help="approve or reject a proposed change")
    s.add_argument("action", choices=["approve", "reject"])
    s.add_argument("chg")
    s.add_argument("--by", required=True)
    s.add_argument("--note")
    s.add_argument("--force", action="store_true")
    s.set_defaults(fn=cmd_change)
    s = sub.add_parser("answer", parents=[common], help="record a clarification answer")
    s.add_argument("qid")
    s.add_argument("--answer", required=True)
    s.add_argument("--source", help="where the answer came from (e.g. client email 2026-10-20)")
    s.add_argument("--close", action="store_true")
    s.set_defaults(fn=cmd_answer)
    s = sub.add_parser("baseline", parents=[common], help="approve / list / diff baselines")
    s.add_argument("action", choices=["approve", "list", "diff"])
    s.add_argument("--by")
    s.add_argument("--accept-risks")
    s.add_argument("--notes")
    s.add_argument("--from", dest="from_v")
    s.add_argument("--to", dest="to_v")
    s.set_defaults(fn=cmd_baseline)
    s = sub.add_parser("set-status", parents=[common], help="set Draft or Reviewed")
    s.add_argument("status", choices=["Draft", "Reviewed"])
    s.add_argument("--reason", required=True)
    s.add_argument("--by")
    s.set_defaults(fn=cmd_set_status)
    s = sub.add_parser("calibrate", parents=[common], help="calibrate from historical actuals CSV")
    s.add_argument("csv")
    s.set_defaults(fn=cmd_calibrate)
    s = sub.add_parser("get", parents=[common], help="print one item by ID")
    s.add_argument("id")
    s.set_defaults(fn=cmd_get)
    s = sub.add_parser("list", parents=[common], help="list items of an entity")
    s.add_argument("entity")
    s.add_argument("--where", action="append", help="field=value filter (repeatable)")
    s.set_defaults(fn=cmd_list)
    s = sub.add_parser("export-csv", parents=[common], help="CSV fallback of the main tables")
    s.set_defaults(fn=cmd_export_csv)
    s = sub.add_parser("status", parents=[common], help="progress, readiness and next step (resume)")
    s.set_defaults(fn=cmd_status)
    return ap


def main(argv=None):
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass
    args = build_parser().parse_args(argv)
    try:
        args.fn(args)
    except RfpError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(2)
