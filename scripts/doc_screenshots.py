"""Generate the README screenshots from the real CloakText window (Windows only).

Development tool, not shipped. It opens the actual Flet app, fills in a synthetic
sample text and captures the window. Language models are NOT used: the sample only
contains structured data (email, phone, IBAN, ID number), which is detected by the
rule-based engine, so no model download is needed and no real data is involved.

    python scripts/doc_screenshots.py

Output: docs/images/{protect,restore}.png (English) and {protect,restore}.es.png (Spanish)
"""

from __future__ import annotations

import asyncio
import ctypes
import ctypes.wintypes
import os
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
OUT = ROOT / "docs" / "images"

# Keep the key file and any data out of the repository.
TMP = tempfile.mkdtemp(prefix="cloaktext-shots-")
os.environ["CLOAKTEXT_APP_DIR"] = TMP

import flet as ft  # noqa: E402
from PIL import ImageGrab  # noqa: E402

import main as app_module  # noqa: E402

SAMPLES = {
    "en": (
        "Hi team,\n\n"
        "Please wire the payment to account GB82 WEST 1234 5698 7654 32 before Friday.\n"
        "Questions? Write to ana.garcia@example.com or call +1 415 555 2671.\n"
        "Account holder SSN: 123-45-6789. Thanks."
    ),
    "es": (
        "Hola equipo,\n\n"
        "Por favor, haced la transferencia a la cuenta ES91 2100 0418 4502 0005 1332 "
        "antes del viernes.\n"
        "Para dudas escribid a ana.garcia@example.com o llamad al +34 612 345 678.\n"
        "DNI del titular: 12345678Z. Gracias."
    ),
}
SUFFIX = {"en": "", "es": ".es"}


class _NoNerUse:
    def __enter__(self):
        return lambda text: SimpleNamespace(ents=[])

    def __exit__(self, *exc):
        return False


class _NoNerManager:
    def usar(self, language):
        return _NoNerUse()


def _capture(name: str) -> bool:
    user32 = ctypes.windll.user32
    hwnd = user32.FindWindowW(None, "CloakText")
    if not hwnd:
        raise SystemExit("CloakText window not found")
    user32.SetForegroundWindow(hwnd)
    rect = ctypes.wintypes.RECT()
    # DWMWA_EXTENDED_FRAME_BOUNDS (9): visible bounds, without the invisible resize border.
    ctypes.windll.dwmapi.DwmGetWindowAttribute(hwnd, 9, ctypes.byref(rect), ctypes.sizeof(rect))
    # Abort rather than save a screenshot of whatever covers CloakText (tray flyouts,
    # other apps...): every point of a grid over the window must belong to it.
    width, height = rect.right - rect.left, rect.bottom - rect.top
    for gx in range(8, width - 8, max(1, (width - 16) // 12)):
        for gy in range(8, height - 8, max(1, (height - 16) // 12)):
            point = ctypes.wintypes.POINT(rect.left + gx, rect.top + gy)
            if user32.GetAncestor(user32.WindowFromPoint(point), 2) != hwnd:
                return False
    OUT.mkdir(parents=True, exist_ok=True)
    ImageGrab.grab(bbox=(rect.left, rect.top, rect.right, rect.bottom), all_screens=True).save(OUT / name)
    print("saved", OUT / name)
    return True


async def _capture_retrying(name: str) -> None:
    for _ in range(6):
        if _capture(name):
            return
        await asyncio.sleep(2)
    raise SystemExit(f"{name}: the window stayed covered by another window; nothing saved")


async def _shoot(app: app_module.CloakTextApp, page: ft.Page, language: str) -> None:
    app._cambiar_modo("anon")
    app._guardar_clave({})  # start numbering from 1000 in every screenshot
    app.dd_idioma.value = language
    app.txt_entrada.value = SAMPLES[language]
    app._on_texto_cambiado(None)
    page.update()
    await app._on_ejecutar(None)
    page.pop_dialog()  # hide the toast so it does not cover the buttons
    page.update()
    await asyncio.sleep(2.5)
    await _capture_retrying(f"protect{SUFFIX[language]}.png")

    protected = app.txt_resultado.value
    app._cambiar_modo("resta")
    app.txt_entrada.value = protected
    app._on_texto_cambiado(None)
    page.update()
    await app._on_ejecutar(None)
    page.pop_dialog()
    page.update()
    await asyncio.sleep(2.5)
    await _capture_retrying(f"restore{SUFFIX[language]}.png")


async def _run(page: ft.Page) -> None:
    ctypes.windll.shcore.SetProcessDpiAwareness(2)
    page.theme_mode = ft.ThemeMode.LIGHT
    app = app_module.CloakTextApp(page)
    app.motor._gestor = _NoNerManager()  # rule-based detection only
    page.window.width, page.window.height = 1180, 760
    page.window.always_on_top = True  # keep other windows out of the capture
    page.update()
    await asyncio.sleep(1.5)

    for language in ("en", "es"):
        app._on_cambiar_idioma_ui(SimpleNamespace(control=SimpleNamespace(data=language)))
        await asyncio.sleep(1.0)
        await _shoot(app, page, language)

    page.window.prevent_close = False
    await page.window.destroy()


def _main(page: ft.Page) -> None:
    page.run_task(_run, page)


if __name__ == "__main__":
    ft.run(_main)
