"""The HTTP interface, end to end, with scripted speech models and the tone voice."""

import base64
import json

import pytest
from conftest import database_url, voiced, whispered
from fastapi.testclient import TestClient

from pratyaksh.api.app import create_app
from pratyaksh.api.container import build
from pratyaksh.config import Settings
from pratyaksh.signals import ScriptedSpeechModels

C = "cust-rahul"
NO_KEY = {"X-Console-Key": ""}


@pytest.fixture
def api(tmp_path):
    settings = Settings(
        _env_file=None,
        database_url=database_url(),
        speech_backend="scripted",
        tts_backend="tone",
        tts_cache_dir=str(tmp_path / "tts"), receipt_key_path=str(tmp_path / "key.pem"),
        ollama_api_key="",
        warm_up_models=False,
        livekit_public_url="ws://192.168.1.10:7880",
        console_key="console-secret",
    )
    models = ScriptedSpeechModels(spoof=0.05)
    container = build(settings, speech=models)
    with TestClient(create_app(container=container)) as client:
        client.models = models
        client.headers["X-Console-Key"] = "console-secret"  # the Console; tests of refusals send none
        yield client


def device(client, customer_id):
    """Headers of the paired Bank App (the token comes from the operator's machine, not HTTP)."""
    return {"X-Device-Token": client.app.state.c.verifier.pairing(customer_id)}


def send(client, call_id, transcript, audio, latency=700):
    client.models.push(transcript)
    r = client.post(
        f"/v1/calls/{call_id}/responses",
        files={"audio": ("reply.wav", audio.to_wav(), "audio/wav")},
        data={"reply_latency_ms": str(latency)},
    )
    assert r.status_code == 200, r.text
    return r.json()


def test_a_full_call_over_http(api):
    customers = api.get("/v1/customers").json()
    assert {c["id"] for c in customers} >= {C}

    step = api.post("/v1/calls", json={"customer_id": C, "room": "room-a"}).json()
    call_id = step["call_id"]
    assert step["listen"] is True

    step = send(api, call_id, "naya payee add karna hai", voiced())
    phrase = api.get(f"/v1/calls/{call_id}").json()["challenges"][-1]["phrase"]
    step = send(api, call_id, phrase, whispered())
    assert "code" in step["say"]

    assert api.get(f"/v1/customers/{C}/inbox").status_code == 403  # no device token
    inbox = api.get(f"/v1/customers/{C}/inbox", headers=device(api, C)).json()
    code = inbox["messages"][0]["body"]["code"]
    step = send(api, call_id, code, voiced(), 900)
    assert step["end"] is True and step["outcome"] == "passed"

    call = api.get(f"/v1/calls/{call_id}").json()
    assert call["verdict"] == "PASS" and call["events"][0]["kind"] == "call_started"
    assert api.get("/v1/calls").json()[0]["id"] == call_id


def test_app_approval_and_review_over_http(api):
    call_id = api.post("/v1/calls", json={"customer_id": C}).json()["call_id"]
    step = send(api, call_id, "transfer 7 lakh, I can't do this, use the bank app", voiced())
    assert step["wait"] is True
    assert api.get(f"/v1/calls/{call_id}/step").json()["wait"] is True
    r = api.post(f"/v1/calls/{call_id}/app-approval", json={"customer_id": C, "approve": True})
    assert r.status_code == 403  # the Clone's laptop has no device token
    r = api.post(f"/v1/calls/{call_id}/app-approval", json={"customer_id": "cust-meera", "approve": True},
                 headers=device(api, "cust-meera"))
    assert r.status_code == 409
    step = api.post(f"/v1/calls/{call_id}/app-approval", json={"customer_id": C, "approve": True},
                    headers=device(api, C)).json()
    assert step["outcome"] == "approved_in_app"
    assert api.post(f"/v1/calls/{call_id}/review", json={"approve": False}, headers=NO_KEY).status_code == 403
    reviewed = api.post(f"/v1/calls/{call_id}/review", json={"approve": False}).json()
    assert reviewed["review_status"] == "rejected"


def test_voice_returns_cached_wav(api):
    r1 = api.get("/v1/voice", params={"text": "Please whisper these words"})
    r2 = api.get("/v1/voice", params={"text": "Please  whisper these words"})
    assert r1.status_code == 200 and r1.headers["content-type"] == "audio/wav"
    assert r1.content[:4] == b"RIFF" and r1.content == r2.content


def test_livekit_token_is_scoped_to_one_room(api):
    r = api.post("/v1/livekit/token", json={"customer_id": C}).json()
    assert r["url"] == "ws://192.168.1.10:7880" and r["room"].startswith(f"call-{C}-")
    payload = json.loads(base64.urlsafe_b64decode(r["token"].split(".")[1] + "=="))
    assert payload["sub"] == C and payload["video"]["room"] == r["room"] and payload["video"]["roomJoin"]
    assert api.post("/v1/livekit/token", json={"customer_id": "nobody"}).status_code == 404


