"""Markdown deliverables: 05 risks & assumptions, 06 scope, 08 decision log, 11 coverage."""
from __future__ import annotations

from .estimate import OPEN_Q
from .state import active, phases
from .trace import outputs_present, validate
from .util import fmt_num, join_ids, now_iso

LEVEL = {"Low": 1, "Medium": 2, "High": 3}


def _cell(v) -> str:
    if isinstance(v, (list, tuple)):
        v = ", ".join(str(x) for x in v)
    return str(v if v not in (None, "") else "—").replace("|", "/").replace("\n", " ")


def _table(headers, rows) -> list:
    out = ["| " + " | ".join(headers) + " |", "|" + "|".join("---" for _ in headers) + "|"]
    out += ["| " + " | ".join(_cell(c) for c in r) + " |" for r in rows]
    return out


def _header(state, title, internal=True):
    p = state["project"]
    return [f"# {title}", "",
            f"**Project:** {p.get('name') or '(not set)'}  ",
            f"**Client:** {p.get('client') or '(not set)'}  ",
            f"**Status:** {p.get('status')}" +
            (f" (baseline v{p['baseline_version']})" if p.get("baseline_version") else "") + "  ",
            f"**Generated:** {now_iso()}" + ("  \n**Classification:** INTERNAL" if internal else ""),
            ""]


# --------------------------------------------------------------------------- 05
def risks_and_assumptions(state, config) -> str:
    L = _header(state, "Risks, Assumptions & Dependencies")
    est_by_wbs = {w["id"]: w.get("estimate_id") for w in state["wbs"]}
    L += ["## 1. Client-confirmed facts", "",
          "Only items confirmed by the client in writing are listed here. Everything else in this "
          "document is an assumption or a risk.", ""]
    facts = [q for q in state["clarifications"] if q["status"] in ("Answered", "Closed") and q.get("answer")]
    confirmed = [r for r in state["requirements"] if r.get("status") == "Confirmed"]
    if facts or confirmed:
        L += _table(["Ref", "Fact", "Source"],
                    [[q["id"], f"{q['question']} → {q['answer']}", q.get("answer_source")] for q in facts] +
                    [[r["id"], r["description"], "Requirement confirmed"] for r in confirmed])
    else:
        L.append("_No client confirmations recorded yet._")
    L += ["", "## 2. Risk register", ""]
    risks = sorted(state["risks"], key=lambda k: (-(LEVEL.get(k["probability"], 2) * LEVEL.get(k["impact"], 2)),
                                                  k["id"]))
    if risks:
        L += _table(["Risk ID", "Description", "Related Requirements", "Probability", "Impact", "Score",
                     "Mitigation", "Owner", "Status"],
                    [[k["id"], k["description"], k.get("requirements", []) + k.get("wbs", []),
                      k["probability"], k["impact"],
                      LEVEL.get(k["probability"], 2) * LEVEL.get(k["impact"], 2), k.get("mitigation"),
                      k.get("owner") or "TBD", k["status"]] for k in risks])
        L += ["", "Score = probability × impact (Low=1, Medium=2, High=3)."]
    else:
        L.append("_No risks recorded._")
    L += ["", "## 3. Assumptions", "",
          "Assumptions are **not** client-confirmed facts. Each must be confirmed, approved or "
          "replaced before the baseline is relied on.", ""]
    if state["assumptions"]:
        rows = []
        for a in state["assumptions"]:
            wbs = sorted(set(a.get("wbs", [])) |
                         {w["id"] for w in state["wbs"] if a["id"] in w.get("assumptions", [])})
            ests = [est_by_wbs[w] for w in wbs if est_by_wbs.get(w)]
            rows.append([a["id"], a["description"], a.get("source"), a.get("rationale"),
                         "Yes" if a["status"] == "Confirmed" else "No", a["status"],
                         a.get("requirements", []) + wbs + ests, a.get("if_wrong")])
        L += _table(["ID", "Assumption", "Source", "Why Needed", "Client-Confirmed", "Status",
                     "Dependent REQ / WBS / EST", "If Incorrect"], rows)
    else:
        L.append("_No assumptions recorded._")
    L += ["", "## 4. Dependencies", ""]
    if state["dependencies"]:
        L += _table(["ID", "Dependency", "Type", "Owner", "Needed By", "Related", "Status"],
                    [[d["id"], d["description"], d["type"], d.get("owner") or "TBD",
                      d.get("needed_by"), d.get("requirements", []) + d.get("wbs", []), d["status"]]
                     for d in state["dependencies"]])
    else:
        L.append("_No dependencies recorded._")
    L += ["", "## 5. Open critical questions affecting estimates", ""]
    crit = [q for q in state["clarifications"] if q["priority"] == "Critical" and q["status"] in OPEN_Q]
    if crit:
        L += _table(["Question", "Audience", "Question Text", "Related Requirements"],
                    [[q["id"], q["audience"], q["question"], q.get("requirements", [])] for q in crit])
        L += ["", "Estimates linked to these requirements are marked **provisional**."]
    else:
        L.append("_None._")
    est = state.get("estimates") or []
    prov = [e for e in est if e["provisional"]]
    L += ["", "## 6. Estimation confidence", ""]
    if est:
        counts = {lvl: sum(1 for e in est if e["confidence"] == lvl) for lvl in ("High", "Medium", "Low")}
        L.append(f"- Work packages by confidence: High {counts['High']}, Medium {counts['Medium']}, "
                 f"Low {counts['Low']}.")
        L.append(f"- Provisional estimates: {len(prov)} "
                 f"({fmt_num(sum(e['total_md'] for e in prov))} MD).")
        t = state["estimation_summary"]["totals"]
        L.append(f"- Range: Low {fmt_num(t['low'])} / Likely {fmt_num(t['likely'])} / High "
                 f"{fmt_num(t['high'])} MD; contingency {fmt_num(t['contingency_md'])} MD "
                 f"({fmt_num(t['effective_contingency_pct'])}%).")
    else:
        L.append("_Estimates not yet computed._")
    return "\n".join(L) + "\n"


