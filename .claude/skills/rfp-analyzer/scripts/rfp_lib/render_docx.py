"""Client-facing Statement of Work (07-statement-of-work.docx).

Final SOWs are generated only from an Approved Baseline whose figures still match
the approved snapshot. Internal details (AI productivity assumptions, contingency,
prompt effort, confidence, provisional flags) never appear in the client document.
"""
from __future__ import annotations

import math
import re
import shutil
import subprocess
from pathlib import Path

from .state import active, audit, is_active, paths, phases
from .util import RfpError, apportion, fmt_num, now_iso, round_to, round_up_to, today

try:
    from docx import Document
    from docx.enum.table import WD_TABLE_ALIGNMENT
    from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_BREAK
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn
    from docx.shared import Cm, Pt, RGBColor
except ImportError:  # pragma: no cover - environment dependent
    Document = None

REQUIRED_CONTENT = ["introduction", "background", "objectives", "proposed_solution",
                    "client_responsibilities", "vendor_responsibilities", "acceptance_criteria",
                    "testing_uat", "deployment_handover"]
DEFAULT_CHANGE_MGMT = (
    "Any change to the scope, deliverables, assumptions or timeline described in this Statement "
    "of Work will be handled through a written change request. Each change request will describe "
    "the requested change and its assessed impact on effort, timeline, deliverables and "
    "assumptions. Changes will be implemented only after written approval by both parties, and "
    "approved changes will be reflected in a revised version of this document.")


# --------------------------------------------------------------------------- docx helpers
def _field(paragraph, instr, placeholder="1"):
    run = paragraph.add_run()
    for kind, text in (("begin", None), ("instr", instr), ("separate", None), ("text", placeholder),
                       ("end", None)):
        if kind == "instr":
            el = OxmlElement("w:instrText")
            el.set(qn("xml:space"), "preserve")
            el.text = text
        elif kind == "text":
            el = OxmlElement("w:t")
            el.text = text
        else:
            el = OxmlElement("w:fldChar")
            el.set(qn("w:fldCharType"), kind)
        run._r.append(el)
    return run


def _shade(cell, hex_color):
    tc_pr = cell._tc.get_or_add_tcPr()
    shd = OxmlElement("w:shd")
    shd.set(qn("w:val"), "clear")
    shd.set(qn("w:color"), "auto")
    shd.set(qn("w:fill"), hex_color)
    tc_pr.append(shd)


def _repeat_header(row):
    tr_pr = row._tr.get_or_add_trPr()
    el = OxmlElement("w:tblHeader")
    el.set(qn("w:val"), "true")
    tr_pr.append(el)


