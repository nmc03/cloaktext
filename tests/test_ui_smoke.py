"""Smoke tests for building and basic behavior of the Flet interface."""

import asyncio

import flet as ft

from branding import LOGO_BYTES
from key_store import load_key, save_key_atomic
from main import CloakTextApp


class FakePage:
    def __init__(self):
        self.web = True
        self.controls = []
        self.tasks = []
        self.dialogs = []
        self.pop_count = 0

    def add(self, *controls):
        self.controls.extend(controls)

    def run_task(self, handler, *args, **kwargs):
        self.tasks.append((handler, args, kwargs))
        return None

    def update(self):
        return None

    def show_dialog(self, dialog):
        self.dialogs.append(dialog)
        return None

    def pop_dialog(self):
        self.pop_count += 1
        return None


def _create_app(tmp_path, monkeypatch):
    monkeypatch.setenv("CLOAKTEXT_APP_DIR", str(tmp_path))
    page = FakePage()
    return page, CloakTextApp(page)


def test_interface_builds_with_pinned_flet(tmp_path, monkeypatch):
    page, app = _create_app(tmp_path, monkeypatch)

    assert page.title == "CloakText"
    assert page.controls
    assert app.dd_language.value == "es"
    assert app.dd_language.on_select == app._on_language_changed
    assert app.btn_run.content == "Proteger datos"
    assert app.btn_clear_text.content == "Limpiar"
    assert app.btn_clear_json.content == "Limpiar JSON"
    assert not hasattr(app, "txt_diccionario")
    assert not hasattr(app, "txt_mapa_resultado")
    assert (tmp_path / "cloaktext.json").is_file()
    assert app.txt_active_key.value == "Restauración: cloaktext.json predeterminado"

    image = app.header.content.controls[0].content
    assert isinstance(image, ft.Image)
    assert image.src == LOGO_BYTES
    assert LOGO_BYTES.startswith(b"\x89PNG")


def test_clear_text_does_not_touch_json(tmp_path, monkeypatch):
    page, app = _create_app(tmp_path, monkeypatch)
    save_key_atomic({"[PERSONA_1000]": "Ana"})

    app.txt_input.value = "texto"
    app.txt_result.value = "resultado"
    app._on_clear_text(None)

    assert app.txt_input.value == ""
    assert app.txt_result.value == ""
    assert load_key() == {"[PERSONA_1000]": "Ana"}


def test_clear_json_asks_confirmation_and_empties_only_the_default(tmp_path, monkeypatch):
    page, app = _create_app(tmp_path, monkeypatch)
    save_key_atomic({"[PERSONA_1000]": "Ana"})

    app._on_clear_json(None)

    dialog = page.dialogs[-1]
    assert isinstance(dialog, ft.AlertDialog)
    assert "dejarán de poder restaurarse" in dialog.content.value
    assert "copias JSON" in dialog.content.value

    app._confirm_clear_json(None)

    assert load_key() == {}
    assert page.pop_count == 1


def test_changing_language_unloads_previous_model(tmp_path, monkeypatch):
    page, app = _create_app(tmp_path, monkeypatch)

    class FakeEngine:
        def __init__(self):
            self.unloads = 0

        @staticmethod
        def model_available(_language):
            return True

        @staticmethod
        def loaded_language():
            return "es"

        def unload_model(self):
            self.unloads += 1
            return True

    engine = FakeEngine()
    app.engine = engine
    app.dd_language.value = "en"

    app._on_language_changed(None)

    assert engine.unloads == 1


def test_default_key_is_saved_and_reused(tmp_path, monkeypatch):
    page, app = _create_app(tmp_path, monkeypatch)

    class FakeEngine:
        @staticmethod
        def validate_mapping(mapping):
            assert isinstance(mapping, dict)

        @staticmethod
        def protect(text, mapping, filters, language, terms=None):
            mapping["[PERSONA_1000]"] = "Ana"
            return text.replace("Ana", "[PERSONA_1000]")

        @staticmethod
        def restore(text, mapping):
            for token, value in mapping.items():
                text = text.replace(token, value)
            return text

    app.engine = FakeEngine()
    asyncio.run(app._run_protect("Hola Ana", "es"))

    assert app.txt_result.value == "Hola [PERSONA_1000]"
    assert load_key() == {"[PERSONA_1000]": "Ana"}

    asyncio.run(app._run_restore("Hola [PERSONA_1000]"))
    assert app.txt_result.value == "Hola Ana"
    assert "cloaktext.json" in app.txt_summary.value


