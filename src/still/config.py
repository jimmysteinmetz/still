"""Load and validate config/still.yaml — the product's user interface.

The config file is how sources, sections, interests, teams, and quotas are
managed (no admin UI). This module is the gatekeeper: a config edit either
validates cleanly or fails loudly with a pointed error before any pipeline run.
"""

from pathlib import Path
from typing import Annotated, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

DEFAULT_CONFIG_PATH = Path("config/still.yaml")

SourceClass = Literal["trusted", "firehose"]


class StrictModel(BaseModel):
    """Reject unknown keys so config typos fail instead of being ignored."""

    model_config = ConfigDict(extra="forbid")


class WeekdayEdition(StrictModel):
    max_items: int = Field(gt=0, le=30)


class WeekendEdition(StrictModel):
    max_items: int = Field(gt=0, le=30)
    long_read: bool = True
    day: Literal["saturday", "sunday"] = "saturday"


class EditionConfig(StrictModel):
    timezone: str
    weekday: WeekdayEdition
    weekend: WeekendEdition
    # LLM-facing "recently covered" window for cross-day topic dedup (TASK-3).
    dedup_lookback_days: int = Field(default=7, gt=0, le=30)


class Section(StrictModel):
    id: str = Field(pattern=r"^[a-z][a-z0-9-]*$")
    title: str
    max_items: int = Field(gt=0, le=20)  # headroom for a busy section to backfill two pages
    # Optional per-section writing guidance injected into the editorial prompt
    # (editorial.build_prompt) next to this section's quota — e.g. tone/register
    # instructions for a section that reads too close-to-the-metal (TASK-7). Freeform;
    # a section with no `style` gets no extra guidance line, so this is opt-in per
    # section rather than a behavior change for the whole prompt.
    style: str | None = None


class SourceBase(StrictModel):
    name: str
    section: str
    class_: SourceClass = Field(alias="class")
    max_items: int = Field(gt=0, le=10)
    enabled: bool = True
    # Optional per-source guidance injected into the editorial prompt
    # (editorial.build_prompt) next to this source's quota line — e.g. steering
    # a trusted source away from a narrow recurring subtopic without hard-filtering
    # its other content. Freeform; a source with no `note` gets no extra guidance
    # line, so this is opt-in per source rather than a blanket prompt change.
    # Mirrors Section.style.
    note: str | None = None


class RssSource(SourceBase):
    method: Literal["rss"]
    url: str = Field(pattern=r"^https?://")


class HnAlgoliaSource(SourceBase):
    method: Literal["hn_algolia"]
    min_points: int = Field(gt=0)


class RedditSource(SourceBase):
    method: Literal["reddit"]
    subreddit: str
    min_upvotes: int = Field(gt=0)


class EmailSource(SourceBase):
    """Newsletter ingest inbox — deferred to v1.1 (spec §5.5)."""

    method: Literal["email"]
    address: str


class ScrapeSource(SourceBase):
    """Last-resort scraping — deferred (spec §5.1)."""

    method: Literal["scrape"]
    url: str = Field(pattern=r"^https?://")


Source = Annotated[
    RssSource | HnAlgoliaSource | RedditSource | EmailSource | ScrapeSource,
    Field(discriminator="method"),
]


class YourDayModule(StrictModel):
    enabled: bool = True
    weekdays_only: bool = True
    calendar_id: str = "primary"  # a secondary/work calendar id (often an email) if not primary


class WeatherModule(StrictModel):
    enabled: bool = True
    label: str
    lat: float = Field(ge=-90, le=90)
    lng: float = Field(ge=-180, le=180)


class Team(StrictModel):
    name: str
    short: str | None = None  # crest alt / fallback label; defaults to name
    league: str | None = None  # human label for `config check`, e.g. "NFL"
    espn_path: str  # ESPN sport/league, e.g. "football/nfl", "soccer/eng.1"
    espn_id: int
    enabled: bool = True
    # Scoreboard render position, shared with `Series.order` — teams and series
    # are merged and sorted by this single field so a series can land between
    # two teams (TASK-8). Lower renders first.
    order: int = 0


class Series(StrictModel):
    """A motorsport series (next-race-only); fetched from an ESPN racing scoreboard."""

    name: str
    short: str | None = None
    espn_path: str  # e.g. "racing/irl"
    enabled: bool = True
    # See `Team.order` — teams and series share one ordered Scoreboard sequence.
    order: int = 0


class ToggleModule(StrictModel):
    enabled: bool = False


class LessonsModule(StrictModel):
    """Rotating "Margin" lessons. `deck` is a freeform topic list (edit at will);
    code rotates it deterministically by edition number and the editorial LLM
    writes `per_edition` short lessons. Count is clamped again in code."""

    enabled: bool = True
    per_edition: int = Field(default=2, gt=0, le=4)
    deck: list[str] = Field(default_factory=list)


class ShowsModule(StrictModel):
    """Upcoming NYC-metro shows for followed artists (SeatGeek). Needs a free
    `client_id` in the SEATGEEK_CLIENT_ID env var; without it the card hides."""

    enabled: bool = False
    artists: list[str] = Field(default_factory=list)
    lat: float = Field(default=40.7128, ge=-90, le=90)
    lng: float = Field(default=-74.0060, ge=-180, le=180)
    range_mi: int = Field(default=40, gt=0, le=200)
    max_rows: int = Field(default=6, gt=0, le=12)


class AlmanacConfig(StrictModel):
    your_day: YourDayModule
    weather: WeatherModule
    teams: list[Team] = []
    series: list[Series] = []
    french_holidays: ToggleModule = ToggleModule()
    sports_week: ToggleModule = ToggleModule()
    lessons: LessonsModule = LessonsModule()
    shows: ShowsModule = ShowsModule()


class DeliveryConfig(StrictModel):
    email: str = Field(pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    archive: Path


class StillConfig(StrictModel):
    edition: EditionConfig
    interests: list[str] = Field(min_length=1)
    sections: list[Section] = Field(min_length=1)
    sources: list[Source] = Field(min_length=1)
    almanac: AlmanacConfig
    delivery: DeliveryConfig

    @model_validator(mode="after")
    def check_cross_references(self) -> "StillConfig":
        section_ids = [s.id for s in self.sections]
        if len(section_ids) != len(set(section_ids)):
            raise ValueError("duplicate section ids")
        for source in self.sources:
            if source.section not in section_ids:
                raise ValueError(
                    f"source {source.name!r} references unknown section "
                    f"{source.section!r} (known: {', '.join(section_ids)})"
                )
        names = [s.name for s in self.sources]
        if len(names) != len(set(names)):
            raise ValueError("duplicate source names")
        return self

    def sources_for(self, section_id: str) -> list["Source"]:
        return [s for s in self.sources if s.section == section_id and s.enabled]


def load_config(path: Path = DEFAULT_CONFIG_PATH) -> StillConfig:
    """Parse and validate the config file, raising on any problem."""
    with path.open() as f:
        raw = yaml.safe_load(f)
    return StillConfig.model_validate(raw)
