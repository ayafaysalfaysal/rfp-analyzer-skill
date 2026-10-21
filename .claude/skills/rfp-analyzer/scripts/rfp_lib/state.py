"""Project state: the JSON source of truth behind every deliverable.

All client-facing and internal documents are *rendered* from this state. IDs are
allocated from monotonically increasing counters so an ID is never reused, even
after an item is removed (items are marked ``Removed``, never deleted).
"""
from __future__ import annotations

from pathlib import Path

from . import STATE_SCHEMA_VERSION
from .util import (RfpError, as_list, deepcopy, id_parts, is_id, make_id, now_iso,
                   read_json, write_json)

STATE_DIRNAME = ".rfp-state"

REQUIREMENT_TYPES = [
    "Functional", "Non-functional", "UI/UX", "Frontend", "Backend", "Mobile", "Database",
    "Integrations", "Infrastructure", "Security and compliance", "AI/ML", "Data migration",
    "Reporting and analytics", "Testing", "Deployment", "Training", "Documentation",
    "Maintenance and support",
]

# Effort components a work package may break its Likely estimate into (section 8.1).
EFFORT_COMPONENTS = [
    "requirements_refinement", "architecture_design", "ai_generation", "human_validation",
    "integration", "debugging_refactoring", "security_performance", "functional_testing",
    "regression_testing", "deployment", "documentation", "project_management",
]

LEVELS = ["High", "Medium", "Low"]

