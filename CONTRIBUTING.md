# Contributing

Bug reports and improvement proposals are welcome. [Versión en español más abajo.](#contribuir)

**Never include real personal data or real restore keys** in issues, pull requests, tests or screenshots. Use invented data (`ana@example.com`, `ES91 2100 0418 4502 0005 1332`…).

## Set up

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements-dev.txt
python main.py
```

The first run of the Flet desktop client downloads its own runtime (one time, from Flet's GitHub releases). That is a development convenience; packaged builds bundle it.

## Before opening a pull request

```bash
python -m pytest
python -m compileall -q main.py motor_local.py language_models.py key_store.py i18n.py branding.py version.py
python -m pip check
```

CI runs the same three commands. The tests do not need language models: the engine tests stub the NER step and exercise the rule-based detectors, the key store, the safe wheel extraction and a UI smoke test.

## Guidelines

- One goal per pull request, with tests when behaviour changes.
- **Detection changes need both directions tested**: a case that must be protected and a case that must be left alone. When in doubt, favour protecting (a missed datum is worse than an extra placeholder).
- Do not weaken the privacy model: no network access other than the pinned language-pack download, no logging of user text, no telemetry.
- Language packs: URLs and SHA-256 hashes live in `language_models.py`. Changing a model version means updating both and the license table in `THIRD_PARTY_NOTICES.md`.
- Never rename keys or placeholder formats that users may already have stored in `cloaktext.json` (`[TYPE_1000]`); the format must stay readable by older keys.
- Interface strings live in `i18n.py` (Spanish and English). Add every new string to **both** languages; a test fails if a key is missing or the format placeholders differ. Never translate placeholder type names (`PERSONA`, `EMAIL`…) or `cloaktext.json` keys.
- Commit messages: [Conventional Commits](https://www.conventionalcommits.org/) (`feat:`, `fix:`, `docs:`, `test:`…).

## README screenshots

`scripts/doc_screenshots.py` opens the real app on Windows, protects a synthetic sample and saves `docs/images/protect.png`, `restore.png` and the `.es.png` Spanish versions. It refuses to save if another window covers CloakText, but check every image before committing it. Re-run it whenever the interface changes. It uses a temporary key folder and no language model.

---

# Contribuir

Los informes de errores y las propuestas de mejora son bienvenidos.

**No incluyas nunca datos personales reales ni claves de restauración reales** en issues, pull requests, tests o capturas. Usa datos inventados (`ana@example.com`, `ES91 2100 0418 4502 0005 1332`…).

## Entorno de desarrollo

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements-dev.txt
python main.py
```

La primera ejecución del cliente de escritorio de Flet descarga su propio runtime (una vez, desde los releases de Flet en GitHub). Es una comodidad de desarrollo; los ejecutables empaquetados ya lo incluyen.

## Antes de abrir un pull request

```bash
python -m pytest
python -m compileall -q main.py motor_local.py language_models.py key_store.py i18n.py branding.py version.py
python -m pip check
```

La CI ejecuta esos mismos tres comandos. Los tests no necesitan modelos de idioma: los del motor sustituyen el paso de NER y prueban los detectores por reglas, la clave, la extracción segura de wheels y un smoke test de la interfaz.

## Pautas

- Un objetivo por pull request, con tests cuando cambie el comportamiento.
- **Los cambios de detección se prueban en ambos sentidos**: un caso que debe protegerse y otro que debe dejarse intacto. En caso de duda, protege (omitir un dato es peor que un marcador de más).
- No debilites el modelo de privacidad: ningún acceso a red salvo la descarga fijada de paquetes de idioma, ningún registro del texto del usuario, ninguna telemetría.
- Paquetes de idioma: las URL y los SHA-256 están en `language_models.py`. Cambiar la versión de un modelo implica actualizar ambos y la tabla de licencias de `THIRD_PARTY_NOTICES.md`.
- No cambies el formato de marcadores (`[TIPO_1000]`) que los usuarios ya tienen en su `cloaktext.json`; las claves antiguas deben seguir siendo legibles.
- Las cadenas de la interfaz están en `i18n.py` (español e inglés). Añade cada cadena nueva en **ambos** idiomas; un test falla si falta una clave o difieren los marcadores de formato. No traduzcas nunca los tipos de marcador (`PERSONA`, `EMAIL`…) ni las claves de `cloaktext.json`.
- Mensajes de commit: [Conventional Commits](https://www.conventionalcommits.org/) (`feat:`, `fix:`, `docs:`, `test:`…).

## Capturas del README

`scripts/doc_screenshots.py` abre la aplicación real en Windows, protege un ejemplo sintético y guarda `docs/images/protect.png`, `restore.png` y las versiones `.es.png`. Se niega a guardar si otra ventana tapa CloakText, pero revisa cada imagen antes de subirla. Vuelve a ejecutarlo cada vez que cambie la interfaz. Usa una carpeta temporal para la clave y ningún modelo de idioma.
