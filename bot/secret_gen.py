import os
from config import TLS_DOMAIN


def generate_raw_secret() -> str:
    """Raw 16-byte hex secret for telemt API."""
    return os.urandom(16).hex()


def make_tls_link_secret(raw_secret: str) -> str:
    """Full FakeTLS secret for tg://proxy link: ee + raw + hex(domain)."""
    domain_hex = TLS_DOMAIN.encode().hex()
    return "ee" + raw_secret + domain_hex
