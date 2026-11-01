"""Voice Consent: the owner of a voice decides who may use it, for what, for how long, and how many times."""

import csv
import random

import pytest
from conftest import Clock, database_url, voiced
from fastapi.testclient import TestClient

from pratyaksh.api.app import create_app
from pratyaksh.api.container import build
from pratyaksh.config import Settings
from pratyaksh.signals import ScriptedSpeechModels, SignalExtractor
from pratyaksh.verification import (
    ConsentNotFound, Database, DeviceNotPaired, EventHub, Interpreter, NotAllowed, ReceiptSigner, UnknownCustomer,
    Verifier, VoiceConsents,
)
from pratyaksh.policy import Policy
from pratyaksh.verification.consent import PURPOSES
from pratyaksh.verification.store import VoiceConsentRow

RAHUL, MEERA = "cust-rahul", "cust-meera"
LAB = "Omnitrons Lab"
DIGIT_WORDS = ("zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine")


class Bench:
    def __init__(self):
        self.db = Database(database_url())
        self.db.create_schema()
        self.db.seed_demo_customers()
        self.models = ScriptedSpeechModels()
        self.clock = Clock()
        self.consents = VoiceConsents(self.db, SignalExtractor(self.models), ReceiptSigner.generate(),
                                      rng=random.Random(3), clock=self.clock)
        self.verifier = Verifier(self.db, Policy.load(), SignalExtractor(self.models), Interpreter(None), EventHub(),
                                 clock=self.clock)

    def device(self, customer: str) -> str:
        return self.verifier.pairing(customer)

    def ask(self, customer=RAHUL, purpose="security_test", minutes=60, max_uses=3, requester=LAB) -> dict:
        return self.consents.ask(customer, requester, purpose, minutes, max_uses)

    def speak(self, asked: dict, heard: str | None = None, customer=RAHUL) -> dict:
        self.models.push(asked["statement"] if heard is None else heard)
        return self.consents.give(asked["id"], customer, self.device(customer), voiced(), b"statement-audio")

    def granted(self, **kw) -> tuple[dict, str]:
        asked = self.ask(**kw)
        result = self.speak(asked, customer=kw.get("customer", RAHUL))
        assert result["granted"], result
        return asked, result["consent_pass"]

    def use(self, consent_pass, purpose="security_test", requester=LAB, customer=RAHUL) -> dict:
        return self.consents.use(customer, requester, purpose, "clone-1", consent_pass)


@pytest.fixture
def bench() -> Bench:
    return Bench()


def test_the_request_reaches_only_the_owners_phone(bench):
    asked = bench.ask()
    mine = bench.consents.mine(RAHUL, bench.device(RAHUL))
    assert [c["id"] for c in mine["consents"]] == [asked["id"]]
    assert mine["consents"][0]["status"] == "pending"
    assert LAB in mine["consents"][0]["statement"] and "security testing" in mine["consents"][0]["statement"]
    assert bench.consents.mine(MEERA, bench.device(MEERA))["consents"] == []
    with pytest.raises(DeviceNotPaired):
        bench.consents.mine(RAHUL, "someone-elses-phone")


@pytest.mark.parametrize("customer, name", [(RAHUL, "Rahul Verma"), (MEERA, "Meera Iyer"), ("cust-ananya", "Ananya Rao")])
def test_every_customer_reads_the_statement_in_english(bench, customer, name):
    shown = bench.ask(customer=customer)["statement"]
    assert shown.startswith(f"I am {name}. I allow {LAB} to use my voice for security testing. Number ")
    assert all(w in DIGIT_WORDS for w in shown.split()[-2:])


def test_each_statement_has_a_fresh_number(bench):
    # So an old recording cannot be replayed.
    assert len({bench.ask()["statement"] for _ in range(6)}) > 1


def test_consent_is_given_by_speaking_the_statement_on_the_registered_device(bench):
    asked = bench.ask()
    result = bench.speak(asked)
    assert result["granted"] and result["consent_pass"]
    view = bench.consents.mine(RAHUL, bench.device(RAHUL))["consents"][0]
    assert view["status"] == "active" and view["uses"] == 0 and view["max_uses"] == 3


