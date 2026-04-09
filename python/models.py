"""
Data models for the RA Genre Network pipeline.

podcast_id is the primary key (unique per episode).
ra_mix_number is extracted from the title for display purposes (e.g. "RA.1033").
One ra_mix_number can map to multiple podcast_ids (e.g. RA.1000 celebration series has 10).
"""
from __future__ import annotations

import re
from typing import Optional
from pydantic import BaseModel, Field, model_validator


def extract_ra_mix_number(title: str) -> str:
    """Extract RA.XXXX from title string. Returns empty string if not found."""
    m = re.search(r"RA\.(\d+)", title or "")
    return f"RA.{m.group(1)}" if m else ""


class Episode(BaseModel):
    """One RA podcast mix episode. podcast_id is the primary key."""

    podcast_id: str = Field(..., description="Unique episode ID (from RA.co internal)")
    url: str
    title: str
    artist_name: Optional[str] = ""
    artist_id: Optional[str] = ""
    date: str = Field(..., description="Release date (YYYY-MM-DD)")
    duration_seconds: Optional[int] = None
    duration_raw: Optional[str] = None
    image_url: Optional[str] = None
    streaming_url: Optional[str] = None
    description: Optional[str] = None
    blurb: Optional[str] = None
    keywords: list[str] = Field(default_factory=list)
    has_tracklist: bool = False
    tracklist_raw: Optional[str] = None
    archived: bool = False
    scrape_source: str = ""
    scrape_quality: str = ""
    scraped_at: Optional[str] = None

    # Derived display field — populated by migration script
    ra_mix_number: str = Field(default="", description="Display ID (e.g. 'RA.1033'), extracted from title")

    @model_validator(mode="after")
    def populate_ra_mix_number(self) -> Episode:
        if not self.ra_mix_number:
            self.ra_mix_number = extract_ra_mix_number(self.title)
        return self


class Track(BaseModel):
    """One track in a podcast tracklist."""

    track_id: str
    podcast_id: str
    position: int
    artist: str = ""
    title: str = ""
    label: Optional[str] = None
    timestamp: Optional[str] = None
    raw_line: Optional[str] = None
    parse_confidence: str = "low"


class GenreEdge(BaseModel):
    """Genre assignment for an episode."""

    entity_type: str = "episode"
    entity_id: str = Field(..., description="Same as podcast_id")
    genre_raw: str
    genre_canonical: str
    source: str = "regex"
    confidence: float = 0.5


class LabelEntry(BaseModel):
    """LLM-extracted genres and labels for an episode."""

    podcast_id: str
    genres: list[str] = Field(default_factory=list)
    labels: list[str] = Field(default_factory=list)
    label_categories: dict[str, list[str]] = Field(default_factory=dict)
    notes: str = ""
    model: str = ""
    usage: dict = Field(default_factory=dict)


class ConsolidatedMix(BaseModel):
    """
    Fully denormalized mix record — combines Episode, LabelEntry, and genres.
    This is what build_network_html.py reads from consolidated.json.
    """

    podcast_id: str
    ra_mix_number: str
    title: str
    artist_name: Optional[str] = ""
    date: str
    image_url: Optional[str] = None
    streaming_url: Optional[str] = None
    description: Optional[str] = None
    blurb: Optional[str] = None
    keywords: list[str] = Field(default_factory=list)
    has_tracklist: bool = False
    duration_raw: Optional[str] = None

    # From LLM cache
    genres: list[str] = Field(default_factory=list)
    labels: list[str] = Field(default_factory=list)
    label_categories: dict[str, list[str]] = Field(default_factory=dict)
    notes: str = ""


class ConsolidatedData(BaseModel):
    """Root structure of data/consolidated.json."""

    version: str = "2.0"
    generated_at: str
    total_mixes: int
    mixes: list[ConsolidatedMix]
