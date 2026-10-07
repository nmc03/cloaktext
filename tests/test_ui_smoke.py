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
        def anonimizar(texto, mapa, filtros, idioma):
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