def test_custom_json_is_only_used_when_selected(tmp_path, monkeypatch):
    monkeypatch.setenv("CLOAKTEXT_APP_DIR", str(tmp_path))
    save_key_atomic({"[PERSONA_1000]": "Ana"})
    page = FakePage()
    app = CloakTextApp(page)

    class FakeEngine:
        @staticmethod
        def validate_mapping(mapping):
            assert isinstance(mapping, dict)

        @staticmethod
        def restore(text, mapping):
            return mapping.get(text, text)

    app.engine = FakeEngine()
    asyncio.run(app._run_restore("[PERSONA_1000]"))
    assert app.txt_result.value == "Ana"

    app.custom_restore_mapping = {"[PERSONA_1000]": "Eva"}
    app.custom_key_name = "otra.json"
    asyncio.run(app._run_restore("[PERSONA_1000]"))
    assert app.txt_result.value == "Eva"
    assert "otra.json" in app.txt_summary.value


def test_buttons_show_no_tooltips(tmp_path, monkeypatch):
    _page, app = _create_app(tmp_path, monkeypatch)

    buttons = [
        app.btn_model,
        app.btn_clear_text,
        app.btn_clear_json,
        app.btn_export_key,
    ]
    assert all(getattr(button, "tooltip", None) in (None, "") for button in buttons)


# --- new features: highlighting, manual words, password, language ---

import re  # noqa: E402
from types import SimpleNamespace  # noqa: E402
from pathlib import Path  # noqa: E402

import pytest  # noqa: E402

import i18n  # noqa: E402
import key_store  # noqa: E402
from main import highlighted_spans  # noqa: E402


def test_highlighted_spans_mark_only_the_placeholders():
    spans = highlighted_spans("Hola [PERSONA_1000], mira [EMAIL_1001].")
    texts = [span.text for span in spans]

    assert "".join(texts) == "Hola [PERSONA_1000], mira [EMAIL_1001]."
    styled = [span.text for span in spans if span.style is not None]
    assert styled == ["[PERSONA_1000]", "[EMAIL_1001]"]


def test_result_is_highlighted_and_can_be_toggled(tmp_path, monkeypatch):
    page, app = _create_app(tmp_path, monkeypatch)
    app._show_result("Hola [PERSONA_1000]")

    assert app.sw_highlight.visible and app.highlight_view.visible
    assert not app.txt_result.visible

    app.sw_highlight.value = False
    app._on_toggle_highlight(None)

    assert not app.highlight_view.visible and app.txt_result.visible


def test_extra_words_reach_the_engine(tmp_path, monkeypatch):
    page, app = _create_app(tmp_path, monkeypatch)
    received = {}

    class FakeEngine:
        @staticmethod
        def validate_mapping(mapping):
            pass

        @staticmethod
        def protect(text, mapping, filters, language, terms=None):
            received["terminos"] = terms
            return text

    app.engine = FakeEngine()
    app.txt_terms.value = "Proyecto Atlas\nAna María"
    asyncio.run(app._run_protect("texto", "es"))

    assert received["terminos"] == ["Proyecto Atlas", "Ana María"]


def test_encrypted_key_asks_for_password_on_open(tmp_path, monkeypatch):
    monkeypatch.setenv("CLOAKTEXT_APP_DIR", str(tmp_path))
    save_key_atomic({"[PERSONA_1000]": "Ana"}, password="correct horse")

    page = FakePage()
    app = CloakTextApp(page)

    assert app._key_locked
    assert isinstance(page.dialogs[-1], ft.AlertDialog)
    with pytest.raises(key_store.KeyEncryptedError):
        asyncio.run(app._run_protect("Hola Ana", "es"))
    # the file was not modified
    assert key_store.is_encrypted()


def test_with_password_the_key_is_saved_encrypted(tmp_path, monkeypatch):
    page, app = _create_app(tmp_path, monkeypatch)
    save_key_atomic({}, password="correct horse")
    app._password = "correct horse"

    class FakeEngine:
        @staticmethod
        def validate_mapping(mapping):
            pass

        @staticmethod
        def protect(text, mapping, filters, language, terms=None):
            mapping["[PERSONA_1000]"] = "Ana"
            return text.replace("Ana", "[PERSONA_1000]")

    app.engine = FakeEngine()
    asyncio.run(app._run_protect("Hola Ana", "es"))

    assert "Ana" not in (tmp_path / "cloaktext.json").read_text(encoding="utf-8")
    assert load_key(password="correct horse") == {"[PERSONA_1000]": "Ana"}


