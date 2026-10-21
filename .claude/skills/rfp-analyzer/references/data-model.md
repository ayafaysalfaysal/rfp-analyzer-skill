# Data model and upsert format

The state file `<analysis-dir>/.rfp-state/state.json` is the source of truth. Excel, Word and Markdown
deliverables are rendered from it. Do not edit `state.json` by hand. Use `rfp.py upsert`, which
validates the input, allocates IDs and records history.

## ID scheme (stable, never reused)

| Prefix | Entity (`state` key) | Created by |
|---|---|---|
| DOC | documents | `ingest` (you may update `role`, `title`, `notes`, `status`, `reviewed_manually`) |
| REQ | requirements | you |
| Q | clarifications | you |
| WBS | wbs | you |
| EST | estimates (one per WBS item, stored as `wbs.estimate_id`) | `estimate` (computed) |
| ASM | assumptions | you |
| RSK | risks | you |
| DEP | dependencies | you |
| DEL | deliverables | you |
| MS | milestones | you |
| DEC | decisions | you, plus automatic records from approvals |
| EXC | exclusions | you |
| CHG | changes | `impact --propose` |

Items are never deleted. To remove one, set `"status": "Removed"` (requirements, wbs, deliverables,
milestones, exclusions). The ID remains reserved.

## Upsert batch

```json
{
  "reason": "Initial extraction from DOC-001..DOC-004",
  "project": {"name": "...", "client": "...", "rfp_reference": "RFP 2026/014", "solution_types": ["Web application", "Integrations"], "deadline": "", "submission_date": "", "phases": ["Phase 1", "Phase 2"]},
  "requirements": [ {...} ],
  "clarifications": [ {...} ],
  "wbs": [ {...} ],
  "assumptions": [], "risks": [], "dependencies": [], "deliverables": [], "milestones": [],
  "decisions": [], "exclusions": [],
  "missing_documents": [{"reference": "Annex C", "referenced_in": "DOC-001 (page 4)", "status": "Missing", "notes": "Data dictionary; requested via Q-012"}],
  "scope_strategy": {...},
  "pm_recommendations": {...},
  "sow": {"content": {...}}
}
```

Matching rules:
- `"id": "REQ-004"` updates REQ-004. An unknown ID is an error, so never invent IDs.
- With no `id`, an item creates a new record. Add a `"key"` (any unique slug, e.g. `"req-login"`) so that
  later batches and other items can refer to it. Re-sending the same `key` updates the same record.
  Use keys for everything you create; this is what keeps IDs stable when you refresh an analysis.
- Reference fields (`requirements`, `wbs`, `depends_on`, `assumptions`, `risks`, `deliverables`,
  `milestone`, `sources[].doc`, `duplicate_of`) accept IDs or keys.
- List fields are **replaced**, not appended. Send the full list.
- The batch is atomic: any error rejects the whole batch with a list of problems. Fix the problems and resend.
- `--dry-run` validates without saving. Once WBS items exist, an upsert recomputes estimates automatically.
- After a baseline is approved, material fields of requirements, wbs, assumptions, deliverables,
  milestones and exclusions are locked. Use `impact --propose` (see change-management.md).

## Entities: fields (defaults) and enums

**requirements**: `module`*, `description`*, `title`, `type`, `classification`, `priority`,
`priority_source`, `phase`, `status`, `scope`, `clarification_required` (bool), `sources`,
`interpretation`, `acceptance_hint`, `notes`
- `type`: Functional | Non-functional | UI/UX | Frontend | Backend | Mobile | Database | Integrations |
  Infrastructure | Security and compliance | AI/ML | Data migration | Reporting and analytics | Testing |
  Deployment | Training | Documentation | Maintenance and support
- `classification`: Mandatory | Optional | Proposed Improvement | Assumption | Clarification Needed
- `priority`: Must | Should | Could | Won't. `priority_source`: Client (cite it) | Proposed (default)
- `status`: Open | Confirmed | Changed | Removed. `scope`: In Scope | Out of Scope | Deferred
- `sources`: `[{"doc": "DOC-001", "location": "§4.2, p.12", "quote": "short verbatim excerpt"}]`

**clarifications**: `question`*, `audience`, `category`, `topic`, `why`, `impact`, `priority`,
`requirements`, `assumptions`, `status`, `answer`, `answer_source`, `answered_date`
- `audience`: Client | Internal Technical | Document Request | Management Decision
- `category`: Business & Functional | Technical | Project Delivery | Commercial & Contractual
- `priority`: Critical | Important | Optional. `status`: Open | Sent | Answered | Closed | Withdrawn