def test_a_statement_with_the_wrong_number_gives_no_consent_and_can_be_tried_again(bench):
    asked = bench.ask()
    wrong = "one one" if asked["statement"].endswith("nine nine") else "nine nine"
    result = bench.speak(asked, heard=asked["statement"].rsplit("Number", 1)[0] + f"Number {wrong}")
    assert not result["granted"] and "consent_pass" not in result
    assert bench.consents.mine(RAHUL, bench.device(RAHUL))["consents"][0]["status"] == "pending"
    assert bench.speak(asked)["granted"]


STATEMENT = "I am Rahul Verma. I allow Omnitrons Lab to use my voice for security testing. Number 7 3"
SENTENCE = "I am Rahul Verma. I allow Omnitrons Lab to use my voice for security testing."


@pytest.mark.parametrize("heard", [
    # What real speech-to-text wrote: the number comes in many spellings, and all of them are this number.
    "I am Rahul Varma. I allow Omnitran's lab to use my voice for security testing. No.73",
    f"{SENTENCE} Number seven three.",
    f"{SENTENCE} Number 7-3",
    f"{SENTENCE} Number 73",
])
def test_the_number_is_heard_however_it_was_written(heard):
    models = ScriptedSpeechModels()
    models.push(heard)
    assert SignalExtractor(models).statement_match(voiced(), STATEMENT)[1] >= 0.6


@pytest.mark.parametrize("heard", [
    f"{SENTENCE} Number 8 3",
    f"{SENTENCE} Number 3 7",
    SENTENCE,
    "Number 7 3",  # the number alone is not a statement
    "We could not verify this call. So for your safety, the request has been stopped.",
    "We could not verify this call. Number seven three.",  # nor is the right number on another sentence
    "",
])
def test_a_wrong_number_or_a_different_sentence_is_no_consent(heard):
    models = ScriptedSpeechModels()
    models.push(heard)
    assert SignalExtractor(models).statement_match(voiced(), STATEMENT)[1] < 0.6


def test_a_number_lost_at_the_end_is_listened_to_again():
    models = ScriptedSpeechModels()
    extractor = SignalExtractor(models)
    models.push(f"{SENTENCE} Number")
    models.push("Seven three.")
    assert extractor.statement_match(voiced(), STATEMENT)[1] >= 0.6
    models.push(f"{SENTENCE} Number")
    models.push("Five six.")
    assert extractor.statement_match(voiced(), STATEMENT)[1] < 0.6


def test_the_statement_is_heard_with_no_hint_and_the_second_listen_is_not_told_the_number():
    # With the words as hotwords, speech-to-text steered an old recording onto a new number (Oct 31: 1 of 6 accepted;
    # 0 of 6 with no hint).
    models = ScriptedSpeechModels()
    models.push(SENTENCE)
    SignalExtractor(models).statement_match(voiced(seconds=10), STATEMENT)
    assert [(h.language, h.hotwords) for h in models.hints] == [
        ("en", None), ("en", "zero one two three four five six seven eight nine"),
    ]


def test_another_phone_cannot_give_consent(bench):
    asked = bench.ask()
    bench.models.push(asked["statement"])
    with pytest.raises(DeviceNotPaired):
        bench.consents.give(asked["id"], RAHUL, bench.device(MEERA), voiced(), b"x")
    with pytest.raises(DeviceNotPaired):
        bench.consents.give(asked["id"], MEERA, bench.device(MEERA) + "x", voiced(), b"x")


def test_one_customers_phone_cannot_answer_for_another(bench):
    asked = bench.ask()
    with pytest.raises(ConsentNotFound):
        bench.consents.give(asked["id"], MEERA, bench.device(MEERA), voiced(), b"x")
    with pytest.raises(ConsentNotFound):
        bench.consents.revoke(asked["id"], MEERA, bench.device(MEERA))


