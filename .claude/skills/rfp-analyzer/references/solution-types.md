# Adapting to the solution type

Classify the RFP into one or more types (`project.solution_types`). Many RFPs are hybrids. Use this
table to make sure the requirements, questions and WBS cover what each type actually needs.
Do not force a web/mobile template onto other kinds of project.

| Type | Typical modules / workstreams | Key questions | Estimation notes |
|---|---|---|---|
| Web application / portal | UX, frontend, backend/API, auth, CMS, search, notifications, admin | Roles, content ownership, accessibility (WCAG), browsers, SEO, languages | High AI suitability for CRUD/UI; budget for UX iterations |
| Mobile application | iOS/Android or cross-platform, offline sync, push, device features, store publishing | Native vs cross-platform, minimum OS, offline needs, MDM, store accounts | Device testing matrix, store review lead times |
| Enterprise platform | Workflow engine, RBAC, audit, reporting, integrations, multi-entity | Org structure, delegation, audit/retention, SSO, scale | Medium suitability for workflow/business rules |
| SaaS product | Multi-tenancy, billing/subscription, onboarding, admin console, telemetry | Tenancy model, billing provider, SLAs, data isolation | Security and tenancy isolation testing |
| AI / ML solution | Data pipeline, model selection/training/fine-tuning or LLM integration, evaluation, guardrails, MLOps, human review | Data availability and quality, accuracy targets and how they are measured, hosting and data residency, explainability | Low suitability for experimentation and evaluation; plan discovery and evaluation cycles; accuracy is not guaranteed |
| Workflow automation | Process mapping, RPA/BPM, connectors, exception handling, monitoring | Current process, volumes, exceptions, system access, licences | Integration access often drives the schedule |
| Data migration / DB modernization | Profiling, mapping, cleansing, ETL, reconciliation, cut-over, rollback | Sources, volumes, quality, ownership of cleansing, downtime window | Low suitability; repeated trial migrations; reconciliation effort |
| API / third-party integrations | API design, adapters, auth, error handling, monitoring, sandbox testing | Docs, sandbox, rate limits, who builds which side, SLAs | Undocumented or legacy APIs → Low suitability and Low confidence |
| Infrastructure / DevOps | Landing zone, IaC, CI/CD, observability, backup/DR, security hardening | Cloud provider, existing accounts, compliance, on-call model | IaC is partly AI-suitable; validation and access lead times dominate |
| Legacy modernization | Assessment, reverse engineering, strangler pattern, parity testing, data migration | Source availability, documentation, freeze periods, parity definition | Discovery-heavy; parity testing is significant |
| Hybrid software + infrastructure | Combination of the above | Responsibility split (RACI), environments | Watch cross-team dependencies in the schedule |

Always consider these cross-cutting non-functional areas: security and compliance (e.g. data protection
regulation, ISO 27001, SOC 2, sector rules stated in the RFP), performance and scalability, availability and DR,
observability, accessibility, localisation, data retention, and audit.