class SowWriter:
    def __init__(self, config, draft):
        if Document is None:
            raise RfpError("python-docx is required for the SOW: pip install python-docx. "
                           "Fallback: `rfp.py sow --markdown` writes 07-statement-of-work.md.")
        self.config = config
        self.draft = draft
        self.doc = Document()
        self.primary = (config.get("company") or {}).get("primary_color", "1F3864")
        self.font = (config.get("company") or {}).get("font", "Calibri")
        self.text_log = []
        self.placeholders = []
        self._setup()

    def _setup(self):
        d = self.doc
        sec = d.sections[0]
        sec.top_margin = sec.bottom_margin = Cm(2.2)
        sec.left_margin = sec.right_margin = Cm(2.3)
        normal = d.styles["Normal"]
        normal.font.name = self.font
        normal.font.size = Pt(10.5)
        normal.element.get_or_add_rPr().get_or_add_rFonts().set(qn("w:eastAsia"), self.font)
        normal.paragraph_format.space_after = Pt(6)
        normal.paragraph_format.line_spacing = 1.15
        for name, size in (("Heading 1", 15), ("Heading 2", 12.5), ("Heading 3", 11), ("Title", 26)):
            st = d.styles[name]
            st.font.name = self.font
            st.font.size = Pt(size)
            st.font.color.rgb = RGBColor.from_string(self.primary)
            st.font.bold = name != "Title"
            rpr = st.element.get_or_add_rPr()
            rpr.get_or_add_rFonts().set(qn("w:eastAsia"), self.font)
        settings = d.settings.element
        upd = OxmlElement("w:updateFields")
        upd.set(qn("w:val"), "true")
        settings.append(upd)

    # text --------------------------------------------------------------
    def _log(self, text):
        self.text_log.append(str(text))

    def para(self, text, bold=False, italic=False, size=None, align=None, color=None, style=None):
        p = self.doc.add_paragraph(style=style)
        run = p.add_run(str(text))
        run.bold, run.italic = bold, italic
        if size:
            run.font.size = Pt(size)
        if color:
            run.font.color.rgb = RGBColor.from_string(color)
        if align:
            p.alignment = align
        self._log(text)
        return p

    def heading(self, text, level=1):
        self._log(text)
        return self.doc.add_heading(text, level=level)

    def bullet(self, text):
        self._log(text)
        return self.doc.add_paragraph(str(text), style="List Bullet")

    def rich(self, value, missing_label=None):
        """Render a string (paragraphs, '- ' bullets) or a list of strings as bullets."""
        if value in (None, "", [], {}):
            if missing_label:
                self.placeholders.append(missing_label)
                self.para(f"[To be completed: {missing_label}]", italic=True, color="C00000")
            return
        if isinstance(value, (list, tuple)):
            for item in value:
                self.bullet(item if isinstance(item, str) else item.get("text", str(item)))
            return
        for block in re.split(r"\n\s*\n", str(value).strip()):
            lines = block.splitlines()
            if all(l.strip().startswith(("- ", "* ")) for l in lines if l.strip()):
                for l in lines:
                    if l.strip():
                        self.bullet(l.strip()[2:])
            else:
                self.para(" ".join(l.strip() for l in lines))

    def table(self, headers, rows, widths=None, bold_last=False, align_right=()):
        t = self.doc.add_table(rows=1, cols=len(headers))
        t.style = "Table Grid"
        t.alignment = WD_TABLE_ALIGNMENT.CENTER
        hdr = t.rows[0]
        _repeat_header(hdr)
        for i, h in enumerate(headers):
            c = hdr.cells[i]
            c.text = ""
            r = c.paragraphs[0].add_run(str(h))
            r.bold = True
            r.font.color.rgb = RGBColor(0xFF, 0xFF, 0xFF)
            r.font.size = Pt(9.5)
            _shade(c, self.primary)
            self._log(h)
        for n, row in enumerate(rows):
            cells = t.add_row().cells
            for i, v in enumerate(row):
                text = ", ".join(v) if isinstance(v, (list, tuple)) else ("" if v is None else str(v))
                cells[i].text = ""
                run = cells[i].paragraphs[0].add_run(text)
                run.font.size = Pt(9.5)
                if bold_last and n == len(rows) - 1:
                    run.bold = True
                if i in align_right:
                    cells[i].paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.RIGHT
                if n % 2 == 1:
                    _shade(cells[i], "F2F2F2")
                self._log(text)
        if widths:
            for row in t.rows:
                for i, w in enumerate(widths):
                    if w:
                        row.cells[i].width = Cm(w)
        self.doc.add_paragraph()
        return t

    def header_footer(self, title, company, footer_note):
        sec = self.doc.sections[0]
        sec.different_first_page_header_footer = True
        hp = sec.header.paragraphs[0]
        hp.text = f"{company}  |  {title}"
        hp.runs[0].font.size = Pt(8.5)
        hp.runs[0].font.color.rgb = RGBColor(0x59, 0x59, 0x59)
        if self.draft:
            r = hp.add_run("    DRAFT — NOT APPROVED FOR DISTRIBUTION")
            r.bold = True
            r.font.size = Pt(8.5)
            r.font.color.rgb = RGBColor(0xC0, 0x00, 0x00)
        fp = sec.footer.paragraphs[0]
        fp.alignment = WD_ALIGN_PARAGRAPH.CENTER
        lead = fp.add_run(f"{footer_note}  |  Page ")
        lead.font.size = Pt(8.5)
        _field(fp, "PAGE").font.size = Pt(8.5)
        mid = fp.add_run(" of ")
        mid.font.size = Pt(8.5)
        _field(fp, "NUMPAGES").font.size = Pt(8.5)
        self._log(f"{company} {title} {footer_note}")

    def toc(self):
        p = self.doc.add_paragraph()
        _field(p, 'TOC \\o "1-2" \\h \\z \\u',
               "Right-click and choose 'Update Field' to refresh the table of contents.")

    def page_break(self):
        self.doc.add_paragraph().add_run().add_break(WD_BREAK.PAGE)


