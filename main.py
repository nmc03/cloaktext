"""Interfaz de escritorio de CloakText."""

from __future__ import annotations

import asyncio
from collections import Counter
from datetime import datetime
import json
import logging
import re

import flet as ft

from branding import LOGO_BYTES
from i18n import UI_LANGUAGES, get_language, resolve_language, set_language, tr
from key_store import (
    MIN_PASSWORD_LENGTH,
    KeyEncryptedError,
    WrongPasswordError,
    decrypt_key,
    default_key_path,
    encrypt_key,
    find_older_than,
    is_encrypted,
    is_encrypted_envelope,
    load_dates,
    load_key,
    load_settings,
    purge,
    save_dates,
    save_key_atomic,
    save_settings,
    stamp_tokens,
    using_fallback_directory,
)
from language_models import info_modelo
from motor_local import IDIOMAS_SOPORTADOS, ModeloNoDisponibleError, MotorLocal
from version import __version__

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

C_MARCA = ft.Colors.BLUE_700
C_MARCA_OSCURO = ft.Colors.BLUE_900
C_RESTA = ft.Colors.TEAL_600
C_RESTA_OSCURO = ft.Colors.TEAL_800

G_MARCA = ft.LinearGradient(
    begin=ft.Alignment.TOP_LEFT,
    end=ft.Alignment.BOTTOM_RIGHT,
    colors=[C_MARCA_OSCURO, ft.Colors.CYAN_600],
)
G_RESTA = ft.LinearGradient(
    begin=ft.Alignment.TOP_LEFT,
    end=ft.Alignment.BOTTOM_RIGHT,
    colors=[C_RESTA_OSCURO, ft.Colors.GREEN_600],
)

TOKEN_TIPO_RE = re.compile(r"\[([A-Z][A-Z0-9_]*)_\d+\]")
TOKEN_RESALTADO_RE = re.compile(r"(\[[A-Z][A-Z0-9_]*_\d+\])")
MAX_DICCIONARIO_BYTES = 10 * 1024 * 1024


def nombre_idioma(codigo: str) -> str:
    return tr(f"lang.{codigo}")


def spans_resaltados(texto: str) -> list[ft.TextSpan]:
    """Divide `texto` resaltando los marcadores `[TIPO_1000]`."""
    estilo = ft.TextStyle(
        bgcolor=ft.Colors.PRIMARY_CONTAINER,
        color=ft.Colors.ON_PRIMARY_CONTAINER,
        weight=ft.FontWeight.BOLD,
    )
    spans: list[ft.TextSpan] = []
    for trozo in TOKEN_RESALTADO_RE.split(texto):
        if not trozo:
            continue
        if TOKEN_RESALTADO_RE.fullmatch(trozo):
            spans.append(ft.TextSpan(trozo, style=estilo))
        else:
            spans.append(ft.TextSpan(trozo))
    return spans


