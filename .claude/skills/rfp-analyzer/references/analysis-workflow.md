# Analysis workflow (stages 1–4)

Run the stages back-to-back for `analyze`. For single-stage commands, run only the named stage, but first
run `$RFP status` so you build on the existing state instead of starting over.

## §1 Analyze: ingest and executive summary

1. `$RFP ingest <folder> [--dir <analysis-dir>]`. This discovers files recursively, extracts text to
   `.rfp-state/extracted/DOC-xxx.txt` (with `[[page n]]`, `[[sheet x]]` and `[[slide n]]` markers),
   unpacks ZIP archives and e-mail attachments, and flags:
   duplicates, possible versions, scanned pages, unsupported formats, referenced documents that may be missing,
   amendment/clarification documents, and instruction-like text (possible prompt injection).
2. Read `.rfp-state/ingestion-report.md`, then read **every** extracted text file in full.
   For long files, read them in chunks. Do not stop at the first 2,000 lines.
3. For each document with status `Partial` or `Needs Vision/OCR`, open the original with the Read tool
   (it renders PDF pages and images) for the listed pages. Record what you found, then upsert the
   document with `reviewed_manually: true` and notes. For `Unsupported` or `Unreadable` files, report
   them to the user as unprocessed. Never pretend you read them.
4. Decide the role of each document (Main RFP / Annex / Amendment / Clarification / Technical
   Specification / Commercial / Template) and confirm or correct the guesses with an upsert.
   - **Amendments and clarifications override** the main RFP where they conflict. Record the governing
     source in requirement `sources` and note superseded text in `notes`.
   - **Conflicting versions**: if two versions disagree and no amendment settles it, raise a Critical
     client question and do not choose silently.
   - **Missing referenced documents**: review the candidates. Some are only section references. Update
     `missing_documents` (status `Missing` | `Not a document` | `Requested` | `Received`) and create a
     `Document Request` clarification for each real gap.
5. Classify the solution using [solution-types.md](solution-types.md) and set `project.solution_types`,
   `project.name`, `project.client` and `project.rfp_reference` **only from the documents**. If the client name
   is not stated, leave it empty.
6. Write `<analysis-dir>/01-executive-summary.md` from
   [../templates/01-executive-summary.md](../templates/01-executive-summary.md):
   - Answer every question in the template. If the RFP does not say, write "Not specified in the RFP".
     Do not guess.
   - Tag statements: **[RFP]** = documented (with DOC/section citation) and **[Interpretation]** = your reading.
   - "What the Client Actually Wants" is plain language for a business reader: no jargon, 5–10 sentences.
   - Keep the summary short. It should be readable in 5 minutes, with detail left to the matrix.

## §2 Clarify: requirements

Extract requirements from all processed documents, including tables, annexes, schedules, compliance
matrices and technical specifications. Rules:

- **One testable need per requirement.** Split compound sentences ("The system shall X and Y"). Merge
  exact duplicates that appear in several documents into one REQ with several `sources`.
- `module`: a client-recognisable functional area (e.g. "Case Management", "Reporting", "Integrations",
  "Platform & Security"). Keep the module list short (typically 5–15).
- `type`: choose the closest of the 18 types. `classification` follows the RFP wording:
  "shall/must/mandatory" → Mandatory; "should/may/desirable/optional" → Optional; your own suggestions
  → Proposed Improvement; unstated conditions you depend on → create an **assumption**, not a requirement.
  Use `Clarification Needed` when the scope cannot be sized without an answer.
- `priority`: if the RFP states priority or weighting, set `priority_source: "Client"` and cite it.
  Otherwise propose one and leave `priority_source: "Proposed"`.
- `phase`: as requested by the RFP. If phases are not stated, use "Phase 1" and propose phasing in stage 4.
- `sources`: DOC-ID plus the most precise location (section number, page marker, sheet/row) and a short quote.
- `interpretation`: anything you inferred. Keep it separate from the description.
- Non-functional requirements (performance, availability, security, accessibility, localisation,
  data residency, audit, backup/DR, browser/device support) are requirements too. Extract them.
- Delivery obligations (training, documentation, warranty, support, hosting, handover, UAT support)
  are requirements of type Training, Documentation or Maintenance and support.

Load them in batches of about 40 via upsert (with keys), then run `$RFP render requirements`.

## §2b Clarify: questions

Follow [clarification-methodology.md](clarification-methodology.md), then run `$RFP render clarifications`.

## §3 Estimate

Follow [estimation-methodology.md](estimation-methodology.md), then run `$RFP render estimation`.

## §4 Review: risks, assumptions, scope strategy

1. **Assumptions** (ASM): every material assumption behind an estimate, with `source`, `rationale`, `if_wrong`,
   and links to the requirements/WBS that depend on it. Status `Proposed` until the PM approves it or the client confirms it.
2. **Risks** (RSK): delivery, technical, commercial and dependency risks, with probability, impact,
   mitigation, owner (only if known) and linked requirements/WBS.
3. **Dependencies** (DEP): client inputs, third-party APIs, environments, data, licences.
4. **Deliverables** (DEL) and **milestones** (MS): map every in-scope requirement to at least one
   deliverable (via `requirements` or the WBS `deliverables` field). Give each deliverable acceptance criteria.
5. **Exclusions** (EXC): what is explicitly not included, to protect scope. Every Out-of-Scope or
   Deferred requirement must appear in an exclusion or a deferral.
6. **Scope strategy**: MVP, mandatory scope, optional modules, phasing, deferrals **with RFP compliance impact**,
   reuse, simplifications, AI-acceleration opportunities, architecture considerations, key decisions.
   Never descope a Mandatory requirement silently: a deferral needs a `compliance_impact` text and an Approved DEC.
7. `$RFP render all` and `$RFP validate`. Fix every ERROR you can resolve from the documents.
   Present the remaining errors and warnings to the user as decisions or open questions.
8. Present the **review summary**: total man-days (low/likely/high, contingency), timeline in weeks,
   effort by module, provisional estimates, open critical questions, top risks, and items needing approval.
   Then stop. Do not approve anything.

## Refreshing after new documents (amendments, Q&A responses)

Re-run `$RFP ingest <folder>`. Unchanged files keep their DOC IDs, changed files are re-extracted with history,
and new files get new IDs. Read only the new or changed documents. Update the affected requirements
through upserts that reuse their IDs/keys. Before baseline these are ordinary updates; after baseline,
material changes go through `impact --propose`.
