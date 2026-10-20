"""User-interface strings for CloakText (Spanish and English, plus other languages).

`tr("key", name=value)` returns the string in the active language. The language is
chosen in this order: CLOAKTEXT_UI_LANG (development/tests) > saved preference >
Windows UI language > English. Data markers (`[PERSONA_1000]`, ...) and the key
names in `cloaktext.json` are NOT translated: they are persisted format.
"""

from __future__ import annotations

import locale
import os
import sys

UI_LANGUAGES = {
    "es": "Español",
    "en": "English",
    "fr": "Français",
    "de": "Deutsch",
    "it": "Italiano",
    "pt": "Português",
    "ca": "Català",
}
DEFAULT_LANGUAGE = "en"

_current = DEFAULT_LANGUAGE

from locales import ca, de, en, es, fr, it, pt

# Explicit imports (not importlib) so PyInstaller bundles every language.
STRINGS: dict[str, dict[str, str]] = {
    "es": es.STRINGS,
    "en": en.STRINGS,
    "fr": fr.STRINGS,
    "de": de.STRINGS,
    "it": it.STRINGS,
    "pt": pt.STRINGS,
    "ca": ca.STRINGS,
}


# Windows primary language identifiers (LANGID & 0x3FF) -> interface language.
_WINDOWS_PRIMARY_LANGUAGE = {0x0A: "es", 0x09: "en", 0x0C: "fr", 0x07: "de", 0x10: "it", 0x16: "pt", 0x03: "ca"}


def detect_system_language() -> str:
    """Interface language matching the OS language, or English if unsupported."""
    if sys.platform == "win32":
        try:
            import ctypes

            primary = ctypes.windll.kernel32.GetUserDefaultUILanguage() & 0x3FF
            return _WINDOWS_PRIMARY_LANGUAGE.get(primary, DEFAULT_LANGUAGE)
        except (AttributeError, OSError):
            pass
    try:
        code = (locale.getlocale()[0] or os.environ.get("LANG", "")).lower()
    except (ValueError, TypeError):
        code = ""
    return code[:2] if code[:2] in UI_LANGUAGES else DEFAULT_LANGUAGE


def resolve_language(saved: str | None = None) -> str:
    forced = os.environ.get("CLOAKTEXT_UI_LANG")
    for candidate in (forced, saved):
        if candidate in UI_LANGUAGES:
            return candidate
    return detect_system_language()


def set_language(code: str) -> None:
    global _current
    _current = code if code in UI_LANGUAGES else DEFAULT_LANGUAGE


def get_language() -> str:
    return _current


def tr(key: str, **values: object) -> str:
    text = STRINGS.get(_current, {}).get(key) or STRINGS[DEFAULT_LANGUAGE].get(key) or key
    return text.format(**values) if values else text
