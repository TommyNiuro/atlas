"""Cifrado de tokens OAuth con Fernet.

La llave maestra vive en el almacen nativo del sistema (Keychain en macOS,
Credential Locker en Windows) via keyring; la genera scripts/setup.py.
ATLAS_FERNET_KEY existe solo para contenedores y CI, donde no hay almacen
nativo. Nunca va en .env de un escritorio.
"""
import os

from cryptography.fernet import Fernet

SERVICE = "atlas"
KEY_NAME = "fernet-key"


def get_fernet() -> Fernet:
    key = os.environ.get("ATLAS_FERNET_KEY")
    if not key:
        import keyring

        key = keyring.get_password(SERVICE, KEY_NAME)
    if not key:
        raise RuntimeError(
            "Sin llave Fernet. Corre `python3 scripts/setup.py` (escritorio) "
            "o define ATLAS_FERNET_KEY (contenedor/CI)."
        )
    return Fernet(key)


def encrypt(value: str, f: Fernet | None = None) -> str:
    return (f or get_fernet()).encrypt(value.encode()).decode()


def decrypt(token: str, f: Fernet | None = None) -> str:
    return (f or get_fernet()).decrypt(token.encode()).decode()
