"""Exercise UI dialog callbacks with isolated storage and no spaCy models."""

import asyncio
from datetime import date
import json
from types import SimpleNamespace

import flet as ft
import pytest

import i18n
import key_store
from test_ui_smoke import _create_app


PASSWORD = "fictional password"
NEW_PASSWORD = "another fictional password"
MAPPING = {"[PERSONA_1000]": "Mira Example"}


class FakeEngine:
    def __init__(self):
        self.validated = []

    @staticmethod
    def model_available(_language):
        return False

    def validate_mapping(self, mapping):
        assert isinstance(mapping, dict)
        assert all(isinstance(value, str) for value in mapping.values())
        self.validated.append(mapping.copy())

    @staticmethod
    def protect(text, mapping, filters, language, terms=None):
        for token, value in mapping.items():
            text = text.replace(value, token)
        return text

    @staticmethod
    def restore(text, mapping):
        for token, value in mapping.items():
            text = text.replace(token, value)
        return text


@pytest.fixture
def make_app(tmp_path, monkeypatch):
    monkeypatch.setenv("CLOAKTEXT_APP_DIR", str(tmp_path))

    def create(password=None):
        key_store.save_key_atomic(MAPPING, password=password)
        page, app = _create_app(tmp_path, monkeypatch)
        app.engine = FakeEngine()
        assert app.default_key_file == tmp_path / "cloaktext.json"
        return page, app

    return create


def password_controls(page):
    dialog = page.dialogs[-1]
    assert isinstance(dialog, ft.AlertDialog)
    fields = [control for control in dialog.content.controls if isinstance(control, ft.TextField)]
    return dialog, fields


def submit_password(page, password, repeat=None):
    dialog, fields = password_controls(page)
    fields[0].value = password
    if repeat is not None:
        fields[1].value = repeat
    asyncio.run(dialog.actions[1].on_click(None))
    return fields


def unlock(page):
    submit_password(page, PASSWORD)


def test_set_password_rejects_short_value(make_app, tmp_path):
    page, app = make_app()
    original = (tmp_path / "cloaktext.json").read_bytes()
    asyncio.run(app._on_set_password(None))

    fields = submit_password(page, "short", "short")

    assert fields[0].error == i18n.tr("pw.error_short", n=key_store.MIN_PASSWORD_LENGTH)
    assert page.pop_count == 0
    assert app._password is None
    assert (tmp_path / "cloaktext.json").read_bytes() == original


def test_set_password_rejects_mismatched_confirmation(make_app, tmp_path):
    page, app = make_app()
    original = (tmp_path / "cloaktext.json").read_bytes()
    asyncio.run(app._on_set_password(None))

    fields = submit_password(page, PASSWORD, NEW_PASSWORD)

    assert fields[1].error == i18n.tr("pw.error_mismatch")
    assert page.pop_count == 0
    assert app._password is None
    assert (tmp_path / "cloaktext.json").read_bytes() == original


def test_set_password_encrypts_existing_key(make_app, tmp_path):
    page, app = make_app()
    asyncio.run(app._on_set_password(None))

    fields = submit_password(page, PASSWORD, PASSWORD)

    assert all(field.error is None for field in fields)
    assert page.pop_count == 1
    assert app._password == PASSWORD
    payload = (tmp_path / "cloaktext.json").read_text(encoding="utf-8")
    assert key_store.is_encrypted_envelope(json.loads(payload))
    assert MAPPING["[PERSONA_1000]"] not in payload
    assert key_store.load_key(password=PASSWORD) == MAPPING
    with pytest.raises(key_store.KeyEncryptedError):
        key_store.load_key()


def test_set_password_cancel_preserves_plain_key(make_app, tmp_path):
    page, app = make_app()
    original = (tmp_path / "cloaktext.json").read_bytes()
    asyncio.run(app._on_set_password(None))
    dialog, fields = password_controls(page)
    fields[0].value = PASSWORD
    fields[1].value = PASSWORD

    dialog.actions[0].on_click(None)

    assert page.pop_count == 1
    assert app._password is None
    assert (tmp_path / "cloaktext.json").read_bytes() == original


def test_change_password_reencrypts_without_losing_entries(make_app):
    page, app = make_app(password=PASSWORD)
    unlock(page)
    asyncio.run(app._on_set_password(None))

    submit_password(page, NEW_PASSWORD, NEW_PASSWORD)

    assert app._password == NEW_PASSWORD
    assert page.pop_count == 2
    assert key_store.is_encrypted()
    assert key_store.load_key(password=NEW_PASSWORD) == MAPPING
    with pytest.raises(key_store.WrongPasswordError):
        key_store.load_key(password=PASSWORD)