SPECS = {
    "documents": {
        "prefix": "DOC", "create_via_upsert": False, "lockable": False,
        "required": ["path"],
        "defaults": {"name": "", "title": "", "format": "", "size": 0, "sha256": "",
                     "status": "Processed", "role": "Other", "duplicate_of": None,
                     "version_group": "", "pages": None, "unreadable_pages": [],
                     "extracted_path": "", "notes": "", "reviewed_manually": False,
                     "chars": 0, "meta": {}, "children": []},
        "enums": {"status": ["Processed", "Partial", "Needs Vision/OCR", "Unreadable",
                             "Unsupported", "Duplicate", "Excluded"],
                  "role": ["Main RFP", "Annex", "Amendment", "Clarification",
                           "Technical Specification", "Commercial", "Template", "Other"]},
        "refs": {"duplicate_of": "documents"},
        "material": [],
    },
    "requirements": {
        "prefix": "REQ", "create_via_upsert": True, "lockable": True,
        "required": ["description", "module"],
        "defaults": {"title": "", "type": "Functional", "classification": "Mandatory",
                     "priority": "Should", "priority_source": "Proposed", "phase": "Phase 1",
                     "status": "Open", "scope": "In Scope", "clarification_required": False,
                     "sources": [], "interpretation": "", "acceptance_hint": "", "notes": ""},
        "enums": {"type": REQUIREMENT_TYPES,
                  "classification": ["Mandatory", "Optional", "Proposed Improvement",
                                     "Assumption", "Clarification Needed"],
                  "priority": ["Must", "Should", "Could", "Won't"],
                  "priority_source": ["Client", "Proposed"],
                  "status": ["Open", "Confirmed", "Changed", "Removed"],
                  "scope": ["In Scope", "Out of Scope", "Deferred"]},
        "refs": {},
        "material": ["description", "module", "type", "classification", "scope", "phase",
                     "status", "priority"],
    },
    "clarifications": {
        "prefix": "Q", "create_via_upsert": True, "lockable": False,
        "required": ["question"],
        "defaults": {"audience": "Client", "category": "Business & Functional", "topic": "",
                     "why": "", "impact": "", "priority": "Important", "requirements": [],
                     "assumptions": [], "status": "Open", "answer": "", "answer_source": "",
                     "answered_date": "", "needs_review": False},
        "enums": {"audience": ["Client", "Internal Technical", "Document Request",
                               "Management Decision"],
                  "category": ["Business & Functional", "Technical", "Project Delivery",
                               "Commercial & Contractual"],
                  "priority": ["Critical", "Important", "Optional"],
                  "status": ["Open", "Sent", "Answered", "Closed", "Withdrawn"]},
        "refs": {"requirements": "requirements", "assumptions": "assumptions"},
        "material": [],
    },
    "wbs": {
        "prefix": "WBS", "create_via_upsert": True, "lockable": True,
        "required": ["module", "activity", "role"],
        "defaults": {"workstream": "", "description": "", "phase": "Phase 1",
                     "requirements": [], "depends_on": [], "complexity": "Medium",
                     "ai_suitability": "Medium", "confidence": "Medium", "assumptions": [],
                     "risks": [], "deliverables": [], "components": {}, "low_md": None,
                     "likely_md": None, "high_md": None, "effort_drivers": "",
                     "estimation_notes": "", "scheduling": "task", "elapsed_days": None,
                     "max_people": None, "cross_cutting": False, "provisional": False,
                     "needs_review": False, "status": "Active", "estimate_id": None},
        "enums": {"complexity": ["Low", "Medium", "High", "Very High"],
                  "ai_suitability": LEVELS, "confidence": LEVELS,
                  "scheduling": ["task", "level_of_effort"],
                  "status": ["Active", "Removed"]},
        "refs": {"requirements": "requirements", "depends_on": "wbs",
                 "assumptions": "assumptions", "risks": "risks", "deliverables": "deliverables"},
        "material": ["module", "activity", "role", "requirements", "components", "low_md",
                     "likely_md", "high_md", "ai_suitability", "confidence", "status",
                     "phase", "depends_on"],
    },
    "assumptions": {
        "prefix": "ASM", "create_via_upsert": True, "lockable": True,
        "required": ["description"],
        "defaults": {"source": "Estimator", "rationale": "", "status": "Proposed",
                     "requirements": [], "wbs": [], "if_wrong": "", "client_facing": True},
        "enums": {"source": ["RFP", "Client", "PM", "Estimator", "Technical Team",
                             "Clarification"],
                  "status": ["Proposed", "Approved", "Confirmed", "Invalidated", "Superseded"]},
        "refs": {"requirements": "requirements", "wbs": "wbs"},
        "material": ["description", "status", "requirements", "wbs"],
    },
    "risks": {
        "prefix": "RSK", "create_via_upsert": True, "lockable": False,
        "required": ["description"],
        "defaults": {"probability": "Medium", "impact": "Medium", "mitigation": "",
                     "owner": "", "status": "Open", "requirements": [], "wbs": [],
                     "assumptions": [], "category": ""},
        "enums": {"probability": LEVELS, "impact": LEVELS,
                  "status": ["Open", "Mitigating", "Closed", "Occurred"]},
        "refs": {"requirements": "requirements", "wbs": "wbs", "assumptions": "assumptions"},
        "material": [],
    },
    "dependencies": {
        "prefix": "DEP", "create_via_upsert": True, "lockable": False,
        "required": ["description"],
        "defaults": {"type": "Client", "owner": "", "needed_by": "", "status": "Open",
                     "requirements": [], "wbs": [], "client_facing": True},
        "enums": {"type": ["Client", "Third Party", "Technical", "Internal"],
                  "status": ["Open", "Met", "At Risk"]},
        "refs": {"requirements": "requirements", "wbs": "wbs"},
        "material": [],
    },
    "deliverables": {
        "prefix": "DEL", "create_via_upsert": True, "lockable": True,
        "required": ["name"],
        "defaults": {"description": "", "type": "Software", "requirements": [], "wbs": [],
                     "acceptance_criteria": "", "milestone": None, "phase": "Phase 1",
                     "status": "Planned", "client_facing": True},
        "enums": {"type": ["Software", "Document", "Service", "Environment", "Training",
                           "Data"],
                  "status": ["Planned", "Removed"]},
        "refs": {"requirements": "requirements", "wbs": "wbs", "milestone": "milestones"},
        "material": ["name", "description", "requirements", "wbs", "acceptance_criteria",
                     "status"],
    },
    "milestones": {
        "prefix": "MS", "create_via_upsert": True, "lockable": True,
        "required": ["name"],
        "defaults": {"phase": "Phase 1", "description": "", "criteria": "",
                     "status": "Planned"},
        "enums": {"status": ["Planned", "Removed"]},
        "refs": {},
        "material": ["name", "phase", "status"],
    },
    "decisions": {
        "prefix": "DEC", "create_via_upsert": True, "lockable": False,
        "required": ["description"],
        "defaults": {"status": "Proposed", "owner": "", "date": "", "requirements": [],
                     "scope_impact": "", "estimate_impact": "", "timeline_impact": "",
                     "rationale": "", "effect": {}},
        "enums": {"status": ["Proposed", "Approved", "Rejected", "Superseded"]},
        "refs": {"requirements": "requirements"},
        "material": [],
    },
    "exclusions": {
        "prefix": "EXC", "create_via_upsert": True, "lockable": True,
        "required": ["description"],
        "defaults": {"requirements": [], "rationale": "", "client_facing": True,
                     "status": "Active"},
        "enums": {"status": ["Active", "Removed"]},
        "refs": {"requirements": "requirements"},
        "material": ["description", "requirements", "status"],
    },
    "changes": {
        "prefix": "CHG", "create_via_upsert": False, "lockable": False,
        "required": ["description"], "defaults": {}, "enums": {}, "refs": {}, "material": [],
    },
}