**wbs**: `module`*, `activity`*, `role`*, `workstream`, `description`, `phase`, `requirements`,
`depends_on`, `complexity` (Low|Medium|High|Very High), `ai_suitability` (High|Medium|Low),
`confidence` (High|Medium|Low), `assumptions`, `risks`, `deliverables`, `components`, `likely_md`,
`low_md`, `high_md`, `effort_drivers`, `estimation_notes`, `scheduling` (task|level_of_effort),
`elapsed_days`, `max_people`, `cross_cutting` (bool), `provisional` (bool), `needs_review` (bool), `status`
- `role` must match a key in config `team.roles` (e.g. "Backend Engineer", "QA", "PM").
- `components` (man-days; their sum becomes Likely): requirements_refinement, architecture_design,
  ai_generation, human_validation, integration, debugging_refactoring, security_performance,
  functional_testing, regression_testing, deployment, documentation, project_management
- Give either `components` or `likely_md`. `low_md`/`high_md` are optional; if omitted, the range
  comes from the confidence multipliers in the config.
- `cross_cutting: true` for PM, architecture, environment, QA-strategy and similar items not tied to one requirement.

**assumptions**: `description`*, `source` (RFP|Client|PM|Estimator|Technical Team|Clarification),
`rationale` (why it is needed), `status` (Proposed|Approved|Confirmed|Invalidated|Superseded),
`requirements`, `wbs`, `if_wrong` (consequence if incorrect), `client_facing` (bool: appears in SOW)

**risks**: `description`*, `probability`, `impact` (High|Medium|Low), `mitigation`, `owner`,
`status` (Open|Mitigating|Closed|Occurred), `requirements`, `wbs`, `assumptions`, `category`

**dependencies**: `description`*, `type` (Client|Third Party|Technical|Internal), `owner`, `needed_by`,
`status` (Open|Met|At Risk), `requirements`, `wbs`, `client_facing`

**deliverables**: `name`*, `description`, `type` (Software|Document|Service|Environment|Training|Data),
`requirements`, `wbs`, `acceptance_criteria`, `milestone`, `phase`, `status`, `client_facing`

**milestones**: `name`*, `phase`, `description`, `criteria`, `status`

**decisions**: `description`*, `status` (Proposed|Approved|Rejected|Superseded), `owner`, `date`,
`requirements`, `scope_impact`, `estimate_impact`, `timeline_impact`, `rationale`,
`effect` — optional machine-checkable expectation, e.g. `{"REQ-010": {"scope": "Deferred"}}`.
Only record `Approved` when the user has stated who approved it and when.

**exclusions**: `description`*, `requirements`, `rationale`, `client_facing`, `status`

## Free-form sections

`scope_strategy` (rendered in 06):
```json
{"mvp": {"description": "...", "requirements": ["REQ-001"]},
 "phases": [{"name": "Phase 1", "description": "...", "requirements": ["REQ-001"]}],
 "deferrals": [{"requirements": ["REQ-020"], "proposal": "Move to Phase 2", "rationale": "...", "compliance_impact": "RFP §5.3 lists it as mandatory for go-live; deferral requires client agreement", "decision": "DEC-002"}],
 "simplifications": [{"description": "...", "requirements": [], "effort_saving_md": 4, "compliance_impact": "None"}],
 "reuse": [{"component": "...", "requirements": [], "notes": "..."}],
 "functional_dependencies": ["..."], "technical_dependencies": ["..."],
 "ai_acceleration": ["..."], "architecture_considerations": ["..."], "key_decisions": ["..."]}
```

`pm_recommendations` (internal sheet of 03): lists of strings under `scope_reduction`, `reuse`,
`deferrable`, `mvp`, `architecture_discussions`, `risks`, `management_issues`, `discussion_strategy`.

`sow.content` (see sow-generation.md): `introduction`, `background`, `objectives`, `proposed_solution`,
`scope_overview`, `module_descriptions` {module: text}, `technical_scope`, `implementation_approach`,
`phase_descriptions` {phase: text}, `client_responsibilities`, `vendor_responsibilities`,
`acceptance_criteria`, `change_management`, `testing_uat`, `deployment_handover`, `warranty_support`,
`out_of_scope_notes`. Strings may contain blank-line paragraphs and `- ` bullets. Lists render as bullets.

A complete worked batch: [../templates/upsert-example.json](../templates/upsert-example.json).
