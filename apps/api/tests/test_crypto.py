from cryptography.fernet import Fernet

from atlas.core import crypto


def test_roundtrip_y_columna_ilegible():
    f = Fernet(Fernet.generate_key())
    token = crypto.encrypt("secreto-oauth", f)
    assert token != "secreto-oauth"
    assert "secreto" not in token
    assert crypto.decrypt(token, f) == "secreto-oauth"
