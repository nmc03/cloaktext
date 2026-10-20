"""Smoke tests de construcción y comportamiento básico de la interfaz Flet."""

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


def _crear_app(tmp_path, monkeypatch):
    monkeypatch.setenv("CLOAKTEXT_APP_DIR", str(tmp_path))
    page = FakePage()
    return page, CloakTextApp(page)


def test_interfaz_se_construye_con_flet_fijado(tmp_path, monkeypatch):
    page, app = _crear_app(tmp_path, monkeypatch)

    assert page.title == "CloakText"
    assert page.controls
    assert app.dd_idioma.value == "es"
    assert app.dd_idioma.on_select == app._on_idioma_cambiado
    assert app.btn_ejecutar.content == "Proteger datos"
    assert app.btn_limpiar_texto.content == "Limpiar"
    assert app.btn_limpiar_json.content == "Limpiar JSON"
    assert not hasattr(app, "txt_diccionario")
    assert not hasattr(app, "txt_mapa_resultado")
    assert (tmp_path / "cloaktext.json").is_file()
    assert app.txt_clave_activa.value == "Restauración: cloaktext.json predeterminado"

    imagen = app.cabecera.content.controls[0].content
    assert isinstance(imagen, ft.Image)
    assert imagen.src == LOGO_BYTES
    assert LOGO_BYTES.startswith(b"\x89PNG")


def test_limpiar_texto_no_toca_json(tmp_path, monkeypatch):
    page, app = _crear_app(tmp_path, monkeypatch)
    save_key_atomic({"[PERSONA_1000]": "Ana"})

    app.txt_entrada.value = "texto"
    app.txt_resultado.value = "resultado"
    app._on_limpiar_texto(None)

    assert app.txt_entrada.value == ""
    assert app.txt_resultado.value == ""
    assert load_key() == {"[PERSONA_1000]": "Ana"}


def test_limpiar_json_pide_confirmacion_y_vacia_solo_predeterminado(tmp_path, monkeypatch):
    page, app = _crear_app(tmp_path, monkeypatch)
    save_key_atomic({"[PERSONA_1000]": "Ana"})

    app._on_limpiar_json(None)

    dialogo = page.dialogs[-1]
    assert isinstance(dialogo, ft.AlertDialog)
    assert "dejarán de poder restaurarse" in dialogo.content.value
    assert "copias JSON" in dialogo.content.value

    app._confirmar_limpiar_json(None)

    assert load_key() == {}
    assert page.pop_count == 1


def test_cambiar_idioma_libera_modelo_anterior(tmp_path, monkeypatch):
    page, app = _crear_app(tmp_path, monkeypatch)

    class FakeMotor:
        def __init__(self):
            self.descargas = 0

        @staticmethod
        def modelo_disponible(_idioma):
            return True

        @staticmethod
        def idioma_cargado():
            return "es"

        def descargar_modelo(self):
            self.descargas += 1
            return True

    motor = FakeMotor()
    app.motor = motor
    app.dd_idioma.value = "en"

    app._on_idioma_cambiado(None)

    assert motor.descargas == 1


def test_clave_predeterminada_se_guarda_y_reutiliza(tmp_path, monkeypatch):
    page, app = _crear_app(tmp_path, monkeypatch)

    class FakeMotor:
        @staticmethod
        def validar_mapa(mapa):
            assert isinstance(mapa, dict)

        @staticmethod
        def anonimizar(texto, mapa, filtros, idioma, terminos=None):
            mapa["[PERSONA_1000]"] = "Ana"
            return texto.replace("Ana", "[PERSONA_1000]")

        @staticmethod
        def desanonimizar(texto, mapa):
            for token, valor in mapa.items():
                texto = texto.replace(token, valor)
            return texto

    app.motor = FakeMotor()
    asyncio.run(app._ejecutar_anonimizar("Hola Ana", "es"))

    assert app.txt_resultado.value == "Hola [PERSONA_1000]"
    assert load_key() == {"[PERSONA_1000]": "Ana"}

    asyncio.run(app._ejecutar_desanonimizar("Hola [PERSONA_1000]"))
    assert app.txt_resultado.value == "Hola Ana"
    assert "cloaktext.json" in app.txt_resumen.value