ENTITY_BY_PREFIX = {spec["prefix"]: name for name, spec in SPECS.items()}
ENTITY_BY_PREFIX["EST"] = "estimates"

DICT_SECTIONS = ("project", "sow", "scope_strategy", "pm_recommendations")
PROJECT_EDITABLE = ("name", "client", "rfp_reference", "solution_types", "deadline",
                    "submission_date", "phases", "summary_line", "notes")
REMOVED_STATUSES = {"Removed"}
SYSTEM_FIELDS = ("history", "created", "updated")


# --------------------------------------------------------------------------- paths
def paths(analysis_dir) -> dict:
    root = Path(analysis_dir)
    sdir = root / STATE_DIRNAME
    return {
        "root": root,
        "state_dir": sdir,
        "state": sdir / "state.json",
        "extracted": sdir / "extracted",
        "baselines": sdir / "baselines",
        "history": sdir / "history",
        "changes": sdir / "changes",
        "work": sdir / "work",
        "ingestion_json": sdir / "ingestion.json",
        "ingestion_report": sdir / "ingestion-report.md",
    }


# --------------------------------------------------------------------------- lifecycle
def new_state(rfp_folder: str) -> dict:
    state = {
        "schema_version": STATE_SCHEMA_VERSION,
        "project": {
            "name": "", "client": "", "rfp_reference": "", "rfp_folder": rfp_folder,
            "solution_types": [], "deadline": "", "submission_date": "", "phases": [],
            "status": "Draft", "baseline_version": None, "created": now_iso(),
            "updated": now_iso(), "summary_line": "", "notes": "",
        },
        "counters": {},
        "keys": {},
        "missing_documents": [],
        "estimates": [],
        "estimation_summary": {},
        "timeline": {},
        "estimate_inputs_hash": "",
        "scope_strategy": {},
        "pm_recommendations": {},
        "sow": {"content": {}, "versions": []},
        "baselines": [],
        "calibration": {},
        "audit_log": [],
    }
    for name in SPECS:
        state[name] = []
    return state


def load_state(analysis_dir) -> dict:
    p = paths(analysis_dir)["state"]
    if not p.exists():
        raise RfpError(
            f"No analysis state found at {p}. Run `rfp.py ingest <rfp-folder>` first, "
            "or pass --dir to point at an existing analysis directory."
        )
    state = read_json(p)
    if state.get("schema_version") != STATE_SCHEMA_VERSION:
        raise RfpError(f"Unsupported state schema version {state.get('schema_version')}.")
    for name in SPECS:
        state.setdefault(name, [])
    return state