def test_only_a_fingerprint_of_the_statement_audio_is_kept(bench):
    asked = bench.ask()
    bench.speak(asked)
    with bench.db.session() as s:
        row = s.get(VoiceConsentRow, asked["id"])
        assert len(row.statement_sha256) == 64
        assert not any(isinstance(getattr(row, c.name), bytes) for c in VoiceConsentRow.__table__.columns)


def test_a_declined_request_can_never_be_used(bench):
    asked = bench.ask()
    bench.consents.decline(asked["id"], RAHUL, bench.device(RAHUL))
    assert bench.consents.mine(RAHUL, bench.device(RAHUL))["consents"][0]["status"] == "declined"
    with pytest.raises(NotAllowed):
        bench.speak(asked)


def test_a_request_left_unanswered_lapses(bench):
    asked = bench.ask()
    bench.clock.advance(301)
    assert bench.consents.mine(RAHUL, bench.device(RAHUL))["consents"][0]["status"] == "lapsed"
    with pytest.raises(NotAllowed):
        bench.speak(asked)


def test_consent_cannot_be_given_twice(bench):
    asked = bench.ask()
    bench.speak(asked)
    with pytest.raises(NotAllowed):
        bench.speak(asked)


@pytest.mark.parametrize("kw", [
    {"purpose": "mind_control"}, {"minutes": 0}, {"minutes": 1441}, {"max_uses": 0}, {"max_uses": 101},
    {"requester": ""}, {"requester": "x" * 61},
])
def test_a_request_outside_the_rules_is_refused(bench, kw):
    with pytest.raises(NotAllowed):
        bench.ask(**kw)


def test_a_request_for_an_unknown_customer_is_refused(bench):
    with pytest.raises(UnknownCustomer):
        bench.ask(customer="cust-nobody")


def test_the_voice_can_be_used_for_what_was_agreed(bench):
    _, consent_pass = bench.granted()
    decision = bench.use(consent_pass)
    assert decision["allowed"] and decision["uses_left"] == 2


def test_no_pass_no_voice(bench):
    decision = bench.use(None)
    assert not decision["allowed"] and "no Consent Pass" in decision["reason"]


def test_a_different_purpose_is_refused(bench):
    _, consent_pass = bench.granted()
    decision = bench.use(consent_pass, purpose="advertising")
    assert not decision["allowed"] and "purpose" in decision["reason"]


def test_a_different_requester_is_refused(bench):
    _, consent_pass = bench.granted()
    decision = bench.use(consent_pass, requester="Shady Ads Ltd")
    assert not decision["allowed"] and "Omnitrons Lab" in decision["reason"]


def test_a_pass_is_only_for_its_owners_voice(bench):
    _, consent_pass = bench.granted()
    assert not bench.use(consent_pass, customer=MEERA)["allowed"]


def test_a_tampered_pass_is_refused(bench):
    _, consent_pass = bench.granted()
    head, body, sig = consent_pass.split(".")
    assert not bench.use(f"{head}.{body[:-2]}xx.{sig}")["allowed"]


def test_uses_run_out(bench):
    _, consent_pass = bench.granted(max_uses=2)
    assert bench.use(consent_pass)["allowed"] and bench.use(consent_pass)["allowed"]
    decision = bench.use(consent_pass)
    assert not decision["allowed"] and "used up" in decision["reason"]


def test_consent_expires(bench):
    _, consent_pass = bench.granted(minutes=5)
    bench.clock.advance(5 * 60 + 1)
    decision = bench.use(consent_pass)
    assert not decision["allowed"] and "expired" in decision["reason"]


def test_revoking_stops_the_voice_at_once(bench):
    asked, consent_pass = bench.granted()
    assert bench.use(consent_pass)["allowed"]
    bench.consents.revoke(asked["id"], RAHUL, bench.device(RAHUL))
    decision = bench.use(consent_pass)
    assert not decision["allowed"] and "revoked" in decision["reason"]
    assert bench.consents.mine(RAHUL, bench.device(RAHUL))["consents"][0]["status"] == "revoked"


