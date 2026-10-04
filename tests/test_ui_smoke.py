"""Smoke tests de construcción de la interfaz Flet."""

from main import CloakTextApp


class FakePage:
    def __init__(self):
        self.web = True
        self.controls = []
        self.tasks = []

    def add(self, *controls):
        self.controls.extend(controls)

    def run_task(self, handler, *args, **kwargs):
        self.tasks.append((handler, args, kwargs))
        return None

    def update(self):
        return None

    def show_dialog(self, _dialog):
        return None

    def pop_dialog(self):
        return None


def test_interfaz_se_construye_con_flet_fijado():
    page = FakePage()
    app = CloakTextApp(page)

    assert page.title == "CloakText"
    assert page.controls
    assert app.dd_idioma.value == "es"
    assert app.dd_idioma.on_select == app._on_idioma_cambiado
    assert app.btn_ejecutar.content == "Proteger datos"


def test_clave_predeterminada_se_guarda_y_reutiliza(tmp_path, monkeypatch):
    import asyncio
    from key_store import load_key

    monkeypatch.setenv("CLOAKTEXT_APP_DIR", str(tmp_path))
    page = FakePage()
    app = CloakTextApp(page)

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
    import asyncio
    from key_store import save_key_atomic

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
