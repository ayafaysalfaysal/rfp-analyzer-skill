# AI-first ("vibe coding") estimation methodology

**This is the default and only estimation approach unless the user explicitly asks for another.** Do not
produce traditional-vs-AI comparisons. Do not derive estimates by dividing a traditional estimate by a
factor.

The estimate is the **human effort** for a team that uses Claude Code and AI coding tools throughout to
deliver **production-ready** software: reviewed, integrated, secured, tested, deployed and documented.
AI-generated code is not production-ready by default. Validation, integration, debugging and testing
are real effort, and they usually make up most of it.

## §1 Building the WBS

- Organise by **module** (functional area) and **workstream** (e.g. "Frontend", "Backend/API",
  "Integrations", "Data", "Platform/DevOps", "QA", "Management"). Use `workstream` for parallel tracks.
- One work package = a coherent piece of work that one role can own, typically **1–15 MD**. Combine
  micro-tasks. Split anything above about 20 MD unless it is level-of-effort.
- Include, as applicable: requirements refinement, solution architecture, UI/UX design, frontend, backend
  services, mobile, database design, integrations, data migration, infrastructure/DevOps/CI-CD, security
  implementation and testing, QA (functional plus regression automation), UAT support, deployment/cut-over,
  documentation, training, hypercare, and project management.
- Link each package to its `requirements`. Mark PM, architecture, environments, QA strategy and similar items as
  `cross_cutting: true`.
- `depends_on`: only real finish-to-start dependencies (e.g. "API for X" before "UI for X integration",
  "environments" before "deployment"). Do not chain everything. The scheduler uses this together with team capacity.
- `role` must be one of the config `team.roles`. PM effort should use `scheduling: "level_of_effort"`, or
  the PM role, which is level-of-effort by default.
- UAT support: set `elapsed_days` to the client UAT window, so its effort is spread over that window rather than compressed.
- Never add a "contingency", "buffer" or "reserve" line. Contingency is applied separately (validation flags it).

## §2 Sizing a work package

For each package, think through the effort components and record them in `components` (in MD). Their sum
becomes the Likely estimate:

| Component | What it covers |
|---|---|
| requirements_refinement | clarifying stories, acceptance criteria, edge cases |
| architecture_design | design decisions, data model, API contracts for this package |
| ai_generation | prompting, context preparation and iterative generation with AI tools |
| human_validation | reading, reviewing and correcting generated code; aligning it with standards |
| integration | wiring into the rest of the system and external services |
| debugging_refactoring | fixing defects, refactoring generated code for maintainability |
| security_performance | security review, authz checks, performance tuning |
| functional_testing | writing and executing tests for the package |
| regression_testing | regression automation and re-runs |
| deployment | pipeline, configuration and release work for the package |
| documentation | technical and user documentation for the package |
| project_management | only for PM packages |

Small packages can use `likely_md` alone, provided `effort_drivers` explains it. Add `low_md` and `high_md` when you have
specific reasons, such as an undocumented API or an unknown data quality. Otherwise the configured confidence
multipliers derive the range.

### AI suitability (classify every package)

- **High**: standard CRUD, forms, basic user management, conventional dashboards, standard reports,
  common UI components. Generation does most of the typing; validation and testing dominate.
- **Medium**: complex workflows, custom APIs, role-based business logic, multi-step processes,
  advanced reporting, complex front-end interactions. AI helps substantially, but design and
  correctness checking take real effort.
- **Low**: legacy or undocumented integrations, complex data migration, specialised algorithms,
  critical security components, complex infrastructure. Human analysis, experimentation and
  verification dominate; AI gives limited acceleration.

These are examples, not rules. Judge each package on its merits and record why in `effort_drivers`.

### Starting heuristics (not benchmarks)

These indicative ranges are for an experienced AI-first team. They are a sanity check, not data, so never cite them
to the client as benchmarks:
- Standard CRUD entity end-to-end (API + UI + validation + tests): ~1.5–3 MD
- Role/permission model with admin UI: ~3–6 MD
- Multi-step approval workflow with notifications: ~5–12 MD
- Standard report or dashboard page: ~1–3 MD; complex analytics dashboard: ~4–8 MD
- Well-documented REST integration: ~3–6 MD; legacy/undocumented integration: ~8–20+ MD
- Data migration per significant source: ~5–15+ MD, driven by data quality and reconciliation
- Environments and CI/CD per platform: ~4–10 MD
- QA: typically ≥15% of build effort; PM: typically 8–15% of total effort

If historical estimate/actual data is supplied, run `$RFP calibrate <csv>`
(columns `ai_suitability, estimated_md, actual_md`). Its factors replace the config calibration and are shown
in the workbook. If no data was provided, say so and do not claim benchmarks.

### Confidence

- **High**: requirement is clear and the solution well understood.
- **Medium**: some unknowns, with bounded impact.
- **Low**: significant unknowns, such as an undocumented external system, an undefined business rule or unknown data.

Any package linked to a requirement with an **open Critical clarification** is marked *provisional*
automatically and receives an extra contingency surcharge. You may also set `provisional: true` yourself.

## §3 What the CLI computes (do not compute by hand)

For each package:
`Likely = round(sum(components) or likely_md × team-profile multiplier[AI suitability] × calibration)`.
Low and High use the same multipliers (or confidence ranges). Then:
`PERT = (L + 4M + H) / 6`, `Contingency = Likely × pct(confidence, provisional)`,
`Total = Likely + Contingency`, and `Hours = Total × hours_per_man_day`.

It also produces rollups by module, role, phase and AI suitability, and the overall totals. It builds a schedule
that respects `depends_on`, the configured headcount and allocation per role, `max_people`, the client review days per
phase milestone, phase gating (if configured) and a go-live buffer. Person-days are never treated as calendar days.

After upserting WBS items, read the CLI output (or `$RFP estimate`) and sanity-check it:
- Does each module total look plausible against the heuristics?
- Are the PM and QA shares in range? The CLI warns if not.
- Is the critical path sensible? Are any roles overloaded (timeline warnings)?
- Are low-confidence packages driving most of the range?

## §4 Reporting

Report base, contingency and total man-days, the low/likely/high range, timeline in weeks, top effort
drivers, provisional man-days and what would firm them up. Internal details (profile multipliers,
component splits, contingency) stay in `04-wbs-estimation.xlsx` and never go into the SOW.