# --------------------------------------------------------------------------- 06
def scope_recommendations(state, config) -> str:
    ss = state.get("scope_strategy") or {}
    reqs = {r["id"]: r for r in state["requirements"]}
    est_sum = (state.get("estimation_summary") or {})
    L = _header(state, "Scope Recommendations & Delivery Strategy")

    def req_rows(ids):
        return [[i, reqs[i]["module"], reqs[i]["description"], reqs[i].get("classification"),
                 reqs[i].get("scope")] for i in ids if i in reqs]

    mandatory = [r for r in state["requirements"] if r.get("classification") == "Mandatory"
                 and r.get("status") != "Removed"]
    m_in = [r for r in mandatory if r.get("scope") == "In Scope"]
    deferral_ids = {i for d in ss.get("deferrals", []) or [] for i in d.get("requirements", [])}
    L += ["## RFP compliance position", "",
          f"- Mandatory requirements identified: **{len(mandatory)}**; in scope: **{len(m_in)}**.",
          f"- Mandatory requirements proposed for deferral or exclusion: "
          f"**{len([r for r in mandatory if r['id'] in deferral_ids or r.get('scope') != 'In Scope'])}** "
          "(each listed below with its compliance impact).",
          "- No mandatory requirement is removed silently: every change of scope for a mandatory "
          "item requires an approved decision (DEC) and is listed in the decision log.", ""]
    mvp = ss.get("mvp") or {}
    L += ["## 1. Proposed MVP", "", mvp.get("description") or "_Not defined._", ""]
    if mvp.get("requirements"):
        L += _table(["Requirement", "Module", "Description", "Classification", "Scope"],
                    req_rows(mvp["requirements"])) + [""]
    L += ["## 2. Mandatory scope", ""]
    by_mod = {}
    for r in m_in:
        by_mod.setdefault(r["module"], []).append(r["id"])
    L += _table(["Module", "Mandatory In-Scope Requirements"], [[m, ids] for m, ids in sorted(by_mod.items())]) \
        if by_mod else ["_None identified._"]
    L += ["", "## 3. Optional modules and proposed improvements", ""]
    opt = [r["id"] for r in state["requirements"] if r.get("classification") in ("Optional", "Proposed Improvement")
           and r.get("status") != "Removed"]
    L += (_table(["Requirement", "Module", "Description", "Classification", "Scope"], req_rows(opt))
          if opt else ["_None._"])
    L += ["", "## 4. Phasing", ""]
    if ss.get("phases"):
        for ph in ss["phases"]:
            md = (est_sum.get("by_phase") or {}).get(ph.get("name"), {}).get("total_md")
            L.append(f"### {ph.get('name')}" + (f" — {fmt_num(md)} MD (internal estimate)" if md else ""))
            L += ["", ph.get("description", ""), ""]
            if ph.get("requirements"):
                L.append(f"Requirements: {join_ids(ph['requirements'])}")
                L.append("")
    else:
        L += [f"- {p}" for p in phases(state)] or ["_Single phase._"]
    L += ["", "## 5. Proposed deferrals and RFP-compliance impact", ""]
    if ss.get("deferrals"):
        rows = []
        for d in ss["deferrals"]:
            for i in d.get("requirements", []):
                r = reqs.get(i, {})
                flag = "MANDATORY — " if r.get("classification") == "Mandatory" else ""
                rows.append([i, r.get("description", ""), d.get("proposal"), d.get("rationale"),
                             flag + (d.get("compliance_impact") or "NOT STATED — required"),
                             d.get("decision") or "Pending"])
        L += _table(["Requirement", "Description", "Proposal", "Rationale", "RFP Compliance Impact",
                     "Decision"], rows)
    else:
        L.append("_No deferrals proposed._")
    for key, title in (("functional_dependencies", "6. Functional dependencies"),
                       ("technical_dependencies", "7. Technical dependencies")):
        L += ["", f"## {title}", ""]
        L += [f"- {x}" for x in ss.get(key, [])] or ["_None recorded._"]
    L += ["", "## 8. Reusable functionality", ""]
    if ss.get("reuse"):
        L += _table(["Component", "Applies To", "Notes"],
                    [[x.get("component"), x.get("requirements", []), x.get("notes")] for x in ss["reuse"]])
    else:
        L.append("_None identified._")
    L += ["", "## 9. Possible simplifications", ""]
    if ss.get("simplifications"):
        L += _table(["Simplification", "Requirements", "Indicative Saving (MD)", "Compliance Impact"],
                    [[x.get("description"), x.get("requirements", []), x.get("effort_saving_md"),
                      x.get("compliance_impact") or "None"] for x in ss["simplifications"]])
    else:
        L.append("_None proposed._")
    L += ["", "## 10. Accelerating delivery with AI-first engineering and reuse (internal)", ""]
    L += [f"- {x}" for x in ss.get("ai_acceleration", [])] or ["_Not assessed._"]
    mix = est_sum.get("by_ai_suitability") or {}
    if mix:
        L += ["", "Effort by AI suitability (likely MD): " +
              ", ".join(f"{k}: {fmt_num(v['likely'])}" for k, v in mix.items()) + "."]
    L += ["", "## 11. Architecture considerations", ""]
    L += [f"- {x}" for x in ss.get("architecture_considerations", [])] or ["_None recorded._"]
    L += ["", "## 12. Key decisions before implementation", ""]
    pending = [d for d in state["decisions"] if d["status"] == "Proposed"]
    L += [f"- {x}" for x in ss.get("key_decisions", [])]
    L += [f"- {d['id']}: {d['description']} (owner: {d.get('owner') or 'TBD'})" for d in pending]
    if not ss.get("key_decisions") and not pending:
        L.append("_None recorded._")
    return "\n".join(L) + "\n"


