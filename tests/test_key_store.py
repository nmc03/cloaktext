import json
from pathlib import Path

import pytest

from key_store import default_key_path, load_key, save_key_atomic


def test_default_key_lives_in_application_directory(tmp_path, monkeypatch):
    monkeypatch.setenv("CLOAKTEXT_APP_DIR", str(tmp_path))
    assert default_key_path() == tmp_path.resolve() / "cloaktext.json"


def test_key_roundtrip_is_utf8_and_persistent(tmp_path, monkeypatch):
    monkeypatch.setenv("CLOAKTEXT_APP_DIR", str(tmp_path))
    original = {"[PERSONA_1000]": "María", "[LUGAR_1001]": "Madrid"}

    path = save_key_atomic(original)

    assert path == tmp_path.resolve() / "cloaktext.json"
    assert load_key() == original
    assert "María" in path.read_text(encoding="utf-8")


def test_missing_default_key_is_empty(tmp_path, monkeypatch):
    monkeypatch.setenv("CLOAKTEXT_APP_DIR", str(tmp_path))
    assert load_key() == {}


def test_invalid_key_is_rejected(tmp_path):
    path = tmp_path / "bad.json"
    path.write_text("[]", encoding="utf-8")
    with pytest.raises(ValueError, match="objeto"):
        load_key(path)


def test_models_live_next_to_portable_app(tmp_path, monkeypatch):
    from language_packs import models_directory

    monkeypatch.setenv("CLOAKTEXT_APP_DIR", str(tmp_path))
    monkeypatch.delenv("CLOAKTEXT_DATA_DIR", raising=False)

    assert models_directory() == tmp_path.resolve() / "models"


def test_models_data_override_is_only_for_test_and_dev(tmp_path, monkeypatch):
    from language_packs import models_directory

    override = tmp_path / "isolated-data"
    monkeypatch.setenv("CLOAKTEXT_DATA_DIR", str(override))

    assert models_directory() == override.resolve() / "models"


# --- password encryption ---

from datetime import date  # noqa: E402

import key_store  # noqa: E402


def test_encrypted_key_roundtrip_and_no_plaintext_on_disk(tmp_path):
    path = tmp_path / "k.json"
    data = {"[PERSONA_1000]": "María Pérez", "[EMAIL_1001]": "ana@example.com"}

    key_store.save_key_atomic(data, path, password="correct horse")

    raw = path.read_text(encoding="utf-8")
    assert "María" not in raw and "ana@example.com" not in raw
    assert key_store.is_encrypted(path)
    assert key_store.load_key(path, password="correct horse") == data


def test_encrypted_key_requires_password(tmp_path):
    path = tmp_path / "k.json"
    key_store.save_key_atomic({"[EMAIL_1000]": "a@b.co"}, path, password="correct horse")

    with pytest.raises(key_store.KeyEncryptedError):
        key_store.load_key(path)
    with pytest.raises(key_store.WrongPasswordError):
        key_store.load_key(path, password="wrong password")


def test_encrypted_key_detects_tampering(tmp_path):
    path = tmp_path / "k.json"
    key_store.save_key_atomic({"[EMAIL_1000]": "a@b.co"}, path, password="correct horse")
    envelope = json.loads(path.read_text(encoding="utf-8"))
    envelope["ciphertext"] = envelope["ciphertext"][:-8] + "AAAAAAA="
    path.write_text(json.dumps(envelope), encoding="utf-8")

    with pytest.raises(ValueError):
        key_store.load_key(path, password="correct horse")


def test_encrypted_key_rejects_abusive_kdf_parameters(tmp_path):
    envelope = key_store.encrypt_key({"[EMAIL_1000]": "a@b.co"}, "correct horse")
    envelope["n"] = 2**30  # would exhaust memory
    with pytest.raises(ValueError):
        key_store.decrypt_key(envelope, "correct horse")


def test_short_password_is_rejected(tmp_path):
    with pytest.raises(ValueError):
        key_store.save_key_atomic({}, tmp_path / "k.json", password="short")


def test_plain_legacy_key_still_loads_with_or_without_password(tmp_path):
    path = tmp_path / "k.json"
    key_store.save_key_atomic({"[EMAIL_1000]": "a@b.co"}, path)
    assert key_store.is_encrypted(path) is False
    assert key_store.load_key(path, password="ignored") == {"[EMAIL_1000]": "a@b.co"}


# --- fallback folder ---


def test_falls_back_to_user_profile_when_app_dir_not_writable(tmp_path, monkeypatch):
    monkeypatch.delenv("CLOAKTEXT_APP_DIR", raising=False)
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    monkeypatch.setattr(key_store, "_is_writable", lambda directory: False)

    assert key_store.application_directory() == key_store.fallback_directory()
    assert tmp_path in key_store.fallback_directory().parents


# --- dates and cleanup ---


def test_stamp_new_tokens_and_drop_orphans():
    mapping = {"[EMAIL_1000]": "a", "[EMAIL_1001]": "b"}
    dates = {"[EMAIL_1000]": "2026-01-01", "[PERSONA_1002]": "2026-01-01"}

    result = key_store.stamp_tokens(mapping, dates, today=date(2026, 10, 20))

    assert result == {"[EMAIL_1000]": "2026-01-01", "[EMAIL_1001]": "2026-10-20"}


def test_find_older_than_and_purge():
    mapping = {"[EMAIL_1000]": "a", "[EMAIL_1001]": "b"}
    dates = {"[EMAIL_1000]": "2026-08-01", "[EMAIL_1001]": "2026-10-19"}

    old_tokens = key_store.find_older_than(dates, 30, today=date(2026, 10, 20))
    new_mapping, new_dates = key_store.purge(mapping, dates, old_tokens)

    assert old_tokens == {"[EMAIL_1000]"}
    assert new_mapping == {"[EMAIL_1001]": "b"}
    assert new_dates == {"[EMAIL_1001]": "2026-10-19"}


def test_dates_file_roundtrip_and_tolerates_garbage(tmp_path):
    path = tmp_path / "d.json"
    assert key_store.load_dates(path) == {}
    key_store.save_dates({"[EMAIL_1000]": "2026-10-20"}, path)
    assert key_store.load_dates(path) == {"[EMAIL_1000]": "2026-10-20"}
    path.write_text("not json", encoding="utf-8")
    assert key_store.load_dates(path) == {}
