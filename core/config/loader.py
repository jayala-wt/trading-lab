from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Tuple

import yaml

from core.common.paths import repo_root
from core.config.models import BotConfig, PatternConfig, RiskDefaults, StrategyConfig


def _load_yaml(path: Path) -> Dict[str, Any]:
    payload = yaml.safe_load(path.read_text())
    if not payload:
        return {}
    if not isinstance(payload, dict):
        raise ValueError(f"YAML root must be a mapping: {path}")
    return payload


def resolve_path(path_str: str) -> Path:
    path = Path(path_str)
    if path.is_absolute():
        return path
    return repo_root() / path


def load_bot_config(path_str: str) -> BotConfig:
    path = resolve_path(path_str)
    payload = _load_yaml(path)
    return BotConfig.parse_obj(payload)


def load_pattern_config(path_str: str) -> PatternConfig:
    path = resolve_path(path_str)
    payload = _load_yaml(path)
    return PatternConfig.parse_obj(payload)


def load_strategy_config(path_str: str) -> StrategyConfig:
    path = resolve_path(path_str)
    payload = _load_yaml(path)
    return StrategyConfig.parse_obj(payload)


def load_risk_defaults(path_str: str | None) -> RiskDefaults:
    if not path_str:
        return RiskDefaults()
    path = resolve_path(path_str)
    payload = _load_yaml(path)
    return RiskDefaults.parse_obj(payload)


def load_bot_with_risk(path_str: str) -> Tuple[BotConfig, RiskDefaults]:
    bot = load_bot_config(path_str)
    risk = load_risk_defaults(bot.execution.risk_defaults)
    overrides: Dict[str, Any] = {}
    if getattr(bot.execution, "__fields_set__", None):
        extra = getattr(bot.execution, "__dict__", {})
        overrides = extra.get("risk_overrides") or extra.get("risk") or {}
    if overrides:
        merged = risk.dict()
        merged.update(overrides)
        risk = RiskDefaults.parse_obj(merged)
    return bot, risk