class CloakTextApp:
    def __init__(self, page: ft.Page):
        self.page = page
        set_language(resolve_language(load_settings().get("ui_language")))
        self.motor = MotorLocal(ttl_minutos=20)
        self.clipboard = ft.Clipboard()
        self.modo = "anon"
        self.mapa_actual: dict[str, str] = {}
        self.mapa_restauracion_personalizado: dict[str, str] | None = None
        self.nombre_clave_personalizada: str | None = None
        self.ruta_clave_predeterminada = default_key_path()
        self._busy = False
        self._password: str | None = None
        self._clave_bloqueada = False

        self._configurar_pagina()
        self._construir_ui()
        self._inicializar_clave_predeterminada()
        page.run_task(self._actualizar_estado_periodico)
        if self._clave_bloqueada:
            self._mostrar_desbloqueo()

    def _configurar_pagina(self) -> None:
        self.page.title = "CloakText"
        self.page.theme_mode = ft.ThemeMode.SYSTEM
        self.page.theme = ft.Theme(
            color_scheme_seed=C_MARCA,
            use_material3=True,
        )
        self.page.padding = 0
        self.page.spacing = 0
        self.page.bgcolor = ft.Colors.SURFACE_CONTAINER_LOW

        if not self.page.web:
            self.page.window.width = 1180
            self.page.window.height = 820
            self.page.window.min_width = 760
            self.page.window.min_height = 620
            self.page.window.prevent_close = True
            self.page.window.on_event = self._on_window_event

    # ------------------------------------------------------------------ UI

    def _construir_ui(self) -> None:
        self.dd_idioma = ft.Dropdown(
            label=tr("lang.label"),
            width=220,
            value=getattr(self, "_idioma_texto", "es"),
            on_select=self._on_idioma_cambiado,
            options=[
                ft.DropdownOption(key=codigo, text=nombre_idioma(codigo))
                for codigo in sorted(IDIOMAS_SOPORTADOS, key=nombre_idioma)
            ],
        )

        self.txt_estado_modelo = ft.Text(
            tr("model.pending"),
            size=12,
            color=ft.Colors.OUTLINE,
        )
        self.btn_modelo = ft.OutlinedButton(
            content=tr("btn.prepare_language"),
            icon=ft.Icons.DOWNLOAD_OUTLINED,
            on_click=self._on_accion_modelo,
        )

        self.btn_modo_anon = ft.Button(
            content=tr("mode.protect"),
            icon=ft.Icons.VISIBILITY_OFF_OUTLINED,
            on_click=lambda _: self._cambiar_modo("anon"),
        )
        self.btn_modo_resta = ft.OutlinedButton(
            content=tr("mode.restore"),
            icon=ft.Icons.VISIBILITY_OUTLINED,
            on_click=lambda _: self._cambiar_modo("resta"),
        )

        self.txt_entrada = ft.TextField(
            label=tr("field.input_protect"),
            margin=ft.Margin.symmetric(horizontal=4, vertical=2),
            hint_text=tr("hint.input_protect"),
            multiline=True,
            min_lines=12,
            max_lines=18,
            autofocus=True,
            on_change=self._on_texto_cambiado,
        )
        self.txt_contador = ft.Text(
            tr("counter.zero"),
            size=11,
            color=ft.Colors.OUTLINE,
        )
        self.btn_terminos = ft.TextButton(
            content=tr("terms.toggle"),
            icon=ft.Icons.EDIT_NOTE_OUTLINED,
            on_click=self._on_alternar_terminos,
        )
        self.txt_terminos = ft.TextField(
            label=tr("terms.label"),
            hint_text=tr("terms.hint"),
            multiline=True,
            min_lines=3,
            max_lines=6,
            visible=False,
        )

        self.txt_clave_activa = ft.Text(
            tr("restore.active_default"),
            size=12,
            color=ft.Colors.OUTLINE,
            visible=False,
        )
        self.btn_cargar_diccionario = ft.OutlinedButton(
            content=tr("btn.other_json"),
            icon=ft.Icons.FILE_OPEN_OUTLINED,
            on_click=self._on_cargar_diccionario,
            visible=False,
        )
        self.btn_usar_predeterminado = ft.TextButton(
            content=tr("btn.default_json"),
            icon=ft.Icons.RESTART_ALT,
            on_click=self._on_usar_predeterminado,
            visible=False,
        )

        self.barra_progreso = ft.ProgressBar(visible=False)
        self.txt_estado_proceso = ft.Text(
            "",
            size=12,
            color=ft.Colors.OUTLINE,
        )

        self.btn_ejecutar = ft.Button(
            content=tr("btn.run_protect"),
            icon=ft.Icons.SHIELD_OUTLINED,
            on_click=self._on_ejecutar,
        )
        self.btn_limpiar_texto = ft.OutlinedButton(
            content=tr("common.clear"),
            icon=ft.Icons.CLEAR_ALL_OUTLINED,
            on_click=self._on_limpiar_texto,
        )
        self.btn_limpiar_json = ft.TextButton(
            content=tr("btn.clear_json"),
            icon=ft.Icons.DELETE_FOREVER_OUTLINED,
            on_click=self._on_limpiar_json,
            style=ft.ButtonStyle(color=ft.Colors.ERROR),
        )

        self.txt_resultado = ft.TextField(
            label=tr("field.result_protect"),
            margin=ft.Margin.symmetric(horizontal=4, vertical=2),
            hint_text=tr("hint.result_protect"),
            multiline=True,
            min_lines=12,
            max_lines=18,
            read_only=True,
        )
        self.texto_resaltado = ft.Text("", selectable=True, size=14)
        self.vista_resaltada = ft.Container(
            visible=False,
            height=318,
            padding=14,
            margin=ft.Margin.symmetric(horizontal=4, vertical=2),
            border=ft.Border.all(1, ft.Colors.OUTLINE),
            border_radius=4,
            content=ft.Column(controls=[self.texto_resaltado], scroll=ft.ScrollMode.AUTO),
        )
        self.sw_resaltar = ft.Switch(
            label=tr("highlight.switch"),
            value=True,
            on_change=self._on_alternar_resaltado,
            visible=False,
        )
        self.txt_resumen = ft.Text(
            tr("summary.none_yet"),
            size=12,
            color=ft.Colors.OUTLINE,
        )
        self.btn_copiar_resultado = ft.OutlinedButton(
            content=tr("btn.copy"),
            icon=ft.Icons.CONTENT_COPY,
            on_click=self._on_copiar_resultado,
            disabled=True,
        )

        self.txt_aviso_mapa = ft.Text("", size=12, color=ft.Colors.AMBER_900, expand=True)
        self.aviso_mapa = ft.Container(
            visible=False,
            padding=12,
            border_radius=12,
            bgcolor=ft.Colors.AMBER_50,
            content=ft.Row(
                controls=[
                    ft.Icon(ft.Icons.KEY_OUTLINED, color=ft.Colors.AMBER_900, size=20),
                    self.txt_aviso_mapa,
                ],
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
        )
        self.btn_exportar_diccionario = ft.OutlinedButton(
            content=tr("btn.export"),
            icon=ft.Icons.SAVE_ALT_OUTLINED,
            on_click=self._on_guardar_diccionario,
        )
        self.menu_clave = ft.PopupMenuButton(
            content=ft.Container(
                padding=ft.Padding.symmetric(horizontal=12, vertical=9),
                border_radius=20,
                border=ft.Border.all(1, ft.Colors.OUTLINE),
                content=ft.Row(
                    controls=[
                        ft.Icon(ft.Icons.KEY_OUTLINED, size=18),
                        ft.Text(tr("menu.key"), size=13),
                        ft.Icon(ft.Icons.ARROW_DROP_DOWN, size=18),
                    ],
                    spacing=6,
                    tight=True,
                ),
            ),
            items=[],
        )
        self._actualizar_menu_clave()

        selector_idioma_ui = ft.PopupMenuButton(
            tooltip=tr("ui.language_tooltip"),
            content=ft.Container(
                padding=ft.Padding.symmetric(horizontal=12, vertical=7),
                border_radius=999,
                bgcolor=ft.Colors.WHITE_12,
                content=ft.Row(
                    controls=[
                        ft.Icon(ft.Icons.LANGUAGE, color=ft.Colors.WHITE, size=16),
                        ft.Text(
                            get_language().upper(),
                            size=11,
                            weight=ft.FontWeight.BOLD,
                            color=ft.Colors.WHITE,
                        ),
                    ],
                    spacing=6,
                ),
            ),
            items=[
                ft.PopupMenuItem(
                    content=nombre,
                    data=codigo,
                    on_click=self._on_cambiar_idioma_ui,
                )
                for codigo, nombre in UI_LANGUAGES.items()
            ],
        )

        self.cabecera = ft.Container(
            gradient=G_MARCA,
            padding=ft.Padding.symmetric(horizontal=28, vertical=20),
            content=ft.Row(
                controls=[
                    ft.Container(
                        width=46,
                        height=46,
                        border_radius=14,
                        bgcolor=ft.Colors.WHITE_12,
                        alignment=ft.Alignment.CENTER,
                        content=ft.Image(
                            src=LOGO_BYTES,
                            width=38,
                            height=38,
                            fit=ft.BoxFit.CONTAIN,
                            semantics_label="CloakText",
                        ),
                    ),
                    ft.Column(
                        controls=[
                            ft.Text(
                                "CloakText",
                                size=23,
                                weight=ft.FontWeight.BOLD,
                                color=ft.Colors.WHITE,
                            ),
                            ft.Text(
                                tr("app.tagline"),
                                size=12,
                                color=ft.Colors.WHITE_70,
                            ),
                        ],
                        spacing=2,
                    ),
                    ft.Container(expand=True),
                    selector_idioma_ui,
                    ft.Container(
                        padding=ft.Padding.symmetric(horizontal=12, vertical=7),
                        border_radius=999,
                        bgcolor=ft.Colors.WHITE_12,
                        content=ft.Row(
                            controls=[
                                ft.Icon(ft.Icons.LOCK_OUTLINE, color=ft.Colors.WHITE, size=16),
                                ft.Text(
                                    tr("app.badge_local"),
                                    size=11,
                                    weight=ft.FontWeight.BOLD,
                                    color=ft.Colors.WHITE,
                                ),
                            ],
                            spacing=6,
                        ),
                    ),
                ],
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                spacing=12,
            ),
        )

        selector_modo = ft.Container(
            padding=6,
            border_radius=14,
            bgcolor=ft.Colors.SURFACE_CONTAINER,
            content=ft.Row(
                controls=[self.btn_modo_anon, self.btn_modo_resta],
                spacing=6,
            ),
        )

        self.estado_modelo = ft.Row(
            controls=[
                ft.Row(
                    controls=[
                        ft.Icon(ft.Icons.MEMORY_OUTLINED, size=17, color=ft.Colors.OUTLINE),
                        self.txt_estado_modelo,
                    ],
                    spacing=7,
                ),
                self.btn_modelo,
            ],
            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        )

        card_entrada = self._card(
            tr("card.input_title"),
            tr("card.input_sub"),
            ft.Column(
                controls=[
                    ft.Row(
                        controls=[self.dd_idioma, ft.Container(expand=True), selector_modo],
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                    self.txt_entrada,
                    ft.Row(
                        controls=[self.btn_terminos, ft.Container(expand=True), self.txt_contador],
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                    self.txt_terminos,
                    ft.Row(
                        controls=[
                            self.txt_clave_activa,
                            ft.Container(expand=True),
                            self.btn_usar_predeterminado,
                            self.btn_cargar_diccionario,
                        ],
                        alignment=ft.MainAxisAlignment.END,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                        visible=True,
                    ),
                    self.barra_progreso,
                    ft.Row(
                        controls=[
                            self.txt_estado_proceso,
                            ft.Container(expand=True),
                            self.btn_limpiar_texto,
                            self.btn_limpiar_json,
                            self.btn_ejecutar,
                        ],
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                    ft.Divider(height=1),
                    self.estado_modelo,
                ],
                horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
                spacing=14,
            ),
        )
        card_entrada.col = {"xs": 12, "lg": 6}

        card_resultado = self._card(
            tr("card.result_title"),
            tr("card.result_sub"),
            ft.Column(
                controls=[
                    self.sw_resaltar,
                    self.txt_resultado,
                    self.vista_resaltada,
                    ft.Row(
                        controls=[
                            self.txt_resumen,
                            ft.Container(expand=True),
                            self.btn_copiar_resultado,
                        ],
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                    self.aviso_mapa,
                    ft.Row(
                        controls=[self.menu_clave, ft.Container(expand=True), self.btn_exportar_diccionario],
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                ],
                horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
                spacing=14,
            ),
        )
        card_resultado.col = {"xs": 12, "lg": 6}

        pie = ft.Row(
            controls=[
                ft.Text(
                    f"CloakText {__version__}",
                    size=11,
                    color=ft.Colors.OUTLINE,
                ),
                ft.Container(expand=True),
                ft.Text(
                    tr("app.footer"),
                    size=11,
                    color=ft.Colors.OUTLINE,
                ),
            ],
        )

        self.page.add(
            self.cabecera,
            ft.Container(
                expand=True,
                padding=ft.Padding.symmetric(horizontal=24, vertical=20),
                content=ft.Column(
                    controls=[
                        ft.Container(
                            content=ft.Text(
                                tr("app.intro"),
                                size=12,
                                color=ft.Colors.OUTLINE,
                            ),
                        ),
                        ft.ResponsiveRow(
                            controls=[card_entrada, card_resultado],
                            spacing=18,
                            run_spacing=18,
                        ),
                        pie,
                    ],
                    spacing=16,
                    scroll=ft.ScrollMode.AUTO,
                ),
            ),
        )

        self._sincronizar_modo_ui()
        self._refrescar_estado_modelo()

    @staticmethod
    def _card(titulo: str, subtitulo: str, contenido: ft.Control) -> ft.Container:
        return ft.Container(
            padding=20,
            border_radius=20,
            bgcolor=ft.Colors.SURFACE_CONTAINER_LOWEST,
            border=ft.Border.all(1, ft.Colors.OUTLINE_VARIANT),
            content=ft.Column(
                controls=[
                    ft.Text(titulo, size=17, weight=ft.FontWeight.BOLD),
                    ft.Text(subtitulo, size=12, color=ft.Colors.OUTLINE),
                    ft.Divider(height=1),
                    contenido,
                ],
                spacing=10,
            ),
        )

    def _cambiar_modo(self, modo: str) -> None:
        if self._busy or modo == self.modo:
            return
        self.modo = modo
        self._sincronizar_modo_ui()
        self.page.update()

    def _sincronizar_modo_ui(self) -> None:
        en_anon = self.modo == "anon"

        self.btn_modo_anon.style = ft.ButtonStyle(
            bgcolor=C_MARCA if en_anon else ft.Colors.TRANSPARENT,
            color=ft.Colors.WHITE if en_anon else ft.Colors.ON_SURFACE,
        )
        self.btn_modo_resta.style = ft.ButtonStyle(
            bgcolor=C_RESTA if not en_anon else ft.Colors.TRANSPARENT,
            color=ft.Colors.WHITE if not en_anon else ft.Colors.ON_SURFACE,
        )

        self.btn_ejecutar.content = tr("btn.run_protect") if en_anon else tr("btn.run_restore")
        self.btn_ejecutar.icon = (
            ft.Icons.SHIELD_OUTLINED if en_anon else ft.Icons.VISIBILITY_OUTLINED
        )
        self.btn_ejecutar.style = ft.ButtonStyle(
            bgcolor=C_MARCA if en_anon else C_RESTA,
            color=ft.Colors.WHITE,
        )
        self.cabecera.gradient = G_MARCA if en_anon else G_RESTA
        self.dd_idioma.visible = en_anon
        self.estado_modelo.visible = en_anon
        self.btn_terminos.visible = en_anon
        if not en_anon:
            self.txt_terminos.visible = False
        self.txt_entrada.label = tr("field.input_protect") if en_anon else tr("field.input_restore")
        self.txt_entrada.hint_text = (
            tr("hint.input_protect") if en_anon else tr("hint.input_restore")
        )
        self.txt_resultado.label = (
            tr("field.result_protect") if en_anon else tr("field.result_restore")
        )
        self.txt_resultado.hint_text = (
            tr("hint.result_protect") if en_anon else tr("hint.result_restore")
        )
        self.txt_clave_activa.visible = not en_anon
        self.btn_cargar_diccionario.visible = not en_anon
        self.btn_usar_predeterminado.visible = (
            not en_anon and self.mapa_restauracion_personalizado is not None
        )
        self._actualizar_texto_clave_activa()
        self._limpiar_resultado()

    def _on_alternar_terminos(self, _event) -> None:
        self.txt_terminos.visible = not self.txt_terminos.visible
        self.page.update()

    def _terminos_manuales(self) -> list[str]:
        return (self.txt_terminos.value or "").splitlines()

    # ------------------------------------------------- idioma de la interfaz

    def _on_cambiar_idioma_ui(self, event) -> None:
        codigo = event.control.data
        if codigo == get_language() or self._busy:
            return
        set_language(codigo)
        ajustes = load_settings()
        ajustes["ui_language"] = codigo
        save_settings(ajustes)

        entrada = self.txt_entrada.value or ""
        terminos = self.txt_terminos.value or ""
        mostrar_terminos = self.txt_terminos.visible
        modo = self.modo
        self._idioma_texto = self.dd_idioma.value or "es"

        self.page.controls.clear()
        self.modo = "anon"
        self._construir_ui()
        self.txt_entrada.value = entrada
        self.txt_terminos.value = terminos
        self.txt_terminos.visible = mostrar_terminos
        self._actualizar_contador()
        if modo != "anon":
            self._cambiar_modo(modo)
        self.page.update()

    # ----------------------------------------------------------------- clave

    def _cargar_clave(self) -> dict[str, str]:
        return load_key(password=self._password)

    def _guardar_clave(self, mapa: dict[str, str]) -> None:
        save_key_atomic(mapa, password=self._password)

    def _inicializar_clave_predeterminada(self) -> None:
        try:
            if not self.ruta_clave_predeterminada.exists():
                save_key_atomic({})
            elif is_encrypted():
                self._clave_bloqueada = True
            else:
                mapa = load_key()
                self.motor.validar_mapa(mapa)
        except (OSError, ValueError):
            logger.exception("No se pudo inicializar cloaktext.json")
        self._actualizar_menu_clave()

    def _clave_esta_cifrada(self) -> bool:
        return self._password is not None or self._clave_bloqueada

    def _actualizar_texto_aviso_mapa(self) -> None:
        clave = "notice.key_encrypted" if self._clave_esta_cifrada() else "notice.key_plain"
        donde = (
            tr("notice.where_profile", path=str(self.ruta_clave_predeterminada.parent))
            if using_fallback_directory()
            else tr("notice.where_app")
        )
        self.txt_aviso_mapa.value = tr(clave, where=donde)

    def _actualizar_menu_clave(self) -> None:
        if self._clave_esta_cifrada():
            items = [
                ft.PopupMenuItem(
                    content=tr("menu.change_password"),
                    icon=ft.Icons.LOCK_RESET,
                    on_click=self._on_establecer_contrasena,
                ),
                ft.PopupMenuItem(
                    content=tr("menu.remove_password"),
                    icon=ft.Icons.LOCK_OPEN_OUTLINED,
                    on_click=self._on_quitar_contrasena,
                ),
            ]
        else:
            items = [
                ft.PopupMenuItem(
                    content=tr("menu.set_password"),
                    icon=ft.Icons.LOCK_OUTLINE,
                    on_click=self._on_establecer_contrasena,
                )
            ]
        items.append(
            ft.PopupMenuItem(
                content=tr("menu.purge"),
                icon=ft.Icons.AUTO_DELETE_OUTLINED,
                on_click=self._on_limpiar_antiguas,
            )
        )
        self.menu_clave.items = items
        self._actualizar_texto_aviso_mapa()

    def _dialogo_contrasena(
        self,
        titulo: str,
        cuerpo: str,
        etiqueta_boton: str,
        al_confirmar,
        repetir: bool = False,
    ) -> None:
        """Diálogo modal con contraseña. `al_confirmar(pw)` devuelve un error (str) o None."""
        campo = ft.TextField(
            label=tr("pw.field"),
            password=True,
            can_reveal_password=True,
            autofocus=True,
        )
        campo2 = (
            ft.TextField(label=tr("pw.field_confirm"), password=True, can_reveal_password=True)
            if repetir
            else None
        )

        async def confirmar(_event) -> None:
            password = campo.value or ""
            if campo2 is not None:
                if len(password) < MIN_PASSWORD_LENGTH:
                    campo.error = tr("pw.error_short", n=MIN_PASSWORD_LENGTH)
                    self.page.update()
                    return
                if password != (campo2.value or ""):
                    campo2.error = tr("pw.error_mismatch")
                    self.page.update()
                    return
            error = await al_confirmar(password)
            if error:
                campo.error = error
                self.page.update()
                return
            self.page.pop_dialog()
            self.page.update()

        controles: list[ft.Control] = [ft.Text(cuerpo, size=13), campo]
        if campo2 is not None:
            controles.append(campo2)
        campo.on_submit = confirmar
        self.page.show_dialog(
            ft.AlertDialog(
                modal=True,
                title=ft.Text(titulo),
                content=ft.Column(controls=controles, tight=True, spacing=12, width=420),
                actions=[
                    ft.TextButton(content=tr("common.cancel"), on_click=lambda _: self.page.pop_dialog()),
                    ft.Button(content=etiqueta_boton, on_click=confirmar),
                ],
                actions_alignment=ft.MainAxisAlignment.END,
            )
        )

    def _mostrar_desbloqueo(self) -> None:
        async def desbloquear(password: str) -> str | None:
            try:
                mapa = await asyncio.to_thread(load_key, None, password)
                self.motor.validar_mapa(mapa)
            except WrongPasswordError:
                return tr("pw.error_wrong")
            except ValueError as exc:
                return str(exc)
            self._password = password
            self._clave_bloqueada = False
            self._actualizar_menu_clave()
            self._snack(tr("pw.unlocked"))
            return None

        self._dialogo_contrasena(
            tr("pw.unlock_title"),
            tr("pw.unlock_body", name=self.ruta_clave_predeterminada.name),
            tr("pw.unlock_btn"),
            desbloquear,
        )

    async def _on_establecer_contrasena(self, _event) -> None:
        if self._busy:
            return
        if self._clave_bloqueada:
            self._mostrar_desbloqueo()
            return

        async def cifrar(password: str) -> str | None:
            try:
                mapa = await asyncio.to_thread(self._cargar_clave)
                await asyncio.to_thread(save_key_atomic, mapa, None, password)
            except (OSError, ValueError) as exc:
                return str(exc)
            self._password = password
            self._actualizar_menu_clave()
            self._snack(tr("pw.set_done"))
            return None

        self._dialogo_contrasena(
            tr("pw.set_title"),
            tr("pw.set_body"),
            tr("pw.set_btn"),
            cifrar,
            repetir=True,
        )

    def _on_quitar_contrasena(self, _event) -> None:
        if self._busy or self._password is None:
            return

        async def quitar(_e) -> None:
            try:
                mapa = await asyncio.to_thread(self._cargar_clave)
                await asyncio.to_thread(save_key_atomic, mapa)
            except (OSError, ValueError) as exc:
                self._snack(str(exc))
                return
            self._password = None
            self._actualizar_menu_clave()
            self.page.pop_dialog()
            self._snack(tr("pw.remove_done"))

        self.page.show_dialog(
            ft.AlertDialog(
                modal=True,
                icon=ft.Icon(ft.Icons.WARNING_AMBER_ROUNDED, color=ft.Colors.ERROR),
                title=ft.Text(tr("pw.remove_title")),
                content=ft.Text(tr("pw.remove_body")),
                actions=[
                    ft.TextButton(content=tr("common.cancel"), on_click=lambda _: self.page.pop_dialog()),
                    ft.Button(
                        content=tr("pw.remove_btn"),
                        style=ft.ButtonStyle(bgcolor=ft.Colors.ERROR, color=ft.Colors.ON_ERROR),
                        on_click=quitar,
                    ),
                ],
                actions_alignment=ft.MainAxisAlignment.END,
            )
        )

    async def _on_limpiar_antiguas(self, _event) -> None:
        if self._busy:
            return
        if self._clave_bloqueada:
            self._mostrar_desbloqueo()
            return
        try:
            mapa = await asyncio.to_thread(self._cargar_clave)
        except (OSError, ValueError) as exc:
            self._snack(str(exc))
            return
        fechas = stamp_tokens(mapa, load_dates())

        campo = ft.TextField(
            label=tr("purge.days"),
            value="30",
            width=140,
            keyboard_type=ft.KeyboardType.NUMBER,
            input_filter=ft.NumbersOnlyInputFilter(),
            max_length=5,
        )
        resumen = ft.Text("", size=13)

        def dias() -> int | None:
            try:
                return int(campo.value or "")
            except ValueError:
                return None

        def refrescar(_e=None) -> None:
            n = dias()
            if n is None:
                resumen.value = tr("purge.invalid")
            else:
                resumen.value = tr(
                    "purge.count", count=len(find_older_than(fechas, n)), total=len(mapa)
                )
            self.page.update()

        async def eliminar(_e) -> None:
            n = dias()
            if n is None:
                refrescar()
                return
            antiguos = find_older_than(fechas, n)
            nuevo_mapa, nuevas_fechas = purge(mapa, fechas, antiguos)
            try:
                await asyncio.to_thread(self._guardar_clave, nuevo_mapa)
                await asyncio.to_thread(save_dates, nuevas_fechas)
            except (OSError, ValueError) as exc:
                self._snack(str(exc))
                return
            self.mapa_actual = {}
            self.page.pop_dialog()
            self._snack(tr("purge.done", count=len(antiguos)))

        campo.on_change = refrescar
        resumen.value = tr("purge.count", count=len(find_older_than(fechas, 30)), total=len(mapa))
        self.page.show_dialog(
            ft.AlertDialog(
                modal=True,
                title=ft.Text(tr("purge.title")),
                content=ft.Column(
                    controls=[ft.Text(tr("purge.body"), size=13), campo, resumen],
                    tight=True,
                    spacing=12,
                    width=420,
                ),
                actions=[
                    ft.TextButton(content=tr("common.cancel"), on_click=lambda _: self.page.pop_dialog()),
                    ft.Button(
                        content=tr("purge.btn"),
                        icon=ft.Icons.DELETE_FOREVER_OUTLINED,
                        style=ft.ButtonStyle(bgcolor=ft.Colors.ERROR, color=ft.Colors.ON_ERROR),
                        on_click=eliminar,
                    ),
                ],
                actions_alignment=ft.MainAxisAlignment.END,
            )
        )

    # ------------------------------------------------------------ restaurar

    def _actualizar_texto_clave_activa(self) -> None:
        if self.mapa_restauracion_personalizado is not None:
            self.txt_clave_activa.value = tr(
                "restore.active_custom",
                name=self.nombre_clave_personalizada or tr("restore.custom_fallback_name"),
            )
        else:
            self.txt_clave_activa.value = tr("restore.active_default")

    def _on_usar_predeterminado(self, _event) -> None:
        self.mapa_restauracion_personalizado = None
        self.nombre_clave_personalizada = None
        self.btn_usar_predeterminado.visible = False
        self._actualizar_texto_clave_activa()
        self.page.update()
        self._snack(tr("msg.use_default"))

    def _actualizar_contador(self) -> None:
        texto = self.txt_entrada.value or ""
        if not texto:
            self.txt_contador.value = tr("counter.zero")
            return
        lineas = texto.count("\n") + 1
        self.txt_contador.value = tr(
            "counter",
            chars=f"{len(texto):,}".replace(",", "."),
            lines=f"{lineas:,}".replace(",", "."),
        )

    def _on_texto_cambiado(self, _event) -> None:
        self._actualizar_contador()
        self.txt_contador.update()

    def _on_idioma_cambiado(self, _event) -> None:
        seleccionado = self.dd_idioma.value or "es"
        cargado = self.motor.idioma_cargado()
        if cargado is not None and cargado != seleccionado:
            self.motor.descargar_modelo()
        self._refrescar_estado_modelo()
        self.page.update()

    async def _on_accion_modelo(self, _event) -> None:
        if self._busy:
            return
        idioma = self.dd_idioma.value or "es"
        if not self.motor.modelo_disponible(idioma):
            self._mostrar_instalacion_idioma(idioma)

    def _mostrar_instalacion_idioma(self, idioma: str) -> None:
        info = info_modelo(idioma)
        nombre = nombre_idioma(idioma)
        tamano = info.size_bytes / (1024 * 1024)
        dialogo = ft.AlertDialog(
            modal=True,
            title=ft.Text(tr("model.dialog_title", name=nombre)),
            content=ft.Column(
                controls=[
                    ft.Text(tr("model.dialog_body", size=tamano)),
                    ft.Text(
                        tr("model.dialog_note"),
                        size=12,
                        color=ft.Colors.OUTLINE,
                    ),
                    ft.Container(
                        padding=12,
                        border_radius=12,
                        bgcolor=ft.Colors.SURFACE_CONTAINER,
                        content=ft.Text(
                            tr("model.dialog_license", license=info.license),
                            size=12,
                            weight=ft.FontWeight.BOLD,
                        ),
                    ),
                ],
                tight=True,
                spacing=12,
            ),
            actions=[
                ft.TextButton(content=tr("common.cancel"), on_click=lambda _: self.page.pop_dialog()),
                ft.Button(
                    content=tr("btn.prepare_language"),
                    icon=ft.Icons.DOWNLOAD_OUTLINED,
                    data=idioma,
                    on_click=self._on_instalar_idioma,
                ),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
        )
        self.page.show_dialog(dialogo)

    async def _on_instalar_idioma(self, event) -> None:
        idioma = event.control.data
        self.page.pop_dialog()
        nombre = nombre_idioma(idioma)
        self._poner_cargando(True)
        self.txt_estado_proceso.value = tr("model.downloading", name=nombre)
        self.page.update()
        try:
            await asyncio.to_thread(self.motor.instalar_modelo, idioma)
            self.txt_estado_proceso.value = ""
            self._snack(tr("model.installed", name=nombre))
        except Exception:
            logger.exception("No se pudo instalar el paquete de idioma %s", idioma)
            self._snack(tr("model.install_failed"))
        finally:
            self._poner_cargando(False)
            self._refrescar_estado_modelo()
            self.page.update()

    async def _on_copiar_resultado(self, _event) -> None:
        if self.txt_resultado.value:
            await self.clipboard.set(self.txt_resultado.value)
            self._snack(tr("msg.copied"))

    async def _on_guardar_diccionario(self, _event) -> None:
        try:
            mapa = await asyncio.to_thread(self._cargar_clave)
            self.motor.validar_mapa(mapa)
        except KeyEncryptedError:
            self._mostrar_desbloqueo()
            return
        except (OSError, ValueError) as exc:
            self._snack(tr("msg.export_failed", error=exc))
            return

        nombre = f"cloaktext-key-{datetime.now():%Y%m%d-%H%M%S}.json"
        # Si la clave está cifrada, la copia exportada también lo está.
        carga = encrypt_key(mapa, self._password) if self._password else mapa
        contenido = (json.dumps(carga, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
        ruta = await ft.FilePicker().save_file(
            dialog_title=tr("picker.export_title"),
            file_name=nombre,
            file_type=ft.FilePickerFileType.CUSTOM,
            allowed_extensions=["json"],
            src_bytes=contenido,
        )
        if ruta or self.page.web:
            self._snack(tr("msg.export_done"))

    async def _on_cargar_diccionario(self, _event) -> None:
        archivos = await ft.FilePicker().pick_files(
            dialog_title=tr("picker.open_title"),
            allow_multiple=False,
            with_data=True,
            file_type=ft.FilePickerFileType.CUSTOM,
            allowed_extensions=["json"],
        )
        if not archivos:
            return
        archivo = archivos[0]
        datos = archivo.bytes or b""
        if len(datos) > MAX_DICCIONARIO_BYTES:
            self._snack(tr("msg.key_too_big"))
            return
        try:
            bruto = datos.decode("utf-8-sig")
            contenido = json.loads(bruto)
        except (UnicodeDecodeError, json.JSONDecodeError):
            self._snack(tr("msg.custom_invalid"))
            return

        nombre = archivo.name or tr("restore.custom_fallback_name")
        if is_encrypted_envelope(contenido):
            self._pedir_contrasena_clave_personalizada(contenido, nombre)
            return
        try:
            self.motor.validar_mapa(contenido)
        except ValueError:
            self._snack(tr("msg.custom_invalid"))
            return
        self._usar_clave_personalizada(contenido, nombre)

    def _pedir_contrasena_clave_personalizada(self, envoltorio: dict, nombre: str) -> None:
        async def descifrar(password: str) -> str | None:
            try:
                mapa = await asyncio.to_thread(decrypt_key, envoltorio, password)
                self.motor.validar_mapa(mapa)
            except WrongPasswordError:
                return tr("pw.error_wrong")
            except ValueError as exc:
                return str(exc)
            self._usar_clave_personalizada(mapa, nombre)
            return None

        self._dialogo_contrasena(
            tr("pw.unlock_title"),
            tr("pw.unlock_body", name=nombre),
            tr("pw.unlock_btn"),
            descifrar,
        )

    def _usar_clave_personalizada(self, mapa: dict[str, str], nombre: str) -> None:
        self.mapa_restauracion_personalizado = mapa
        self.nombre_clave_personalizada = nombre
        self._actualizar_texto_clave_activa()
        self.btn_usar_predeterminado.visible = True
        self.page.update()
        self._snack(tr("msg.custom_ready", count=len(mapa)))

    # ------------------------------------------------------------- procesar

    async def _on_ejecutar(self, _event) -> None:
        if self._busy:
            return

        texto = self.txt_entrada.value or ""
        if not texto.strip():
            self._snack(tr("msg.enter_text"))
            return

        idioma = self.dd_idioma.value or "es"
        self._poner_cargando(True)

        try:
            if self.modo == "anon":
                await self._ejecutar_anonimizar(texto, idioma)
            else:
                await self._ejecutar_desanonimizar(texto)
        except KeyEncryptedError:
            self._mostrar_desbloqueo()
        except ModeloNoDisponibleError as exc:
            logger.info("Paquete de idioma no instalado: %s", exc.modelo)
            self._mostrar_instalacion_idioma(exc.idioma)
        except ValueError as exc:
            self._snack(str(exc))
        except Exception:
            logger.exception("Error inesperado durante el procesamiento")
            self._snack(tr("msg.process_failed"))
        finally:
            self._poner_cargando(False)
            self._refrescar_estado_modelo()
            self.page.update()

    async def _ejecutar_anonimizar(self, texto: str, idioma: str) -> None:
        self.txt_estado_proceso.value = tr("status.analysing")
        self.page.update()

        mapa = await asyncio.to_thread(self._cargar_clave)
        self.motor.validar_mapa(mapa)

        resultado = await asyncio.to_thread(
            self.motor.anonimizar,
            texto,
            mapa,
            None,
            idioma,
            self._terminos_manuales(),
        )
        await asyncio.to_thread(self._guardar_clave, mapa)
        await asyncio.to_thread(self._registrar_fechas, mapa)

        self.mapa_actual = mapa
        self.txt_resultado.value = resultado
        self._mostrar_resultado(resultado)
        self.aviso_mapa.visible = True
        self.btn_copiar_resultado.disabled = not bool(resultado)

        tokens_actuales = list(TOKEN_TIPO_RE.finditer(resultado))
        conteo = Counter(match.group(1) for match in tokens_actuales)

        if not tokens_actuales:
            self.txt_resumen.value = tr("summary.nothing_found")
        else:
            detalle = " · ".join(f"{tipo}: {cantidad}" for tipo, cantidad in sorted(conteo.items()))
            self.txt_resumen.value = tr("summary.found", count=len(tokens_actuales), detail=detalle)

        self.txt_estado_proceso.value = ""
        uno = len(tokens_actuales) == 1
        self._snack(
            tr(
                "msg.done",
                count=len(tokens_actuales),
                noun=tr("msg.noun_one" if uno else "msg.noun_many"),
                verb=tr("msg.verb_one" if uno else "msg.verb_many"),
            )
        )

    @staticmethod
    def _registrar_fechas(mapa: dict[str, str]) -> None:
        """Anota la fecha de alta de los marcadores nuevos (no crítico)."""
        try:
            save_dates(stamp_tokens(mapa, load_dates()))
        except OSError:
            logger.warning("No se pudieron guardar las fechas de las entradas")

    async def _ejecutar_desanonimizar(self, texto: str) -> None:
        if self.mapa_restauracion_personalizado is not None:
            mapa = self.mapa_restauracion_personalizado
        else:
            mapa = await asyncio.to_thread(self._cargar_clave)
            self.motor.validar_mapa(mapa)

        if not mapa:
            raise ValueError(tr("msg.empty_key"))

        self.txt_estado_proceso.value = tr("status.restoring")
        self.page.update()
        resultado = await asyncio.to_thread(self.motor.desanonimizar, texto, mapa)

        self.txt_resultado.value = resultado
        self._mostrar_resultado(resultado)
        origen = (
            self.nombre_clave_personalizada
            if self.mapa_restauracion_personalizado is not None
            else "cloaktext.json"
        )
        self.txt_resumen.value = tr("summary.restored", source=origen)
        self.aviso_mapa.visible = False
        self.btn_copiar_resultado.disabled = not bool(resultado)
        self.txt_estado_proceso.value = ""
        self._snack(tr("msg.restored"))

    # ------------------------------------------------------------ resultado

    def _mostrar_resultado(self, resultado: str) -> None:
        """Muestra el resultado, con los marcadores resaltados si procede."""
        en_anon = self.modo == "anon"
        self.texto_resaltado.spans = spans_resaltados(resultado) if en_anon else []
        self.sw_resaltar.visible = en_anon and bool(resultado)
        self._aplicar_resaltado()

    def _aplicar_resaltado(self) -> None:
        resaltar = self.sw_resaltar.visible and bool(self.sw_resaltar.value)
        self.vista_resaltada.visible = resaltar
        self.txt_resultado.visible = not resaltar

    def _on_alternar_resaltado(self, _event) -> None:
        self._aplicar_resaltado()
        self.page.update()

    def _on_limpiar_texto(self, _event) -> None:
        if self._busy:
            return
        self.txt_entrada.value = ""
        self.txt_terminos.value = ""
        self._actualizar_contador()
        self._limpiar_resultado()
        self.page.update()

    def _on_limpiar_json(self, _event) -> None:
        if self._busy:
            return
        dialogo = ft.AlertDialog(
            modal=True,
            icon=ft.Icon(ft.Icons.WARNING_AMBER_ROUNDED, color=ft.Colors.ERROR),
            title=ft.Text(tr("dialog.clear_json_title")),
            content=ft.Text(tr("dialog.clear_json_body")),
            actions=[
                ft.TextButton(
                    content=tr("common.cancel"),
                    on_click=lambda _: self.page.pop_dialog(),
                ),
                ft.Button(
                    content=tr("btn.clear_json"),
                    icon=ft.Icons.DELETE_FOREVER_OUTLINED,
                    style=ft.ButtonStyle(
                        bgcolor=ft.Colors.ERROR,
                        color=ft.Colors.ON_ERROR,
                    ),
                    on_click=self._confirmar_limpiar_json,
                ),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
        )
        self.page.show_dialog(dialogo)

    def _confirmar_limpiar_json(self, _event) -> None:
        try:
            self._guardar_clave({})
            save_dates({})
        except OSError:
            logger.exception("No se pudo limpiar cloaktext.json")
            self._snack(tr("msg.json_clear_failed"))
            return
        self.mapa_actual = {}
        self.page.pop_dialog()
        self._snack(tr("msg.json_cleared"))

    def _limpiar_resultado(self) -> None:
        self.mapa_actual = {}
        self.txt_resultado.value = ""
        self.texto_resaltado.spans = []
        self.vista_resaltada.visible = False
        self.txt_resultado.visible = True
        self.sw_resaltar.visible = False
        self.aviso_mapa.visible = False
        self.btn_copiar_resultado.disabled = True
        self.txt_resumen.value = tr("summary.none_yet")
        self.txt_estado_proceso.value = ""

    def _poner_cargando(self, activo: bool) -> None:
        self._busy = activo
        self.barra_progreso.visible = activo
        self.btn_ejecutar.disabled = activo
        self.btn_limpiar_texto.disabled = activo
        self.btn_limpiar_json.disabled = activo
        self.btn_modo_anon.disabled = activo
        self.btn_modo_resta.disabled = activo
        self.dd_idioma.disabled = activo
        self.btn_modelo.disabled = activo
        self.btn_cargar_diccionario.disabled = activo
        self.btn_usar_predeterminado.disabled = activo
        self.btn_exportar_diccionario.disabled = activo
        self.btn_terminos.disabled = activo
        self.menu_clave.disabled = activo
        self.page.update()

    def _refrescar_estado_modelo(self) -> None:
        seleccionado = self.dd_idioma.value or "es"
        nombre = nombre_idioma(seleccionado)
        disponible = self.motor.modelo_disponible(seleccionado)

        if disponible:
            self.txt_estado_modelo.value = tr("model.ready", name=nombre)
            self.txt_estado_modelo.color = ft.Colors.ON_SURFACE
            self.btn_modelo.visible = False
        else:
            self.txt_estado_modelo.value = tr("model.prepare_to_start", name=nombre)
            self.txt_estado_modelo.color = ft.Colors.OUTLINE
            self.btn_modelo.visible = True
            self.btn_modelo.content = tr("btn.prepare_language")
            self.btn_modelo.icon = ft.Icons.DOWNLOAD_OUTLINED
            self.btn_modelo.disabled = self._busy

    async def _actualizar_estado_periodico(self) -> None:
        while True:
            await asyncio.sleep(15)
            try:
                self._refrescar_estado_modelo()
                self.page.update()
            except Exception:
                return

    async def _on_window_event(self, event: ft.WindowEvent) -> None:
        if event.type == ft.WindowEventType.CLOSE:
            self.motor.detener()
            await self.page.window.destroy()

    def _snack(self, mensaje: str) -> None:
        self.page.show_dialog(
            ft.SnackBar(
                content=ft.Text(mensaje),
                behavior=ft.SnackBarBehavior.FLOATING,
                show_close_icon=True,
            )
        )


def main(page: ft.Page) -> None:
    CloakTextApp(page)


if __name__ == "__main__":
    ft.run(main)
