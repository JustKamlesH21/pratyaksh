"""Eval Run report (Wilson intervals, conditions, channels, caught-by, latency) and Whisper Score calibration."""

import csv
import hashlib
import json
from importlib import resources

import pytest
from conftest import voiced, whispered

from pratyaksh.domain import Audio
from pratyaksh.eval.calibrate import Sample, calibrate
from pratyaksh.eval.run import evaluate, main, read_manifest
from pratyaksh.eval.stats import rate, wilson
from pratyaksh.policy import Policy
from pratyaksh.signals import ScriptedSpeechModels

PHRASE = "naale saat baje meeting"
OLD_FIELDS = ["session_id", "label", "request", "kind", "audio", "reply_latency_ms", "expected", "code_match", "transcript"]


@pytest.mark.parametrize("k,n,lo,hi", [(10, 10, 0.722, 1.0), (20, 20, 0.839, 1.0), (0, 20, 0.0, 0.161)])
def test_wilson_interval_matches_known_values(k, n, lo, hi):
    got = wilson(k, n)
    assert got[0] == pytest.approx(lo, abs=1e-3) and got[1] == pytest.approx(hi, abs=1e-3)
    assert rate(k, n)["ci95"] == [pytest.approx(lo, abs=1e-3), pytest.approx(hi, abs=1e-3)]


def test_wilson_interval_needs_trials():
    assert wilson(0, 0) is None and rate(0, 0) == {"k": 0, "n": 0, "rate": None, "ci95": None}


def _wav(folder, name: str, audio: Audio) -> str:
    (folder / name).write_bytes(audio.to_wav())
    return name


def _manifest(tmp_path, rows: list[dict], fields=None):
    path = tmp_path / "manifest.csv"
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields or list(rows[0]), extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)
    return path


def _session(tmp_path, sid, label, *, whisper=True, latency=700, code=True, request="add_payee", phrases=1, **extra):
    rows = [{
        "session_id": sid, "label": label, "request": request, "kind": "whisper_phrase",
        "audio": _wav(tmp_path, f"{sid}-w{i}.wav", whispered(seed=i) if whisper else voiced(seed=i)),
        "reply_latency_ms": latency, "expected": PHRASE, "code_match": "", "transcript": PHRASE, **extra,
    } for i in range(phrases)]
    rows.append({
        "session_id": sid, "label": label, "request": request, "kind": "possession_code",
        "audio": _wav(tmp_path, f"{sid}-c.wav", voiced()), "reply_latency_ms": latency, "expected": "",
        "code_match": str(code).lower(), "transcript": "4 8 1 9 2 7", **extra,
    })
    return rows


def _evaluate(path):
    return evaluate(read_manifest(path), Policy.load(), lambda r: ScriptedSpeechModels([r.transcript], spoof=0.05))


BLANK = {"condition": "", "channel": "", "language": ""}


def test_report_counts_rates_with_intervals_conditions_channels_and_caught_by(tmp_path):
    rows = (
        _session(tmp_path, "real-1", "real", **{**BLANK, "language": "kn"})
        + _session(tmp_path, "real-2", "real", **{**BLANK, "channel": "cable", "language": "en"})
        + _session(tmp_path, "real-3", "real", whisper=False, **{**BLANK, "language": "en"})  # spoke aloud
        # Clone without the Registered Device: wrong code, voiced phrase, typed slowly.
        + _session(tmp_path, "clone-1", "clone", whisper=False, latency=3100, code=False, **BLANK)
        # Clone given the right code (inferred code_supplied): only the voice Signals can catch it.
        + _session(tmp_path, "clone-2", "clone", whisper=False, latency=900, request="sim_swap", phrases=2, **BLANK)
        # Explicit condition; a whispering Clone with the right code gets through.
        + _session(tmp_path, "clone-3", "clone", latency=900, **{**BLANK, "condition": "code_supplied"})
    )
    report = _evaluate(_manifest(tmp_path, rows))
    s = report["summary"]

    assert (s["catch"]["k"], s["catch"]["n"]) == (2, 3) and s["catch_rate"] == pytest.approx(0.667)
    assert s["catch"]["ci95"] == [pytest.approx(0.208, abs=1e-3), pytest.approx(0.939, abs=1e-3)]
    assert (s["false_reject"]["k"], s["false_reject"]["n"]) == (1, 3)
    assert (s["clone_pass"]["k"], s["clone_pass"]["n"]) == (1, 3)

    assert (s["by_condition"]["code_withheld"]["k"], s["by_condition"]["code_withheld"]["n"]) == (1, 1)
    assert (s["by_condition"]["code_supplied"]["k"], s["by_condition"]["code_supplied"]["n"]) == (1, 2)

    by_row = {r["session_id"]: r for r in report["rows"]}
    assert {"possession_code", "reply_latency"} <= set(by_row["clone-1"]["caught_by"])
    assert by_row["clone-2"]["caught_by"] == ["whisper_score"]
    assert by_row["clone-3"]["caught_by"] == [] and by_row["real-1"]["condition"] is None
    assert s["caught_by"]["whisper_score"] == 2 and s["caught_by_only"] == {"whisper_score": 1}

    assert s["by_channel"]["cable"]["false_reject"] == rate(0, 1)
    assert s["by_channel"]["mic"]["false_reject"]["n"] == 2 and s["by_channel"]["mic"]["catch"]["n"] == 3
    assert s["by_language"]["kn"]["false_reject"] == rate(0, 1)
    assert s["by_language"]["en"]["false_reject"] == rate(1, 2)
    assert s["by_language"]["unspecified"]["catch"]["n"] == 3

    h = s["hearing_ms"]
    assert h["n"] == len(rows) and h["max"] >= h["p95"] >= h["median"]
    assert s["added_seconds"]["real"]["n"] == 3 and s["added_seconds"]["real"]["median"] > 8
    assert s["live_hearing_ms"] is None


