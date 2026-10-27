"""Tests for the clip-bank helpers (pure Python; run with the attacker venv)."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from clip_bank import (  # noqa: E402
    ClipRow,
    append_row,
    done_keys,
    fuzzy_lookup,
    read_manifest,
    resolve_device,
)


def _rows():
    return [
        {"phrase": "dinner naale at five", "variant": "normal", "file": "a.wav"},
        {"phrase": "bring two kilos of tomato", "variant": "normal", "file": "b.wav"},
        {"phrase": "dinner naale at five", "variant": "dsp-whisper", "file": "c.wav"},
    ]


def test_fuzzy_exact_match_ranks_first():
    hits = fuzzy_lookup(_rows(), "bring two kilos of tomato")
    assert hits[0][1]["file"] == "b.wav"
    assert hits[0][0] >= 0.95


def test_fuzzy_is_case_and_space_insensitive():
    hits = fuzzy_lookup(_rows(), "  BRING   two Kilos of TOMATO ")
    assert hits[0][1]["file"] == "b.wav"


def test_fuzzy_variant_filter():
    hits = fuzzy_lookup(_rows(), "dinner naale at five", variant="dsp-whisper")
    assert len(hits) == 1
    assert hits[0][1]["file"] == "c.wav"


def test_fuzzy_substring_boost():
    hits = fuzzy_lookup(_rows(), "two kilos")
    assert hits[0][1]["file"] == "b.wav"


def test_resolve_device_substring_and_index():
    devices = [
        {"name": "Microphone (Realtek)", "max_output_channels": 0},
        {"name": "CABLE Input (VB-Audio Virtual Cable)", "max_output_channels": 2},
        {"name": "Speakers", "max_output_channels": 2},
    ]
    assert resolve_device(devices, "CABLE Input") == 1
    assert resolve_device(devices, "cable") == 1
    assert resolve_device(devices, "2") == 2
    assert resolve_device(devices, None) is None
    assert resolve_device(devices, "nonexistent") is None
    # A name that only matches an input-only device must not be chosen for output.
    assert resolve_device(devices, "Microphone") is None


def test_manifest_roundtrip(tmp_path):
    m = tmp_path / "manifest.csv"
    append_row(m, ClipRow("dinner at five", "normal", "x.wav", 1.234, 5.6, 24000, "2026-10-27T10:00:00"))
    append_row(m, ClipRow("two kilos", "dsp-whisper", "y.wav", 2.0, 7.0, 24000, "2026-10-27T10:01:00"))
    rows = read_manifest(m)
    assert len(rows) == 2
    assert rows[0]["phrase"] == "dinner at five"
    assert rows[0]["seconds"] == "1.234"
    assert done_keys(rows) == {("dinner at five", "normal"), ("two kilos", "dsp-whisper")}


def test_read_manifest_absent(tmp_path):
    assert read_manifest(tmp_path / "nope.csv") == []
