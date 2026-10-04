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