def test_older_manifests_still_run_and_infer_the_condition(tmp_path):
    rows = _session(tmp_path, "real-1", "real") + _session(tmp_path, "clone-1", "clone", whisper=False, code=False)
    s = _evaluate(_manifest(tmp_path, rows, OLD_FIELDS))["summary"]
    assert s["catch_rate"] == 1.0 and s["false_reject_rate"] == 0.0
    assert set(s["by_condition"]) == {"code_withheld"} and set(s["by_channel"]) == {"mic"}


def test_manifest_rejects_unknown_condition_or_channel(tmp_path):
    rows = _session(tmp_path, "c", "clone", **{**BLANK, "condition": "code_guessed"})
    with pytest.raises(SystemExit, match="condition"):
        read_manifest(_manifest(tmp_path, rows))
    rows = _session(tmp_path, "r", "real", **{**BLANK, "channel": "phone"})
    with pytest.raises(SystemExit, match="channel"):
        read_manifest(_manifest(tmp_path, rows))


def test_cli_run_prints_rates_as_counts_with_wilson_intervals(tmp_path, capsys):
    rows = _session(tmp_path, "real-1", "real") + _session(tmp_path, "clone-1", "clone", whisper=False, code=False)
    out_json = tmp_path / "report.json"
    main(["run", str(_manifest(tmp_path, rows, OLD_FIELDS)), "--speech", "scripted", "--no-save",
          "--json", str(out_json)])
    text = capsys.readouterr().out
    assert "Catch Rate:        1/1 = 100% (95% CI 21%-100%)" in text
    assert "False Reject Rate: 0/1 = 0% (95% CI 0%-79%)" in text
    assert "Hearing time per Response" in text and "Added Time per real Call" in text
    assert json.loads(out_json.read_text(encoding="utf-8"))["summary"]["catch"]["ci95"][1] == 1.0


# -- calibrate ---------------------------------------------------------------------------------


def _policy_hash() -> str:
    return hashlib.sha256(resources.files("pratyaksh").joinpath("policy.yaml").read_bytes()).hexdigest()


def test_calibrate_cli_summarises_classes_suggests_a_threshold_and_writes_a_dot_plot(tmp_path, capsys):
    root = tmp_path / "calibration"
    makers = {
        "whisper": lambda i: whispered(seed=i),
        "normal": lambda i: voiced(seed=i),
        "soft": lambda i: voiced(f0=220, seed=i),
        "silence": lambda i: Audio.silence(1.0),
    }
    for cls, make in makers.items():
        (root / cls).mkdir(parents=True)
        for i in range(2):
            _wav(root / cls, f"{cls}-{i}.wav", make(i))
    before = _policy_hash()
    html_out, json_out = tmp_path / "plot.html", tmp_path / "cal.json"
    main(["calibrate", str(root), "--html", str(html_out), "--json", str(json_out)])
    text = capsys.readouterr().out

    report = json.loads(json_out.read_text(encoding="utf-8"))
    assert report["classes"]["whisper"]["n"] == 2 and report["classes"]["whisper"]["min"] == 1.0
    assert report["classes"]["silence"]["no_speech"] == 2
    assert report["gap"] is True and report["highest_negative"]["class"] == "soft"
    s = report["suggested"]
    assert s["low_exclusive"] < s["threshold"] <= s["high_inclusive"] == 1.0
    assert (s["false_accepts"]["k"], s["false_accepts"]["n"]) == (0, 6)
    assert s["false_accept_rule_of_three"] == pytest.approx(0.5)
    assert report["current"]["threshold"] == 0.6
    assert "suggested whisper_score.min" in text and "rule of three" in text and "policy.yaml is not changed" in text

    page = html_out.read_text(encoding="utf-8")
    assert "<svg" in page and "<circle" in page and "<script" not in page
    assert "http" not in page.replace("http://www.w3.org", "")
    assert _policy_hash() == before


def test_calibrate_reads_an_exported_manifest(tmp_path, capsys):
    rows = _session(tmp_path, "real-1", "real") + _session(tmp_path, "clone-1", "clone", whisper=False)
    main(["calibrate", str(_manifest(tmp_path, rows, OLD_FIELDS))])
    text = capsys.readouterr().out
    assert (tmp_path / "calibration.html").exists()
    for cls in ("whisper", "normal", "clone"):
        assert f"\n{cls} " in text


def test_calibrate_without_a_gap_prefers_zero_false_accepts():
    samples = [Sample("whisper", f"w{i}", v) for i, v in enumerate([0.55, 0.8, 0.9, 0.95])] + [
        Sample("normal", "n1", 0.2), Sample("clone", "c1", 0.61), Sample("noise", "x1", 0.99),
        Sample("whisper", "w9", None),
    ]
    report = calibrate(samples, exclude=("noise",), current_min=0.6)
    assert report["gap"] is False and report["classes"]["noise"]["role"] == "excluded"
    s = report["suggested"]
    assert s["threshold"] == 0.62 and s["false_accepts"]["k"] == 0
    assert (s["false_rejects"]["k"], s["false_rejects"]["n"]) == (2, 5)  # 0.55 and the whisper with no speech
    assert report["current"]["false_accepts"]["k"] == 1  # the Clone at 0.61 passes today's 0.60
    assert report["notes"]
