from __future__ import annotations

from pathlib import Path


def repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def data_dir() -> Path:
    return repo_root() / "data"


def artifacts_dir() -> Path:
    return data_dir() / "artifacts"


def charts_dir() -> Path:
    return artifacts_dir() / "charts"


def queue_dir() -> Path:
    return artifacts_dir() / "queue"


def reports_dir() -> Path:
    return artifacts_dir() / "reports"


def configs_dir() -> Path:
    return repo_root() / "configs"


def services_dir() -> Path:
    return repo_root() / "services"


def scripts_dir() -> Path:
    return repo_root() / "scripts"