def test_a_consent_pass_is_not_a_verification_receipt(bench):
    # Same token format, separate key: otherwise a pass would pass verify_receipt (it names no Call to check).
    _, consent_pass = bench.granted()
    assert bench.verifier.verify_receipt(consent_pass)["valid"] is False


def test_a_verification_receipt_is_not_a_consent_pass(bench):
    signer = ReceiptSigner.generate()
    consents = VoiceConsents(bench.db, SignalExtractor(bench.models), signer, clock=bench.clock)
    assert not consents.use(RAHUL, LAB, "security_test", "clone-1", signer.sign({"sub": RAHUL, "jti": "x"}))["allowed"]


def test_the_owner_sees_every_refused_attempt(bench):
    bench.consents.use(RAHUL, "Shady Ads Ltd", "advertising", "clone-1", None)
    refused = bench.consents.mine(RAHUL, bench.device(RAHUL))["refused"]
    assert refused[0]["requester"] == "Shady Ads Ltd" and "no Consent Pass" in refused[0]["reason"]


def test_the_ledger_is_a_tamper_evident_record_of_everything(bench):
    asked, consent_pass = bench.granted()
    bench.use(consent_pass)
    bench.use(None)
    bench.consents.revoke(asked["id"], RAHUL, bench.device(RAHUL))
    seen = bench.consents.overview()
    kinds = [e["kind"] for e in seen["ledger"]]
    assert kinds == ["consent_revoked", "voice_use_refused", "voice_use_allowed", "consent_granted", "consent_requested"]
    assert seen["ledger_intact"] is True


def test_overview_lists_what_can_be_asked_for(bench):
    assert {p["id"] for p in bench.consents.overview()["purposes"]} == set(PURPOSES)


def test_authorize_needs_only_the_pass(bench):
    _, consent_pass = bench.granted()
    assert bench.consents.authorize(consent_pass, LAB, "security_test", "line-1")["allowed"]
    assert not bench.consents.authorize("not.a.pass", LAB, "security_test", "line-1")["allowed"]
    assert not bench.consents.authorize("", LAB, "security_test", "line-1")["allowed"]


# -- over HTTP -------------------------------------------------------------------------------------


@pytest.fixture
def api(tmp_path):
    real, clone = tmp_path / "real.wav", tmp_path / "clone.wav"
    real.write_bytes(voiced().to_wav())
    clone.write_bytes(voiced(f0=180).to_wav())
    manifest = tmp_path / "manifest.csv"
    with manifest.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, ["phrase", "variant", "file"])
        w.writeheader()
        w.writerow({"phrase": "whispered line", "variant": "dsp-whisper", "file": str(clone)})
        w.writerow({"phrase": "a spoken line", "variant": "normal", "file": str(clone)})
    settings = Settings(
        _env_file=None, database_url=database_url(), speech_backend="scripted", tts_backend="tone",
        tts_cache_dir=str(tmp_path / "tts"), receipt_key_path=str(tmp_path / "key.pem"),
        consent_key_path=str(tmp_path / "consent.pem"), ollama_api_key="", warm_up_models=False,
        console_key="console-secret", clone_manifest=str(manifest), clone_reference=str(real),
    )
    models = ScriptedSpeechModels()
    with TestClient(create_app(container=build(settings, speech=models))) as client:
        client.models = models
        client.headers["X-Console-Key"] = "console-secret"
        yield client


def device(client, customer):
    return {"X-Device-Token": client.app.state.c.verifier.pairing(customer)}


def ask(client, customer=RAHUL, **kw):
    body = {"customer_id": customer, "requester": LAB, "purpose": "security_test", "minutes": 60, "max_uses": 3, **kw}
    r = client.post("/v1/voice-consents", json=body)
    assert r.status_code == 200, r.text
    return r.json()


def speak(client, asked, customer=RAHUL, audio=None):
    client.models.push(asked["statement"])
    return client.post(
        f"/v1/voice-consents/{asked['id']}/statement", headers=device(client, customer),
        data={"customer_id": customer}, files={"audio": ("statement.wav", (audio or voiced()).to_wav(), "audio/wav")},
    )


