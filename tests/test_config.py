"""Version reporting — WG_VERSION wins, pyproject.toml is the fallback."""

import tomllib
from pathlib import Path

from wiregui.config import Settings, _project_version

PYPROJECT = Path(__file__).resolve().parent.parent / "pyproject.toml"


def _pyproject_version() -> str:
    with PYPROJECT.open("rb") as f:
        return tomllib.load(f)["project"]["version"]


def test_project_version_matches_pyproject():
    assert _project_version() == _pyproject_version()


def test_version_defaults_to_pyproject():
    assert Settings(_env_file=None).version == _pyproject_version()


def test_wg_version_env_overrides(monkeypatch):
    """The container image bakes the released version in as WG_VERSION."""
    monkeypatch.setenv("WG_VERSION", "9.9.9-rc1")
    assert Settings(_env_file=None).version == "9.9.9-rc1"


def test_missing_pyproject_falls_back_to_unknown(monkeypatch, tmp_path):
    monkeypatch.setattr("wiregui.config.Path", lambda *_: tmp_path / "nope" / "config.py")
    assert _project_version() == "unknown"
