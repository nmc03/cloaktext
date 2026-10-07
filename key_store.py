"""Persistencia local de la clave de restauración de CloakText."""

from __future__ import annotations

import json
import os
from pathlib import Path
import sys
import tempfile


DEFAULT_KEY_FILENAME = "cloaktext.json"
MAX_KEY_BYTES = 10 * 1024 * 1024


def application_directory() -> Path:
    """Carpeta de la aplicación: junto al EXE empaquetado o al código en desarrollo."""
    override = os.environ.get("CLOAKTEXT_APP_DIR")
    if override:
        return Path(override).expanduser().resolve()
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def default_key_path() -> Path:
    return application_directory() / DEFAULT_KEY_FILENAME


def load_key(path: Path | None = None) -> dict[str, str]:
    path = path or default_key_path()
    if not path.exists():
        return {}
    if not path.is_file():
        raise ValueError(f"La clave predeterminada no es un archivo: {path.name}")
    if path.stat().st_size > MAX_KEY_BYTES:
        raise ValueError("La clave supera el límite de 10 MB.")

    try:
        raw = path.read_text(encoding="utf-8-sig")
        data = json.loads(raw)
    except UnicodeDecodeError as exc:
        raise ValueError("La clave JSON no está codificada en UTF-8.") from exc
    except json.JSONDecodeError as exc:
        raise ValueError("La clave JSON no contiene un JSON válido.") from exc

    if not isinstance(data, dict):
        raise ValueError("La clave JSON debe contener un objeto.")
    return data


def save_key_atomic(data: dict[str, str], path: Path | None = None) -> Path:
    """Guarda JSON UTF-8 de forma atómica para no dejar una clave parcial."""
    path = path or default_key_path()
    path.parent.mkdir(parents=True, exist_ok=True)

    payload = json.dumps(data, ensure_ascii=False, indent=2) + "\n"
    encoded = payload.encode("utf-8")
    if len(encoded) > MAX_KEY_BYTES:
        raise ValueError("La clave supera el límite de 10 MB.")

    fd, tmp_name = tempfile.mkstemp(
        prefix=f".{path.name}.",
        suffix=".tmp",
        dir=path.parent,
    )
    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
        try:
            os.chmod(tmp_path, 0o600)
        except OSError:
            pass
        os.replace(tmp_path, path)
        try:
            os.chmod(path, 0o600)
        except OSError:
            pass
    finally:
        tmp_path.unlink(missing_ok=True)

    return path
