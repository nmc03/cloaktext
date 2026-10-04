"""Interfaz de escritorio de CloakText."""

from __future__ import annotations

import asyncio
from collections import Counter
from datetime import datetime
import json
import logging
import re

import flet as ft

from motor_local import IDIOMAS_SOPORTADOS, ModeloNoDisponibleError, MotorLocal
from language_models import info_modelo
from version import __version__

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

NOMBRES_IDIOMA = {
    "es": "Español",
    "en": "Inglés",
    "fr": "Francés",
    "de": "Alemán",
    "it": "Italiano",
    "pt": "Portugués",
    "ca": "Catalán",
}

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
MAX_DICCIONARIO_BYTES = 10 * 1024 * 1024


class CloakTextApp:
    def __init__(self, page: ft.Page):
        self.page = page
        self.motor = MotorLocal(ttl_minutos=20)
        self.clipboard = ft.Clipboard()
        self.modo = "anon"
        self.mapa_actual: dict[str, str] = {}
        self._busy = False

        self._configurar_pagina()
        self._construir_ui()
        page.run_task(self._actualizar_estado_periodico)

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

    def _construir_ui(self) -> None:
        self.dd_idioma = ft.Dropdown(
            label="Idioma del texto",
            width=220,
            value="es",
            on_select=self._on_idioma_cambiado,
            options=[
                ft.DropdownOption(key=codigo, text=NOMBRES_IDIOMA[codigo])
                for codigo in sorted(IDIOMAS_SOPORTADOS, key=lambda c: NOMBRES_IDIOMA[c])
            ],
        )

        self.txt_estado_modelo = ft.Text(
            "Idioma pendiente",
            size=12,
            color=ft.Colors.OUTLINE,
        )
        self.btn_modelo = ft.OutlinedButton(
            content="Preparar idioma",
            icon=ft.Icons.DOWNLOAD_OUTLINED,
            on_click=self._on_accion_modelo,
            tooltip="Prepara este idioma para reconocer nombres, lugares y organizaciones.",
        )

        self.btn_modo_anon = ft.Button(
            content="Proteger",
            icon=ft.Icons.VISIBILITY_OFF_OUTLINED,
            on_click=lambda _: self._cambiar_modo("anon"),
        )
        self.btn_modo_resta = ft.OutlinedButton(
            content="Restaurar",
            icon=ft.Icons.VISIBILITY_OUTLINED,
            on_click=lambda _: self._cambiar_modo("resta"),
        )

        self.txt_entrada = ft.TextField(
            label="Texto a proteger",
            hint_text="Pega aquí el texto con datos sensibles que quieres proteger…",
            multiline=True,
            min_lines=12,
            max_lines=18,
            autofocus=True,
            on_change=self._on_texto_cambiado,
        )
        self.txt_contador = ft.Text(
            "0 caracteres",
            size=11,
            color=ft.Colors.OUTLINE,
        )

        self.txt_diccionario = ft.TextField(
            label="Clave de restauración (JSON)",
            hint_text='Pega la clave JSON generada por CloakText, por ejemplo {"[PERSONA_1000]": "Ana"}',
            multiline=True,
            min_lines=5,
            max_lines=9,
            visible=False,
        )
        self.btn_cargar_diccionario = ft.OutlinedButton(
            content="Abrir clave JSON",
            icon=ft.Icons.FILE_OPEN_OUTLINED,
            on_click=self._on_cargar_diccionario,
            visible=False,
        )

        self.barra_progreso = ft.ProgressBar(visible=False)
        self.txt_estado_proceso = ft.Text(
            "",
            size=12,
            color=ft.Colors.OUTLINE,
        )

        self.btn_ejecutar = ft.Button(
            content="Proteger datos",
            icon=ft.Icons.SHIELD_OUTLINED,
            on_click=self._on_ejecutar,
        )
        self.btn_limpiar = ft.TextButton(
            content="Limpiar",
            icon=ft.Icons.DELETE_OUTLINE,
            on_click=self._on_limpiar,
        )

        self.txt_resultado = ft.TextField(
            label="Texto protegido",
            hint_text="El resultado aparecerá aquí.",
            multiline=True,
            min_lines=12,
            max_lines=18,
            read_only=True,
        )
        self.txt_resumen = ft.Text(
            "Todavía no se ha procesado ningún texto.",
            size=12,
            color=ft.Colors.OUTLINE,
        )
        self.btn_copiar_resultado = ft.OutlinedButton(
            content="Copiar texto",
            icon=ft.Icons.CONTENT_COPY,
            on_click=self._on_copiar_resultado,
            disabled=True,
        )

        self.txt_mapa_resultado = ft.TextField(
            label="Clave de restauración (JSON)",
            multiline=True,
            min_lines=5,
            max_lines=9,
            read_only=True,
            visible=False,
        )
        self.aviso_mapa = ft.Container(
            visible=False,
            padding=12,
            border_radius=12,
            bgcolor=ft.Colors.AMBER_50,
            content=ft.Row(
                controls=[
                    ft.Icon(ft.Icons.KEY_OUTLINED, color=ft.Colors.AMBER_900, size=20),
                    ft.Text(
                        "La clave contiene los datos originales. Guárdala como información confidencial.",
                        size=12,
                        color=ft.Colors.AMBER_900,
                        expand=True,
                    ),
                ],
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
        )
        self.btn_copiar_diccionario = ft.OutlinedButton(
            content="Copiar clave",
            icon=ft.Icons.CONTENT_COPY,
            on_click=self._on_copiar_diccionario,
            visible=False,
        )
        self.btn_guardar_diccionario = ft.OutlinedButton(
            content="Guardar clave",
            icon=ft.Icons.SAVE_OUTLINED,
            on_click=self._on_guardar_diccionario,
            visible=False,
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
                            src="cloaktext-icon.png",
                            width=38,
                            height=38,
                            fit=ft.BoxFit.CONTAIN,
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
                                "Protección local y reversible para texto sensible",
                                size=12,
                                color=ft.Colors.WHITE_70,
                            ),
                        ],
                        spacing=2,
                    ),
                    ft.Container(expand=True),
                    ft.Container(
                        padding=ft.Padding.symmetric(horizontal=12, vertical=7),
                        border_radius=999,
                        bgcolor=ft.Colors.WHITE_12,
                        content=ft.Row(
                            controls=[
                                ft.Icon(ft.Icons.LOCK_OUTLINE, color=ft.Colors.WHITE, size=16),
                                ft.Text(
                                    "100 % local",
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
            "1. Texto a proteger",
            "Elige el idioma y pega el contenido. El texto nunca se envía fuera del equipo.",
            ft.Column(
                controls=[
                    ft.Row(
                        controls=[self.dd_idioma, ft.Container(expand=True), selector_modo],
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                    self.txt_entrada,
                    ft.Row(
                        controls=[self.txt_contador],
                        alignment=ft.MainAxisAlignment.END,
                    ),
                    self.txt_diccionario,
                    ft.Row(
                        controls=[self.btn_cargar_diccionario],
                        alignment=ft.MainAxisAlignment.END,
                    ),
                    self.barra_progreso,
                    ft.Row(
                        controls=[
                            self.txt_estado_proceso,
                            ft.Container(expand=True),
                            self.btn_limpiar,
                            self.btn_ejecutar,
                        ],
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                    ft.Divider(height=1),
                    self.estado_modelo,
                ],
                spacing=14,
            ),
        )
        card_entrada.col = {"xs": 12, "lg": 6}

        self.fila_acciones_mapa = ft.Row(
            controls=[self.btn_copiar_diccionario, self.btn_guardar_diccionario],
            alignment=ft.MainAxisAlignment.END,
            wrap=True,
            visible=False,
        )

        card_resultado = self._card(
            "2. Texto protegido",
            "Comprueba el resultado antes de compartirlo. CloakText resalta lo que ha protegido automáticamente.",
            ft.Column(
                controls=[
                    self.txt_resultado,
                    ft.Row(
                        controls=[
                            self.txt_resumen,
                            ft.Container(expand=True),
                            self.btn_copiar_resultado,
                        ],
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                    self.aviso_mapa,
                    self.txt_mapa_resultado,
                    self.fila_acciones_mapa,
                ],
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
                    "Local · reversible · sin telemetría de contenido",
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
                                "Protege, revisa y comparte. Tú mantienes el control del texto y de la clave.",
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

        self.btn_ejecutar.content = "Proteger datos" if en_anon else "Restaurar texto"
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
        self.txt_entrada.label = "Texto a proteger" if en_anon else "Texto protegido"
        self.txt_entrada.hint_text = (
            "Pega aquí el texto que quieres proteger…"
            if en_anon
            else "Pega aquí el texto protegido que quieres restaurar…"
        )
        self.txt_resultado.label = "Texto protegido" if en_anon else "Texto restaurado"
        self.txt_resultado.hint_text = (
            "El texto listo para compartir aparecerá aquí."
            if en_anon
            else "El texto restaurado aparecerá aquí."
        )
        self.txt_diccionario.visible = not en_anon
        self.btn_cargar_diccionario.visible = not en_anon
        self._limpiar_resultado()

    def _on_texto_cambiado(self, _event) -> None:
        texto = self.txt_entrada.value or ""
        lineas = texto.count("\n") + (1 if texto else 0)
        self.txt_contador.value = f"{len(texto):,} caracteres · {lineas:,} líneas".replace(",", ".")
        self.txt_contador.update()

    def _on_idioma_cambiado(self, _event) -> None:
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
        nombre = NOMBRES_IDIOMA.get(idioma, idioma)
        tamano = info.size_bytes / (1024 * 1024)
        dialogo = ft.AlertDialog(
            modal=True,
            title=ft.Text(f"Preparar {nombre}"),
            content=ft.Column(
                controls=[
                    ft.Text(
                        f"CloakText necesita un paquete de idioma de {tamano:.1f} MB "
                        "para reconocer personas, lugares y organizaciones."
                    ),
                    ft.Text(
                        "Se descargará una sola vez desde el repositorio oficial de spaCy. "
                        "Después, el análisis del texto seguirá siendo local y podrá funcionar sin conexión.",
                        size=12,
                        color=ft.Colors.OUTLINE,
                    ),
                    ft.Container(
                        padding=12,
                        border_radius=12,
                        bgcolor=ft.Colors.SURFACE_CONTAINER,
                        content=ft.Text(
                            f"Licencia del paquete: {info.license}",
                            size=12,
                            weight=ft.FontWeight.BOLD,
                        ),
                    ),
                ],
                tight=True,
                spacing=12,
            ),
            actions=[
                ft.TextButton(content="Cancelar", on_click=lambda _: self.page.pop_dialog()),
                ft.Button(
                    content="Preparar idioma",
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
        nombre = NOMBRES_IDIOMA.get(idioma, idioma)
        self._poner_cargando(True)
        self.txt_estado_proceso.value = f"Descargando el paquete de {nombre}…"
        self.page.update()
        try:
            await asyncio.to_thread(self.motor.instalar_modelo, idioma)
            self.txt_estado_proceso.value = ""
            self._snack(f"{nombre} está listo. Ya puedes proteger el texto sin conexión.")
        except Exception:
            logger.exception("No se pudo instalar el paquete de idioma %s", idioma)
            self._snack(
                "No se pudo instalar el paquete de idioma. "
                "Comprueba la conexión e inténtalo de nuevo."
            )
        finally:
            self._poner_cargando(False)
            self._refrescar_estado_modelo()
            self.page.update()

    async def _on_copiar_resultado(self, _event) -> None:
        if self.txt_resultado.value:
            await self.clipboard.set(self.txt_resultado.value)
            self._snack("Texto protegido copiado.")

    async def _on_copiar_diccionario(self, _event) -> None:
        if self.txt_mapa_resultado.value:
            await self.clipboard.set(self.txt_mapa_resultado.value)
            self._snack("Clave copiada. Recuerda que contiene datos originales.")

    async def _on_guardar_diccionario(self, _event) -> None:
        if not self.txt_mapa_resultado.value:
            return
        nombre = f"cloaktext-clave-{datetime.now():%Y%m%d-%H%M%S}.json"
        ruta = await ft.FilePicker().save_file(
            dialog_title="Guardar clave de restauración",
            file_name=nombre,
            file_type=ft.FilePickerFileType.CUSTOM,
            allowed_extensions=["json"],
            src_bytes=self.txt_mapa_resultado.value.encode("utf-8"),
        )
        if ruta or self.page.web:
            self._snack("Clave guardada. Consérvala como información confidencial.")

    async def _on_cargar_diccionario(self, _event) -> None:
        archivos = await ft.FilePicker().pick_files(
            dialog_title="Abrir clave de restauración",
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
            self._snack("La clave supera el límite de 10 MB.")
            return
        try:
            bruto = datos.decode("utf-8-sig")
            mapa = json.loads(bruto)
            self.motor.validar_mapa(mapa)
        except (UnicodeDecodeError, json.JSONDecodeError, ValueError):
            self._snack("El archivo no contiene una clave válida de CloakText.")
            return

        self.txt_diccionario.value = json.dumps(mapa, ensure_ascii=False, indent=2)
        self.txt_diccionario.update()
        self._snack(f"Clave cargada: {len(mapa)} elementos.")

    async def _on_ejecutar(self, _event) -> None:
        if self._busy:
            return

        texto = self.txt_entrada.value or ""
        if not texto.strip():
            self._snack("Introduce un texto antes de procesarlo.")
            return

        idioma = self.dd_idioma.value or "es"
        self._poner_cargando(True)

        try:
            if self.modo == "anon":
                await self._ejecutar_anonimizar(texto, idioma)
            else:
                await self._ejecutar_desanonimizar(texto)
        except ModeloNoDisponibleError as exc:
            logger.info("Paquete de idioma no instalado: %s", exc.modelo)
            self._mostrar_instalacion_idioma(exc.idioma)
        except ValueError as exc:
            self._snack(str(exc))
        except Exception:
            logger.exception("Error inesperado durante el procesamiento")
            self._snack("No se ha podido procesar el texto. Revisa los datos e inténtalo de nuevo.")
        finally:
            self._poner_cargando(False)
            self._refrescar_estado_modelo()
            self.page.update()

    async def _ejecutar_anonimizar(self, texto: str, idioma: str) -> None:
        self.txt_estado_proceso.value = "Analizando texto…"
        self.page.update()

        mapa: dict[str, str] = {}
        resultado = await asyncio.to_thread(
            self.motor.anonimizar,
            texto,
            mapa,
            None,
            idioma,
        )

        self.mapa_actual = mapa
        self.txt_resultado.value = resultado
        self.txt_mapa_resultado.value = json.dumps(mapa, ensure_ascii=False, indent=2)
        self.txt_mapa_resultado.visible = bool(mapa)
        self.aviso_mapa.visible = bool(mapa)
        self.btn_copiar_diccionario.visible = bool(mapa)
        self.btn_guardar_diccionario.visible = bool(mapa)
        self.fila_acciones_mapa.visible = bool(mapa)
        self.btn_copiar_resultado.disabled = not bool(resultado)

        conteo = Counter()
        for token in mapa:
            match = TOKEN_TIPO_RE.fullmatch(token)
            if match:
                conteo[match.group(1)] += 1

        if not mapa:
            self.txt_resumen.value = "No se han detectado datos sensibles automáticamente. Revisa el texto antes de compartirlo."
        else:
            detalle = " · ".join(f"{tipo}: {cantidad}" for tipo, cantidad in sorted(conteo.items()))
            self.txt_resumen.value = f"{len(mapa)} datos protegidos · {detalle}"

        self.txt_estado_proceso.value = ""
        self._snack(
            f"Proceso terminado: {len(mapa)} dato{'s' if len(mapa) != 1 else ''} protegido"
            f"{'s' if len(mapa) != 1 else ''}."
        )

    async def _ejecutar_desanonimizar(self, texto: str) -> None:
        bruto = (self.txt_diccionario.value or "").strip()
        if not bruto:
            self._snack("Abre o pega la clave JSON creada al proteger el texto.")
            return
        if len(bruto.encode("utf-8")) > MAX_DICCIONARIO_BYTES:
            raise ValueError("La clave supera el límite de 10 MB.")

        try:
            mapa = json.loads(bruto)
        except json.JSONDecodeError as exc:
            raise ValueError("La clave no contiene un JSON válido.") from exc

        self.motor.validar_mapa(mapa)
        self.txt_estado_proceso.value = "Restaurando texto…"
        self.page.update()
        resultado = await asyncio.to_thread(self.motor.desanonimizar, texto, mapa)

        self.txt_resultado.value = resultado
        self.txt_resumen.value = f"Texto restaurado con {len(mapa)} elementos de la clave."
        self.txt_mapa_resultado.visible = False
        self.aviso_mapa.visible = False
        self.fila_acciones_mapa.visible = False
        self.btn_copiar_diccionario.visible = False
        self.btn_guardar_diccionario.visible = False
        self.btn_copiar_resultado.disabled = not bool(resultado)
        self.txt_estado_proceso.value = ""
        self._snack("Texto restaurado.")

    def _on_limpiar(self, _event) -> None:
        if self._busy:
            return
        self.txt_entrada.value = ""
        self.txt_diccionario.value = ""
        self.txt_contador.value = "0 caracteres"
        self._limpiar_resultado()
        self.page.update()

    def _limpiar_resultado(self) -> None:
        self.mapa_actual = {}
        self.txt_resultado.value = ""
        self.txt_mapa_resultado.value = ""
        self.txt_mapa_resultado.visible = False
        self.aviso_mapa.visible = False
        self.fila_acciones_mapa.visible = False
        self.btn_copiar_diccionario.visible = False
        self.btn_guardar_diccionario.visible = False
        self.btn_copiar_resultado.disabled = True
        self.txt_resumen.value = "Todavía no se ha procesado ningún texto."
        self.txt_estado_proceso.value = ""

    def _poner_cargando(self, activo: bool) -> None:
        self._busy = activo
        self.barra_progreso.visible = activo
        self.btn_ejecutar.disabled = activo
        self.btn_limpiar.disabled = activo
        self.btn_modo_anon.disabled = activo
        self.btn_modo_resta.disabled = activo
        self.dd_idioma.disabled = activo
        self.btn_modelo.disabled = activo
        self.btn_cargar_diccionario.disabled = activo
        self.page.update()

    def _refrescar_estado_modelo(self) -> None:
        seleccionado = self.dd_idioma.value or "es"
        nombre = NOMBRES_IDIOMA.get(seleccionado, seleccionado)
        disponible = self.motor.modelo_disponible(seleccionado)

        if disponible:
            self.txt_estado_modelo.value = f"{nombre} listo"
            self.txt_estado_modelo.color = ft.Colors.ON_SURFACE
            self.btn_modelo.visible = False
        else:
            self.txt_estado_modelo.value = f"Prepara {nombre} para empezar"
            self.txt_estado_modelo.color = ft.Colors.OUTLINE
            self.btn_modelo.visible = True
            self.btn_modelo.content = "Preparar idioma"
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