def test_console_websocket_gets_a_snapshot_then_live_calls(api):
    with api.websocket_connect("/v1/events") as ws:
        ws.send_json({"key": "console-secret"})
        assert ws.receive_json()["type"] == "snapshot"
        call_id = api.post("/v1/calls", json={"customer_id": C}).json()["call_id"]
        msg = ws.receive_json()
        assert msg["type"] == "call" and msg["call"]["id"] == call_id


def test_errors(api):
    assert api.get("/v1/calls/nope").status_code == 404
    assert api.post("/v1/calls", json={"customer_id": "nobody"}).status_code == 404
    assert api.get("/v1/eval-runs/latest").status_code == 404
    call_id = api.post("/v1/calls", json={"customer_id": C}).json()["call_id"]
    r = api.post(f"/v1/calls/{call_id}/responses", files={"audio": ("x.wav", b"not audio", "audio/wav")})
    assert r.status_code == 422


def test_only_the_voice_agent_can_start_calls_and_post_responses(tmp_path):
    settings = Settings(
        _env_file=None, database_url=database_url(), speech_backend="scripted", tts_backend="tone",
        tts_cache_dir=str(tmp_path / "tts"), receipt_key_path=str(tmp_path / "key.pem"), warm_up_models=False, agent_key="agent-secret",
    )
    agent = {"X-Agent-Key": "agent-secret"}
    reply = {"files": {"audio": ("r.wav", voiced().to_wav(), "audio/wav")}, "data": {"reply_latency_ms": "300"}}
    with TestClient(create_app(container=build(settings, speech=ScriptedSpeechModels(spoof=0.05)))) as client:
        assert client.post("/v1/calls", json={"customer_id": C}).status_code == 401
        call_id = client.post("/v1/calls", json={"customer_id": C}, headers=agent).json()["call_id"]
        # The attacker's laptop cannot post a Response with a forged Reply Latency, poll, hang up or render audio.
        assert client.post(f"/v1/calls/{call_id}/responses", **reply).status_code == 401
        assert client.get(f"/v1/calls/{call_id}/step").status_code == 401
        assert client.post(f"/v1/calls/{call_id}/hangup").status_code == 401
        assert client.get("/v1/voice", params={"text": "hello"}).status_code == 401
        assert client.post(f"/v1/calls/{call_id}/responses", headers={"X-Agent-Key": "guess"}, **reply).status_code == 401
        assert client.post(f"/v1/calls/{call_id}/responses", headers={"X-Agent-Key": "ключ".encode()}, **reply).status_code == 401
        assert client.post("/v1/calls", json={"customer_id": C}, headers={"X-Agent-Key": "ключ".encode()}).status_code == 401
        # Without the key a big upload is refused before a byte of it is read or spooled to disk.
        big = {"files": {"audio": ("r.wav", b"0" * (20 * 1024 * 1024), "audio/wav")}}
        assert client.post(f"/v1/calls/{call_id}/responses", **big).status_code == 401
        assert client.post(f"/v1/calls/{call_id}/responses", headers=agent, **big).status_code == 413
        # The Voice Agent, the Caller app and the Console carry on as before.
        assert client.post(f"/v1/calls/{call_id}/responses", headers=agent, **reply).status_code == 200
        assert client.get("/v1/customers").status_code == 200
        assert client.get(f"/v1/calls/{call_id}").json()["events"][0]["kind"] == "call_started"


def test_oversized_or_overlong_audio_is_refused(api):
    call_id = api.post("/v1/calls", json={"customer_id": C}).json()["call_id"]
    huge = api.post(f"/v1/calls/{call_id}/responses", files={"audio": ("r.wav", b"0" * (9 * 1024 * 1024), "audio/wav")})
    assert huge.status_code == 413
    from pratyaksh.domain import Audio

    long = Audio.silence(61).to_wav()
    assert api.post(f"/v1/calls/{call_id}/responses", files={"audio": ("r.wav", long, "audio/wav")}).status_code == 413

    # A header claiming 100 Hz would be resampled into gigabytes: refused from the header, before decoding.
    import io

    import numpy as np
    import soundfile as sf

    buf = io.BytesIO()
    sf.write(buf, np.zeros(40_000, dtype=np.float32), 100, format="WAV", subtype="PCM_16")
    r = api.post(f"/v1/calls/{call_id}/responses", files={"audio": ("r.wav", buf.getvalue(), "audio/wav")})
    assert r.status_code == 422 and "sample rate" in r.json()["detail"]

    # JSON routes take small bodies only.
    assert api.post("/v1/receipts/verify", json={"receipt": "x" * 100_000}).status_code == 413
    chunked = iter([b"{" * 40_000, b"{" * 40_000])  # no Content-Length: counted as it arrives
    assert api.post("/v1/receipts/verify", content=chunked, headers={"content-type": "application/json"}).status_code == 413


