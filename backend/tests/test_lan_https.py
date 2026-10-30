import importlib.util
import ipaddress
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives.asymmetric import padding

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "lan_https.py"


def load(tmp_path, monkeypatch):
    spec = importlib.util.spec_from_file_location("lan_https", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    for name, path in [("KEYS", tmp_path), ("CA_KEY", tmp_path / "ca.key"), ("CA_CRT", tmp_path / "ca.crt"),
                       ("SERVER_KEY", tmp_path / "s.key"), ("SERVER_CRT", tmp_path / "s.crt"),
                       ("PUBLIC_CA", tmp_path / "public" / "ca.crt")]:
        monkeypatch.setattr(mod, name, path)
    return mod


def test_a_phone_that_trusts_the_ca_accepts_the_lan_certificate(tmp_path, monkeypatch):
    mod = load(tmp_path, monkeypatch)
    mod.issue("172.16.0.124")
    ca = x509.load_pem_x509_certificate((tmp_path / "ca.crt").read_bytes())
    server = x509.load_pem_x509_certificates((tmp_path / "s.crt").read_bytes())[0]  # leaf, then the CA

    ca.public_key().verify(server.signature, server.tbs_certificate_bytes, padding.PKCS1v15(),
                           server.signature_hash_algorithm)
    sans = server.extensions.get_extension_for_class(x509.SubjectAlternativeName).value
    assert ipaddress.ip_address("172.16.0.124") in sans.get_values_for_type(x509.IPAddress)
    assert "localhost" in sans.get_values_for_type(x509.DNSName)
    assert (server.not_valid_after_utc - server.not_valid_before_utc).days <= 825  # Apple's limit
    assert x509.load_der_x509_certificate((tmp_path / "public" / "ca.crt").read_bytes()) == ca


def test_a_new_venue_ip_reuses_the_ca_the_phone_already_trusts(tmp_path, monkeypatch):
    mod = load(tmp_path, monkeypatch)
    mod.issue("172.16.0.124")
    first_ca = (tmp_path / "ca.crt").read_bytes()
    mod.issue("10.0.0.5")
    assert (tmp_path / "ca.crt").read_bytes() == first_ca
    server = x509.load_pem_x509_certificates((tmp_path / "s.crt").read_bytes())[0]
    sans = server.extensions.get_extension_for_class(x509.SubjectAlternativeName).value
    assert ipaddress.ip_address("10.0.0.5") in sans.get_values_for_type(x509.IPAddress)
