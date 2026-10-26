# Privacy

CloakText is designed so that your text never leaves your computer. This document says exactly what the application does with your data. [Versión en español más abajo.](#privacidad)

## What stays on your computer

| Data | Where | Notes |
| --- | --- | --- |
| The text you paste | Memory only | It is not written to disk by CloakText. |
| The protected text | Memory only | Copy it to the clipboard to use it elsewhere. |
| The restore key (`cloaktext.json`) | Next to `CloakText.exe` | **Contains your original data in plain text.** Updated automatically every time you protect a text; it grows over time. |
| Entry dates (`cloaktext.dates.json`) | Next to the key | Only the placeholder and the day it was created, to clear old entries. No original data. |
| Preferences (`cloaktext.settings.json`) | Next to the key | Interface language only. |
| Language packs | `models/` next to the executable | Public spaCy models; they contain no user data. |

If the application folder is not writable, all of these live in `%LOCALAPPDATA%\CloakText` instead.

## What goes over the network

Only one thing, and only if you accept it: downloading a language pack from the official `explosion/spacy-models` GitHub releases. The request contains the package URL and a `User-Agent` header (`CloakText/1.0`). Your text is never part of any request. The download is verified by size and SHA-256 (both pinned in the source code) before anything is installed.

CloakText has no accounts, no analytics and no telemetry. It does not check for updates.

## The restore key

`cloaktext.json` maps each placeholder to the original value, in plain text. Anyone who gets it and the protected text can recover your data. Therefore:

- you can **encrypt it with a password** (Key menu): AES-256-GCM with a key derived by scrypt; the file is authenticated, so tampering is detected. There is no password recovery;
- do not publish, e-mail or sync it without encryption (for example, avoid putting the CloakText folder inside a cloud-synced folder);
- do not attach it to issues or support requests;
- use **Clear JSON**, or *Key → Clear old entries…*, to delete stored mappings you no longer need;
- the password is kept in memory only while the app is open and is never written to disk;
- the file is written atomically, and on systems that support it with owner-only permissions. On Windows the file inherits the permissions of its folder, so keep CloakText in a folder only you can access.

## Limits of the protection

- Automatic detection can miss data (unusual formats, typos, names the language model does not recognise) and can flag harmless words. Review every result.
- Placeholders keep the structure and meaning of the text. Context can still identify someone even when names are replaced.
- Text is held in memory while it is processed, like any application.
- Encryption protects the file at rest. It does not protect against malware running as you while the app is open.

## Reporting a privacy problem

See [SECURITY.md](SECURITY.md). Never attach real sensitive text or real keys.

---

# Privacidad

CloakText está pensado para que tu texto no salga nunca de tu equipo. Este documento describe exactamente qué hace la aplicación con tus datos.

## Qué se queda en tu equipo

| Dato | Dónde | Notas |
| --- | --- | --- |
| El texto que pegas | Solo en memoria | CloakText no lo escribe en disco. |
| El texto protegido | Solo en memoria | Cópialo al portapapeles para usarlo en otro sitio. |
| La clave de restauración (`cloaktext.json`) | Junto a `CloakText.exe` | **Contiene tus datos originales en texto plano.** Se actualiza al proteger cada texto y crece con el tiempo. |
| Fechas de las entradas (`cloaktext.dates.json`) | Junto a la clave | Solo el marcador y el día de creación, para limpiar entradas antiguas. Sin datos originales. |
| Preferencias (`cloaktext.settings.json`) | Junto a la clave | Solo el idioma de la interfaz. |
| Paquetes de idioma | `models/`, junto al ejecutable | Modelos públicos de spaCy; no contienen datos del usuario. |

Si la carpeta de la aplicación no admite escritura, todo esto se guarda en `%LOCALAPPDATA%\CloakText`.

## Qué viaja por la red

Solo una cosa, y solo si la aceptas: la descarga de un paquete de idioma desde los releases oficiales de `explosion/spacy-models` en GitHub. La petición incluye la URL del paquete y una cabecera `User-Agent` (`CloakText/1.0`). Tu texto nunca forma parte de ninguna petición. La descarga se verifica por tamaño y SHA-256 (ambos fijados en el código) antes de instalar nada.

CloakText no tiene cuentas, analítica ni telemetría, y no comprueba actualizaciones.

## La clave de restauración

`cloaktext.json` relaciona cada marcador con su valor original, en texto plano. Quien tenga la clave y el texto protegido puede recuperar tus datos. Por eso:

- puedes **cifrarla con contraseña** (menú Clave): AES-256-GCM con clave derivada por scrypt; el archivo está autenticado, así que cualquier manipulación se detecta. No hay recuperación de contraseña;
- no la publiques, envíes por correo ni sincronices sin cifrar (por ejemplo, evita poner la carpeta de CloakText dentro de una carpeta sincronizada en la nube);
- no la adjuntes a issues ni a solicitudes de soporte;
- usa **Limpiar JSON**, o *Clave → Limpiar entradas antiguas…*, para borrar las correspondencias que ya no necesites;
- la contraseña solo está en memoria mientras la aplicación está abierta y nunca se escribe en disco;
- el archivo se escribe de forma atómica y, en sistemas que lo soportan, con permisos solo para el propietario. En Windows hereda los permisos de su carpeta, así que mantén CloakText en una carpeta a la que solo accedas tú.

## Límites de la protección

- La detección automática puede omitir datos (formatos poco habituales, erratas, nombres que el modelo no reconoce) y marcar palabras inocuas. Revisa cada resultado.
- Los marcadores conservan la estructura y el sentido del texto. El contexto puede seguir identificando a alguien aunque se sustituyan los nombres.
- El texto está en memoria mientras se procesa, como en cualquier aplicación.
- El cifrado protege el archivo en reposo. No protege frente a malware que se ejecute con tu usuario mientras la aplicación está abierta.

## Notificar un problema de privacidad

Consulta [SECURITY.md](SECURITY.md). No adjuntes nunca textos sensibles reales ni claves reales.
