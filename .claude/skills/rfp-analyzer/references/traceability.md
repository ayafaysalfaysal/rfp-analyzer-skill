# Traceability and validation

## Links (many-to-many)

```
DOC ──sources── REQ ──clarified by── Q
                 │
                 ├─implemented by── WBS ──estimated by── EST
                 │                   ├─assumes── ASM
                 │                   ├─exposed to── RSK
                 │                   └─produces── DEL ── MS
                 ├─assumes / exposed to (direct) ── ASM / RSK
                 ├─delivered in── DEL
                 ├─decided by── DEC
                 └─excluded by── EXC
CHG ── targets REQ, changes WBS/ASM/DEL, recorded as DEC
```

A requirement's trace includes everything linked directly **and** everything linked through its WBS
items. `$RFP trace [REQ-xxx]` prints it, and `09-requirements-traceability.xlsx` contains the matrix,
the reverse view (WBS → requirements), the deliverables, a flat link list and the gaps/findings.

## Trace status per requirement

Traced · Traced (provisional) · GAP: no WBS · GAP: no estimate · GAP: no deliverable · Out of Scope ·
Deferred · Removed · Assumption (no build)

## Validation (`$RFP validate`)

Runs these deterministic checks and writes `11-scope-coverage-report.md`:

| Check | Severity |
|---|---|
| Referential integrity (unknown IDs, duplicate IDs, unknown source docs) | ERROR |
| In-scope requirement without WBS / without estimate | ERROR |
| WBS item without estimate; estimates stale versus inputs | ERROR |
| Module with in-scope requirements but no WBS work | ERROR |
| Open Critical clarification | ERROR (blocks baseline unless risk accepted) |
| WBS relying on an invalidated assumption | ERROR |
| Estimated WBS whose requirements are all out of scope | ERROR |
| Rollup by module / role / phase ≠ total; base + contingency ≠ total; hours ≠ MD × hours/day; Low ≤ Likely ≤ High | ERROR |
| Contingency or buffer line inside the WBS (double counting) | ERROR |
| Approved decision `effect` not reflected in requirement fields | ERROR |
| Mandatory requirement descoped without compliance impact and an approved decision | ERROR |
| Approved change not applied; final SOW out of sync with the current baseline | ERROR |
| Orphan WBS (no requirement, not cross-cutting) / orphan deliverable | WARNING |
| In-scope requirement without deliverable; deliverable without acceptance criteria | WARNING |
| WBS relying on an unapproved assumption; assumption without "if wrong" consequence | WARNING |
| Estimate without justification (no drivers, components, notes or assumptions) | WARNING |
| Out-of-scope requirement not documented in exclusions or deferrals | WARNING |
| Requirement without source; client priority claimed without source | WARNING |
| PM/QA effort share outside the configured range; timeline/capacity warnings; unknown roles | WARNING |
| Unprocessed or partially processed documents; missing referenced documents | WARNING |
| Executive summary missing or lacking required sections | WARNING |
| Pending change requests; unlinked assumptions; sample company name | INFO |

Readiness: **NOT READY** if any ERROR exists, **READY WITH WARNINGS** if there are warnings only, otherwise **READY**.

## Fixing findings

Resolve findings through upserts (add WBS links, deliverables, sources, exclusions and so on). Do not suppress them.
When a finding needs human judgment, such as an open Critical question, a mandatory deferral or an
unapproved assumption, present it to the user as a decision. Do not resolve it yourself.