def test_the_whole_journey_over_http(api):
    asked = ask(api)
    mine = api.get(f"/v1/customers/{RAHUL}/voice", headers=device(api, RAHUL)).json()
    assert mine["consents"][0]["id"] == asked["id"]

    r = speak(api, asked)
    assert r.status_code == 200 and r.json()["granted"]
    seen = api.get("/v1/voice-consents").json()
    consent_pass = seen["consents"][0]["consent_pass"]
    clip = next(c["id"] for c in seen["clips"] if c["kind"] == "clone")

    use = {"customer_id": RAHUL, "requester": LAB, "purpose": "security_test", "clip": clip}
    assert api.post("/v1/voice-consents/use", json=use).status_code == 403  # no pass
    played = api.post("/v1/voice-consents/use", json={**use, "consent_pass": consent_pass})
    assert played.status_code == 200 and played.headers["content-type"] == "audio/wav" and played.content[:4] == b"RIFF"

    refused = api.post("/v1/voice-consents/use", json={**use, "consent_pass": consent_pass, "purpose": "advertising"})
    assert refused.status_code == 403 and "purpose" in refused.json()["detail"]

    r = api.post(f"/v1/voice-consents/{asked['id']}/revoke", headers=device(api, RAHUL), json={"customer_id": RAHUL})
    assert r.status_code == 200
    assert api.post("/v1/voice-consents/use", json={**use, "consent_pass": consent_pass}).status_code == 403


def test_a_real_statement_recording_fits_through_the_upload_guard(api):
    # The guard caps JSON at 64 KB: a 10 s recording is far larger, and this route must not need the agent's key.
    assert speak(api, ask(api), audio=voiced(seconds=10)).json()["granted"]


def test_staff_routes_need_the_console_key(api):
    api.headers["X-Console-Key"] = ""
    assert api.get("/v1/voice-consents").status_code == 403
    assert api.post("/v1/voice-consents/use", json={"customer_id": RAHUL, "requester": LAB, "purpose": "security_test",
                                                    "clip": "real"}).status_code == 403


def test_the_owners_routes_need_the_paired_phone(api):
    asked = ask(api)
    assert api.get(f"/v1/customers/{RAHUL}/voice", headers={"X-Device-Token": "x"}).status_code == 403
    assert api.post(f"/v1/voice-consents/{asked['id']}/revoke", headers={"X-Device-Token": "x"},
                    json={"customer_id": RAHUL}).status_code == 403


def test_an_unknown_clip_never_reads_a_file(api):
    speak(api, asked := ask(api))
    seen = api.get("/v1/voice-consents").json()
    body = {"customer_id": RAHUL, "requester": LAB, "purpose": "security_test", "clip": "../../.env",
            "consent_pass": seen["consents"][0]["consent_pass"]}
    assert api.post("/v1/voice-consents/use", json=body).status_code == 404
    uses = next(c for c in api.get("/v1/voice-consents").json()["consents"] if c["id"] == asked["id"])["uses"]
    assert uses == 0


def test_a_bad_request_is_a_clear_refusal(api):
    r = api.post("/v1/voice-consents", json={"customer_id": RAHUL, "requester": LAB, "purpose": "nope", "minutes": 60,
                                             "max_uses": 3})
    assert r.status_code == 409


def test_a_tool_with_a_pass_is_checked_without_the_console_key(api):
    speak(api, ask(api))
    consent_pass = api.get("/v1/voice-consents").json()["consents"][0]["consent_pass"]
    api.headers["X-Console-Key"] = ""
    body = {"consent_pass": consent_pass, "requester": LAB, "purpose": "security_test", "clip": "line"}
    assert api.post("/v1/voice-consents/authorize", json=body).json()["allowed"] is True
    assert api.post("/v1/voice-consents/authorize", json={**body, "purpose": "advertising"}).json()["allowed"] is False


def test_the_public_key_is_published(api):
    keys = api.get("/v1/voice-consents/key").json()["keys"]
    assert keys[0]["crv"] == "Ed25519"
    assert keys[0]["kid"] != api.get("/v1/receipts/key").json()["keys"][0]["kid"]
