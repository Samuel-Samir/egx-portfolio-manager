"""Loads config.yaml and builds a ConfigurationSnapshot for Engines to consume.

This is the one place in the codebase that reads config.yaml directly.
Engines never touch config files (or any I/O) themselves — Orchestration
loads config once per Job run and passes a ConfigurationSnapshot into the
pure functions that need it.
"""

from __future__ import annotations

from pathlib import Path

import yaml

from egxpm.persistence.models import ConfigurationSnapshot

DEFAULT_CONFIG_PATH = "config.yaml"

_RISK_SETTINGS_KEYS = [
    "max_per_stock_pct", "max_per_sector_pct", "risk_per_trade_pct",
    "max_position_pct", "max_portfolio_heat_pct", "atr_multiplier",
    "risk_reward_ratio", "unusual_volume_threshold",
]


def load_raw_config(path: str | Path = DEFAULT_CONFIG_PATH) -> dict:
    with open(path) as f:
        return yaml.safe_load(f)


def build_configuration_snapshot(
    raw: dict, weight_profile: str = "longterm_weights", notes: str | None = None
) -> ConfigurationSnapshot:
    """Resolves config.yaml's flat structure into one ConfigurationSnapshot.

    weight_profile selects which of config.yaml's weight sets
    ("longterm_weights" or "swing_weights") becomes this snapshot's active
    scoring_weights — a ConfigurationSnapshot always represents one
    resolved policy for one Job run, not both profiles at once.
    """
    scoring_weights = dict(raw.get(weight_profile, {}))
    scoring_weights["null_handling_policy"] = raw.get(
        "null_handling_policy", "exclude_and_renormalize"
    )
    risk_settings = {key: raw[key] for key in _RISK_SETTINGS_KEYS if key in raw}
    allocation_targets = dict(raw.get("allocation_targets", {}))

    return ConfigurationSnapshot(
        scoring_weights=scoring_weights,
        risk_settings=risk_settings,
        allocation_targets=allocation_targets,
        notes=notes,
    )


def load_configuration_snapshot(
    path: str | Path = DEFAULT_CONFIG_PATH, weight_profile: str = "longterm_weights"
) -> ConfigurationSnapshot:
    return build_configuration_snapshot(load_raw_config(path), weight_profile=weight_profile)
