"""Tests for the LPC noise-excitation whisperiser (run with the attacker venv)."""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dsp_whisper import _lpc, whisperise  # noqa: E402


def test_lpc_recovers_known_ar_process():
    # x[n] = 0.6 x[n-1] - 0.3 x[n-2] + e[n]  =>  A(z) = 1 - 0.6 z^-1 + 0.3 z^-2
    from scipy.signal import lfilter

    rng = np.random.default_rng(1)
    e = rng.standard_normal(20000)
    x = lfilter([1.0], [1.0, -0.6, 0.3], e)
    a = _lpc(x * np.hanning(len(x)), order=2)
    assert a[0] == 1.0
    assert abs(a[1] - (-0.6)) < 0.05
    assert abs(a[2] - 0.3) < 0.05


def _voiced(sr=24000, secs=0.5, f0=120.0):
    t = np.arange(int(sr * secs)) / sr
    # A buzzy, periodic source shaped by a couple of fixed formants.
    sig = sum(np.sin(2 * np.pi * k * f0 * t) / k for k in range(1, 20))
    return (0.3 * sig / np.max(np.abs(sig))).astype(np.float32)


def test_whisperise_shape_and_range():
    x = _voiced()
    out = whisperise(x, 24000)
    assert out.dtype == np.float32
    assert out.shape == x.shape
    assert np.all(np.isfinite(out))
    assert np.max(np.abs(out)) <= 1.0


def test_whisperise_level_is_usable():
    # Peak-normalised to safe headroom, and audibly non-silent (not crushed to zero).
    x = _voiced()
    out = whisperise(x, 24000)
    assert 0.9 < np.max(np.abs(out)) <= 1.0
    assert np.sqrt(np.mean(out ** 2)) > 1e-3


def test_whisperise_preserves_loudness_contour():
    # A quiet half followed by a loud half must stay quieter-then-louder after
    # the per-frame matched gain.
    sr = 24000
    loud = _voiced(sr=sr, secs=0.4)
    sig = np.concatenate([0.1 * loud, loud]).astype(np.float32)
    out = whisperise(sig, sr)
    half = len(out) // 2
    first = np.sqrt(np.mean(out[:half] ** 2))
    second = np.sqrt(np.mean(out[half:] ** 2))
    assert second > first * 3


def test_whisperise_removes_periodicity():
    # A whisper has no pitch: the normalized autocorrelation at the pitch lag
    # should be far weaker than in the voiced input.
    sr = 24000
    x = _voiced(sr=sr, f0=120.0)
    out = whisperise(x, sr)
    lag = int(sr / 120.0)

    def ac(sig, k):
        s = sig - sig.mean()
        return float(np.dot(s[:-k], s[k:]) / np.dot(s, s))

    assert ac(x, lag) > 0.4          # voiced input is strongly periodic
    assert ac(out, lag) < ac(x, lag) - 0.2  # whisper is much less so


def test_whisperise_silence_stays_silent():
    out = whisperise(np.zeros(12000, dtype=np.float32), 24000)
    assert np.max(np.abs(out)) < 1e-3


def test_whisperise_empty():
    out = whisperise(np.zeros(0, dtype=np.float32), 24000)
    assert out.size == 0
