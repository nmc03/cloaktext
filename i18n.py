"""Cadenas de la interfaz de CloakText (español e inglés).

`tr("clave", nombre=valor)` devuelve la cadena en el idioma activo. El idioma se
elige así: CLOAKTEXT_UI_LANG (desarrollo/tests) > preferencia guardada > idioma de
Windows > inglés. Los marcadores de los datos (`[PERSONA_1000]`, ...) y los nombres
de las claves de `cloaktext.json` NO se traducen: son formato persistido.
"""

from __future__ import annotations

import locale
import os
import sys

UI_LANGUAGES = {"es": "Español", "en": "English"}
DEFAULT_LANGUAGE = "en"

_current = DEFAULT_LANGUAGE

STRINGS: dict[str, dict[str, str]] = {
    "es": {
        # general
        "app.tagline": "Protección local y reversible para texto sensible",
        "app.badge_local": "100 % local",
        "app.intro": "Protege, revisa y comparte. Tú mantienes el control del texto y de la clave.",
        "app.footer": "Local · reversible · sin telemetría de contenido",
        "common.cancel": "Cancelar",
        "common.accept": "Aceptar",
        "common.clear": "Limpiar",
        # idiomas de texto
        "lang.es": "Español",
        "lang.en": "Inglés",
        "lang.fr": "Francés",
        "lang.de": "Alemán",
        "lang.it": "Italiano",
        "lang.pt": "Portugués",
        "lang.ca": "Catalán",
        "lang.label": "Idioma del texto",
        "ui.language_tooltip": "Idioma de la interfaz",
        # modos
        "mode.protect": "Proteger",
        "mode.restore": "Restaurar",
        "btn.run_protect": "Proteger datos",
        "btn.run_restore": "Restaurar texto",
        "btn.clear_json": "Limpiar JSON",
        "btn.copy": "Copiar texto",
        "btn.export": "Exportar JSON",
        "btn.other_json": "Usar otro JSON",
        "btn.default_json": "Usar cloaktext.json",
        "btn.prepare_language": "Preparar idioma",
        # tarjetas
        "card.input_title": "1. Texto a proteger",
        "card.input_sub": "Elige el idioma y pega el contenido. El texto nunca se envía fuera del equipo.",
        "card.result_title": "2. Texto protegido",
        "card.result_sub": "Comprueba el resultado antes de compartirlo. CloakText resalta lo que ha protegido automáticamente.",
        "field.input_protect": "Texto a proteger",
        "field.input_restore": "Texto protegido",
        "hint.input_protect": "Pega aquí el texto que quieres proteger…",
        "hint.input_restore": "Pega aquí el texto protegido que quieres restaurar…",
        "field.result_protect": "Texto protegido",
        "field.result_restore": "Texto restaurado",
        "hint.result_protect": "El texto listo para compartir aparecerá aquí.",
        "hint.result_restore": "El texto restaurado aparecerá aquí.",
        "counter": "{chars} caracteres · {lines} líneas",
        "counter.zero": "0 caracteres",
        "summary.none_yet": "Todavía no se ha procesado ningún texto.",
        "summary.nothing_found": "No se han detectado datos sensibles automáticamente. Revisa el texto antes de compartirlo.",
        "summary.found": "{count} datos protegidos · {detail}",
        "summary.restored": "Texto restaurado usando {source}.",
        "status.analysing": "Analizando texto…",
        "status.restoring": "Restaurando texto…",
        "restore.active_default": "Restauración: cloaktext.json predeterminado",
        "restore.active_custom": "Restauración: {name}",
        "restore.custom_fallback_name": "JSON personalizado",
        # resaltado
        "highlight.switch": "Resaltar lo protegido",
        # palabras manuales
        "terms.toggle": "Palabras adicionales",
        "terms.label": "Proteger también estas palabras",
        "terms.hint": "Una por línea: nombres de proyectos, clientes, apodos…",
        # aviso clave
        "notice.key_plain": "La clave se guarda automáticamente en cloaktext.json ({where}). Contiene datos originales en texto plano: protégela como información confidencial, o cífrala con contraseña desde el menú Clave.",
        "notice.key_encrypted": "La clave se guarda cifrada con tu contraseña en cloaktext.json ({where}). Sin la contraseña no se podrán restaurar los textos.",
        "notice.where_app": "junto a la aplicación",
        "notice.where_profile": "en {path}",
        # menú clave
        "menu.key": "Clave",
        "menu.set_password": "Proteger la clave con contraseña…",
        "menu.change_password": "Cambiar la contraseña…",
        "menu.remove_password": "Quitar la contraseña…",
        "menu.purge": "Limpiar entradas antiguas…",
        # estado modelo
        "model.ready": "{name} listo",
        "model.prepare_to_start": "Prepara {name} para empezar",
        "model.pending": "Idioma pendiente",
        "model.dialog_title": "Preparar {name}",
        "model.dialog_body": "CloakText necesita un paquete de idioma de {size:.1f} MB para reconocer personas, lugares y organizaciones.",
        "model.dialog_note": "Se descargará una sola vez desde el repositorio oficial de spaCy. Después, el análisis del texto seguirá siendo local y podrá funcionar sin conexión.",
        "model.dialog_license": "Licencia del paquete: {license}",
        "model.downloading": "Descargando el paquete de {name}…",
        "model.installed": "{name} está listo. Ya puedes proteger el texto sin conexión.",
        "model.install_failed": "No se pudo instalar el paquete de idioma. Comprueba la conexión e inténtalo de nuevo.",
        # mensajes
        "msg.enter_text": "Introduce un texto antes de procesarlo.",
        "msg.process_failed": "No se ha podido procesar el texto. Revisa los datos e inténtalo de nuevo.",
        "msg.done": "Proceso terminado: {count} {noun} {verb}. cloaktext.json actualizado.",
        "msg.noun_one": "dato",
        "msg.noun_many": "datos",
        "msg.verb_one": "protegido",
        "msg.verb_many": "protegidos",
        "msg.restored": "Texto restaurado.",
        "msg.copied": "Texto protegido copiado.",
        "msg.use_default": "Se usará cloaktext.json para restaurar.",
        "msg.empty_key": "cloaktext.json está vacío. Protege un texto primero o usa otro JSON.",
        "msg.export_done": "Copia JSON exportada.",
        "msg.export_failed": "No se puede exportar la clave predeterminada: {error}",
        "msg.custom_ready": "JSON personalizado listo: {count} elementos.",
        "msg.custom_invalid": "El archivo no contiene una clave válida de CloakText.",
        "msg.key_too_big": "La clave supera el límite de 10 MB.",
        "msg.json_cleared": "cloaktext.json se ha vaciado. Las copias exportadas no se han modificado.",
        "msg.json_clear_failed": "No se pudo limpiar cloaktext.json.",
        "picker.export_title": "Exportar clave de restauración",
        "picker.open_title": "Abrir clave de restauración",
        "dialog.clear_json_title": "Limpiar cloaktext.json",
        "dialog.clear_json_body": "Esto vaciará la clave predeterminada cloaktext.json y eliminará todas las asociaciones guardadas. Los textos protegidos con esas asociaciones dejarán de poder restaurarse con el JSON predeterminado. No se borrarán las copias JSON que hayas exportado ni los archivos personalizados que tengas en otras ubicaciones.",
        # contraseña
        "pw.unlock_title": "Clave cifrada",
        "pw.unlock_body": "Introduce la contraseña de {name} para poder proteger y restaurar textos.",
        "pw.unlock_btn": "Desbloquear",
        "pw.field": "Contraseña",
        "pw.field_confirm": "Repite la contraseña",
        "pw.unlocked": "Clave desbloqueada.",
        "pw.set_title": "Proteger la clave con contraseña",
        "pw.set_body": "La clave se cifrará con AES-256 y solo podrá leerse con esta contraseña. Si la olvidas, los textos ya protegidos NO se podrán restaurar: no existe forma de recuperarla.",
        "pw.set_btn": "Cifrar clave",
        "pw.set_done": "Clave cifrada con contraseña.",
        "pw.remove_title": "Quitar la contraseña",
        "pw.remove_body": "La clave volverá a guardarse en texto plano en cloaktext.json. Cualquiera con acceso al archivo podrá leer los datos originales.",
        "pw.remove_btn": "Quitar contraseña",
        "pw.remove_done": "La clave se guarda ahora sin cifrar.",
        "pw.error_mismatch": "Las contraseñas no coinciden.",
        "pw.error_short": "Usa al menos {n} caracteres.",
        "pw.error_wrong": "Contraseña incorrecta.",
        "pw.needs_unlock": "La clave está cifrada: introduce la contraseña.",
        # limpieza
        "purge.title": "Limpiar entradas antiguas",
        "purge.body": "Elimina de cloaktext.json las asociaciones creadas hace más de los días indicados. Los textos protegidos con ellas dejarán de poder restaurarse.",
        "purge.days": "Días",
        "purge.count": "{count} entradas se eliminarían (de {total}).",
        "purge.btn": "Eliminar",
        "purge.done": "{count} entradas eliminadas de cloaktext.json.",
        "purge.invalid": "Indica un número de días válido.",
        # errores de motor y clave
        "err.not_file": "No es un archivo: {name}",
        "err.key_too_big": "La clave supera el límite de 10 MB.",
        "err.key_utf8": "La clave JSON no está codificada en UTF-8.",
        "err.key_json": "La clave JSON no contiene un JSON válido.",
        "err.key_object": "La clave JSON debe contener un objeto.",
        "err.pw_short": "La contraseña debe tener al menos {n} caracteres.",
        "err.enc_format": "Formato de clave cifrada no compatible.",
        "err.enc_params": "Parámetros de cifrado no válidos.",
        "err.enc_damaged": "La clave cifrada está dañada o tiene un formato no válido.",
        "err.map_not_object": "El diccionario debe ser un objeto JSON.",
        "err.map_too_big": "El diccionario es demasiado grande.",
        "err.map_bad_token": "Token de diccionario no válido: {token}",
        "err.map_bad_value": "El valor de {token} debe ser texto.",
    },
    "en": {
        "app.tagline": "Local, reversible protection for sensitive text",
        "app.badge_local": "100% local",
        "app.intro": "Protect, review and share. You stay in control of the text and the key.",
        "app.footer": "Local · reversible · no content telemetry",
        "common.cancel": "Cancel",
        "common.accept": "OK",
        "common.clear": "Clear",
        "lang.es": "Spanish",
        "lang.en": "English",
        "lang.fr": "French",
        "lang.de": "German",
        "lang.it": "Italian",
        "lang.pt": "Portuguese",
        "lang.ca": "Catalan",
        "lang.label": "Text language",
        "ui.language_tooltip": "Interface language",
        "mode.protect": "Protect",
        "mode.restore": "Restore",
        "btn.run_protect": "Protect data",
        "btn.run_restore": "Restore text",
        "btn.clear_json": "Clear JSON",
        "btn.copy": "Copy text",
        "btn.export": "Export JSON",
        "btn.other_json": "Use another JSON",
        "btn.default_json": "Use cloaktext.json",
        "btn.prepare_language": "Prepare language",
        "card.input_title": "1. Text to protect",
        "card.input_sub": "Pick the language and paste the content. The text never leaves your computer.",
        "card.result_title": "2. Protected text",
        "card.result_sub": "Check the result before sharing it. CloakText highlights what it protected automatically.",
        "field.input_protect": "Text to protect",
        "field.input_restore": "Protected text",
        "hint.input_protect": "Paste the text you want to protect here…",
        "hint.input_restore": "Paste the protected text you want to restore here…",
        "field.result_protect": "Protected text",
        "field.result_restore": "Restored text",
        "hint.result_protect": "The text ready to share will appear here.",
        "hint.result_restore": "The restored text will appear here.",
        "counter": "{chars} characters · {lines} lines",
        "counter.zero": "0 characters",
        "summary.none_yet": "No text has been processed yet.",
        "summary.nothing_found": "No sensitive data was detected automatically. Review the text before sharing it.",
        "summary.found": "{count} items protected · {detail}",
        "summary.restored": "Text restored using {source}.",
        "status.analysing": "Analysing text…",
        "status.restoring": "Restoring text…",
        "restore.active_default": "Restore with: default cloaktext.json",
        "restore.active_custom": "Restore with: {name}",
        "restore.custom_fallback_name": "custom JSON",
        "highlight.switch": "Highlight protected items",
        "terms.toggle": "Extra words",
        "terms.label": "Also protect these words",
        "terms.hint": "One per line: project names, clients, nicknames…",
        "notice.key_plain": "The key is saved automatically in cloaktext.json ({where}). It contains original data in plain text: treat it as confidential information, or encrypt it with a password from the Key menu.",
        "notice.key_encrypted": "The key is saved encrypted with your password in cloaktext.json ({where}). Without the password the texts cannot be restored.",
        "notice.where_app": "next to the application",
        "notice.where_profile": "in {path}",
        "menu.key": "Key",
        "menu.set_password": "Protect the key with a password…",
        "menu.change_password": "Change the password…",
        "menu.remove_password": "Remove the password…",
        "menu.purge": "Clear old entries…",
        "model.ready": "{name} ready",
        "model.prepare_to_start": "Prepare {name} to get started",
        "model.pending": "Language pending",
        "model.dialog_title": "Prepare {name}",
        "model.dialog_body": "CloakText needs a {size:.1f} MB language package to recognise people, places and organisations.",
        "model.dialog_note": "It is downloaded once from the official spaCy repository. Afterwards, text analysis stays local and can work offline.",
        "model.dialog_license": "Package license: {license}",
        "model.downloading": "Downloading the {name} package…",
        "model.installed": "{name} is ready. You can now protect text offline.",
        "model.install_failed": "The language package could not be installed. Check your connection and try again.",
        "msg.enter_text": "Enter some text before processing it.",
        "msg.process_failed": "The text could not be processed. Check the data and try again.",
        "msg.done": "Done: {count} {noun} {verb}. cloaktext.json updated.",
        "msg.noun_one": "item",
        "msg.noun_many": "items",
        "msg.verb_one": "protected",
        "msg.verb_many": "protected",
        "msg.restored": "Text restored.",
        "msg.copied": "Protected text copied.",
        "msg.use_default": "cloaktext.json will be used to restore.",
        "msg.empty_key": "cloaktext.json is empty. Protect a text first or use another JSON.",
        "msg.export_done": "JSON copy exported.",
        "msg.export_failed": "The default key cannot be exported: {error}",
        "msg.custom_ready": "Custom JSON ready: {count} entries.",
        "msg.custom_invalid": "The file does not contain a valid CloakText key.",
        "msg.key_too_big": "The key exceeds the 10 MB limit.",
        "msg.json_cleared": "cloaktext.json has been emptied. Exported copies were not modified.",
        "msg.json_clear_failed": "cloaktext.json could not be cleared.",
        "picker.export_title": "Export restore key",
        "picker.open_title": "Open restore key",
        "dialog.clear_json_title": "Clear cloaktext.json",
        "dialog.clear_json_body": "This will empty the default key cloaktext.json and delete every stored association. Texts protected with those associations will no longer be restorable with the default JSON. Exported JSON copies and custom files in other locations will not be deleted.",
        "pw.unlock_title": "Encrypted key",
        "pw.unlock_body": "Enter the password for {name} to protect and restore texts.",
        "pw.unlock_btn": "Unlock",
        "pw.field": "Password",
        "pw.field_confirm": "Repeat the password",
        "pw.unlocked": "Key unlocked.",
        "pw.set_title": "Protect the key with a password",
        "pw.set_body": "The key will be encrypted with AES-256 and can only be read with this password. If you forget it, already protected texts can NOT be restored: there is no way to recover it.",
        "pw.set_btn": "Encrypt key",
        "pw.set_done": "Key encrypted with a password.",
        "pw.remove_title": "Remove the password",
        "pw.remove_body": "The key will be stored in plain text again in cloaktext.json. Anyone with access to the file will be able to read the original data.",
        "pw.remove_btn": "Remove password",
        "pw.remove_done": "The key is now stored unencrypted.",
        "pw.error_mismatch": "The passwords do not match.",
        "pw.error_short": "Use at least {n} characters.",
        "pw.error_wrong": "Wrong password.",
        "pw.needs_unlock": "The key is encrypted: enter the password.",
        "purge.title": "Clear old entries",
        "purge.body": "Removes from cloaktext.json the associations created more than the given number of days ago. Texts protected with them will no longer be restorable.",
        "purge.days": "Days",
        "purge.count": "{count} entries would be removed (of {total}).",
        "purge.btn": "Remove",
        "purge.done": "{count} entries removed from cloaktext.json.",
        "purge.invalid": "Enter a valid number of days.",
        "err.not_file": "Not a file: {name}",
        "err.key_too_big": "The key exceeds the 10 MB limit.",
        "err.key_utf8": "The JSON key is not UTF-8 encoded.",
        "err.key_json": "The key file does not contain valid JSON.",
        "err.key_object": "The JSON key must contain an object.",
        "err.pw_short": "The password must be at least {n} characters long.",
        "err.enc_format": "Unsupported encrypted key format.",
        "err.enc_params": "Invalid encryption parameters.",
        "err.enc_damaged": "The encrypted key is damaged or has an invalid format.",
        "err.map_not_object": "The dictionary must be a JSON object.",
        "err.map_too_big": "The dictionary is too large.",
        "err.map_bad_token": "Invalid dictionary token: {token}",
        "err.map_bad_value": "The value of {token} must be text.",
    },
}


def detect_system_language() -> str:
    """Español si Windows (o el entorno) está en español; si no, inglés."""
    if sys.platform == "win32":
        try:
            import ctypes

            primary = ctypes.windll.kernel32.GetUserDefaultUILanguage() & 0x3FF
            return "es" if primary == 0x0A else "en"
        except (AttributeError, OSError):
            pass
    try:
        code = (locale.getlocale()[0] or os.environ.get("LANG", "")).lower()
    except (ValueError, TypeError):
        code = ""
    return "es" if code.startswith("es") else DEFAULT_LANGUAGE


def resolve_language(saved: str | None = None) -> str:
    forced = os.environ.get("CLOAKTEXT_UI_LANG")
    for candidate in (forced, saved):
        if candidate in UI_LANGUAGES:
            return candidate
    return detect_system_language()


def set_language(code: str) -> None:
    global _current
    _current = code if code in UI_LANGUAGES else DEFAULT_LANGUAGE


def get_language() -> str:
    return _current


def tr(key: str, **values: object) -> str:
    text = STRINGS.get(_current, {}).get(key) or STRINGS[DEFAULT_LANGUAGE].get(key) or key
    return text.format(**values) if values else text
