"""Shared helpers for the Clone clip bank: the manifest schema, reading/appending it,
fuzzy phrase lookup, and resolving an output device name.

Pure Python (csv + difflib) so it imports without torch/soundfile and is unit-testable
with the attacker venv. make_clone_bank.py writes the manifest; play_clip.py reads it.
"""

from __future__ import annotations

import csv
import re
from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path

# Manifest columns, in order. One row per generated Clone clip.
FIELDS = ["phrase", "variant", "file", "seconds", "gen_seconds", "sample_rate", "created"]

VARIANTS = ("normal", "whispered-ref", "dsp-whisper")


@dataclass
class ClipRow:
    phrase: str
    variant: str
    file: str
    seconds: float
    gen_seconds: float
    sample_rate: int
    created: str

    def as_dict(self) -> dict:
        return {
            "phrase": self.phrase,
            "variant": self.variant,
            "file": self.file,
            "seconds": f"{self.seconds:.3f}",
            "gen_seconds": f"{self.gen_seconds:.3f}",
            "sample_rate": str(self.sample_rate),
            "created": self.created,
        }


def read_manifest(path: str | Path) -> list[dict]:
    """Return the manifest rows as a list of dicts (empty if the file is absent)."""
    path = Path(path)
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def append_row(path: str | Path, row: ClipRow) -> None:
    """Append one row, writing the header first if the manifest is new."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    new = not path.exists()
    with path.open("a", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=FIELDS)
        if new:
            w.writeheader()
        w.writerow(row.as_dict())


def done_keys(rows: list[dict]) -> set[tuple[str, str]]:
    """(phrase, variant) pairs already present — so a run can resume without redoing them."""
    return {(r["phrase"], r["variant"]) for r in rows}


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", s.strip().lower())


def fuzzy_lookup(rows: list[dict], query: str, *, variant: str | None = None,
                 n: int = 1) -> list[tuple[float, dict]]:
    """Rank manifest rows by how well their phrase matches `query`.

    Returns up to `n` (score, row) pairs, best first. Case- and whitespace-insensitive.
    `variant` restricts the search to one Clone variant.
    """
    q = _norm(query)
    pool = [r for r in rows if variant is None or r["variant"] == variant]
    scored = []
    for r in pool:
        ratio = SequenceMatcher(None, q, _norm(r["phrase"])).ratio()
        # Nudge exact substring hits up so "dinner at five" finds the longer phrase.
        if q and q in _norm(r["phrase"]):
            ratio = max(ratio, 0.95)
        scored.append((ratio, r))
    scored.sort(key=lambda t: t[0], reverse=True)
    return scored[:n]


def resolve_device(devices: list[dict], name: str | None) -> int | None:
    """Map an output-device name (or substring, case-insensitive) to its index.

    `devices` is sounddevice.query_devices() output (a list of dicts). Returns the index,
    or None when `name` is None or no output device matches — the caller then falls back
    to the system default and tells the user. VB-Cable not being installed yet (no "CABLE"
    device) therefore degrades gracefully instead of crashing.
    """
    if name is None:
        return None
    if name.isdigit():
        return int(name)
    needle = name.lower()
    for i, d in enumerate(devices):
        if d.get("max_output_channels", 0) > 0 and needle in str(d.get("name", "")).lower():
            return i
    return None