def save_state(analysis_dir, state) -> None:
    state["project"]["updated"] = now_iso()
    write_json(paths(analysis_dir)["state"], state)


def audit(state, action: str, detail: str = "", actor: str = "rfp.py") -> None:
    state.setdefault("audit_log", []).append(
        {"ts": now_iso(), "action": action, "detail": detail, "actor": actor})


# --------------------------------------------------------------------------- lookup
def next_id(state, entity: str) -> str:
    prefix = SPECS[entity]["prefix"] if entity in SPECS else "EST"
    counters = state.setdefault("counters", {})
    current = counters.get(prefix, 0)
    # Never collide with an ID already present (e.g. hand-edited state).
    existing = [id_parts(i.get("id", ""))[1] for i in state.get(entity, [])
                if id_parts(i.get("id", ""))]
    nxt = max([current] + existing) + 1
    counters[prefix] = nxt
    return make_id(prefix, nxt)


def index(state) -> dict:
    idx = {}
    for name in list(SPECS) + ["estimates"]:
        for item in state.get(name, []):
            if item.get("id"):
                idx[item["id"]] = (name, item)
    return idx


def get(state, ident: str):
    hit = index(state).get(ident)
    return hit[1] if hit else None


def entity_of(ident: str):
    parts = id_parts(ident)
    return ENTITY_BY_PREFIX.get(parts[0]) if parts else None


def is_active(item) -> bool:
    return item.get("status") not in REMOVED_STATUSES


def active(state, entity: str):
    return [i for i in state.get(entity, []) if is_active(i)]


def is_locked(state) -> bool:
    return state["project"].get("status") == "Approved Baseline"


# --------------------------------------------------------------------------- upsert
def _normalize_enum(value, allowed):
    if value is None:
        return None
    for a in allowed:
        if str(value).strip().lower() == a.lower():
            return a
    return value


def _known_fields(spec):
    return set(spec["defaults"]) | set(spec["required"]) | {"id", "key"} | set(SYSTEM_FIELDS)


