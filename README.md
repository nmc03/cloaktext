<p align="center">
  <img src="assets/cloaktext.png" alt="CloakText logo" width="128">
</p>

<h1 align="center">CloakText</h1>

<p align="center">
  Protección local y reversible para texto sensible.
</p>

<p align="center">
  <img alt="Python 3.11–3.14" src="https://img.shields.io/badge/Python-3.11%E2%80%933.14-3776AB?logo=python&logoColor=white">
  <img alt="Windows" src="https://img.shields.io/badge/Windows-10%20%2F%2011-0078D4?logo=windows11&logoColor=white">
  <img alt="CI" src="https://github.com/nmc03/cloaktext/actions/workflows/ci.yml/badge.svg">
  <img alt="License MIT" src="https://img.shields.io/badge/License-MIT-green.svg">
  <img alt="Privacy" src="https://img.shields.io/badge/text%20processing-local-2E7D32">
</p>

CloakText protege datos sensibles dentro de un texto sustituyéndolos por identificadores reversibles como `[PERSONA_1000]` o `[EMAIL_1001]`. La clave de restauración permite recuperar exactamente los valores originales cuando sea necesario.

El texto se procesa en el propio equipo. No se envía a una API ni a un servidor para protegerlo o restaurarlo.

## Por qué CloakText

- **Privacidad local:** el contenido permanece en tu equipo.
- **Reversible:** puedes recuperar el texto original con la clave generada.
- **Fácil de revisar:** muestra qué tipos de datos ha protegido.
- **Sin cuenta:** no requiere registro ni servicio remoto.
- **Sin telemetría de contenido:** CloakText no recopila el texto procesado.
- **Open source:** el código propio se publica bajo MIT.

> [!IMPORTANT]
> La detección automática puede omitir información sensible. Revisa siempre el resultado antes de compartirlo.

## Qué protege

CloakText combina reglas para datos estructurados con reconocimiento de entidades mediante spaCy. Puede detectar, según el idioma:

- personas;
- lugares;
- organizaciones;
- direcciones de correo;
- IBAN;
- IPv4;
- teléfonos;
- documentos de identidad;
- pasaportes;
- determinadas fechas.

Idiomas disponibles: español, inglés, francés, alemán, italiano, portugués y catalán.

## Descargar para Windows

Las versiones estables se publican en [GitHub Releases](https://github.com/nmc03/cloaktext/releases).

Descarga:

```text
CloakText-<versión>-windows-x64.zip
```

Descomprímelo completo y ejecuta:

```text
CloakText/
└── CloakText.exe
```

CloakText utiliza una distribución portable `onedir`: `CloakText.exe` debe permanecer junto al resto de archivos de su carpeta.

Cada release incluye `SHA256SUMS.txt`.

### Verificar el ZIP

```powershell
Get-FileHash .\CloakText-1.0.1-windows-x64.zip -Algorithm SHA256
Get-Content .\SHA256SUMS.txt
```

Los hashes deben coincidir.

La primera versión no está firmada digitalmente, por lo que Windows SmartScreen puede mostrar una advertencia.

## Primer uso

El paquete base no redistribuye modelos lingüísticos de terceros. Al utilizar un idioma por primera vez, CloakText muestra:

- el paquete que necesita;
- su tamaño;
- la licencia del paquete.

Solo si el usuario acepta, CloakText lo descarga desde los releases oficiales de `explosion/spacy-models`, verifica un SHA-256 fijado en el código y lo instala dentro de la carpeta de datos de CloakText.

Después de esa instalación inicial, el análisis de ese idioma vuelve a ser local y puede funcionar sin conexión.

Esto mantiene clara la licencia MIT de CloakText y evita mezclar dentro del ZIP modelos que tienen licencias distintas.

## Uso

### Proteger un texto

1. Selecciona **Proteger**.
2. Elige el idioma.
3. Pega el texto.
4. Si es la primera vez que usas ese idioma, pulsa **Instalar idioma** y revisa su licencia.
5. Pulsa **Proteger datos**.
6. Revisa el texto protegido antes de compartirlo.
7. Si necesitas restaurarlo en el futuro, guarda la **clave de restauración**.

### Restaurar un texto

1. Selecciona **Restaurar**.
2. Pega el texto protegido.
3. Abre o pega su clave JSON.
4. Pulsa **Restaurar texto**.

> [!WARNING]
> La clave de restauración contiene los datos originales. Protégela como protegerías el documento original.

## Ejecutar desde código fuente

Requiere Python **3.11–3.14**. Se recomienda Python 3.12.

### Windows

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements-dev.txt
python main.py
```

### Linux / macOS

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements-dev.txt
python main.py
```

La propia aplicación gestiona la instalación opcional de los paquetes de idioma. Para desarrollo también puedes instalar uno manualmente, por ejemplo:

```bash
python -m spacy download es_core_news_sm
```

## Compilar el EXE final

El ejecutable Windows debe construirse en Windows.

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements-dev.txt

python -m pytest
python -m compileall -q main.py motor_local.py language_models.py version.py
python -m pip check

python build.py
```

Salida:

```text
dist/
├── CloakText/
│   ├── CloakText.exe
│   ├── LICENSE.txt
│   └── THIRD_PARTY_NOTICES.md
├── CloakText-1.0.1-windows-x64.zip
└── SHA256SUMS.txt
```

Los modelos de idioma no se incluyen en el ZIP y no es necesario instalarlos para generar el ejecutable.

Consulta [docs/BUILDING.md](docs/BUILDING.md) para el proceso de publicación.

## Desarrollo

```bash
python -m pytest
python -m compileall -q main.py motor_local.py language_models.py version.py
python -m pip check
```

Estructura:

```text
main.py               Interfaz Flet
motor_local.py        Detección y protección reversible
language_models.py    Descarga, verificación e instalación de idiomas
build.py              Build portable de Windows
version.py            Versión
tests/                Pruebas automatizadas
.github/workflows/    CI, build Windows y release
```

## Seguridad y privacidad

- El contenido se procesa localmente.
- Las descargas de idioma provienen de un origen fijado y se verifican por SHA-256 antes de instalarse.
- La extracción del paquete rechaza rutas inseguras.
- No publiques textos reales sensibles ni claves de restauración en issues.

Consulta [SECURITY.md](SECURITY.md) para vulnerabilidades.

## Contribuir

Consulta [CONTRIBUTING.md](CONTRIBUTING.md).

## Versiones

CloakText usa versionado semántico. Consulta [CHANGELOG.md](CHANGELOG.md).

La versión estable preparada para publicación es **v1.0.1**.

## Licencia

El código original de CloakText se publica bajo la [MIT License](LICENSE).

Flet, spaCy y los paquetes lingüísticos opcionales mantienen sus propias licencias. Consulta [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).

## Autor

Copyright © 2026 Nahúm ([@nmc03](https://github.com/nmc03)).
