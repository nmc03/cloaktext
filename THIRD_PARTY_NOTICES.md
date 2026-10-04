# Third-party notices

CloakText original source code is licensed under the MIT License.

The base Windows distribution contains Flet, spaCy and their runtime dependencies. Language models are **not bundled** in the CloakText ZIP. When the user enables a language for the first time, CloakText can download the corresponding model package directly from the official `explosion/spacy-models` GitHub releases, verifies the pinned SHA-256 and stores the extracted model in the portable `models` directory next to `CloakText.exe`.

## Main bundled dependencies

| Component | Version used by v1.0.0 | License |
| --- | --- | --- |
| Flet | 1.0.3 | Apache License 2.0 |
| spaCy | 3.8.16 | MIT |

Copies of those primary license texts are included in `licenses/`.

## Optional language packages

These packages are obtained separately by the user and remain governed by their own licenses:

| Package | Language | Package license |
| --- | --- | --- |
| `en_core_web_lg` 3.8.0 | English | MIT |
| `de_core_news_lg` 3.8.0 | German | MIT |
| `es_core_news_lg` 3.8.0 | Spanish | GNU GPL 3.0 |
| `ca_core_news_lg` 3.8.0 | Catalan | GNU GPL 3.0 |
| `fr_core_news_lg` 3.8.0 | French | LGPL-LR |
| `pt_core_news_lg` 3.8.0 | Portuguese | CC BY-SA 4.0 |
| `it_core_news_lg` 3.8.0 | Italian | CC BY-NC-SA 3.0 |

CloakText displays the applicable package license before download. The MIT License for CloakText does not replace or override those terms.

## Transitive dependencies

The packaged application includes additional Python and runtime dependencies required by Flet, spaCy and PyInstaller. Their own licenses remain in force.
