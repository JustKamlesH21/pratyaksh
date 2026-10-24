"""Record Calls with RETAIN_AUDIO, export them to a manifest, and run an Eval Run on it."""

from conftest import database_url, voiced, whispered
from fastapi.testclient import TestClient

from pratyaksh.api.app import create_app
from pratyaksh.api.container import build
from pratyaksh.config import Settings
from pratyaksh.eval.run import evaluate, export, main, read_manifest
from pratyaksh.policy import Policy
from pratyaksh.signals import ScriptedSpeechModels

C = "cust-ananya"


def _call(client, models, genuine: bool):
    call_id = client.post("/v1/calls", json={"customer_id": C}).json()["call_id"]

    def send(text, audio, latency):
        models.push(text)
        client.post(f"/v1/calls/{call_id}/responses",
                    files={"audio": ("r.wav", audio.to_wav(), "audio/wav")}, data={"reply_latency_ms": str(latency)})

    send("add a payee", voiced(), 800)
    phrase = client.get(f"/v1/calls/{call_id}").json()["challenges"][-1]["phrase"]
    if genuine:
        send(phrase, whispered(), 700)
        token = client.app.state.c.verifier.pairing(C)
        code = client.get(f"/v1/customers/{C}/inbox", headers={"X-Device-Token": token}).json()["messages"][0]["body"]["code"]
        send(code, voiced(), 900)
    else:
        send("some other words", voiced(), 3100)
        send("9 9 9 9 9 9", voiced(), 3200)
        send("9 9 9 9 9 9", voiced(), 3300)  # the one retry
    return client.get(f"/v1/calls/{call_id}").json()


def test_record_export_and_evaluate(tmp_path, monkeypatch):
    db_url = database_url(f"sqlite:///{tmp_path / 'eval.db'}")
    settings = Settings(
        _env_file=None, database_url=db_url, speech_backend="scripted", tts_backend="tone",
        tts_cache_dir=str(tmp_path / "tts"), receipt_key_path=str(tmp_path / "key.pem"), warm_up_models=False, retain_audio=True,
        audio_dir=str(tmp_path / "rec"),
    )
    models = ScriptedSpeechModels(spoof=0.05)
    container = build(settings, speech=models)
    with TestClient(create_app(container=container)) as client:
        assert _call(client, models, genuine=True)["verdict"] == "PASS"
        manifest = tmp_path / "manifest.csv"
        assert export(container.db, tmp_path / "rec", "real", None, manifest) == 2
        assert _call(client, models, genuine=False)["verdict"] == "BLOCK"

    rows = read_manifest(manifest)
    # Export again for the clone Call only (already-exported real rows stay labelled real).
    clone_id = container.verifier.calls(1)[0]["id"]
    from datetime import datetime
    since = datetime.fromisoformat(container.verifier.call(clone_id)["created_at"])
    assert export(container.db, tmp_path / "rec", "clone", since, manifest) == 2
    rows = read_manifest(manifest)
    assert {r.label for r in rows} == {"real", "clone"} and len(rows) == 4

    report = evaluate(rows, Policy.load(), lambda r: ScriptedSpeechModels([r.transcript], spoof=0.05))
    s = report["summary"]
    assert s["real_calls"] == 1 and s["clone_calls"] == 1
    assert s["catch_rate"] == 1.0 and s["false_reject_rate"] == 0.0
    assert s["avg_added_seconds_real"] > 8

    # The CLI stores the run where the Eval page reads it.
    monkeypatch.setenv("DATABASE_URL", db_url)
    main(["run", str(manifest), "--speech", "scripted", "--label", "test run"])
    assert container.db.latest_eval_run()["label"] == "test run"
