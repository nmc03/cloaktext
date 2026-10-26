import pytest

import i18n


@pytest.fixture(autouse=True)
def _spanish_ui_language(monkeypatch):
    """Tests do not depend on the Windows language: the interface starts in Spanish."""
    monkeypatch.setenv("CLOAKTEXT_UI_LANG", "es")
    i18n.set_language("es")
    yield
    i18n.set_language("es")
