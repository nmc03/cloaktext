"""Desktop interface of CloakText."""

from __future__ import annotations

import asyncio
from collections import Counter
from datetime import datetime
import json
import logging
import re

import flet as ft

from branding import LOGO_BYTES
from i18n import UI_LANGUAGES, format_number, get_language, resolve_language, set_language, tr, tr_count
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
from language_packs import model_info
from local_engine import SUPPORTED_LANGUAGES, ModelUnavailableError, LocalEngine
from version import __version__

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

C_BRAND = ft.Colors.BLUE_700
C_BRAND_DARK = ft.Colors.BLUE_900
C_RESTORE = ft.Colors.TEAL_600
C_RESTORE_DARK = ft.Colors.TEAL_800

G_BRAND = ft.LinearGradient(
    begin=ft.Alignment.TOP_LEFT,
    end=ft.Alignment.BOTTOM_RIGHT,
    colors=[C_BRAND_DARK, ft.Colors.CYAN_600],
)
G_RESTORE = ft.LinearGradient(
    begin=ft.Alignment.TOP_LEFT,
    end=ft.Alignment.BOTTOM_RIGHT,
    colors=[C_RESTORE_DARK, ft.Colors.GREEN_600],
)

TOKEN_TYPE_RE = re.compile(r"\[([A-Z][A-Z0-9_]*)_\d+\]")
HIGHLIGHT_TOKEN_RE = re.compile(r"(\[[A-Z][A-Z0-9_]*_\d+\])")
MAX_CUSTOM_KEY_BYTES = 10 * 1024 * 1024


def language_name(code: str) -> str:
    return tr(f"lang.{code}")


def highlighted_spans(text: str) -> list[ft.TextSpan]:
    """Split `text`, highlighting the `[TYPE_1000]` markers."""
    highlight_style = ft.TextStyle(
        bgcolor=ft.Colors.PRIMARY_CONTAINER,
        color=ft.Colors.ON_PRIMARY_CONTAINER,
        weight=ft.FontWeight.BOLD,
    )
    spans: list[ft.TextSpan] = []
    for piece in HIGHLIGHT_TOKEN_RE.split(text):
        if not piece:
            continue
        if HIGHLIGHT_TOKEN_RE.fullmatch(piece):
            spans.append(ft.TextSpan(piece, style=highlight_style))
        else:
            spans.append(ft.TextSpan(piece))
    return spans