def test_remove_password_confirmation_writes_plain_key(make_app, tmp_path):
    page, app = make_app(password=PASSWORD)
    unlock(page)
    app._on_remove_password(None)
    dialog = page.dialogs[-1]
    assert isinstance(dialog, ft.AlertDialog)
    assert dialog.actions[1].style.bgcolor == ft.Colors.ERROR
    assert app._password == PASSWORD
    assert key_store.is_encrypted()

    asyncio.run(dialog.actions[1].on_click(None))

    assert app._password is None
    assert page.pop_count == 2
    assert not key_store.is_encrypted()
    assert json.loads((tmp_path / "cloaktext.json").read_text(encoding="utf-8")) == MAPPING
    assert key_store.load_key() == MAPPING


def test_remove_password_cancel_preserves_encrypted_key(make_app, tmp_path):
    page, app = make_app(password=PASSWORD)
    unlock(page)
    original = (tmp_path / "cloaktext.json").read_bytes()
    app._on_remove_password(None)

    page.dialogs[-1].actions[0].on_click(None)

    assert app._password == PASSWORD
    assert page.pop_count == 2
    assert (tmp_path / "cloaktext.json").read_bytes() == original
    assert key_store.load_key(password=PASSWORD) == MAPPING


def test_unlock_wrong_password_keeps_key_locked(make_app, tmp_path):
    page, app = make_app(password=PASSWORD)
    original = (tmp_path / "cloaktext.json").read_bytes()
    assert app._key_locked

    fields = submit_password(page, NEW_PASSWORD)

    assert fields[0].error == i18n.tr("pw.error_wrong")
    assert page.pop_count == 0
    assert app._key_locked
    assert app._password is None
    assert app.engine.validated == []
    assert (tmp_path / "cloaktext.json").read_bytes() == original


def test_unlock_correct_password_loads_and_validates_key(make_app, tmp_path):
    page, app = make_app(password=PASSWORD)
    original = (tmp_path / "cloaktext.json").read_bytes()

    fields = submit_password(page, PASSWORD)

    assert fields[0].error is None
    assert not app._key_locked
    assert app._password == PASSWORD
    assert page.pop_count == 1
    assert app.engine.validated == [MAPPING]
    assert (tmp_path / "cloaktext.json").read_bytes() == original
    assert key_store.load_key(password=app._password) == MAPPING


def test_unlock_cancel_keeps_key_locked(make_app, tmp_path):
    page, app = make_app(password=PASSWORD)
    original = (tmp_path / "cloaktext.json").read_bytes()

    page.dialogs[-1].actions[0].on_click(None)

    assert app._key_locked
    assert app._password is None
    assert page.pop_count == 1
    assert (tmp_path / "cloaktext.json").read_bytes() == original


@pytest.fixture
def cleanup_app(make_app, monkeypatch):
    class FixedDate(date):
        @classmethod
        def today(cls):
            return cls(2026, 6, 15)

    monkeypatch.setattr(key_store, "date", FixedDate)
    page, app = make_app()
    mapping = {
        "[PERSONA_1000]": "Mira Example",
        "[PERSONA_1001]": "Tavi Example",
        "[PERSONA_1002]": "Lumi Example",
    }
    dates = {
        "[PERSONA_1000]": "2026-03-01",
        "[PERSONA_1001]": "2026-05-20",
        "[PERSONA_1002]": "2026-06-15",
    }
    key_store.save_key_atomic(mapping)
    key_store.save_dates(dates)
    asyncio.run(app._on_clear_old_entries(None))
    return page, app, mapping, dates


def test_cleanup_days_change_updates_summary(cleanup_app):
    page, app, mapping, dates = cleanup_app
    dialog = page.dialogs[-1]
    _, field, summary = dialog.content.controls
    assert field.value == "30"
    assert summary.value == i18n.tr_count("purge.count", 1, total=3)

    field.value = "10"
    field.on_change(None)

    assert summary.value == i18n.tr_count("purge.count", 2, total=3)
    assert page.pop_count == 0
    assert key_store.load_key() == mapping
    assert key_store.load_dates() == dates


def test_cleanup_confirm_removes_only_entries_older_than_selected_days(cleanup_app):
    page, app, mapping, dates = cleanup_app
    dialog = page.dialogs[-1]
    dialog.content.controls[1].value = "10"
    dialog.content.controls[1].on_change(None)
    app.current_mapping = mapping.copy()

    asyncio.run(dialog.actions[1].on_click(None))

    assert key_store.load_key() == {"[PERSONA_1002]": mapping["[PERSONA_1002]"]}
    assert key_store.load_dates() == {"[PERSONA_1002]": dates["[PERSONA_1002]"]}
    assert app.current_mapping == {}
    assert page.pop_count == 1


