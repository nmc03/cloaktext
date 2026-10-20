"""Persistencia local de la clave de restauración de CloakText.

La clave (`cloaktext.json`) relaciona marcadores con valores originales. Puede
guardarse en claro (formato histórico, un objeto JSON plano) o cifrada con una
contraseña (AES-256-GCM, clave derivada con scrypt). Ambos formatos conviven:
`load_key` detecta cuál es y las claves antiguas siguen funcionando.

Junto a la clave se guarda un archivo auxiliar `cloaktext.dates.json` con la
fecha de alta de cada marcador (sin valores sensibles) para poder limpiar
entradas antiguas.
"""

from __future__ import annotations

import base64
from datetime import date, timedelta
import hashlib
import json
import os
from pathlib import Path
import secrets
import sys
import tempfile

from i18n import tr

DEFAULT_KEY_FILENAME = "cloaktext.json"
DATES_FILENAME = "cloaktext.dates.json"
MAX_KEY_BYTES = 10 * 1024 * 1024

ENCRYPTED_FORMAT = "cloaktext-key"
ENCRYPTED_VERSION = 1
SCRYPT_N = 2**15
SCRYPT_R = 8
SCRYPT_P = 1
MIN_PASSWORD_LENGTH = 8


class KeyEncryptedError(ValueError):
    """La clave está cifrada y no se ha facilitado contraseña."""


class WrongPasswordError(ValueError):
    """La contraseña no es correcta o el archivo cifrado está dañado."""


def _is_writable(directory: Path) -> bool:
    try:
        directory.mkdir(parents=True, exist_ok=True)
        fd, name = tempfile.mkstemp(prefix=".cloaktext-write-test.", dir=directory)
        os.close(fd)
        Path(name).unlink(missing_ok=True)
        return True
    except OSError:
        return False


def fallback_directory() -> Path:
    """Carpeta de usuario con permisos de escritura para datos de CloakText."""
    if sys.platform == "win32":
        base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
        return Path(base) / "CloakText"
    base = os.environ.get("XDG_DATA_HOME") or str(Path.home() / ".local" / "share")
    return Path(base) / "cloaktext"


def application_directory() -> Path:
    """Carpeta de datos: junto al EXE empaquetado o al código en desarrollo.

    Si esa carpeta no admite escritura (p. ej. se descomprimió en Program Files)
    se usa una carpeta del perfil del usuario. CLOAKTEXT_APP_DIR fuerza una ruta.
    """
    override = os.environ.get("CLOAKTEXT_APP_DIR")
    if override:
        return Path(override).expanduser().resolve()
    if getattr(sys, "frozen", False):
        portable = Path(sys.executable).resolve().parent
    else:
        portable = Path(__file__).resolve().parent
    if _is_writable(portable):
        return portable
    return fallback_directory()


def using_fallback_directory() -> bool:
    """True si los datos viven en la carpeta del perfil y no junto a la aplicación."""
    return not os.environ.get("CLOAKTEXT_APP_DIR") and application_directory() == fallback_directory()


def default_key_path() -> Path:
    return application_directory() / DEFAULT_KEY_FILENAME


def dates_path(key_path: Path | None = None) -> Path:
    return (key_path or default_key_path()).with_name(DATES_FILENAME)


# --- cifrado ---------------------------------------------------------------


def _derive(password: str, salt: bytes, n: int, r: int, p: int) -> bytes:
    return hashlib.scrypt(
        password.encode("utf-8"),
        salt=salt,
        n=n,
        r=r,
        p=p,
        maxmem=256 * 1024 * 1024,
        dklen=32,
    )


def encrypt_key(data: dict[str, str], password: str) -> dict:
    """Devuelve el sobre JSON cifrado de `data`."""
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    if len(password) < MIN_PASSWORD_LENGTH:
        raise ValueError(tr("err.pw_short", n=MIN_PASSWORD_LENGTH))
    salt = secrets.token_bytes(16)
    nonce = secrets.token_bytes(12)
    header = {
        "format": ENCRYPTED_FORMAT,
        "version": ENCRYPTED_VERSION,
        "kdf": "scrypt",
        "n": SCRYPT_N,
        "r": SCRYPT_R,
        "p": SCRYPT_P,
        "salt": base64.b64encode(salt).decode("ascii"),
        "nonce": base64.b64encode(nonce).decode("ascii"),
    }
    plaintext = json.dumps(data, ensure_ascii=False).encode("utf-8")
    aad = _associated_data(header)
    ciphertext = AESGCM(_derive(password, salt, SCRYPT_N, SCRYPT_R, SCRYPT_P)).encrypt(
        nonce, plaintext, aad
    )
    return {**header, "ciphertext": base64.b64encode(ciphertext).decode("ascii")}


def _associated_data(header: dict) -> bytes:
    """Cabecera autenticada: modificarla invalida el descifrado."""
    return json.dumps(
        {k: header[k] for k in ("format", "version", "kdf", "n", "r", "p")},
        sort_keys=True,
        separators=(",", ":"),
    ).encode("ascii")