def test_json_personalizado_solo_se_usa_si_se_selecciona(tmp_path, monkeypatch):
    monkeypatch.setenv("CLOAKTEXT_APP_DIR", str(tmp_path))
    save_key_atomic({"[PERSONA_1000]": "Ana"})
    page = FakePage()
    app = CloakTextApp(page)

    class FakeMotor:
        @staticmethod
        def validar_mapa(mapa):
            assert isinstance(mapa, dict)

        @staticmethod
        def desanonimizar(texto, mapa):
            return mapa.get(texto, texto)

    app.motor = FakeMotor()
    asyncio.run(app._ejecutar_desanonimizar("[PERSONA_1000]"))
    assert app.txt_resultado.value == "Ana"

    app.mapa_restauracion_personalizado = {"[PERSONA_1000]": "Eva"}
    app.nombre_clave_personalizada = "otra.json"
    asyncio.run(app._ejecutar_desanonimizar("[PERSONA_1000]"))
    assert app.txt_resultado.value == "Eva"
    assert "otra.json" in app.txt_resumen.value


def test_botones_no_muestran_tooltips(tmp_path, monkeypatch):
    _page, app = _crear_app(tmp_path, monkeypatch)

    botones = [
        app.btn_modelo,
        app.btn_limpiar_texto,
        app.btn_limpiar_json,
        app.btn_exportar_diccionario,
    ]
    assert all(getattr(boton, "tooltip", None) in (None, "") for boton in botones)


# --- funciones nuevas: resaltado, palabras manuales, contraseña, idioma ---

import re  # noqa: E402
from types import SimpleNamespace  # noqa: E402
from pathlib import Path  # noqa: E402

import pytest  # noqa: E402

import i18n  # noqa: E402
import key_store  # noqa: E402
from main import spans_resaltados  # noqa: E402


def test_spans_resaltados_marcan_solo_los_marcadores():
    spans = spans_resaltados("Hola [PERSONA_1000], mira [EMAIL_1001].")
    textos = [span.text for span in spans]

    assert "".join(textos) == "Hola [PERSONA_1000], mira [EMAIL_1001]."
    estilados = [span.text for span in spans if span.style is not None]
    assert estilados == ["[PERSONA_1000]", "[EMAIL_1001]"]


def test_resultado_se_resalta_y_se_puede_alternar(tmp_path, monkeypatch):
    page, app = _crear_app(tmp_path, monkeypatch)
    app._mostrar_resultado("Hola [PERSONA_1000]")

    assert app.sw_resaltar.visible and app.vista_resaltada.visible
    assert not app.txt_resultado.visible

    app.sw_resaltar.value = False
    app._on_alternar_resaltado(None)

    assert not app.vista_resaltada.visible and app.txt_resultado.visible


def test_palabras_adicionales_llegan_al_motor(tmp_path, monkeypatch):
    page, app = _crear_app(tmp_path, monkeypatch)
    recibido = {}

    class FakeMotor:
        @staticmethod
        def validar_mapa(mapa):
            pass

        @staticmethod
        def anonimizar(texto, mapa, filtros, idioma, terminos=None):
            recibido["terminos"] = terminos
            return texto

    app.motor = FakeMotor()
    app.txt_terminos.value = "Proyecto Atlas\nAna María"
    asyncio.run(app._ejecutar_anonimizar("texto", "es"))

    assert recibido["terminos"] == ["Proyecto Atlas", "Ana María"]


def test_clave_cifrada_pide_contrasena_al_abrir(tmp_path, monkeypatch):
    monkeypatch.setenv("CLOAKTEXT_APP_DIR", str(tmp_path))
    save_key_atomic({"[PERSONA_1000]": "Ana"}, password="correct horse")

    page = FakePage()
    app = CloakTextApp(page)

    assert app._clave_bloqueada
    assert isinstance(page.dialogs[-1], ft.AlertDialog)
    with pytest.raises(key_store.KeyEncryptedError):
        asyncio.run(app._ejecutar_anonimizar("Hola Ana", "es"))
    # el archivo no se ha tocado
    assert key_store.is_encrypted()