@pytest.mark.parametrize("invalid_days", ["", "invalid"])
def test_cleanup_invalid_days_prevents_deletion(cleanup_app, invalid_days):
    page, app, mapping, dates = cleanup_app
    dialog = page.dialogs[-1]
    _, field, summary = dialog.content.controls
    field.value = invalid_days
    field.on_change(None)

    asyncio.run(dialog.actions[1].on_click(None))

    assert summary.value == i18n.tr("purge.invalid")
    assert key_store.load_key() == mapping
    assert key_store.load_dates() == dates
    assert page.pop_count == 0


def test_cleanup_cancel_preserves_key_and_dates(cleanup_app):
    page, app, mapping, dates = cleanup_app

    page.dialogs[-1].actions[0].on_click(None)

    assert key_store.load_key() == mapping
    assert key_store.load_dates() == dates
    assert page.pop_count == 1


def test_custom_encrypted_key_rejects_wrong_password(make_app, tmp_path):
    page, app = make_app()
    original = (tmp_path / "cloaktext.json").read_bytes()
    envelope = key_store.encrypt_key({"[PERSONA_2000]": "Neri Example"}, PASSWORD)
    app._ask_custom_key_password(envelope, "fictional-custom.json")

    fields = submit_password(page, NEW_PASSWORD)

    assert fields[0].error == i18n.tr("pw.error_wrong")
    assert app.custom_restore_mapping is None
    assert app.custom_key_name is None
    assert app.engine.validated == []
    assert page.pop_count == 0
    assert (tmp_path / "cloaktext.json").read_bytes() == original


def test_custom_encrypted_key_import_restores_without_replacing_default(make_app, tmp_path):
    page, app = make_app()
    original = (tmp_path / "cloaktext.json").read_bytes()
    custom_mapping = {"[PERSONA_2000]": "Neri Example"}
    envelope = key_store.encrypt_key(custom_mapping, PASSWORD)
    app._ask_custom_key_password(envelope, "fictional-custom.json")

    fields = submit_password(page, PASSWORD)

    assert fields[0].error is None
    assert app.custom_restore_mapping == custom_mapping
    assert app.custom_key_name == "fictional-custom.json"
    assert app.engine.validated == [custom_mapping]
    assert app.btn_use_default.visible
    assert "fictional-custom.json" in app.txt_active_key.value
    assert page.pop_count == 1
    assert app._password is None
    asyncio.run(app._run_restore("Hello [PERSONA_2000]"))
    assert app.txt_result.value == "Hello Neri Example"
    assert (tmp_path / "cloaktext.json").read_bytes() == original
    assert key_store.load_key() == MAPPING


def test_custom_encrypted_key_cancel_preserves_default(make_app, tmp_path):
    page, app = make_app()
    original = (tmp_path / "cloaktext.json").read_bytes()
    envelope = key_store.encrypt_key({"[PERSONA_2000]": "Neri Example"}, PASSWORD)
    app._ask_custom_key_password(envelope, "fictional-custom.json")

    page.dialogs[-1].actions[0].on_click(None)

    assert app.custom_restore_mapping is None
    assert app.custom_key_name is None
    assert page.pop_count == 1
    assert (tmp_path / "cloaktext.json").read_bytes() == original


def test_ui_language_changes_through_all_seven_languages(make_app):
    page, app = make_app()
    control_count = len(page.controls)
    app.txt_input.value = "Fictional project text"
    app.txt_terms.value = "Fictional project"
    app.txt_terms.visible = True

    # Start from English so selecting Spanish also exercises a real change.
    app._on_change_ui_language(SimpleNamespace(control=SimpleNamespace(data="en")))
    for code in ("es", "en", "fr", "de", "it", "pt", "ca"):
        app._on_change_ui_language(SimpleNamespace(control=SimpleNamespace(data=code)))

        assert i18n.get_language() == code
        assert app.btn_run.content == i18n.tr("btn.run_protect")
        assert key_store.load_settings()["ui_language"] == code
        assert app.txt_input.value == "Fictional project text"
        assert app.txt_terms.value == "Fictional project"
        assert app.txt_terms.visible
        assert len(page.controls) == control_count


def test_failed_language_pack_install_clears_progress_status(make_app):
    page, app = make_app()

    def failing_install(_language):
        raise ConnectionError("offline")

    app.engine.install_model = failing_install
    event = SimpleNamespace(control=SimpleNamespace(data="es"))

    asyncio.run(app._on_install_language(event))

    assert app.txt_process_status.value == ""
    assert not app.btn_run.disabled
