"""HTTPS on the demo LAN, so phones (iPhones above all) may use the microphone.

Browsers allow the microphone only on HTTPS or localhost. This makes a small certificate
authority once (data/keys/lan-ca.*, git-ignored) and, on every run, a server certificate for the
current LAN IP signed by it (data/keys/lan-https.*). Install the CA on each phone once; a new
venue IP then needs only a new server certificate, which start.ps1 makes by running this.

  python scripts/lan_https.py 172.16.0.124        # -> data/keys/lan-https.{crt,key}

The CA certificate (public, not secret) is also copied to web/public/pratyaksh-ca.crt, so a
phone can download it from https://<LAN IP>:5173/pratyaksh-ca.crt.
"""

from __future__ import annotations

import datetime as dt
import ipaddress
import sys
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID

ROOT = Path(__file__).resolve().parent.parent
KEYS = ROOT / "data" / "keys"
CA_KEY, CA_CRT = KEYS / "lan-ca.key", KEYS / "lan-ca.crt"
SERVER_KEY, SERVER_CRT = KEYS / "lan-https.key", KEYS / "lan-https.crt"
PUBLIC_CA = ROOT / "web" / "public" / "pratyaksh-ca.crt"


def _key() -> rsa.RSAPrivateKey:
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)  # iOS needs >= 2048-bit RSA


def _write_key(path: Path, key: rsa.RSAPrivateKey) -> None:
    path.write_bytes(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.TraditionalOpenSSL,
                                       serialization.NoEncryption()))


def ensure_ca() -> tuple[rsa.RSAPrivateKey, x509.Certificate]:
    if CA_KEY.exists() and CA_CRT.exists():
        key = serialization.load_pem_private_key(CA_KEY.read_bytes(), password=None)
        return key, x509.load_pem_x509_certificate(CA_CRT.read_bytes())
    key = _key()
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "Pratyaksh demo LAN CA"),
                      x509.NameAttribute(NameOID.ORGANIZATION_NAME, "Team Omnitrons")])
    now = dt.datetime.now(dt.timezone.utc)
    crt = (
        x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - dt.timedelta(days=1)).not_valid_after(now + dt.timedelta(days=730))
        .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
        .add_extension(x509.KeyUsage(digital_signature=True, key_cert_sign=True, crl_sign=True, content_commitment=False,
                                     key_encipherment=False, data_encipherment=False, key_agreement=False,
                                     encipher_only=False, decipher_only=False), critical=True)
        .add_extension(x509.SubjectKeyIdentifier.from_public_key(key.public_key()), critical=False)
        .sign(key, hashes.SHA256())
    )
    KEYS.mkdir(parents=True, exist_ok=True)
    _write_key(CA_KEY, key)
    CA_CRT.write_bytes(crt.public_bytes(serialization.Encoding.PEM))
    return key, crt


def issue(ip: str) -> None:
    ca_key, ca_crt = ensure_ca()
    key = _key()
    now = dt.datetime.now(dt.timezone.utc)
    sans = [x509.IPAddress(ipaddress.ip_address(ip)), x509.IPAddress(ipaddress.ip_address("127.0.0.1")),
            x509.DNSName("localhost")]
    crt = (
        x509.CertificateBuilder()
        .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, ip)]))
        .issuer_name(ca_crt.subject).public_key(key.public_key()).serial_number(x509.random_serial_number())
        # Apple rejects server certificates valid for more than 825 days (398 for public CAs).
        .not_valid_before(now - dt.timedelta(days=1)).not_valid_after(now + dt.timedelta(days=365))
        .add_extension(x509.SubjectAlternativeName(sans), critical=False)
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
        .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]), critical=False)
        .add_extension(x509.AuthorityKeyIdentifier.from_issuer_public_key(ca_key.public_key()), critical=False)
        .sign(ca_key, hashes.SHA256())
    )
    _write_key(SERVER_KEY, key)
    SERVER_CRT.write_bytes(crt.public_bytes(serialization.Encoding.PEM) + ca_crt.public_bytes(serialization.Encoding.PEM))
    PUBLIC_CA.parent.mkdir(parents=True, exist_ok=True)
    PUBLIC_CA.write_bytes(ca_crt.public_bytes(serialization.Encoding.DER))  # iOS installs DER .crt as a profile


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit("usage: python scripts/lan_https.py <LAN IP>")
    issue(sys.argv[1])
    print(f"HTTPS certificate for {sys.argv[1]}, localhost: {SERVER_CRT.relative_to(ROOT)}")