# --------------------------------------------------------------------------- 08
def decision_log(state, config) -> str:
    L = _header(state, "Decision Log & Baseline History")
    L += ["## Lifecycle", "",
          "Draft → Reviewed → Approved Baseline. Approval is recorded only when a named person "
          "approves explicitly; an answered clarification never implies approval.", "",
          f"Current status: **{state['project']['status']}**", ""]
    if state["project"].get("notes"):
        L += [f"> {state['project']['notes']}", ""]
    L += ["## Decisions", ""]
    if state["decisions"]:
        L += _table(["Decision ID", "Description", "Related Requirements", "Status", "Owner", "Date",
                     "Scope Impact", "Estimate Impact", "Timeline Impact"],
                    [[d["id"], d["description"], d.get("requirements", []), d["status"], d.get("owner"),
                      d.get("date") or "not recorded", d.get("scope_impact"), d.get("estimate_impact"),
                      d.get("timeline_impact")] for d in state["decisions"]])
    else:
        L.append("_No decisions recorded._")
    L += ["", "## Baselines", ""]
    if state["baselines"]:
        L += _table(["Version", "Approved By", "Date", "Total MD", "Base MD", "Timeline (days)",
                     "Accepted Risks", "Snapshot"],
                    [[f"v{b['version']}", b["approved_by"], b["date"][:10], fmt_num(b["totals"]["total_md"]),
                      fmt_num(b["totals"]["likely"]), fmt_num(b.get("timeline_days")),
                      b.get("accepted_risks") or "None", b["file"]] for b in state["baselines"]])
        for b in state["baselines"]:
            d = b.get("diff_from_previous")
            if not d:
                continue
            L += ["", f"### Changes in v{b['version']} vs v{b['version'] - 1}", ""]
            for name, e in d["entities"].items():
                L.append(f"- **{name}**: added {join_ids(e['added']) or 'none'}; removed "
                         f"{join_ids(e['removed']) or 'none'}; changed {join_ids(list(e['changed'])) or 'none'}")
            tt = d["totals"].get("total_md")
            if tt:
                L.append(f"- Total effort: {fmt_num(tt['old'])} → {fmt_num(tt['new'])} MD "
                         f"({'+' if tt['delta'] >= 0 else ''}{fmt_num(tt['delta'])})")
    else:
        L.append("_No baseline approved yet._")
    L += ["", "## Changes", ""]
    if state["changes"]:
        L += _table(["Change", "Target", "Summary", "Status", "Decided By", "Decision"],
                    [[c["id"], c.get("created_requirement") or c["target"], c["summary"],
                      c["approval_status"], c.get("decided_by"), c.get("decision")] for c in state["changes"]])
    else:
        L.append("_No change requests._")
    L += ["", "## SOW versions", ""]
    vers = state.get("sow", {}).get("versions", [])
    if vers:
        L += _table(["SOW Version", "Status", "Baseline", "Date", "Total MD", "File"],
                    [[v["version"], v["status"], f"v{v.get('baseline_version')}" if v.get("baseline_version") else "—",
                      v["date"][:10], fmt_num(v.get("total_md")), v.get("file")] for v in vers])
    else:
        L.append("_No SOW generated yet._")
    L += ["", "## Status history", ""]
    L += [f"- {a['ts']}: {a['action']} — {a['detail']} ({a.get('actor', '')})"
          for a in state.get("audit_log", []) if a["action"] in
          ("status", "baseline-approved", "change-approved", "change-rejected", "sow-final", "answer")] \
        or ["_No status events._"]
    return "\n".join(L) + "\n"


