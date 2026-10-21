# Statement of Work generation

## §1 Gate

- A **final** SOW requires `project.status == "Approved Baseline"`, and the current estimates must equal the
  approved baseline totals. The CLI enforces this.
- If there is no approved baseline, offer `$RFP sow --draft`. It produces a watermarked "DRAFT — NOT APPROVED
  FOR DISTRIBUTION" document with red `[To be completed: …]` markers for missing content.
- Before generating a final SOW, confirm with the user that they want the client-ready version issued.
  If a final SOW already exists, the CLI refuses unless `--force` is given. Ask before using it; the
  previous file is archived in `.rfp-state/history/sow/`.
- PDF only on request: `--pdf` (needs LibreOffice, or Word with docx2pdf). If conversion is unavailable,
  report the limitation.

## §2 Writing `sow.content`

Upsert `{"sow": {"content": {...}}}`. The CLI fills everything that comes from the state: scope by
module (in-scope requirements), deliverables with acceptance criteria, phases, milestones with indicative
weeks, man-day table, timeline, dependencies, assumptions, exclusions. It also applies a neutral default
change-management clause. You write the narrative sections:

| Key | Content |
|---|---|
| introduction | Who the parties are and what the document defines (2–4 sentences) |
| background | The client's situation as stated in the RFP, without embellishment |
| objectives | List of business objectives drawn from the RFP |
| proposed_solution | The solution in business terms: components, users, key workflows |
| scope_overview | Optional override of the default scope paragraph |
| module_descriptions | `{module: short description}` shown above each module's functionality table |
| technical_scope | Platforms (web/mobile/desktop), backend services, integrations, hosting, security and compliance in scope |
| implementation_approach | Delivery method in professional terms (defaults to `sow.methodology_statement`) |
| phase_descriptions | `{phase: description}` |
| client_responsibilities | List: SMEs, timely reviews, environments, test data, third-party access, UAT execution |
| vendor_responsibilities | List: design, build, test, deploy, document, train, as scoped |
| acceptance_criteria | General acceptance process: deliverable review period, defect severity, sign-off |
| testing_uat | Testing levels we perform, the UAT approach and client role, entry and exit criteria |
| deployment_handover | Deployment, go-live, knowledge transfer, source code and documentation handover |
| warranty_support | **Only** if the RFP requires it or the user specifies terms. Otherwise omit (the section is skipped) |
| out_of_scope_notes | Extra exclusions not captured as EXC records |

## §3 Client-facing rules

- Use **only** the approved AI-first estimate, with module figures distributed so they add up to the total
  (contingency is included in the module figures and never shown separately unless configured).
- Never mention: vibe coding, prompt engineering, AI productivity factors, internal contingency, confidence
  levels, provisional flags or internal concerns. Describe the method professionally. Disclose AI tooling only
  when `sow.disclose_ai_tooling: true`, because the client asked or the contract requires it. The CLI blocks
  a final SOW that contains configured forbidden terms.
- Be precise: name deliverables and their acceptance criteria, state the assumptions and dependencies,
  and list explicit exclusions. Use no vague phrases like "and other features as needed".
- Make no unsupported guarantees ("will ensure 100% uptime"). Do not invent commercial terms, including
  prices, payment terms, penalties, warranty periods, liability or IP clauses. If the RFP requires
  them, mark them as "to be agreed in the commercial proposal/contract".
- The company name, colors, font and logo come from config `company`. A final SOW is blocked while the
  name is still the sample value.

## §4 After generation

Report the file path, version, total man-days and section list. Remind the user that Word may ask to update
fields (contents and page numbers) on first open. Answer "Yes".