def decrypt_key(envelope: dict, password: str) -> dict[str, str]:
    from cryptography.exceptions import InvalidTag
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    try:
        if envelope.get("version") != ENCRYPTED_VERSION or envelope.get("kdf") != "scrypt":
            raise ValueError(tr("err.enc_format"))
        n, r, p = int(envelope["n"]), int(envelope["r"]), int(envelope["p"])
        if not (2**14 <= n <= 2**20 and n & (n - 1) == 0 and 1 <= r <= 16 and 1 <= p <= 4):
            raise ValueError(tr("err.enc_params"))
        salt = base64.b64decode(envelope["salt"], validate=True)
        nonce = base64.b64decode(envelope["nonce"], validate=True)
        ciphertext = base64.b64decode(envelope["ciphertext"], validate=True)
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError(tr("err.enc_damaged")) from exc

    try:
        plaintext = AESGCM(_derive(password, salt, n, r, p)).decrypt(
            nonce, ciphertext, _associated_data(envelope)
        )
    except InvalidTag as exc:
        raise WrongPasswordError(tr("pw.error_wrong")) from exc

    data = json.loads(plaintext.decode("utf-8"))
    if not isinstance(data, dict):
        raise ValueError(tr("err.key_object"))
    return data


def is_encrypted_envelope(data: object) -> bool:
    return isinstance(data, dict) and data.get("format") == ENCRYPTED_FORMAT


def _read_json(path: Path) -> object:
    if not path.is_file():
        raise ValueError(tr("err.not_file", name=path.name))
    if path.stat().st_size > MAX_KEY_BYTES:
        raise ValueError(tr("err.key_too_big"))
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except UnicodeDecodeError as exc:
        raise ValueError(tr("err.key_utf8")) from exc
    except json.JSONDecodeError as exc:
        raise ValueError(tr("err.key_json")) from exc


def is_encrypted(path: Path | None = None) -> bool:
    path = path or default_key_path()
    if not path.exists():
        return False
    try:
        return is_encrypted_envelope(_read_json(path))
    except ValueError:
        return False


def load_key(path: Path | None = None, password: str | None = None) -> dict[str, str]:
    path = path or default_key_path()
    if not path.exists():
        return {}
    data = _read_json(path)
    if is_encrypted_envelope(data):
        if password is None:
            raise KeyEncryptedError(tr("pw.needs_unlock"))
        return decrypt_key(data, password)
    if not isinstance(data, dict):
        raise ValueError(tr("err.key_object"))
    return data


def save_key_atomic(
    data: dict[str, str],
    path: Path | None = None,
    password: str | None = None,
) -> Path:
    """Guarda JSON UTF-8 de forma atómica para no dejar una clave parcial.

    Con `password` el contenido se cifra; sin ella se guarda en claro.
    """
    path = path or default_key_path()
    path.parent.mkdir(parents=True, exist_ok=True)

    payload_obj = encrypt_key(data, password) if password else data
    payload = json.dumps(payload_obj, ensure_ascii=False, indent=2) + "\n"
    _write_atomic(path, payload.encode("utf-8"))
    return path


def _write_atomic(path: Path, encoded: bytes) -> None:
    if len(encoded) > MAX_KEY_BYTES:
        raise ValueError(tr("err.key_too_big"))

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


# --- fechas de alta y limpieza de entradas antiguas --------------------------


def load_dates(path: Path | None = None) -> dict[str, str]:
    """Fechas ISO (AAAA-MM-DD) por marcador. Tolera archivo ausente o dañado."""
    path = path or dates_path()
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        return {}
    if not isinstance(data, dict):
        return {}
    return {k: v for k, v in data.items() if isinstance(k, str) and isinstance(v, str)}


def save_dates(dates: dict[str, str], path: Path | None = None) -> None:
    path = path or dates_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    _write_atomic(path, (json.dumps(dates, indent=2, sort_keys=True) + "\n").encode("utf-8"))


def stamp_tokens(
    mapa: dict[str, str],
    dates: dict[str, str],
    today: date | None = None,
) -> dict[str, str]:
    """Devuelve `dates` sin marcadores huérfanos y con fecha para los nuevos.

    Las entradas heredadas (sin fecha) envejecen desde la primera vez que se ven.
    """
    hoy = (today or date.today()).isoformat()
    return {token: dates.get(token, hoy) for token in mapa}


def find_older_than(
    dates: dict[str, str],
    days: int,
    today: date | None = None,
) -> set[str]:
    limite = (today or date.today()) - timedelta(days=max(0, days))
    antiguos: set[str] = set()
    for token, valor in dates.items():
        try:
            if date.fromisoformat(valor) < limite:
                antiguos.add(token)
        except ValueError:
            continue
    return antiguos


def purge(
    mapa: dict[str, str],
    dates: dict[str, str],
    tokens: set[str],
) -> tuple[dict[str, str], dict[str, str]]:
    return (
        {t: v for t, v in mapa.items() if t not in tokens},
        {t: d for t, d in dates.items() if t not in tokens},
    )


# --- preferencias de la interfaz ---------------------------------------------

SETTINGS_FILENAME = "cloaktext.settings.json"


def settings_path() -> Path:
    return application_directory() / SETTINGS_FILENAME


def load_settings() -> dict:
    """Preferencias no sensibles (p. ej. idioma de la interfaz). Nunca lanza."""
    try:
        data = json.loads(settings_path().read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def save_settings(settings: dict) -> None:
    try:
        _write_atomic(settings_path(), (json.dumps(settings, indent=2) + "\n").encode("utf-8"))
    except OSError:
        pass
