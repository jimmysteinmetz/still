"""The config file is the product's UI — these tests guard hand-edits."""

from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from still.config import DEFAULT_CONFIG_PATH, StillConfig, load_config

REPO_ROOT = Path(__file__).parent.parent


def load_raw() -> dict:
    with (REPO_ROOT / DEFAULT_CONFIG_PATH).open() as f:
        return yaml.safe_load(f)


def test_shipped_config_is_valid() -> None:
    cfg = load_config(REPO_ROOT / DEFAULT_CONFIG_PATH)
    assert cfg.edition.weekday.max_items == 24  # two-page edition
    assert cfg.edition.dedup_lookback_days == 7
    assert {s.id for s in cfg.sections} == {
        "ai",
        "eng",
        "cloud",
        "sports",
        "music",
        "nyc",
        "personal",
    }
    for sid in ("ai", "sports", "music", "nyc"):
        assert cfg.sources_for(sid), f"{sid} section should have enabled sources"


def test_unknown_section_reference_rejected() -> None:
    raw = load_raw()
    raw["sources"][0]["section"] = "nonexistent"
    with pytest.raises(ValidationError, match="unknown section"):
        StillConfig.model_validate(raw)


def test_missing_method_field_rejected() -> None:
    raw = load_raw()
    rss = next(s for s in raw["sources"] if s["method"] == "rss")
    del rss["url"]
    with pytest.raises(ValidationError):
        StillConfig.model_validate(raw)


def test_typo_key_rejected() -> None:
    raw = load_raw()
    raw["sources"][0]["max_itmes"] = 3
    with pytest.raises(ValidationError):
        StillConfig.model_validate(raw)


def test_duplicate_source_names_rejected() -> None:
    raw = load_raw()
    raw["sources"].append(dict(raw["sources"][0]))
    with pytest.raises(ValidationError, match="duplicate source names"):
        StillConfig.model_validate(raw)
