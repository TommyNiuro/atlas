#!/usr/bin/env python3
"""Instalacion multiplataforma de Atlas (macOS y Windows).

Detecta el sistema, instala dependencias, genera la llave Fernet en el
almacen nativo de credenciales (Keychain / Credential Locker) y deja el
stack listo para `task dev`.
"""
import platform
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def run(cmd: list[str], cwd: Path = ROOT) -> None:
    print(f"$ {' '.join(cmd)}")
    subprocess.check_call(cmd, cwd=cwd)


def main() -> None:
    so = platform.system()
    print(f"Sistema detectado: {so} ({platform.machine()})")

    # cifrado de disco: sin FileVault los correos y tokens quedan legibles en disco
    if so == "Darwin":
        estado = subprocess.run(["fdesetup", "status"], capture_output=True, text=True).stdout
        if "On" not in estado:
            print("⚠️  FileVault APAGADO: tus datos quedarían sin cifrar. Actívalo en")
            print("   Ajustes > Privacidad y seguridad > FileVault antes de usar datos reales.")

    faltan = [t for t in ("uv", "pnpm", "docker") if not shutil.which(t)]
    if faltan:
        print(f"Faltan herramientas: {', '.join(faltan)}")
        if so == "Darwin":
            print("Instala con: brew install uv pnpm orbstack go-task")
        else:
            print("Instala con: winget install astral-sh.uv pnpm.pnpm Docker.DockerDesktop Task.Task")
        sys.exit(1)

    # .env
    env = ROOT / ".env"
    if not env.exists():
        shutil.copy(ROOT / ".env.example", env)
        print("Creado .env (completa ANTHROPIC_API_KEY y VOYAGE_API_KEY)")

    # dependencias
    run(["uv", "sync"], cwd=ROOT / "apps" / "api")
    run(["pnpm", "install"], cwd=ROOT / "apps" / "web")

    # llave Fernet en el almacen nativo, nunca en .env
    run([
        "uv", "run", "python", "-c",
        "import keyring; from cryptography.fernet import Fernet; "
        "keyring.get_password('atlas','fernet-key') or "
        "keyring.set_password('atlas','fernet-key', Fernet.generate_key().decode()); "
        "print('Llave Fernet lista en el almacen del sistema')",
    ], cwd=ROOT / "apps" / "api")

    # migraciones: llegan con el Bloque 1 (Alembic)
    print("\nListo. Levanta el stack con: task dev")


if __name__ == "__main__":
    main()
