# Changelog

The format follows Keep a Changelog principles and versions use SemVer.

## [1.2.0] - 2026-10-20

### Fixed

- **Privacy:** a valid IBAN followed by text (for example, `ES91 2100 0418 4502 0005 1332 antes del viernes`) was not protected, and in some cases the IBAN swallowed the next word. It is now trimmed to the valid IBAN and checked against the official length for its country.
- The result summary no longer says "1 items protected": singular and plural forms are used in every language.
- Spanish landline numbers grouped as `91 123 45 67` are now detected (Spanish and Catalan).

### Added

- **Password-encrypted key** (optional): authenticated AES-256-GCM with a key derived via scrypt. Existing plaintext keys keep working. New dependency: `cryptography`.
- **Interface in 7 languages** (Spanish, English, French, German, Italian, Portuguese (Portugal) and Catalan) with a selector in the header; it follows the Windows language by default.
- **Protect selection**: select text in the input and add it to the extra words with one click.
- README in all 7 interface languages (`README.<code>.md`), with screenshots of the real app in each language.
- Build provenance attestation (GitHub Actions) for the Windows ZIP, as an alternative to code signing.
- **Highlighting** of the markers in the result, with a toggle.
- **Extra words**: your own terms (projects, clients, nicknames) that are always protected.
- **Cleanup of old entries** (Key menu) with creation dates stored in `cloaktext.dates.json` (no original data).
- Alternative data folder (`%LOCALAPPDATA%\CloakText`) used when the application folder is not writable.
- Regression tests for IBAN, phone numbers and DNI with an incorrect letter (it is protected on purpose).
- Real screenshots in the README and the `scripts/doc_screenshots.py` script to regenerate them.
- `PRIVACY.md`, `README.es.md` and an expanded contribution guide (English and Spanish).

### Changed

- **Code in English**: identifiers, modules (`motor_local.py` → `local_engine.py`, `language_models.py` → `language_packs.py`), comments and docstrings. No persisted format changes (`cloaktext.json`, marker types, settings keys).
- Passports and NINO only match in uppercase (fewer false positives such as `abc123456`).
- The Portuguese NIF now validates its check digit (it previously protected any 9-digit number).
- `anonimizar()` and `analizar_spans()` accept an optional `terminos` parameter.

- README, SECURITY and CONTRIBUTING rewritten in English with a Spanish version; gender typo corrections in SECURITY.

## [1.1.0] - 2026-10-07

Maintenance release: Windows build workflow and documentation updated.

## [1.0.0] - 2026-10-03

First version prepared for desktop distribution.

### Added

- Two separate cleanup actions: Clear for the text boxes and Clear JSON with confirmation.
- Logo embedded in the interface so it also appears in the executable header.

- Default `cloaktext.json` that is persistent next to the application; it is updated automatically and is not shown on screen.
- Export of the JSON key and optional choice of a custom JSON when restoring.
- Large spaCy models (`lg`) for all seven languages, downloaded on demand and verified by SHA-256.
- Models are stored in the portable `models` folder next to the executable.

- Responsive interface aimed at non-technical users.
- Loading and saving of restore keys in JSON.
- Direct copy of the protected text and of the restore key.
- Summary of the detected data types.
- Guided language preparation on first use.
- Interface support for Spanish, English, French, German, Italian, Portuguese and Catalan.
- Structured IPv4 detection and IBAN MOD-97 validation.
- Block processing for long texts.
- Automated engine tests.
- CI for Linux and reproducible Windows build.
- Portable Windows package without redistributing third-party language models.
- Optional download of large spaCy models from the official source with SHA-256 verification.
- Executable icon and metadata.

### Changed

- Migration from Flet 0.24 to Flet 1.0.
- Upgrade to spaCy 3.8.
- Entity overlap handling with lower memory usage.
- Structured patterns take priority over overlapping NER detections.
- Clearer error handling and processing states.
- The engine avoids collisions with tokens already present in the text.

### Fixed

- Immediate release of the previous large model when switching language, with forced garbage collection.
- The text boxes fill the full available width inside each card.
- The Windows process description is shown as CloakText.

- Conservative NER false-positive filter for obvious conversational greetings such as `hola`.

- Startup compatibility with Flet 1.0.3: the language selector uses `on_select`, the event supported by `Dropdown`.
- Full interface build test to detect API incompatibilities before generating the executable.

### Security

- Strict validation of the restore key format.
- The model is not unloaded from memory while processing.
- Explicit warnings about the sensitivity of the restore key.
- No internal error messages exposed to the end user.

## [0.1.0] - 2026-06-08

- Initial CloakText prototype.
- Reversible local anonymization with Flet and spaCy.
</content>