def test_verification_receipts_over_http_check_with_any_jwt_library(api):
    jwt = pytest.importorskip("jwt")
    call_id = api.post("/v1/calls", json={"customer_id": C}).json()["call_id"]
    send(api, call_id, "what is my balance", voiced())
    assert api.get(f"/v1/calls/{call_id}/receipt", headers=NO_KEY).status_code == 403  # bank systems only
    issued = api.get(f"/v1/calls/{call_id}/receipt").json()
    assert issued["claims"]["executable"] is True

    checked = api.post("/v1/receipts/verify", json={"receipt": issued["receipt"]}).json()
    assert checked["valid"] is True and checked["claims"]["call_id"] == call_id

    jwk = api.get("/v1/receipts/key").json()["keys"][0]
    key = jwt.PyJWK(jwk).key
    assert jwt.decode(issued["receipt"], key, algorithms=["EdDSA"])["call_id"] == call_id


def test_status_says_what_to_fix_before_the_demo(api):
    status = api.get("/v1/status").json()
    assert status["database"] == {"ok": True, "dialect": status["database"]["dialect"], "audit_triggers": True}
    assert status["ready"] is False  # this test setup never warms models
    assert any("AGENT_KEY is empty" in w for w in status["warnings"])
    assert any("scripted" in w for w in status["warnings"])
    assert not any("CONSOLE_KEY" in w for w in status["warnings"])  # the fixture sets one
    assert len(status["keys"]["receipts"]) == 16


def test_stats_count_outcomes_and_added_time(api):
    test_a_full_call_over_http(api)
    stats = api.get("/v1/stats").json()
    assert stats["calls"] >= 1 and stats["by_outcome"].get("passed_pending_review", 0) + stats["by_outcome"].get("passed", 0) >= 1
    assert stats["avg_added_seconds"] is not None and stats["avg_added_seconds"] >= 0
    hearing = stats["hearing_ms"]
    assert hearing["responses"] == 3 and 0 <= hearing["p50"] <= hearing["p95"]


def test_transcripts_over_http(api):
    test_a_full_call_over_http(api)
    call_id = api.get("/v1/calls").json()[0]["id"]
    lines = api.get(f"/v1/calls/{call_id}/transcript").json()["lines"]
    assert [ln["speaker"] for ln in lines][:3] == ["system", "agent", "caller"]
    r = api.get(f"/v1/calls/{call_id}/transcript", params={"format": "text"})
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/plain")
    assert "attachment" in r.headers["content-disposition"] and "naya payee add karna hai" in r.text
    assert api.get(f"/v1/calls/{call_id}/transcript", params={"format": "pdf"}).status_code == 422
    assert api.get("/v1/calls/nope/transcript").status_code == 404


def test_call_filters_and_customer_risk_over_http(api):
    test_a_full_call_over_http(api)
    assert [c["outcome"] for c in api.get("/v1/calls", params={"outcome": "passed"}).json()] == ["passed"]
    assert api.get("/v1/calls", params={"outcome": "blocked"}).json() == []
    assert api.get("/v1/calls", params={"outcome": "nonsense"}).status_code == 422
    assert len(api.get("/v1/calls", params={"customer_id": C}).json()) == 1
    risk = api.get(f"/v1/customers/{C}/risk").json()
    assert risk["risk"] == "normal" and risk["calls_7d"] == 1 and risk["voice_pause"]["active"] is False
    assert api.get("/v1/customers/nobody/risk").status_code == 404


def test_with_a_console_key_what_callers_said_is_for_bank_staff_only(api):
    from starlette.websockets import WebSocketDisconnect

    test_a_full_call_over_http(api)
    call_id = api.get("/v1/calls").json()[0]["id"]
    for path in ["/v1/calls", f"/v1/calls/{call_id}", f"/v1/calls/{call_id}/audit", f"/v1/calls/{call_id}/transcript",
                 f"/v1/customers/{C}/risk"]:
        assert api.get(path, headers=NO_KEY).status_code == 403, path
        assert api.get(path, headers={"X-Console-Key": "ключ".encode()}).status_code == 403, path
    for path in ["/v1/status", "/v1/stats", "/v1/customers", "/v1/receipts/key"]:
        assert api.get(path, headers=NO_KEY).status_code == 200, path
    with pytest.raises(WebSocketDisconnect) as closed:
        with api.websocket_connect("/v1/events") as ws:
            ws.send_json({"key": "guess"})
            ws.receive_json()
    assert closed.value.code == 4401


def test_core_banking_redeems_a_receipt_once(api):
    call_id = api.post("/v1/calls", json={"customer_id": C}).json()["call_id"]
    send(api, call_id, "what is my balance", voiced())
    first, second = (api.get(f"/v1/calls/{call_id}/receipt").json()["receipt"] for _ in range(2))
    assert api.post("/v1/receipts/redeem", json={"receipt": first}, headers=NO_KEY).status_code == 403
    assert api.post("/v1/receipts/redeem", json={"receipt": first}).json()["redeemed"] is True
    again = api.post("/v1/receipts/redeem", json={"receipt": first})
    assert again.status_code == 409 and "already carried out" in again.json()["detail"]
    assert api.post("/v1/receipts/redeem", json={"receipt": second}).status_code == 409  # a fresh receipt too
    assert api.post("/v1/receipts/verify", json={"receipt": first}).json()["redeemed"] is True
    lines = api.get(f"/v1/calls/{call_id}/transcript").json()["lines"]
    assert lines[-1]["event"] == "receipt_redeemed"
