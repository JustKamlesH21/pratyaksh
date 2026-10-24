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
    assert api.post(f"/v1/calls/{call_id}/review", json={"approve": False}).status_code == 403
    reviewed = api.post(f"/v1/calls/{call_id}/review", json={"approve": False},
                        headers={"X-Console-Key": "console-secret"}).json()
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


def test_verification_receipts_over_http_check_with_any_jwt_library(api):
    jwt = pytest.importorskip("jwt")
    call_id = api.post("/v1/calls", json={"customer_id": C}).json()["call_id"]
    send(api, call_id, "what is my balance", voiced())
    assert api.get(f"/v1/calls/{call_id}/receipt").status_code == 403  # bank systems only
    issued = api.get(f"/v1/calls/{call_id}/receipt", headers={"X-Console-Key": "console-secret"}).json()
    assert issued["claims"]["executable"] is True

    checked = api.post("/v1/receipts/verify", json={"receipt": issued["receipt"]}).json()
    assert checked["valid"] is True and checked["claims"]["call_id"] == call_id

    jwk = api.get("/v1/receipts/key").json()["keys"][0]
    key = jwt.PyJWK(jwk).key
    assert jwt.decode(issued["receipt"], key, algorithms=["EdDSA"])["call_id"] == call_id
