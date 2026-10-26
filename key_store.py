"""Local persistence of the CloakText restore key.

The key file (`cloaktext.json`) maps tokens to original values. It can be
stored in plain text (the historical format, a flat JSON object) or encrypted
with a password (AES-256-GCM, key derived with scrypt). Both formats coexist:
`load_key` detects which one is used, and older keys keep working.

Next to the key, an auxiliary file `cloaktext.dates.json` stores the date each
token was added (no sensitive values), so old entries can be purged.
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
    """The key is encrypted and no password was provided."""


class WrongPasswordError(ValueError):
    """The password is incorrect or the encrypted file is damaged."""


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
    """User folder with write permission for CloakText data."""
    if sys.platform == "win32":
        base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
        return Path(base) / "CloakText"
    base = os.environ.get("XDG_DATA_HOME") or str(Path.home() / ".local" / "share")
    return Path(base) / "cloaktext"


def application_directory() -> Path:
    """Data folder: next to the packaged EXE or the source code in development.

    If that folder is not writable (e.g. it was extracted to Program Files),
    a folder in the user's profile is used. CLOAKTEXT_APP_DIR forces a path.
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
    """True if the data lives in the profile folder instead of next to the application."""
    return not os.environ.get("CLOAKTEXT_APP_DIR") and application_directory() == fallback_directory()


def default_key_path() -> Path:
    return application_directory() / DEFAULT_KEY_FILENAME


def dates_path(key_path: Path | None = None) -> Path:
    return (key_path or default_key_path()).with_name(DATES_FILENAME)


# --- encryption ------------------------------------------------------------


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
    """Return the encrypted JSON envelope for `data`."""
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
    """Authenticated header: modifying it invalidates decryption."""
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
    """Save UTF-8 JSON atomically so a partial key is never left behind.

    With `password` the content is encrypted; without it, it is stored in plain text.
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


# --- creation dates and cleanup of old entries -------------------------------


def load_dates(path: Path | None = None) -> dict[str, str]:
    """ISO dates (YYYY-MM-DD) per token. Tolerates a missing or damaged file."""
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
    mapping: dict[str, str],
    dates: dict[str, str],
    today: date | None = None,
) -> dict[str, str]:
    """Return `dates` without orphaned tokens and with a date for new ones.

    Legacy entries (no date) age from the first time they are seen.
    """
    today_iso = (today or date.today()).isoformat()
    return {token: dates.get(token, today_iso) for token in mapping}


def find_older_than(
    dates: dict[str, str],
    days: int,
    today: date | None = None,
) -> set[str]:
    limit = (today or date.today()) - timedelta(days=max(0, days))
    old_tokens: set[str] = set()
    for token, value in dates.items():
        try:
            if date.fromisoformat(value) < limit:
                old_tokens.add(token)
        except ValueError:
            continue
    return old_tokens


def purge(
    mapping: dict[str, str],
    dates: dict[str, str],
    tokens: set[str],
) -> tuple[dict[str, str], dict[str, str]]:
    return (
        {t: v for t, v in mapping.items() if t not in tokens},
        {t: d for t, d in dates.items() if t not in tokens},
    )


# --- interface preferences ---------------------------------------------------

SETTINGS_FILENAME = "cloaktext.settings.json"


def settings_path() -> Path:
    return application_directory() / SETTINGS_FILENAME


def load_settings() -> dict:
    """Non-sensitive preferences (e.g. interface language). Never raises."""
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