def test_creation_dates_are_recorded_when_protecting(tmp_path, monkeypatch):
    page, app = _create_app(tmp_path, monkeypatch)

    class FakeEngine:
        @staticmethod
        def validate_mapping(mapping):
            pass

        @staticmethod
        def protect(text, mapping, filters, language, terms=None):
            mapping["[EMAIL_1000]"] = "a@b.co"
            return "[EMAIL_1000]"

    app.engine = FakeEngine()
    asyncio.run(app._run_protect("a@b.co", "es"))

    assert list(key_store.load_dates()) == ["[EMAIL_1000]"]


def test_changing_ui_language_rebuilds_and_keeps_the_text(tmp_path, monkeypatch):
    page, app = _create_app(tmp_path, monkeypatch)
    app.txt_input.value = "mi texto"

    app._on_change_ui_language(SimpleNamespace(control=SimpleNamespace(data="en")))

    assert app.btn_run.content == "Protect data"
    assert app.txt_input.value == "mi texto"
    assert key_store.load_settings()["ui_language"] == "en"
    assert i18n.get_language() == "en"


_TR_USES = re.compile(r"""\btr\(\s*["']([a-z_]+\.[a-z_0-9]+)["']""")
_TR_COND_USES = re.compile(r"""["'](msg\.(?:noun|verb)_(?:one|many))["']""")


def _used_keys() -> set[str]:
    root_dir = Path(__file__).resolve().parent.parent
    keys_used: set[str] = set()
    for picked_file in ("main.py", "key_store.py", "local_engine.py"):
        code = (root_dir / picked_file).read_text(encoding="utf-8")
        keys_used |= set(_TR_USES.findall(code)) | set(_TR_COND_USES.findall(code))
    return keys_used


ALL_LANGUAGES = ("es", "en", "fr", "de", "it", "pt", "ca")


def test_all_strings_exist_in_every_language():
    reference = set(i18n.STRINGS["en"])
    for code in ALL_LANGUAGES:
        assert set(i18n.STRINGS[code]) == reference, code
    missing = {key for key in _used_keys() if key not in reference}
    assert not missing, f"keys used in code but not translated: {sorted(missing)}"
    # `lang.<code>` keys are built dynamically
    assert all(f"lang.{code}" in reference for code in ALL_LANGUAGES)
    assert set(i18n.UI_LANGUAGES) == set(ALL_LANGUAGES)


def test_translations_share_format_placeholders():
    field = re.compile(r"\{(\w+)[^}]*\}")
    for code in ALL_LANGUAGES:
        for key_name, translated in i18n.STRINGS[code].items():
            expected = sorted(field.findall(i18n.STRINGS["en"][key_name]))
            assert sorted(field.findall(translated)) == expected, (code, key_name)


def test_non_english_languages_are_actually_translated():
    english = i18n.STRINGS["en"]
    for code in ALL_LANGUAGES:
        if code == "en":
            continue
        same = [k for k, v in i18n.STRINGS[code].items() if v == english[k]]
        assert len(same) <= 6, (code, same)  # only names such as "JSON" may match


def test_unknown_language_falls_back_to_english_and_missing_key_is_returned():
    i18n.set_language("xx")
    assert i18n.get_language() == "en"
    assert i18n.tr("missing.key") == "missing.key"


def test_marking_text_adds_the_selection_to_extra_words(tmp_path, monkeypatch):
    page, app = _create_app(tmp_path, monkeypatch)

    app._on_selection_changed(SimpleNamespace(selected_text="  Proyecto   Atlas "))
    app._on_selection_changed(SimpleNamespace(selected_text=""))  # focus is lost when the button is pressed
    app._on_protect_selection(None)

    assert app.txt_terms.value == "Proyecto Atlas"
    assert app.txt_terms.visible
    app._on_selection_changed(SimpleNamespace(selected_text="proyecto atlas"))
    app._on_protect_selection(None)  # duplicate: not added again
    assert app.txt_terms.value == "Proyecto Atlas"
    app._on_selection_changed(SimpleNamespace(selected_text="Ana María"))
    app._on_protect_selection(None)
    assert app._manual_terms() == ["Proyecto Atlas", "Ana María"]


def test_marking_text_without_selection_warns(tmp_path, monkeypatch):
    page, app = _create_app(tmp_path, monkeypatch)
    app._on_protect_selection(None)

    assert app.txt_terms.value in ("", None)
    assert page.dialogs  # snackbar with the notice