class CloakTextApp:
    def __init__(self, page: ft.Page):
        self.page = page
        set_language(resolve_language(load_settings().get("ui_language")))
        self.engine = LocalEngine(ttl_minutes=20)
        self.clipboard = ft.Clipboard()
        self.mode = "protect"
        self.current_mapping: dict[str, str] = {}
        self.custom_restore_mapping: dict[str, str] | None = None
        self.custom_key_name: str | None = None
        self.default_key_file = default_key_path()
        self._busy = False
        self._password: str | None = None
        self._key_locked = False

        self._configure_page()
        self._build_ui()
        self._init_default_key()
        page.run_task(self._periodic_status_refresh)
        if self._key_locked:
            self._show_unlock()

    def _configure_page(self) -> None:
        self.page.title = "CloakText"
        self.page.theme_mode = ft.ThemeMode.SYSTEM
        self.page.theme = ft.Theme(
            color_scheme_seed=C_BRAND,
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

    def _build_ui(self) -> None:
        self.dd_language = ft.Dropdown(
            label=tr("lang.label"),
            width=220,
            value=getattr(self, "_text_language", "es"),
            on_select=self._on_language_changed,
            options=[
                ft.DropdownOption(key=code, text=language_name(code))
                for code in sorted(SUPPORTED_LANGUAGES, key=language_name)
            ],
        )

        self.txt_model_status = ft.Text(
            tr("model.pending"),
            size=12,
            color=ft.Colors.OUTLINE,
        )
        self.btn_model = ft.OutlinedButton(
            content=tr("btn.prepare_language"),
            icon=ft.Icons.DOWNLOAD_OUTLINED,
            on_click=self._on_model_action,
        )

        self.btn_mode_protect = ft.Button(
            content=tr("mode.protect"),
            icon=ft.Icons.VISIBILITY_OFF_OUTLINED,
            on_click=lambda _: self._switch_mode("protect"),
        )
        self.btn_mode_restore = ft.OutlinedButton(
            content=tr("mode.restore"),
            icon=ft.Icons.VISIBILITY_OUTLINED,
            on_click=lambda _: self._switch_mode("restore"),
        )

        self.txt_input = ft.TextField(
            label=tr("field.input_protect"),
            margin=ft.Margin.symmetric(horizontal=4, vertical=2),
            hint_text=tr("hint.input_protect"),
            multiline=True,
            min_lines=12,
            max_lines=18,
            autofocus=True,
            on_change=self._on_text_changed,
            on_selection_change=self._on_selection_changed,
        )
        self.txt_counter = ft.Text(
            tr("counter.zero"),
            size=11,
            color=ft.Colors.OUTLINE,
        )
        self._selection = ""
        self.btn_selection = ft.TextButton(
            content=tr("terms.add_selection"),
            icon=ft.Icons.ADD_CIRCLE_OUTLINE,
            on_click=self._on_protect_selection,
        )
        self.btn_terms = ft.TextButton(
            content=tr("terms.toggle"),
            icon=ft.Icons.EDIT_NOTE_OUTLINED,
            on_click=self._on_toggle_terms,
        )
        self.txt_terms = ft.TextField(
            label=tr("terms.label"),
            hint_text=tr("terms.hint"),
            multiline=True,
            min_lines=3,
            max_lines=6,
            visible=False,
        )

        self.txt_active_key = ft.Text(
            tr("restore.active_default"),
            size=12,
            color=ft.Colors.OUTLINE,
            visible=False,
        )
        self.btn_load_key_file = ft.OutlinedButton(
            content=tr("btn.other_json"),
            icon=ft.Icons.FILE_OPEN_OUTLINED,
            on_click=self._on_load_key_file,
            visible=False,
        )
        self.btn_use_default = ft.TextButton(
            content=tr("btn.default_json"),
            icon=ft.Icons.RESTART_ALT,
            on_click=self._on_use_default,
            visible=False,
        )

        self.progress_bar = ft.ProgressBar(visible=False)
        self.txt_process_status = ft.Text(
            "",
            size=12,
            color=ft.Colors.OUTLINE,
        )

        self.btn_run = ft.Button(
            content=tr("btn.run_protect"),
            icon=ft.Icons.SHIELD_OUTLINED,
            on_click=self._on_run,
        )
        self.btn_clear_text = ft.OutlinedButton(
            content=tr("common.clear"),
            icon=ft.Icons.CLEAR_ALL_OUTLINED,
            on_click=self._on_clear_text,
        )
        self.btn_clear_json = ft.TextButton(
            content=tr("btn.clear_json"),
            icon=ft.Icons.DELETE_FOREVER_OUTLINED,
            on_click=self._on_clear_json,
            style=ft.ButtonStyle(color=ft.Colors.ERROR),
        )

        self.txt_result = ft.TextField(
            label=tr("field.result_protect"),
            margin=ft.Margin.symmetric(horizontal=4, vertical=2),
            hint_text=tr("hint.result_protect"),
            multiline=True,
            min_lines=12,
            max_lines=18,
            read_only=True,
        )
        self.highlighted_text = ft.Text("", selectable=True, size=14)
        self.highlight_view = ft.Container(
            visible=False,
            height=318,
            padding=14,
            margin=ft.Margin.symmetric(horizontal=4, vertical=2),
            border=ft.Border.all(1, ft.Colors.OUTLINE),
            border_radius=4,
            content=ft.Column(controls=[self.highlighted_text], scroll=ft.ScrollMode.AUTO),
        )
        self.sw_highlight = ft.Switch(
            label=tr("highlight.switch"),
            value=True,
            on_change=self._on_toggle_highlight,
            visible=False,
        )
        self.txt_summary = ft.Text(
            tr("summary.none_yet"),
            size=12,
            color=ft.Colors.OUTLINE,
        )
        self.btn_copy_result = ft.OutlinedButton(
            content=tr("btn.copy"),
            icon=ft.Icons.CONTENT_COPY,
            on_click=self._on_copy_result,
            disabled=True,
        )

        self.txt_key_notice = ft.Text("", size=12, color=ft.Colors.AMBER_900, expand=True)
        self.key_notice = ft.Container(
            visible=False,
            padding=12,
            border_radius=12,
            bgcolor=ft.Colors.AMBER_50,
            content=ft.Row(
                controls=[
                    ft.Icon(ft.Icons.KEY_OUTLINED, color=ft.Colors.AMBER_900, size=20),
                    self.txt_key_notice,
                ],
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
        )
        self.btn_export_key = ft.OutlinedButton(
            content=tr("btn.export"),
            icon=ft.Icons.SAVE_ALT_OUTLINED,
            on_click=self._on_export_key,
        )
        self.key_menu = ft.PopupMenuButton(
            tooltip=tr("menu.key"),
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
        self._update_key_menu()

        ui_language_selector = ft.PopupMenuButton(
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
                    content=name,
                    data=code,
                    on_click=self._on_change_ui_language,
                )
                for code, name in UI_LANGUAGES.items()
            ],
        )

        self.header = ft.Container(
            gradient=G_BRAND,
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
                    ui_language_selector,
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

        mode_selector = ft.Container(
            padding=6,
            border_radius=14,
            bgcolor=ft.Colors.SURFACE_CONTAINER,
            content=ft.Row(
                controls=[self.btn_mode_protect, self.btn_mode_restore],
                spacing=6,
            ),
        )

        self.model_status = ft.Row(
            controls=[
                ft.Row(
                    controls=[
                        ft.Icon(ft.Icons.MEMORY_OUTLINED, size=17, color=ft.Colors.OUTLINE),
                        self.txt_model_status,
                    ],
                    spacing=7,
                ),
                self.btn_model,
            ],
            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        )

        # Card titles live in attributes so they can follow the protect/restore mode.
        self.input_card_title = ft.Text(tr("card.input_title"), size=17, weight=ft.FontWeight.BOLD)
        self.input_card_sub = ft.Text(tr("card.input_sub"), size=12, color=ft.Colors.OUTLINE)
        self.result_card_title = ft.Text(tr("card.result_title"), size=17, weight=ft.FontWeight.BOLD)
        self.result_card_sub = ft.Text(tr("card.result_sub"), size=12, color=ft.Colors.OUTLINE)

        input_card = self._card(
            self.input_card_title,
            self.input_card_sub,
            ft.Column(
                controls=[
                    # Rows wrap instead of clipping: translated labels (German, French...)
                    # are longer than the English ones.
                    ft.Row(
                        controls=[self.dd_language, mode_selector],
                        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                        wrap=True,
                        run_spacing=8,
                    ),
                    self.txt_input,
                    ft.Row(
                        controls=[
                            ft.Row(controls=[self.btn_selection, self.btn_terms], wrap=True, spacing=0),
                            self.txt_counter,
                        ],
                        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                        wrap=True,
                        run_spacing=4,
                    ),
                    self.txt_terms,
                    ft.Row(
                        controls=[
                            self.txt_active_key,
                            ft.Row(controls=[self.btn_use_default, self.btn_load_key_file], wrap=True),
                        ],
                        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                        wrap=True,
                        run_spacing=8,
                    ),
                    self.progress_bar,
                    ft.Row(
                        controls=[
                            self.txt_process_status,
                            ft.Row(
                                controls=[self.btn_clear_text, self.btn_clear_json, self.btn_run],
                                wrap=True,
                                alignment=ft.MainAxisAlignment.END,
                            ),
                        ],
                        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                        wrap=True,
                        run_spacing=8,
                    ),
                    ft.Divider(height=1),
                    self.model_status,
                ],
                horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
                spacing=14,
            ),
        )
        input_card.col = {"xs": 12, "lg": 6}

        result_card = self._card(
            self.result_card_title,
            self.result_card_sub,
            ft.Column(
                controls=[
                    self.sw_highlight,
                    self.txt_result,
                    self.highlight_view,
                    ft.Row(
                        controls=[self.txt_summary, self.btn_copy_result],
                        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                        wrap=True,
                        run_spacing=8,
                    ),
                    self.key_notice,
                    ft.Row(
                        controls=[self.key_menu, self.btn_export_key],
                        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                        wrap=True,
                        run_spacing=8,
                    ),
                ],
                horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
                spacing=14,
            ),
        )
        result_card.col = {"xs": 12, "lg": 6}

        footer = ft.Row(
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
            self.header,
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
                            controls=[input_card, result_card],
                            spacing=18,
                            run_spacing=18,
                        ),
                        footer,
                    ],
                    spacing=16,
                    scroll=ft.ScrollMode.AUTO,
                ),
            ),
        )

        self._sync_mode_ui()
        self._refresh_model_status()

    @staticmethod
    def _card(title: ft.Text, subtitle: ft.Text, body: ft.Control) -> ft.Container:
        return ft.Container(
            padding=20,
            border_radius=20,
            bgcolor=ft.Colors.SURFACE_CONTAINER_LOWEST,
            border=ft.Border.all(1, ft.Colors.OUTLINE_VARIANT),
            content=ft.Column(
                controls=[
                    title,
                    subtitle,
                    ft.Divider(height=1),
                    body,
                ],
                spacing=10,
            ),
        )

    def _switch_mode(self, mode: str) -> None:
        if self._busy or mode == self.mode:
            return
        self.mode = mode
        self._sync_mode_ui()
        self.page.update()

    def _sync_mode_ui(self) -> None:
        is_protect_mode = self.mode == "protect"

        self.btn_mode_protect.style = ft.ButtonStyle(
            bgcolor=C_BRAND if is_protect_mode else ft.Colors.TRANSPARENT,
            color=ft.Colors.WHITE if is_protect_mode else ft.Colors.ON_SURFACE,
        )
        self.btn_mode_restore.style = ft.ButtonStyle(
            bgcolor=C_RESTORE if not is_protect_mode else ft.Colors.TRANSPARENT,
            color=ft.Colors.WHITE if not is_protect_mode else ft.Colors.ON_SURFACE,
        )

        self.btn_run.content = tr("btn.run_protect") if is_protect_mode else tr("btn.run_restore")
        self.btn_run.icon = (
            ft.Icons.SHIELD_OUTLINED if is_protect_mode else ft.Icons.VISIBILITY_OUTLINED
        )
        self.btn_run.style = ft.ButtonStyle(
            bgcolor=C_BRAND if is_protect_mode else C_RESTORE,
            color=ft.Colors.WHITE,
        )
        self.header.gradient = G_BRAND if is_protect_mode else G_RESTORE
        self.dd_language.visible = is_protect_mode
        self.model_status.visible = is_protect_mode
        self.btn_terms.visible = is_protect_mode
        self.btn_selection.visible = is_protect_mode
        if not is_protect_mode:
            self.txt_terms.visible = False
        self.txt_input.label = tr("field.input_protect") if is_protect_mode else tr("field.input_restore")
        self.txt_input.hint_text = (
            tr("hint.input_protect") if is_protect_mode else tr("hint.input_restore")
        )
        self.txt_result.label = (
            tr("field.result_protect") if is_protect_mode else tr("field.result_restore")
        )
        self.txt_result.hint_text = (
            tr("hint.result_protect") if is_protect_mode else tr("hint.result_restore")
        )
        suffix = "" if is_protect_mode else "_restore"
        self.input_card_title.value = tr(f"card.input_title{suffix}")
        self.input_card_sub.value = tr(f"card.input_sub{suffix}")
        self.result_card_title.value = tr(f"card.result_title{suffix}")
        self.result_card_sub.value = tr(f"card.result_sub{suffix}")
        self.txt_active_key.visible = not is_protect_mode
        self.btn_load_key_file.visible = not is_protect_mode
        self.btn_use_default.visible = (
            not is_protect_mode and self.custom_restore_mapping is not None
        )
        self._update_active_key_text()
        self._clear_result()

    def _on_toggle_terms(self, _event) -> None:
        self.txt_terms.visible = not self.txt_terms.visible
        self.page.update()

    def _on_selection_changed(self, event) -> None:
        # The last non-empty selection is kept: when the button is pressed, the field
        # may lose focus and report an empty selection before the click.
        text = " ".join((getattr(event, "selected_text", "") or "").split())
        if text:
            self._selection = text

    def _on_protect_selection(self, _event) -> None:
        selection = self._selection
        if not selection:
            self._snack(tr("terms.select_first"))
            return
        existing_terms = {" ".join(t.split()).casefold() for t in self._manual_terms()}
        if selection.casefold() in existing_terms:
            self._snack(tr("terms.selection_exists", text=selection))
        else:
            actual = (self.txt_terms.value or "").rstrip("\n")
            self.txt_terms.value = f"{actual}\n{selection}" if actual else selection
            self._snack(tr("terms.selection_added", text=selection))
        self.txt_terms.visible = True
        self._selection = ""
        self.page.update()

    def _manual_terms(self) -> list[str]:
        return (self.txt_terms.value or "").splitlines()

    # ------------------------------------------------- interface language

    def _on_change_ui_language(self, event) -> None:
        code = event.control.data
        if code == get_language() or self._busy:
            return
        set_language(code)
        prefs = load_settings()
        prefs["ui_language"] = code
        save_settings(prefs)

        previous_input = self.txt_input.value or ""
        terms = self.txt_terms.value or ""
        show_terms = self.txt_terms.visible
        mode = self.mode
        self._text_language = self.dd_language.value or "es"

        self.page.controls.clear()
        self.mode = "protect"
        self._build_ui()
        self.txt_input.value = previous_input
        self.txt_terms.value = terms
        self.txt_terms.visible = show_terms
        self._update_counter()
        if mode != "protect":
            self._switch_mode(mode)
        self.page.update()

    # ----------------------------------------------------------------- key

    def _load_key(self) -> dict[str, str]:
        return load_key(password=self._password)

    def _save_key(self, mapping: dict[str, str]) -> None:
        save_key_atomic(mapping, password=self._password)

    def _init_default_key(self) -> None:
        try:
            if not self.default_key_file.exists():
                save_key_atomic({})
            elif is_encrypted():
                self._key_locked = True
            else:
                mapping = load_key()
                self.engine.validate_mapping(mapping)
        except (OSError, ValueError):
            logger.exception("Could not initialize cloaktext.json")
        self._update_key_menu()

    def _key_is_encrypted(self) -> bool:
        return self._password is not None or self._key_locked

    def _update_key_notice(self) -> None:
        key_name = "notice.key_encrypted" if self._key_is_encrypted() else "notice.key_plain"
        where_text = (
            tr("notice.where_profile", path=str(self.default_key_file.parent))
            if using_fallback_directory()
            else tr("notice.where_app")
        )
        self.txt_key_notice.value = tr(key_name, where=where_text)

    def _update_key_menu(self) -> None:
        if self._key_is_encrypted():
            items = [
                ft.PopupMenuItem(
                    content=tr("menu.change_password"),
                    icon=ft.Icons.LOCK_RESET,
                    on_click=self._on_set_password,
                ),
                ft.PopupMenuItem(
                    content=tr("menu.remove_password"),
                    icon=ft.Icons.LOCK_OPEN_OUTLINED,
                    on_click=self._on_remove_password,
                ),
            ]
        else:
            items = [
                ft.PopupMenuItem(
                    content=tr("menu.set_password"),
                    icon=ft.Icons.LOCK_OUTLINE,
                    on_click=self._on_set_password,
                )
            ]
        items.append(
            ft.PopupMenuItem(
                content=tr("menu.purge"),
                icon=ft.Icons.AUTO_DELETE_OUTLINED,
                on_click=self._on_clear_old_entries,
            )
        )
        self.key_menu.items = items
        self._update_key_notice()

    def _password_dialog(
        self,
        title: str,
        message_body: str,
        button_label: str,
        on_confirm,
        repeat: bool = False,
        on_success=None,
    ) -> None:
        """Modal password dialog.

        `on_confirm(password)` returns an error message (str) or None on success. `on_success`
        runs AFTER the dialog is closed: showing a snack bar before `pop_dialog()` would pop
        the snack bar instead of the dialog and leave it open.
        """
        field = ft.TextField(
            label=tr("pw.field"),
            password=True,
            can_reveal_password=True,
            autofocus=True,
        )
        field2 = (
            ft.TextField(label=tr("pw.field_confirm"), password=True, can_reveal_password=True)
            if repeat
            else None
        )

        async def confirm(_event) -> None:
            password = field.value or ""
            field.error = None
            if field2 is not None:
                field2.error = None
            if field2 is not None:
                if len(password) < MIN_PASSWORD_LENGTH:
                    field.error = tr("pw.error_short", n=MIN_PASSWORD_LENGTH)
                    self.page.update()
                    return
                if password != (field2.value or ""):
                    field2.error = tr("pw.error_mismatch")
                    self.page.update()
                    return
            error = await on_confirm(password)
            if error:
                field.error = error
                self.page.update()
                return
            self.page.pop_dialog()
            self.page.update()
            if on_success is not None:
                on_success()

        widgets: list[ft.Control] = [ft.Text(message_body, size=13), field]
        if field2 is not None:
            widgets.append(field2)
        field.on_submit = confirm
        self.page.show_dialog(
            ft.AlertDialog(
                modal=True,
                title=ft.Text(title),
                content=ft.Column(controls=widgets, tight=True, spacing=12, width=420),
                actions=[
                    ft.TextButton(content=tr("common.cancel"), on_click=lambda _: self.page.pop_dialog()),
                    ft.Button(content=button_label, on_click=confirm),
                ],
                actions_alignment=ft.MainAxisAlignment.END,
            )
        )

    def _show_unlock(self) -> None:
        async def do_unlock(password: str) -> str | None:
            try:
                mapping = await asyncio.to_thread(load_key, None, password)
                self.engine.validate_mapping(mapping)
            except WrongPasswordError:
                return tr("pw.error_wrong")
            except ValueError as exc:
                return str(exc)
            self._password = password
            self._key_locked = False
            self._update_key_menu()
            return None

        self._password_dialog(
            tr("pw.unlock_title"),
            tr("pw.unlock_body", name=self.default_key_file.name),
            tr("pw.unlock_btn"),
            do_unlock,
            on_success=lambda: self._snack(tr("pw.unlocked")),
        )

    async def _on_set_password(self, _event) -> None:
        if self._busy:
            return
        if self._key_locked:
            self._show_unlock()
            return

        async def do_encrypt(password: str) -> str | None:
            try:
                mapping = await asyncio.to_thread(self._load_key)
                await asyncio.to_thread(save_key_atomic, mapping, None, password)
            except (OSError, ValueError) as exc:
                return str(exc)
            self._password = password
            self._update_key_menu()
            return None

        self._password_dialog(
            tr("pw.set_title"),
            tr("pw.set_body"),
            tr("pw.set_btn"),
            do_encrypt,
            repeat=True,
            on_success=lambda: self._snack(tr("pw.set_done")),
        )

    def _on_remove_password(self, _event) -> None:
        if self._busy or self._password is None:
            return

        async def do_remove_password(_e) -> None:
            try:
                mapping = await asyncio.to_thread(self._load_key)
                await asyncio.to_thread(save_key_atomic, mapping)
            except (OSError, ValueError) as exc:
                self._snack(str(exc))
                return
            self._password = None
            self._update_key_menu()
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
                        on_click=do_remove_password,
                    ),
                ],
                actions_alignment=ft.MainAxisAlignment.END,
            )
        )

    async def _on_clear_old_entries(self, _event) -> None:
        if self._busy:
            return
        if self._key_locked:
            self._show_unlock()
            return
        try:
            mapping = await asyncio.to_thread(self._load_key)
        except (OSError, ValueError) as exc:
            self._snack(str(exc))
            return
        date_map = stamp_tokens(mapping, load_dates())

        field = ft.TextField(
            label=tr("purge.days"),
            value="30",
            width=140,
            keyboard_type=ft.KeyboardType.NUMBER,
            input_filter=ft.NumbersOnlyInputFilter(),
            max_length=5,
        )
        summary_text = ft.Text("", size=13)

        def days_value() -> int | None:
            try:
                return int(field.value or "")
            except ValueError:
                return None

        def refresh(_e=None) -> None:
            n = days_value()
            if n is None:
                summary_text.value = tr("purge.invalid")
            else:
                summary_text.value = tr_count(
                    "purge.count", len(find_older_than(date_map, n)), total=len(mapping)
                )
            self.page.update()

        async def do_remove(_e) -> None:
            n = days_value()
            if n is None:
                refresh()
                return
            old_tokens = find_older_than(date_map, n)
            new_mapping, new_dates = purge(mapping, date_map, old_tokens)
            try:
                await asyncio.to_thread(self._save_key, new_mapping)
                await asyncio.to_thread(save_dates, new_dates)
            except (OSError, ValueError) as exc:
                self._snack(str(exc))
                return
            self.current_mapping = {}
            self.page.pop_dialog()
            self._snack(tr_count("purge.done", len(old_tokens)))

        field.on_change = refresh
        summary_text.value = tr_count("purge.count", len(find_older_than(date_map, 30)), total=len(mapping))
        self.page.show_dialog(
            ft.AlertDialog(
                modal=True,
                title=ft.Text(tr("purge.title")),
                content=ft.Column(
                    controls=[ft.Text(tr("purge.body"), size=13), field, summary_text],
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
                        on_click=do_remove,
                    ),
                ],
                actions_alignment=ft.MainAxisAlignment.END,
            )
        )

    # ------------------------------------------------------------ restore

    def _update_active_key_text(self) -> None:
        if self.custom_restore_mapping is not None:
            self.txt_active_key.value = tr(
                "restore.active_custom",
                name=self.custom_key_name or tr("restore.custom_fallback_name"),
            )
        else:
            self.txt_active_key.value = tr("restore.active_default")

    def _on_use_default(self, _event) -> None:
        self.custom_restore_mapping = None
        self.custom_key_name = None
        self.btn_use_default.visible = False
        self._update_active_key_text()
        self.page.update()
        self._snack(tr("msg.use_default"))

    def _update_counter(self) -> None:
        text = self.txt_input.value or ""
        if not text:
            self.txt_counter.value = tr("counter.zero")
            return
        line_count = text.count("\n") + 1

        def amount(count: int, one: str, many: str) -> str:
            return tr(one if count == 1 else many, n=format_number(count))

        self.txt_counter.value = tr(
            "counter",
            chars=amount(len(text), "counter.chars_one", "counter.chars_many"),
            lines=amount(line_count, "counter.lines_one", "counter.lines_many"),
        )

    def _on_text_changed(self, _event) -> None:
        self._selection = ""
        self._update_counter()
        self.txt_counter.update()

    def _on_language_changed(self, _event) -> None:
        selected = self.dd_language.value or "es"
        loaded = self.engine.loaded_language()
        if loaded is not None and loaded != selected:
            self.engine.unload_model()
        self._refresh_model_status()
        self.page.update()

    async def _on_model_action(self, _event) -> None:
        if self._busy:
            return
        language = self.dd_language.value or "es"
        if not self.engine.model_available(language):
            self._show_language_install(language)

    def _show_language_install(self, language: str) -> None:
        info = model_info(language)
        name = language_name(language)
        size_mb = info.size_bytes / (1024 * 1024)
        dialog = ft.AlertDialog(
            modal=True,
            title=ft.Text(tr("model.dialog_title", name=name)),
            content=ft.Column(
                controls=[
                    ft.Text(tr("model.dialog_body", size=size_mb)),
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
                    data=language,
                    on_click=self._on_install_language,
                ),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
        )
        self.page.show_dialog(dialog)

    async def _on_install_language(self, event) -> None:
        language = event.control.data
        self.page.pop_dialog()
        name = language_name(language)
        self._set_busy_state(True)
        self.txt_process_status.value = tr("model.downloading", name=name)
        self.page.update()
        try:
            await asyncio.to_thread(self.engine.install_model, language)
            self.txt_process_status.value = ""
            self._snack(tr("model.installed", name=name))
        except Exception:
            logger.exception("Could not install the language pack %s", language)
            self._snack(tr("model.install_failed"))
        finally:
            self._set_busy_state(False)
            self._refresh_model_status()
            self.page.update()

    async def _on_copy_result(self, _event) -> None:
        if self.txt_result.value:
            await self.clipboard.set(self.txt_result.value)
            self._snack(tr("msg.copied"))

    async def _on_export_key(self, _event) -> None:
        try:
            mapping = await asyncio.to_thread(self._load_key)
            self.engine.validate_mapping(mapping)
        except KeyEncryptedError:
            self._show_unlock()
            return
        except (OSError, ValueError) as exc:
            self._snack(tr("msg.export_failed", error=exc))
            return

        name = f"cloaktext-key-{datetime.now():%Y%m%d-%H%M%S}.json"
        # If the key is encrypted, the exported copy is encrypted too.
        body_payload = encrypt_key(mapping, self._password) if self._password else mapping
        body = (json.dumps(body_payload, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
        file_path = await ft.FilePicker().save_file(
            dialog_title=tr("picker.export_title"),
            file_name=name,
            file_type=ft.FilePickerFileType.CUSTOM,
            allowed_extensions=["json"],
            src_bytes=body,
        )
        if file_path or self.page.web:
            self._snack(tr("msg.export_done"))

    async def _on_load_key_file(self, _event) -> None:
        picked_files = await ft.FilePicker().pick_files(
            dialog_title=tr("picker.open_title"),
            allow_multiple=False,
            with_data=True,
            file_type=ft.FilePickerFileType.CUSTOM,
            allowed_extensions=["json"],
        )
        if not picked_files:
            return
        picked_file = picked_files[0]
        data = picked_file.bytes or b""
        if len(data) > MAX_CUSTOM_KEY_BYTES:
            self._snack(tr("msg.key_too_big"))
            return
        try:
            raw_text = data.decode("utf-8-sig")
            body = json.loads(raw_text)
        except (UnicodeDecodeError, json.JSONDecodeError):
            self._snack(tr("msg.custom_invalid"))
            return

        name = picked_file.name or tr("restore.custom_fallback_name")
        if is_encrypted_envelope(body):
            self._ask_custom_key_password(body, name)
            return
        try:
            self.engine.validate_mapping(body)
        except ValueError:
            self._snack(tr("msg.custom_invalid"))
            return
        self._use_custom_key(body, name)

    def _ask_custom_key_password(self, envelope_data: dict, name: str) -> None:
        decrypted: dict[str, str] = {}

        async def do_decrypt(password: str) -> str | None:
            try:
                mapping = await asyncio.to_thread(decrypt_key, envelope_data, password)
                self.engine.validate_mapping(mapping)
            except WrongPasswordError:
                return tr("pw.error_wrong")
            except ValueError as exc:
                return str(exc)
            decrypted.update(mapping)
            return None

        self._password_dialog(
            tr("pw.unlock_title"),
            tr("pw.unlock_body", name=name),
            tr("pw.unlock_btn"),
            do_decrypt,
            on_success=lambda: self._use_custom_key(dict(decrypted), name),
        )

    def _use_custom_key(self, mapping: dict[str, str], name: str) -> None:
        self.custom_restore_mapping = mapping
        self.custom_key_name = name
        self._update_active_key_text()
        self.btn_use_default.visible = True
        self.page.update()
        self._snack(tr_count("msg.custom_ready", len(mapping)))

    # ------------------------------------------------------------- process

    async def _on_run(self, _event) -> None:
        if self._busy:
            return

        text = self.txt_input.value or ""
        if not text.strip():
            self._snack(tr("msg.enter_text"))
            return

        language = self.dd_language.value or "es"
        self._set_busy_state(True)

        try:
            if self.mode == "protect":
                await self._run_protect(text, language)
            else:
                await self._run_restore(text)
        except KeyEncryptedError:
            self._show_unlock()
        except ModelUnavailableError as exc:
            logger.info("Language pack not installed: %s", exc.model)
            self._show_language_install(exc.language)
        except ValueError as exc:
            self._snack(str(exc))
        except Exception:
            logger.exception("Unexpected error during processing")
            self._snack(tr("msg.process_failed"))
        finally:
            # An aborted run (e.g. missing language pack) must not leave "Analysing…" on screen.
            self.txt_process_status.value = ""
            self._set_busy_state(False)
            self._refresh_model_status()
            self.page.update()

    async def _run_protect(self, text: str, language: str) -> None:
        self.txt_process_status.value = tr("status.analysing")
        self.page.update()

        mapping = await asyncio.to_thread(self._load_key)
        self.engine.validate_mapping(mapping)

        result = await asyncio.to_thread(
            self.engine.protect,
            text,
            mapping,
            None,
            language,
            self._manual_terms(),
        )
        await asyncio.to_thread(self._save_key, mapping)
        await asyncio.to_thread(self._record_dates, mapping)

        self.current_mapping = mapping
        self.txt_result.value = result
        self._show_result(result)
        self.key_notice.visible = True
        self.btn_copy_result.disabled = not bool(result)

        current_tokens = list(TOKEN_TYPE_RE.finditer(result))
        counts = Counter(match.group(1) for match in current_tokens)
        is_single = len(current_tokens) == 1
        noun = tr("msg.noun_one" if is_single else "msg.noun_many")
        verb = tr("msg.verb_one" if is_single else "msg.verb_many")

        if not current_tokens:
            self.txt_summary.value = tr("summary.nothing_found")
        else:
            detail = " · ".join(f"{kind}: {amount}" for kind, amount in sorted(counts.items()))
            self.txt_summary.value = tr(
                "summary.found", count=format_number(len(current_tokens)), noun=noun, verb=verb, detail=detail
            )

        self.txt_process_status.value = ""
        self._snack(tr("msg.done", count=format_number(len(current_tokens)), noun=noun, verb=verb))

    @staticmethod
    def _record_dates(mapping: dict[str, str]) -> None:
        """Record the creation date of new tokens (non-critical)."""
        try:
            save_dates(stamp_tokens(mapping, load_dates()))
        except OSError:
            logger.warning("Could not save the entry dates")

    async def _run_restore(self, text: str) -> None:
        if self.custom_restore_mapping is not None:
            mapping = self.custom_restore_mapping
        else:
            mapping = await asyncio.to_thread(self._load_key)
            self.engine.validate_mapping(mapping)

        if not mapping:
            raise ValueError(tr("msg.empty_key"))

        self.txt_process_status.value = tr("status.restoring")
        self.page.update()
        result = await asyncio.to_thread(self.engine.restore, text, mapping)

        self.txt_result.value = result
        self._show_result(result)
        source_name = (
            self.custom_key_name
            if self.custom_restore_mapping is not None
            else "cloaktext.json"
        )
        self.txt_summary.value = tr("summary.restored", source=source_name)
        self.key_notice.visible = False
        self.btn_copy_result.disabled = not bool(result)
        self.txt_process_status.value = ""
        self._snack(tr("msg.restored"))

    # ------------------------------------------------------------ result

    def _show_result(self, result: str) -> None:
        """Show the result, with the markers highlighted when applicable."""
        is_protect_mode = self.mode == "protect"
        self.highlighted_text.spans = highlighted_spans(result) if is_protect_mode else []
        self.sw_highlight.visible = is_protect_mode and bool(result)
        self._apply_highlight()

    def _apply_highlight(self) -> None:
        highlight = self.sw_highlight.visible and bool(self.sw_highlight.value)
        self.highlight_view.visible = highlight
        self.txt_result.visible = not highlight

    def _on_toggle_highlight(self, _event) -> None:
        self._apply_highlight()
        self.page.update()

    def _on_clear_text(self, _event) -> None:
        if self._busy:
            return
        self.txt_input.value = ""
        self.txt_terms.value = ""
        self._update_counter()
        self._clear_result()
        self.page.update()

    def _on_clear_json(self, _event) -> None:
        if self._busy:
            return
        dialog = ft.AlertDialog(
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
                    on_click=self._confirm_clear_json,
                ),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
        )
        self.page.show_dialog(dialog)

    def _confirm_clear_json(self, _event) -> None:
        try:
            self._save_key({})
            save_dates({})
        except OSError:
            logger.exception("Could not clear cloaktext.json")
            self._snack(tr("msg.json_clear_failed"))
            return
        self.current_mapping = {}
        self.page.pop_dialog()
        self._snack(tr("msg.json_cleared"))

    def _clear_result(self) -> None:
        self.current_mapping = {}
        self.txt_result.value = ""
        self.highlighted_text.spans = []
        self.highlight_view.visible = False
        self.txt_result.visible = True
        self.sw_highlight.visible = False
        self.key_notice.visible = False
        self.btn_copy_result.disabled = True
        self.txt_summary.value = tr("summary.none_yet")
        self.txt_process_status.value = ""

    def _set_busy_state(self, active: bool) -> None:
        self._busy = active
        self.progress_bar.visible = active
        self.btn_run.disabled = active
        self.btn_clear_text.disabled = active
        self.btn_clear_json.disabled = active
        self.btn_mode_protect.disabled = active
        self.btn_mode_restore.disabled = active
        self.dd_language.disabled = active
        self.btn_model.disabled = active
        self.btn_load_key_file.disabled = active
        self.btn_use_default.disabled = active
        self.btn_export_key.disabled = active
        self.btn_terms.disabled = active
        self.btn_selection.disabled = active
        self.key_menu.disabled = active
        self.page.update()

    def _refresh_model_status(self) -> None:
        selected = self.dd_language.value or "es"
        name = language_name(selected)
        available = self.engine.model_available(selected)

        if available:
            self.txt_model_status.value = tr("model.ready", name=name)
            self.txt_model_status.color = ft.Colors.ON_SURFACE
            self.btn_model.visible = False
        else:
            self.txt_model_status.value = tr("model.prepare_to_start", name=name)
            self.txt_model_status.color = ft.Colors.OUTLINE
            self.btn_model.visible = True
            self.btn_model.content = tr("btn.prepare_language")
            self.btn_model.icon = ft.Icons.DOWNLOAD_OUTLINED
            self.btn_model.disabled = self._busy

    async def _periodic_status_refresh(self) -> None:
        while True:
            await asyncio.sleep(15)
            try:
                self._refresh_model_status()
                self.page.update()
            except Exception:
                return

    async def _on_window_event(self, event: ft.WindowEvent) -> None:
        if event.type == ft.WindowEventType.CLOSE:
            self.engine.stop()
            await self.page.window.destroy()

    def _snack(self, message: str) -> None:
        self.page.show_dialog(
            ft.SnackBar(
                content=ft.Text(message),
                behavior=ft.SnackBarBehavior.FLOATING,
                show_close_icon=True,
            )
        )


def main(page: ft.Page) -> None:
    CloakTextApp(page)


if __name__ == "__main__":
    ft.run(main)