# --------------------------------------------------------------------------- content
def _client_effort_table(state, config):
    s = state["estimation_summary"]
    sc = config["sow"]
    inc = config["estimation"].get("sow_rounding_increment") or 1
    field = "total_md" if sc.get("include_contingency_in_totals", True) else "likely"
    by_mod = {m: g[field] for m, g in s["by_module"].items()}
    raw_total = sum(by_mod.values())
    total = round_up_to(raw_total, inc)  # never under-state the approved effort through rounding
    parts = apportion(by_mod, total, inc)
    rows = [[m, fmt_num(v)] for m, v in parts.items()]
    if sc.get("show_contingency_line") and field == "likely":
        cont = round_to(s["totals"]["contingency_md"], inc)
        rows.append(["Contingency", fmt_num(cont)])
        total += cont
    return rows, total


def check_final_gate(state):
    """A client-ready SOW needs an Approved Baseline whose totals still match the current estimate."""
    if state["project"].get("status") != "Approved Baseline":
        raise RfpError("A final SOW requires an Approved Baseline. Run `rfp.py baseline approve "
                       "--by <PM>` after review, or generate a draft with --draft.")
    bl = state["baselines"][-1]
    cur = state["estimation_summary"]["totals"]
    if abs(bl["totals"]["total_md"] - cur["total_md"]) > 0.01:
        raise RfpError(f"Current estimates ({cur['total_md']} MD) differ from approved baseline "
                       f"v{bl['version']} ({bl['totals']['total_md']} MD). Re-approve the baseline "
                       "or regenerate as --draft.")


def _weeks(day, wdpw):
    return max(1, int(math.ceil(day / wdpw - 1e-9)))


