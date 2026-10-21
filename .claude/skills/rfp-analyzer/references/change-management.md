# Change impact, decisions and baselines

## §1 Showing impact: `/rfp-analyzer impact REQ-012`

Run `$RFP impact REQ-012`. It prints: (1) the original requirement, (2) related clarifications,
(3) WBS activities, (4) current effort, (5) assumptions, (6) risks, (7) SOW deliverables and affected
SOW sections. Present this to the user in the same order. If the user described a change, continue to §2.
Otherwise ask what change they want to assess.

## §2 Assessing a proposed change (items 8–12)

1. Translate the request into a change spec, `.rfp-state/work/chg-<slug>.json`. See
   [../templates/change-spec.example.json](../templates/change-spec.example.json).
   ```json
   {"target": "REQ-012", "description": "Add Azure AD SSO alongside local login",
    "requested_by": "Client (meeting 2026-10-20)", "source": "Minutes §3",
    "requirement": {"description": "Users authenticate via Azure AD SSO or local accounts", "status": "Changed"},
    "wbs": [{"id": "WBS-007", "components": {"architecture_design": 1, "ai_generation": 1, "human_validation": 1.5, "integration": 2, "security_performance": 1, "functional_testing": 1}, "confidence": "Medium", "effort_drivers": "OIDC with tenant config; role mapping"},
            {"key": "wbs-sso-test", "module": "Platform & Security", "activity": "SSO end-to-end tests with client tenant", "role": "QA", "requirements": ["REQ-012"], "likely_md": 1.5, "ai_suitability": "Medium", "confidence": "Medium", "depends_on": ["WBS-007"]}],
    "remove_wbs": [],
    "invalidates_assumptions": ["ASM-004"],
    "assumptions": [{"key": "asm-sso-tenant", "description": "Client provides an Azure AD test tenant and app registration", "source": "Estimator", "rationale": "Needed to build and test SSO", "if_wrong": "+2 MD and a delay to integration testing", "requirements": ["REQ-012"]}],
    "deliverables": [], "exclusions": [], "risks": [], "milestones": []}
   ```
   - `target: "NEW"` with a full `requirement` object adds a new requirement. Use `"NEW"` inside
     `requirements` lists to refer to it.
   - Re-size the affected WBS packages with the same methodology as the original estimate.
2. `$RFP impact REQ-012 --propose .rfp-state/work/chg-<slug>.json`. The CLI evaluates the change on a
   copy of the state, so **the working scope is not modified**. It reports:
   (8) the proposed change, (9) new effort, (10) effort difference overall and by module and WBS item, (11) timeline
   impact and milestone shifts, and (12) whether approval is required (always recorded; *material* when the change crosses the
   `material_change_md` threshold, alters scope or shifts milestones). It also lists the invalidated assumptions,
   the assumptions to re-check and the affected SOW sections. It records `CHG-xxx` as **Pending** and
   updates `10-change-impact-register.xlsx`.
3. Present the concise change summary. Ask the user, via AskUserQuestion, whether to approve, reject or leave the
   change pending, and **who** is approving.
4. Only after an explicit answer, run `$RFP change approve CHG-xxx --by "<name>" [--note "..."]` or
   `$RFP change reject CHG-xxx --by "<name>"`. Approval applies the change with field history,
   recomputes everything, creates a DEC record and, if a baseline existed, sets the status to
   *Reviewed* (re-baseline required). If the state changed after the assessment, the CLI refuses and you
   must re-assess. Use `--force` only if the user explicitly accepts applying it to the changed state.

## §3 Baselines: Draft → Reviewed → Approved Baseline

- **Draft**: the initial analysis. **Reviewed**: internally reviewed
  (`$RFP set-status Reviewed --reason "..." --by "<name>"`). **Approved Baseline**: approved explicitly.
- `/rfp-analyzer approve`:
  1. Run `$RFP validate` and summarise readiness, totals, open Critical questions, provisional MD and
     unapproved assumptions.
  2. Ask the user to approve, naming the approver. If ERRORs remain, explain that approval requires a
     written risk acceptance, and ask for the statement.
  3. `$RFP baseline approve --by "<name>" [--accept-risks "<statement>"] [--notes "..."]`.
     The CLI refuses when errors remain and no risk acceptance is given.
- Approval writes a snapshot (`.rfp-state/baselines/baseline-vN.json`), records the diff against the previous
  baseline, adds a DEC record and locks the material fields. `$RFP baseline list` and
  `$RFP baseline diff [--from N] [--to M]` show history.
- After approval, every material change goes through §2. Previous baselines, estimate history (item
  `history` fields and baseline snapshots) and SOW versions are preserved.

## §4 Decision log

Record decisions (DEC) for scope choices, deferrals, technology choices and accepted risks. Use `Proposed`
until a named owner approves. Record `date` only when it was given or when the approval happened. For
decisions that change requirement fields, add `effect` (e.g. `{"REQ-020": {"scope": "Deferred"}}`) so
validation can verify that the decision was applied. `08-decision-log.md` is rendered from the state.