def upsert(state: dict, batch: dict, reason: str = "", allow_locked: bool = False,
           actor: str = "claude") -> tuple:
    """Create or update entities from a batch. Atomic: returns (new_state, result) or raises.

    Batch format: {"requirements": [ {...}, ... ], "wbs": [...], "project": {...},
    "sow": {...}, "scope_strategy": {...}, "pm_recommendations": {...},
    "missing_documents": [...], "reason": "..."}.

    * Items with ``id`` update that item; items with a ``key`` previously used update
      the item the key maps to; otherwise a new ID is allocated.
    * Reference fields accept IDs or keys (resolved within the batch and from earlier
      batches), so a whole analysis can be loaded in one pass.
    * List fields are replaced, not appended.
    """
    if not isinstance(batch, dict):
        raise RfpError("Upsert batch must be a JSON object.")
    work = deepcopy(state)
    errors, warnings = [], []
    result = {"created": [], "updated": [], "unchanged": [], "warnings": warnings}
    reason = batch.get("reason", reason) or ""
    allowed_top = set(SPECS) | set(DICT_SECTIONS) | {"missing_documents", "reason"}
    for k in batch:
        if k not in allowed_top:
            errors.append(f"Unknown top-level key '{k}'. Allowed: {sorted(allowed_top)}")

    keys = work.setdefault("keys", {})
    existing_ids = {name: {i["id"] for i in work.get(name, [])} for name in SPECS}
    locked = is_locked(work) and not allow_locked

    # Pass 1: resolve target IDs (allocate for new items).
    plan = []  # (entity, item, target_id, is_new)
    for entity, spec in SPECS.items():
        items = batch.get(entity)
        if items is None:
            continue
        if not isinstance(items, list):
            errors.append(f"'{entity}' must be a list of objects.")
            continue
        for n, item in enumerate(items, 1):
            label = f"{entity}[{n}]"
            if not isinstance(item, dict):
                errors.append(f"{label}: must be an object.")
                continue
            target, is_new = None, False
            if item.get("id"):
                target = item["id"]
                if target not in existing_ids[entity]:
                    errors.append(f"{label}: id {target} does not exist. Omit 'id' to create "
                                  "a new item (IDs are allocated by the tool).")
                    continue
            elif item.get("key") and item["key"] in keys.get(entity, {}):
                target = keys[entity][item["key"]]
            else:
                if not spec["create_via_upsert"]:
                    errors.append(f"{label}: {entity} cannot be created via upsert.")
                    continue
                target, is_new = next_id(work, entity), True
                existing_ids[entity].add(target)
                if item.get("key"):
                    keys.setdefault(entity, {})[item["key"]] = target
            plan.append((entity, item, target, is_new))

    def resolve(ref_entity, value, label):
        if value is None or value == "":
            return None
        if is_id(value):
            if value not in existing_ids.get(ref_entity, set()):
                errors.append(f"{label}: unknown {ref_entity} reference {value}.")
            return value
        mapped = keys.get(ref_entity, {}).get(value)
        if not mapped:
            errors.append(f"{label}: '{value}' is neither a known {ref_entity} ID nor key.")
        return mapped

    by_id = {name: {i["id"]: i for i in work.get(name, [])} for name in SPECS}
    ts = now_iso()

    # Pass 2: validate, resolve references, apply.
    for entity, item, target, is_new in plan:
        spec = SPECS[entity]
        label = f"{entity} {target}"
        incoming = {k: v for k, v in item.items() if k not in ("id",) + SYSTEM_FIELDS}
        unknown = set(incoming) - _known_fields(spec)
        if unknown:
            warnings.append(f"{label}: unrecognised field(s) kept as-is: {sorted(unknown)}")
        for field, ref_entity in spec["refs"].items():
            if field not in incoming:
                continue
            if isinstance(spec["defaults"].get(field), list):
                incoming[field] = [r for r in (resolve(ref_entity, v, f"{label}.{field}")
                                               for v in as_list(incoming[field])) if r]
            else:
                incoming[field] = resolve(ref_entity, incoming[field], f"{label}.{field}")
        if entity == "requirements" and "sources" in incoming:
            fixed = []
            for s in as_list(incoming["sources"]):
                if isinstance(s, str):
                    s = {"doc": s}
                if not isinstance(s, dict) or not s.get("doc"):
                    errors.append(f"{label}.sources: each source needs a 'doc' (DOC-xxx).")
                    continue
                s = dict(s)
                s["doc"] = resolve("documents", s["doc"], f"{label}.sources")
                fixed.append(s)
            incoming["sources"] = fixed
        for field, allowed in spec["enums"].items():
            if field in incoming and incoming[field] is not None:
                incoming[field] = _normalize_enum(incoming[field], allowed)
                if incoming[field] not in allowed:
                    errors.append(f"{label}.{field}: '{incoming[field]}' not in {allowed}.")
        if entity == "wbs" and "components" in incoming:
            comps = incoming["components"] or {}
            if not isinstance(comps, dict):
                errors.append(f"{label}.components must be an object of component: man-days.")
            else:
                for c, v in comps.items():
                    if c not in EFFORT_COMPONENTS:
                        errors.append(f"{label}.components: unknown component '{c}'. "
                                      f"Allowed: {EFFORT_COMPONENTS}")
                    elif not isinstance(v, (int, float)) or v < 0:
                        errors.append(f"{label}.components.{c} must be a non-negative number.")
        if entity == "wbs":
            for f in ("low_md", "likely_md", "high_md", "elapsed_days"):
                v = incoming.get(f)
                if v is not None and (not isinstance(v, (int, float)) or v < 0):
                    errors.append(f"{label}.{f} must be a non-negative number or null.")

        if is_new:
            record = deepcopy(spec["defaults"])
            record.update(incoming)
            record["id"] = target
            missing = [f for f in spec["required"] if record.get(f) in (None, "", [])]
            if missing:
                errors.append(f"{label}: missing required field(s) {missing}.")
            if locked and spec["lockable"]:
                errors.append(f"{label}: approved baseline v{work['project']['baseline_version']}"
                              " is locked. Propose the addition with `rfp.py impact` instead.")
            record["created"] = ts
            record["updated"] = ts
            record["history"] = []
            work[entity].append(record)
            by_id[entity][target] = record
            result["created"].append(target)
        else:
            record = by_id[entity][target]
            changed = {f: v for f, v in incoming.items() if record.get(f) != v}
            changed.pop("key", None)
            if not changed:
                result["unchanged"].append(target)
                continue
            material = [f for f in changed if f in spec["material"]]
            if locked and spec["lockable"] and material:
                errors.append(f"{label}: fields {material} are part of approved baseline "
                              f"v{work['project']['baseline_version']}. Use `rfp.py impact` "
                              "to propose the change and get approval.")
            for f in material:
                record.setdefault("history", []).append(
                    {"ts": ts, "field": f, "old": record.get(f), "new": changed[f],
                     "reason": reason, "actor": actor})
            record.update(changed)
            record["updated"] = ts
            result["updated"].append(target)

    for section in DICT_SECTIONS:
        if section in batch:
            value = batch[section]
            if not isinstance(value, dict):
                errors.append(f"'{section}' must be an object.")
                continue
            if section == "project":
                bad = set(value) - set(PROJECT_EDITABLE)
                if bad:
                    errors.append(f"project: fields {sorted(bad)} are managed by the tool or "
                                  f"unknown. Editable: {list(PROJECT_EDITABLE)}")
                    continue
                work["project"].update(deepcopy(value))
            elif section == "sow":
                work["sow"].setdefault("content", {}).update(deepcopy(value.get("content", value)))
            else:
                work[section] = {**work.get(section, {}), **deepcopy(value)}
            result["updated"].append(section)
    if "missing_documents" in batch:
        if not isinstance(batch["missing_documents"], list):
            errors.append("'missing_documents' must be a list.")
        else:
            work["missing_documents"] = deepcopy(batch["missing_documents"])
            result["updated"].append("missing_documents")

    _check_scope_strategy_refs(work, errors)
    if errors:
        raise RfpError("Upsert rejected; nothing was saved:\n  - " + "\n  - ".join(errors))
    audit(work, "upsert", f"{reason} | created={len(result['created'])} "
                          f"updated={len(result['updated'])}", actor)
    return work, result