def build_sow(state, config, analysis_dir, draft=False, force=False, pdf=False):
    p = paths(analysis_dir)
    proj = state["project"]
    sc = config["sow"]
    if not state.get("estimates"):
        raise RfpError("No estimates available. Run `rfp.py estimate` first.")
    if not draft:
        check_final_gate(state)
    out = p["root"] / "07-statement-of-work.docx"
    versions = state["sow"].setdefault("versions", [])
    last = versions[-1] if versions else None
    if out.exists() and last and last.get("status") == "Final" and not force:
        raise RfpError(f"{out.name} is a FINAL SOW (v{last['version']}). Re-run with --force after "
                       "confirming it may be superseded; the previous file will be archived.")

    content = state["sow"].get("content", {})
    company = (config.get("company") or {})
    cname = company.get("legal_name") or company.get("name") or "Vendor"
    vendor = config["terminology"].get("vendor", "Vendor")
    client_word = config["terminology"].get("client", "Client")
    mdays = config["terminology"].get("man_days", "man-days")
    title = sc.get("document_title", "Statement of Work")
    project_name = proj.get("name") or "(project name not set)"
    version_no = len(versions) + 1
    wdpw = int(config["team"].get("working_days_per_week", 5))
    w = SowWriter(config, draft)
    w.header_footer(f"{title} — {project_name}", company.get("name", ""),
                    sc.get("confidentiality_footer", "Confidential"))

    # Cover
    logo = company.get("logo_path")
    if logo and Path(logo).exists():
        w.doc.add_picture(str(logo), width=Cm(5))
    for _ in range(4):
        w.doc.add_paragraph()
    w.para(title, size=28, bold=True, color=w.primary)
    w.para(project_name, size=18, color="404040")
    if proj.get("client"):
        w.para(f"Prepared for: {proj['client']}", size=12)
    w.para(f"Prepared by: {cname}", size=12)
    w.para(f"Version {version_no}{' (DRAFT)' if draft else ''} — {today()}", size=11, color="595959")
    if proj.get("rfp_reference"):
        w.para(f"In response to: {proj['rfp_reference']}", size=11, color="595959")
    w.page_break()
    w.heading("Document Control", 1)
    w.table(["Version", "Date", "Status", "Description"],
            [[v["version"], v["date"][:10], v["status"], v.get("description", "")] for v in versions] +
            [[version_no, today(), "Draft" if draft else "Final",
              "Draft for internal review" if draft else f"Issued from approved baseline "
                                                        f"v{proj.get('baseline_version')}"]],
            widths=[2, 3, 2.5, 9])
    w.heading("Contents", 1)
    w.toc()
    w.page_break()

    sections = []

    def H(text):
        sections.append(text)
        w.heading(f"{len(sections)}. {text}", 1)

    in_scope = [r for r in state["requirements"] if is_active(r) and r.get("scope") == "In Scope"
                and r.get("classification") != "Assumption"]
    modules = []
    for r in in_scope:
        if r["module"] not in modules:
            modules.append(r["module"])

    H("Project Introduction")
    w.rich(content.get("introduction"), "project introduction")
    H("Project Background")
    w.rich(content.get("background"), "project background")
    H("Business Objectives")
    w.rich(content.get("objectives"), "business objectives")
    H("Proposed Solution")
    w.rich(content.get("proposed_solution"), "proposed solution")
    H("Scope of Work")
    w.rich(content.get("scope_overview") or
           f"This Statement of Work covers the {len(modules)} functional area(s) listed below and the "
           "associated technical, testing, deployment and handover activities. Only the items listed "
           "in this document are in scope; anything not listed is excluded (see Exclusions).")
    w.table(["Module / Area", f"In-Scope Requirements"],
            [[m, sum(1 for r in in_scope if r["module"] == m)] for m in modules], widths=[11, 5])
    H("Detailed Modules and Functionality")
    mod_desc = content.get("module_descriptions") or {}
    for m in modules:
        w.heading(m, 2)
        if mod_desc.get(m):
            w.rich(mod_desc[m])
        rows = [[r["id"], r.get("title") or r["description"]] if sc.get("show_requirement_ids", True)
                else [r.get("title") or r["description"]] for r in in_scope if r["module"] == m]
        hdr = ["Ref", "Functionality"] if sc.get("show_requirement_ids", True) else ["Functionality"]
        w.table(hdr, rows, widths=[2.2, 14] if len(hdr) == 2 else None)
    H("Technical Scope")
    w.rich(content.get("technical_scope"), "technical scope")
    H("Deliverables")
    ms_name = {m["id"]: m["name"] for m in state["milestones"]}
    dels = [d for d in active(state, "deliverables") if d.get("client_facing", True)]
    if dels:
        w.table(["ID", "Deliverable", "Description", "Acceptance Criteria", "Milestone"],
                [[d["id"], d["name"], d.get("description"), d.get("acceptance_criteria"),
                  ms_name.get(d.get("milestone"), "")] for d in dels], widths=[1.6, 3.5, 5.5, 4.5, 2.4])
    else:
        w.rich(None, "deliverables list")
    H("Implementation Approach")
    approach = content.get("implementation_approach") or sc.get("methodology_statement")
    w.rich(approach)
    tl = state.get("timeline") or {}
    phase_rows = {p_["phase"]: p_ for p_ in tl.get("phases", [])}
    H("Project Phases")
    ph_desc = content.get("phase_descriptions") or {}
    ph_rows = []
    for ph in phases(state):
        if ph not in phase_rows:
            continue
        mods = sorted({r["module"] for r in in_scope if r.get("phase") == ph})
        ph_rows.append([ph, ph_desc.get(ph, ""), mods])
    w.table(["Phase", "Description", "Modules"], ph_rows, widths=[2.5, 9, 5])
    H("Milestones")
    ms_rows = []
    for m in active(state, "milestones"):
        pr = phase_rows.get(m.get("phase"))
        when = f"Week {_weeks(pr['finish'], wdpw)}" if pr else "To be scheduled"
        ms_rows.append([m["name"], m.get("phase"), m.get("criteria") or m.get("description"), when])
    if ms_rows:
        w.table(["Milestone", "Phase", "Completion Criteria", "Indicative Timing"], ms_rows,
                widths=[4, 2.5, 7, 3])
        w.para("Indicative timing is measured in weeks from the project start date and depends on "
               f"the {client_word} responsibilities and dependencies described in this document.",
               italic=True, size=9)
    else:
        w.rich(None, "milestones")
    H(f"Estimated {mdays.title()}")
    rows, total = _client_effort_table(state, config)
    w.para(f"The estimated effort to deliver the scope described in this document is "
           f"{fmt_num(total)} {mdays}, distributed as follows:")
    w.table(["Module / Deliverable", f"Estimated {mdays.title()}"], rows + [["Total", fmt_num(total)]],
            widths=[11, 5], bold_last=True, align_right=(1,))
    hpd = config["estimation"]["hours_per_man_day"]
    w.para(f"One {config['terminology'].get('man_day', 'man-day')} equals {fmt_num(hpd)} working hours. "
           "Estimates are based on the scope, assumptions and dependencies stated in this document.",
           italic=True, size=9)
    H("Estimated Timeline")
    weeks = _weeks(tl.get("working_days", 0), wdpw) if tl.get("working_days") else None
    if weeks:
        w.para(f"The estimated duration is approximately {weeks} weeks from project start to go-live, "
               f"including {client_word} review periods at each milestone.")
        w.table(["Phase", "Indicative Start", "Indicative Completion (incl. review)"],
                [[p_["phase"], f"Week {_weeks(p_['start'] + 1, wdpw)}", f"Week {_weeks(p_['acceptance'], wdpw)}"]
                 for p_ in tl.get("phases", [])], widths=[5, 4, 6])
        if tl.get("start_date"):
            w.para(f"Based on a start date of {tl['start_date']}; public holidays are not reflected.",
                   italic=True, size=9)
    else:
        w.rich(None, "timeline")
    H(f"{client_word} Responsibilities")
    w.rich(content.get("client_responsibilities"), f"{client_word.lower()} responsibilities")
    H(f"{vendor} Responsibilities")
    w.rich(content.get("vendor_responsibilities"), f"{vendor.lower()} responsibilities")
    H("Dependencies")
    deps = [d for d in state["dependencies"] if d.get("client_facing", True)]
    if deps:
        w.table(["Dependency", "Owner", "Needed By"],
                [[d["description"], d.get("owner") or d["type"], d.get("needed_by") or "As scheduled"]
                 for d in deps], widths=[10, 3.5, 3])
    else:
        w.para("No external dependencies have been identified beyond the "
               f"{client_word} responsibilities listed above.")
    H("Assumptions")
    asm = [a for a in state["assumptions"] if a.get("client_facing", True)
           and a["status"] not in ("Invalidated", "Superseded")]
    if asm:
        for a in asm:
            w.bullet(a["description"])
    else:
        w.rich(None, "assumptions")
    H("Exclusions")
    excl = [x["description"] for x in active(state, "exclusions") if x.get("client_facing", True)]
    excl += [f"{r['id']}: {r.get('title') or r['description']} "
             f"({'planned for a later phase' if r['scope'] == 'Deferred' else 'out of scope'})"
             for r in state["requirements"] if is_active(r) and r.get("scope") in ("Out of Scope", "Deferred")]
    excl += list(content.get("out_of_scope_notes") or [])
    excl.append("Any functionality, integration, service or deliverable not explicitly listed in this "
                "Statement of Work.")
    for x in excl:
        w.bullet(x)
    H("Acceptance Criteria")
    w.rich(content.get("acceptance_criteria"), "acceptance criteria")
    H("Change Management")
    w.rich(content.get("change_management") or DEFAULT_CHANGE_MGMT)
    H("Testing and UAT Approach")
    w.rich(content.get("testing_uat"), "testing and UAT approach")
    H("Deployment and Handover")
    w.rich(content.get("deployment_handover"), "deployment and handover")
    if content.get("warranty_support"):
        H("Warranty and Support")
        w.rich(content["warranty_support"])

    # Quality gates on the rendered text.
    full = "\n".join(w.text_log)
    issues = []
    if not sc.get("disclose_ai_tooling"):
        for t in sc.get("forbidden_terms", []):
            if t.lower() == "contingency" and sc.get("show_contingency_line"):
                continue  # explicitly requested by configuration
            if re.search(re.escape(t), full, re.IGNORECASE):
                issues.append(f"client SOW contains internal term '{t}'")
    if w.placeholders:
        issues.append("missing SOW content: " + ", ".join(w.placeholders))
    if company.get("name") in ("", "Your Company"):
        issues.append("company.name is not configured")
    if issues and not draft:
        raise RfpError("Final SOW not generated:\n  - " + "\n  - ".join(issues) +
                       "\nFix the content (`upsert` the sow section / config) or generate with --draft.")

    if out.exists():
        arch = p["history"] / "sow"
        arch.mkdir(parents=True, exist_ok=True)
        prev_label = f"v{last['version']}-{last['status'].lower()}" if last else "untracked"
        shutil.copy2(out, arch / f"07-statement-of-work-{prev_label}.docx")
    w.doc.core_properties.title = f"{title} — {project_name}"
    w.doc.core_properties.author = company.get("name", "")
    w.doc.save(str(out))
    record = {"version": version_no, "status": "Draft" if draft else "Final", "date": now_iso(),
              "baseline_version": proj.get("baseline_version") if not draft else None,
              "total_md": total, "file": out.name, "sections": sections,
              "description": "Draft for internal review" if draft else
              f"Issued from approved baseline v{proj.get('baseline_version')}",
              "issues": issues}
    versions.append(record)
    audit(state, "sow-final" if not draft else "sow-draft", f"v{version_no} total {total} MD")
    result = {"path": str(out), "record": record, "warnings": issues, "pdf": None}
    if pdf:
        result["pdf"] = _to_pdf(out)
    return result


