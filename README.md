# rfp-analyzer — Claude Code skill for RFP analysis, AI-first estimation and SOW generation

`/rfp-analyzer` turns a folder of client RFP documents into a traceable pre-sales package:
executive summary, requirements matrix, client clarification questions, WBS with AI-first man-day
estimates, risks and assumptions, scope strategy, change-impact register, decision log, coverage report
and a client-ready Statement of Work.

Claude does the interpretation and professional judgment. A bundled Python CLI is the single source of truth for
IDs, arithmetic, scheduling, traceability, validation, baselines and document generation. Requirements,
clarifications, estimates, decisions and SOW deliverables therefore stay synchronized throughout the assessment.

## Capabilities

- **Document intake**: recursive discovery of PDF, DOCX, XLSX, PPTX, CSV, TXT/MD, HTML, ODF, RTF and EML (with
  attachments) files and ZIP archives. It detects scanned pages (routed to Claude's vision), unsupported formats,
  exact duplicates, possible versions, amendments and clarifications, referenced annexes that are missing, and
  instruction-like text (prompt injection). Nothing is skipped silently.
- **Requirements**: REQ-IDs that stay stable across updates, 18 requirement types, Mandatory/Optional/Proposed/
  Assumption/Clarification classification, a separate client-stated vs proposed priority, and a source
  citation for every requirement.
- **Clarifications**: four registers (client, document requests, internal technical, management decisions),
  Critical/Important/Optional priorities, PM discussion strategy, and a separate **client copy** workbook.
- **AI-first estimation**: work packages sized as human effort for a Claude Code-enabled team (component breakdown,
  AI suitability, confidence). Configurable team-maturity profiles, calibration from your historical actuals,
  low/likely/high ranges, PERT, transparent contingency applied once, and rollups by module, role and phase.
- **Timeline**: a dependency- and capacity-aware schedule (headcount and allocation per role, client review windows,
  UAT windows, go-live buffer) with critical path and parallel workstreams. It never confuses person-days with calendar days.
- **Traceability**: REQ ↔ Q ↔ WBS ↔ EST ↔ ASM ↔ RSK ↔ DEL ↔ DEC (many-to-many), gap detection, and
  20+ deterministic coverage and consistency checks with a readiness verdict.
- **Change impact**: `/rfp-analyzer impact REQ-012` shows the full trace and evaluates proposed changes on a copy,
  reporting the effort, timeline, milestone and SOW-section impact. A change is applied only after named approval.
- **Baselines**: Draft → Reviewed → Approved Baseline, with snapshots, diffs, a decision log and locked material fields.
  Approval is refused while critical gaps remain unless the PM documents risk acceptance.
- **SOW**: a professional DOCX with cover, document control, table of contents, page X of Y, branded tables, 23
  sections and man-days that add up. It is generated only from an approved baseline, and internal terms such as
  "vibe coding" and contingency are kept out. Draft mode is watermarked; PDF is optional.

## Requirements

- Claude Code (CLI, desktop or IDE extension) with skills support
- Python **3.9+** on `PATH` (`python` on Windows, `python3` on macOS/Linux)
- Python packages: `openpyxl`, `python-docx`, `PyYAML`, `pypdf`:
  ```bash
  pip install -r .claude/skills/rfp-analyzer/requirements.txt
  ```
- Optional: LibreOffice (`soffice`) to convert legacy `.doc/.xls/.ppt` files and to export the SOW to PDF;
  `pdftotext` (poppler) is used if `pypdf` is missing.

## Installation

**Personal skill** (available in every project):
```bash
git clone https://github.com/ayafaysalfaysal/rfp-analyzer-skill.git
mkdir -p ~/.claude/skills
cp -r rfp-analyzer-skill/.claude/skills/rfp-analyzer ~/.claude/skills/
pip install -r ~/.claude/skills/rfp-analyzer/requirements.txt
```
On Windows PowerShell:
`Copy-Item -Recurse rfp-analyzer-skill\.claude\skills\rfp-analyzer $HOME\.claude\skills\`

**Project skill** (shared with everyone who works in one repository):
```bash
mkdir -p .claude/skills
cp -r /path/to/rfp-analyzer-skill/.claude/skills/rfp-analyzer .claude/skills/
```

Restart Claude Code, or start a new session. Then type `/rfp-analyzer` or ask Claude to "analyze the RFP in ./client-rfp".
Check that the skill is discovered by typing `/` in Claude Code and looking for `rfp-analyzer`.

## Usage

| Command | Purpose |
|---|---|
| `/rfp-analyzer analyze ./client-rfp` | Full analysis (stages 1–4), then a review summary |
| `/rfp-analyzer summary ./client-rfp` | Ingest documents and write the executive summary |
| `/rfp-analyzer requirements` | Extract or refresh the requirements matrix |
| `/rfp-analyzer clarifications` | Clarification registers and PM strategy |
| `/rfp-analyzer estimate` | WBS and AI-first man-day estimate |
| `/rfp-analyzer scope` | Risks, assumptions, scope recommendations, traceability and coverage |
| `/rfp-analyzer impact REQ-012` | Trace of a requirement; describe a change to assess it |
| `/rfp-analyzer answer Q-007 <answer>` | Record a client answer (never treated as approval) |
| `/rfp-analyzer approve` | Baseline approval gate |
| `/rfp-analyzer sow` | Client-ready SOW (`--draft` before approval, `--pdf` on request) |
| `/rfp-analyzer validate` | Coverage and consistency validation |
| `/rfp-analyzer resume` | Show progress and continue where you left off |

Natural language works too: "the client dropped SSO, what's the impact?" or "regenerate the
clarifications workbook".

The CLI can also be used directly, for example in scripts or CI:
```bash
RFP="python .claude/skills/rfp-analyzer/scripts/rfp.py"
$RFP ingest ./client-rfp          # creates ./rfp-analysis
$RFP upsert batch.json            # Claude writes JSON batches; see references/data-model.md
$RFP estimate && $RFP render all && $RFP validate
$RFP impact REQ-011 --propose change.json
$RFP change approve CHG-001 --by "Jane PM"
$RFP baseline approve --by "Jane PM"
$RFP sow
$RFP status                       # resume point
```

## Output

```
rfp-analysis/
├── 01-executive-summary.md            ├── 07-statement-of-work.docx
├── 02-requirements-matrix.xlsx        ├── 08-decision-log.md
├── 03-client-clarifications.xlsx      ├── 09-requirements-traceability.xlsx
├── 03-client-clarifications-CLIENT-COPY.xlsx
├── 04-wbs-estimation.xlsx             ├── 10-change-impact-register.xlsx
├── 05-risks-and-assumptions.md        ├── 11-scope-coverage-report.md
├── 06-scope-recommendations.md
└── .rfp-state/      # internal: state.json, extracted text, baselines, change specs, history
```

Format of the estimate summary printed by `rfp.py estimate`:
```
Team profile: experienced | calibration: none (factor 1.0, no historical data provided)
Base (likely) <B> MD + contingency <C> MD (<C/B>%) = TOTAL <B+C> MD
Range: low <L> / likely <B> / high <H> MD; PERT <P>; provisional <X> MD
By module / By role / By phase: likely and total per group
Timeline: <D> working days (~<W> weeks) incl. contingency; <D0> without.
Critical path: WBS-001 -> WBS-002 -> ...
```
Packages that depend on unanswered Critical clarification questions are marked provisional and carry
extra contingency until those questions are answered.

## Configuration

Copy `config.example.yaml` to `.claude/skills/rfp-analyzer/config.yaml` (team defaults, git-ignored),
to `<project>/.claude/rfp-analyzer.config.yaml`, or to `<analysis-dir>/rfp-config.yaml` (per RFP).
Settings you can change:
hours per man-day, rounding, team roles/headcount/allocation, working days per week, start date,
AI-first team profiles and calibration, contingency policy, client review and go-live buffers, preferred stack,
reusable components, company name, colors, font and logo, terminology, SOW options (contingency display,
AI-tooling disclosure, forbidden terms) and output options. Nothing company-specific is hard-coded.

## Workflow and safeguards

- Internal stages run without approval prompts. Baseline approval, change approval and the final SOW
  require explicit approval by a named person.
- RFP content is treated as untrusted data and never as instructions.
- Assumptions are kept separate from client-confirmed facts. Proposed priorities are labelled as proposed.
- Deliverables are archived before being overwritten. A final SOW is never replaced without `--force`.
- Client material stays in the analysis directory, which is excluded by `.gitignore`.

## Updating the skill

`git pull` in your clone, then copy `.claude/skills/rfp-analyzer` over the installed copy again (your
`config.yaml` is not part of the repo, so it is preserved if you copy files rather than replace the folder).
State files carry a `schema_version`, and the CLI refuses unknown versions rather than silently misreading them.

## Troubleshooting

| Symptom | Fix |
|---|---|
| `/rfp-analyzer` not listed | Check the folder is `~/.claude/skills/rfp-analyzer/SKILL.md` or `.claude/skills/rfp-analyzer/SKILL.md`; restart the session |
| `Python was not found` (Windows) | Install Python 3.9+ and disable the Microsoft Store "App execution alias" for python |
| `PyYAML is required` / `openpyxl is required` | `pip install -r .claude/skills/rfp-analyzer/requirements.txt` |
| PDF shows `Needs Vision/OCR` | Scanned PDF: Claude reads the pages with its vision-capable Read tool; or OCR it and re-run `ingest` |
| `.doc/.xls` shows `Unsupported` | Install LibreOffice, or save as DOCX/XLSX and re-run `ingest` |
| `Baseline NOT approved` | Resolve the listed errors, or approve with `--accept-risks "<statement>"` |
| `Upsert rejected` | The message lists every problem; nothing was saved. Fix and resend |
| Word asks to update fields | Choose **Yes** (table of contents and page numbers) |
| Excel shows formulas not values | Open in Excel/LibreOffice (values compute on open); the `Checks` sheet should show TRUE |

## Repository layout

```
.claude/skills/rfp-analyzer/
├── SKILL.md                  # concise dispatcher (progressive disclosure)
├── config.example.yaml       # all settings with defaults
├── requirements.txt          # Python dependencies
├── references/               # stage methodologies, loaded on demand
├── templates/                # executive summary, upsert batch, change spec, calibration CSV
└── scripts/rfp.py + rfp_lib/ # deterministic CLI
```

## License

Released under the [MIT License](LICENSE).
