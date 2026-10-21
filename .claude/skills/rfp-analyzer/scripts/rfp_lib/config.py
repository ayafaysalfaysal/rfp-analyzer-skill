"""Configuration loading. Defaults live in config.example.yaml next to SKILL.md."""
from __future__ import annotations

from pathlib import Path

from .util import RfpError, deep_merge

SKILL_DIR = Path(__file__).resolve().parents[2]
EXAMPLE_CONFIG = SKILL_DIR / "config.example.yaml"


def _load_yaml(path: Path) -> dict:
    try:
        import yaml  # type: ignore
    except ImportError as exc:  # pragma: no cover - environment dependent
        raise RfpError(
            "PyYAML is required to read configuration. Install with: "
            "pip install -r requirements.txt  (or: pip install pyyaml)"
        ) from exc
    with open(path, encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    if not isinstance(data, dict):
        raise RfpError(f"Configuration file {path} must contain a YAML mapping.")
    return data


def candidate_paths(explicit=None, analysis_dir=None):
    paths = []
    if explicit:
        paths.append(Path(explicit))
    if analysis_dir:
        paths.append(Path(analysis_dir) / "rfp-config.yaml")
    paths.append(Path.cwd() / ".claude" / "rfp-analyzer.config.yaml")
    paths.append(SKILL_DIR / "config.yaml")
    return paths


def load_config(explicit=None, analysis_dir=None) -> dict:
    """Return defaults deep-merged with the first config file found."""
    if not EXAMPLE_CONFIG.exists():
        raise RfpError(f"Default configuration missing: {EXAMPLE_CONFIG}")
    config = _load_yaml(EXAMPLE_CONFIG)
    source = str(EXAMPLE_CONFIG)
    if explicit and not Path(explicit).exists():
        raise RfpError(f"Config file not found: {explicit}")
    for path in candidate_paths(explicit, analysis_dir):
        if path.exists():
            config = deep_merge(config, _load_yaml(path))
            source = str(path)
            break
    config["_source"] = source
    _check(config)
    return config


def _check(config: dict) -> None:
    est = config.get("estimation", {})
    if not est.get("hours_per_man_day") or est["hours_per_man_day"] <= 0:
        raise RfpError("estimation.hours_per_man_day must be a positive number.")
    profile = est.get("ai_first", {}).get("team_profile")
    if profile not in est.get("ai_first", {}).get("profiles", {}):
        raise RfpError(f"estimation.ai_first.team_profile '{profile}' is not defined under profiles.")
    method = est.get("contingency", {}).get("method")
    if method not in ("confidence_based", "flat", "none"):
        raise RfpError("estimation.contingency.method must be confidence_based, flat or none.")
    wdpw = config.get("team", {}).get("working_days_per_week", 5)
    if not 1 <= int(wdpw) <= 7:
        raise RfpError("team.working_days_per_week must be between 1 and 7.")


def role_names(config: dict):
    return list((config.get("team", {}).get("roles") or {}).keys())


def term(config: dict, key: str, default: str) -> str:
    return (config.get("terminology") or {}).get(key) or default