def _to_pdf(docx_path: Path):
    exe = shutil.which("soffice") or shutil.which("libreoffice")
    if exe:
        r = subprocess.run([exe, "--headless", "--convert-to", "pdf", "--outdir", str(docx_path.parent),
                            str(docx_path)], capture_output=True, timeout=300)
        pdf = docx_path.with_suffix(".pdf")
        if r.returncode == 0 and pdf.exists():
            return str(pdf)
    try:
        from docx2pdf import convert  # type: ignore  # uses MS Word on Windows/macOS
        convert(str(docx_path))
        pdf = docx_path.with_suffix(".pdf")
        if pdf.exists():
            return str(pdf)
    except Exception:  # noqa: BLE001 - optional converter
        pass
    return ("PDF not created: install LibreOffice (soffice) or `pip install docx2pdf` with MS Word, "
            "or export the DOCX to PDF from Word.")


def sow_markdown(state, config) -> str:
    """Plain-text fallback when python-docx is unavailable (same gating applies via caller)."""
    rows, total = _client_effort_table(state, config)
    c = state["sow"].get("content", {})
    out = [f"# {config['sow'].get('document_title', 'Statement of Work')} — "
           f"{state['project'].get('name', '')}", "", "> Fallback Markdown rendering. Generate the DOCX "
           "once python-docx is installed.", ""]
    for key in REQUIRED_CONTENT + ["technical_scope", "implementation_approach", "warranty_support"]:
        if c.get(key):
            out += [f"## {key.replace('_', ' ').title()}", ""]
            v = c[key]
            out += ([f"- {x}" for x in v] if isinstance(v, list) else [str(v)]) + [""]
    out += ["## Estimated Man-Days", "", "| Module / Deliverable | Estimated Man-Days |", "|---|---:|"]
    out += [f"| {m} | {v} |" for m, v in rows] + [f"| **Total** | **{fmt_num(total)}** |", ""]
    return "\n".join(out)