# --------------------------------------------------------------------------- 11
MAPPING_CHECKS = {"req-without-wbs", "req-without-estimate", "wbs-without-estimate",
                  "req-without-deliverable", "orphan-wbs", "orphan-deliverable", "module-missing",
                  "assumption-unlinked", "undocumented-exclusion"}
CONFLICT_CHECKS = {"decision-not-applied", "estimate-out-of-scope", "component-mismatch",
                   "rollup-mismatch", "contingency-arithmetic", "double-contingency", "range-order",
                   "hours-arithmetic", "summary-mismatch", "integrity", "mandatory-descoped",
                   "invalid-assumption", "sow-out-of-sync", "stale-estimates", "change-not-applied"}


def coverage_report(state, config, analysis_dir) -> str:
    rep = validate(state, config, analysis_dir)
    F = rep["findings"]
    cov = rep["coverage"]
    L = _header(state, "Scope Coverage & Consistency Report")
    L += [f"## Readiness: **{rep['readiness']}**", "",
          f"Errors: {rep['counts']['ERROR']} · Warnings: {rep['counts']['WARNING']} · "
          f"Info: {rep['counts']['INFO']}", ""]
    if rep["readiness"] == "NOT READY":
        L += ["The baseline cannot be approved until the errors below are resolved, unless the Project "
              "Manager explicitly accepts and documents the associated risks "
              "(`rfp.py baseline approve --accept-risks`).", ""]
    L += ["## 1. Coverage summary", ""]
    L += _table(["Measure", "Value"], [
        ["Requirements (total)", cov["requirements_total"]], ["In scope (buildable)", cov["in_scope"]],
        ["Fully traced", cov["traced"]], ["With gaps", cov["gaps"]],
        ["Out of scope / deferred", cov["out_of_scope"]],
        ["WBS activities (active / estimated)", f"{cov['wbs_active']} / {cov['wbs_estimated']}"],
        ["Open critical questions", cov["open_critical_questions"]],
        ["Provisional estimates", cov["provisional_estimates"]],
        ["Pending change requests", cov["pending_changes"]]])

    def section(title, pred):
        nonlocal L
        rows = [f for f in F if pred(f)]
        L += ["", f"## {title}", ""]
        L += (_table(["Severity", "Check", "Finding"], [[f["severity"], f["check"], f["message"]] for f in rows])
              if rows else ["_None._"])

    section("2. Missing mappings", lambda f: f["check"] in MAPPING_CHECKS)
    section("3. Conflicts and inconsistencies", lambda f: f["check"] in CONFLICT_CHECKS)
    L += ["", "## 4. Open questions", ""]
    oq = sorted([q for q in state["clarifications"] if q["status"] in OPEN_Q],
                key=lambda q: ({"Critical": 0, "Important": 1, "Optional": 2}[q["priority"]], q["id"]))
    L += (_table(["Question", "Priority", "Audience", "Question Text"],
                 [[q["id"], q["priority"], q["audience"], q["question"]] for q in oq]) if oq else ["_None._"])
    L += ["", "## 5. Provisional estimates", ""]
    prov = [e for e in state.get("estimates", []) if e["provisional"]]
    L += (_table(["Estimate", "WBS", "Activity", "Total MD", "Reason"],
                 [[e["id"], e["wbs"], e["activity"], fmt_num(e["total_md"]), "; ".join(e["provisional_reasons"])]
                  for e in prov]) if prov else ["_None._"])
    L += ["", "## 6. Items requiring approval", ""]
    items = [f"- Change {c['id']}: {c['summary']}" for c in state["changes"] if c["approval_status"] == "Pending"]
    items += [f"- Assumption {a['id']} (Proposed): {a['description']}" for a in state["assumptions"]
              if a["status"] == "Proposed"]
    items += [f"- Decision {d['id']} (Proposed): {d['description']}" for d in state["decisions"]
              if d["status"] == "Proposed"]
    if state["project"]["status"] != "Approved Baseline":
        items.append(f"- Baseline: current status is {state['project']['status']}; approval required "
                     "before issuing a final SOW.")
    L += items or ["_None._"]
    section("7. Other findings", lambda f: f["check"] not in MAPPING_CHECKS | CONFLICT_CHECKS)
    L += ["", "## 8. Deliverable files", ""]
    L += [f"- [{'x' if ok else ' '}] {n}" for n, ok in outputs_present(analysis_dir).items()]
    return "\n".join(L) + "\n"
