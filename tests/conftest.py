import pytest

import i18n


@pytest.fixture(autouse=True)
def _idioma_de_interfaz_espanol(monkeypatch):
    """Los tests no dependen del idioma de Windows: la interfaz arranca en español."""
    monkeypatch.setenv("CLOAKTEXT_UI_LANG", "es")
    i18n.set_language("es")
    yield
    i18n.set_language("es")