def _check_scope_strategy_refs(state, errors):
    """Scope strategy references requirements by ID or key; keys are replaced by IDs."""
    req_ids = {r["id"] for r in state["requirements"]}
    req_keys = state.get("keys", {}).get("requirements", {})
    dec_keys = state.get("keys", {}).get("decisions", {})
    ss = state.get("scope_strategy") or {}

    def fix(entry, where):
        if not isinstance(entry, dict):
            return
        out = []
        for i in as_list(entry.get("requirements")):
            rid = i if i in req_ids else req_keys.get(i)
            if not rid:
                errors.append(f"scope_strategy.{where}: unknown requirement {i}.")
            else:
                out.append(rid)
        if "requirements" in entry:
            entry["requirements"] = out
        if entry.get("decision") in dec_keys:
            entry["decision"] = dec_keys[entry["decision"]]

    fix(ss.get("mvp"), "mvp")
    for key in ("phases", "deferrals", "simplifications", "reuse"):
        for n, entry in enumerate(ss.get(key) or [], 1):
            fix(entry, f"{key}[{n}]")


# --------------------------------------------------------------------------- helpers
def requirement_ids_for_wbs(state, wbs_ids):
    reqs = set()
    for w in state["wbs"]:
        if w["id"] in wbs_ids:
            reqs.update(w.get("requirements", []))
    return reqs


def phases(state):
    """Ordered list of phase names: explicit project.phases first, then first appearance."""
    order = list(state["project"].get("phases") or [])
    for coll in ("requirements", "wbs", "deliverables", "milestones"):
        for item in active(state, coll):
            ph = item.get("phase")
            if ph and ph not in order:
                order.append(ph)
    return order
