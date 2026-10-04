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
    from language_models import directorio_modelos

    monkeypatch.setenv("CLOAKTEXT_APP_DIR", str(tmp_path))
    monkeypatch.delenv("CLOAKTEXT_DATA_DIR", raising=False)

    assert directorio_modelos() == tmp_path.resolve() / "models"


def test_models_data_override_is_only_for_test_and_dev(tmp_path, monkeypatch):
    from language_models import directorio_modelos

    override = tmp_path / "isolated-data"
    monkeypatch.setenv("CLOAKTEXT_DATA_DIR", str(override))

    assert directorio_modelos() == override.resolve() / "models"
