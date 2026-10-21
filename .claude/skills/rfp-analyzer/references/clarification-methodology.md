# Clarification methodology

Act as a senior PM preparing a technical and commercial clarification meeting. The goal is to remove
every uncertainty that could materially change scope, design, effort, timeline or commercial exposure
**before** committing to an estimate.

## §1 Where questions come from

Go through each requirement and each module and ask: *could two competent vendors read this differently
and quote materially different effort?* If so, that is a question. Then check the following lists.

**Business & Functional**: missing end-to-end workflows; undefined user roles and permissions; missing
business rules (validation, calculations, statuses, SLAs); unclear module boundaries; approval chains
(levels, delegation, escalation); reports and dashboards (lists, filters, export formats, scheduling);
notification channels and templates; missing acceptance criteria; languages/localisation; volumes
(users, transactions, records, documents).

**Technical**: existing systems, technology constraints and mandated stack; integration counterparts
(API availability, documentation, protocol, authentication, sandbox, rate limits, who builds which side);
hosting (cloud/on-prem, who provides it, environments); existing source code or system to modernise;
performance, availability, RPO/RTO; security standards, penetration testing, certifications; data
migration (sources, volumes, quality, cleansing ownership, cut-over); identity/SSO; mobile platforms and
store publishing; AI/ML data availability, accuracy targets, model hosting, human-in-the-loop.

**Project Delivery**: scope boundaries; fixed dates and their drivers; phase expectations; dependencies
on client or third parties; UAT ownership, duration and environment; client-provided resources (SMEs,
product owner, test data); deployment windows and freeze periods; training audience and format;
documentation set; hypercare and support expectations.

**Commercial & Contractual**: licences and third-party subscription costs (who pays); warranty period
and scope; IP and source-code ownership; scope-change procedure; pricing model assumptions (fixed vs
T&M); penalties or SLAs; payment milestones; data protection obligations; any obligation referenced
but not specified. **Ask; never assume commercial terms.**

## §2 Four registers (audience)

| Audience | Use for | Shared with client? |
|---|---|---|
| Client | Questions the client must answer | Yes, via the CLIENT COPY workbook |
| Document Request | Documents, specs, access or samples to request | Yes |
| Internal Technical | Questions for our architects/engineers (feasibility, reuse, approach) | No |
| Management Decision | Bid/no-bid, risk appetite, pricing strategy, partner choices | No |

## §3 Priority

- **Critical**: a reliable scope or estimate is impossible without it. Linked estimates become
  *provisional* automatically, and open Critical questions block baseline approval unless the PM
  accepts the risk.
- **Important**: could materially affect design or implementation.
- **Optional**: can be resolved during detailed discovery.

Be disciplined. Use Critical only when the answer could swing effort by roughly ±20% or more for a module, or
could change the architecture or the commercial exposure.

## §4 Writing client-ready questions

- One question per entry. Make it neutral, specific and answerable, offering options where helpful:
  "Should approval follow a single level, or multiple levels with delegation? If multiple, please list
  the levels and the roles involved."
- Reference the RFP location: "Section 4.3 states … Please confirm …".
- `why`: one client-safe sentence explaining why the answer matters (it appears in the client copy).
- `impact`: internal note on the effect on effort, design or price (internal sheet only).
- Do not reveal internal estimates, margins, weaknesses or competitive strategy in client questions.
- Set `topic` so related questions group together, and merge duplicates across documents.
  Link every question to its `requirements` (and `assumptions` if the answer would confirm one).

## §5 PM recommendations & discussion strategy (internal)

Fill `pm_recommendations`: ways to reduce complexity, reuse opportunities, deferrable features, an MVP
candidate, architecture topics to raise, top delivery/technical risks, and issues needing management
decisions. Add a short `discussion_strategy`: meeting order, what to confirm first, and what *not* to concede.

## §6 Recording answers

`$RFP answer Q-007 --answer "<client text>" --source "Client email 2026-10-20"`

This marks the question Answered and flags the linked WBS items `needs_review`. Then:
1. Update the affected requirements (description, classification, scope, `status: "Confirmed"` if the
   client confirmed them) and assumptions (`Confirmed` or `Invalidated`) via upsert.
2. Re-size the flagged WBS items and clear `needs_review`.
3. Before a baseline exists these are normal updates. After a baseline, material changes go through
   `impact --propose`.
An answer is **not** an approval of scope or estimates. Never change baseline status because of an answer.