def test_con_contrasena_la_clave_se_guarda_cifrada(tmp_path, monkeypatch):
    page, app = _crear_app(tmp_path, monkeypatch)
    save_key_atomic({}, password="correct horse")
    app._password = "correct horse"

    class FakeMotor:
        @staticmethod
        def validar_mapa(mapa):
            pass

        @staticmethod
        def anonimizar(texto, mapa, filtros, idioma, terminos=None):
            mapa["[PERSONA_1000]"] = "Ana"
            return texto.replace("Ana", "[PERSONA_1000]")

    app.motor = FakeMotor()
    asyncio.run(app._ejecutar_anonimizar("Hola Ana", "es"))

    assert "Ana" not in (tmp_path / "cloaktext.json").read_text(encoding="utf-8")
    assert load_key(password="correct horse") == {"[PERSONA_1000]": "Ana"}


def test_fechas_de_alta_se_registran_al_proteger(tmp_path, monkeypatch):
    page, app = _crear_app(tmp_path, monkeypatch)

    class FakeMotor:
        @staticmethod
        def validar_mapa(mapa):
            pass

        @staticmethod
        def anonimizar(texto, mapa, filtros, idioma, terminos=None):
            mapa["[EMAIL_1000]"] = "a@b.co"
            return "[EMAIL_1000]"

    app.motor = FakeMotor()
    asyncio.run(app._ejecutar_anonimizar("a@b.co", "es"))

    assert list(key_store.load_dates()) == ["[EMAIL_1000]"]


def test_cambiar_idioma_de_la_interfaz_reconstruye_y_conserva_el_texto(tmp_path, monkeypatch):
    page, app = _crear_app(tmp_path, monkeypatch)
    app.txt_entrada.value = "mi texto"

    app._on_cambiar_idioma_ui(SimpleNamespace(control=SimpleNamespace(data="en")))

    assert app.btn_ejecutar.content == "Protect data"
    assert app.txt_entrada.value == "mi texto"
    assert key_store.load_settings()["ui_language"] == "en"
    assert i18n.get_language() == "en"


_USOS_TR = re.compile(r"""\btr\(\s*["']([a-z_]+\.[a-z_0-9]+)["']""")
_USOS_TR_COND = re.compile(r"""["'](msg\.(?:noun|verb)_(?:one|many))["']""")


def _claves_usadas() -> set[str]:
    raiz = Path(__file__).resolve().parent.parent
    claves: set[str] = set()
    for archivo in ("main.py", "key_store.py", "motor_local.py"):
        codigo = (raiz / archivo).read_text(encoding="utf-8")
        claves |= set(_USOS_TR.findall(codigo)) | set(_USOS_TR_COND.findall(codigo))
    return claves


def test_todas_las_cadenas_existen_en_ambos_idiomas():
    es, en = i18n.STRINGS["es"], i18n.STRINGS["en"]
    assert set(es) == set(en)
    faltan = {c for c in _claves_usadas() if c not in es}
    assert not faltan, f"claves sin traducción: {sorted(faltan)}"
    # `lang.<código>` se construye dinámicamente
    assert all(f"lang.{c}" in es for c in ("es", "en", "fr", "de", "it", "pt", "ca"))


def test_las_traducciones_comparten_marcadores_de_formato():
    campo = re.compile(r"\{(\w+)[^}]*\}")
    for clave, texto_es in i18n.STRINGS["es"].items():
        assert set(campo.findall(texto_es)) == set(campo.findall(i18n.STRINGS["en"][clave])), clave


def test_idioma_desconocido_cae_en_ingles_y_clave_ausente_se_devuelve():
    i18n.set_language("xx")
    assert i18n.get_language() == "en"
    assert i18n.tr("clave.inexistente") == "clave.inexistente"
