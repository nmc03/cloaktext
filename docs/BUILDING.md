# Compilar y publicar CloakText

## Requisitos

- Windows 10/11 x64.
- Python 3.12 recomendado.
- Git.

Los modelos spaCy `lg` no se incluyen en la distribución base.

## Crear el entorno

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements-dev.txt
```

## Verificar

```powershell
python -m pytest
python -m compileall -q main.py motor_local.py language_models.py version.py
python -m pip check
```

## Compilar

```powershell
python build.py
```

`build.py`:

1. exige Windows;
2. limpia artefactos anteriores;
3. empaqueta CloakText con Flet/PyInstaller en modo `onedir`;
4. incorpora licencia MIT y avisos principales de terceros;
5. crea el ZIP portable;
6. genera `SHA256SUMS.txt`.

Resultado:

```text
dist/
├── CloakText/
│   ├── CloakText.exe
│   └── ...
├── CloakText-1.0.0-windows-x64.zip
└── SHA256SUMS.txt
```

## Paquetes de idioma

No forman parte del ZIP de CloakText.

En primer uso, la aplicación descarga el paquete elegido desde los releases oficiales de `explosion/spacy-models`, verifica el tamaño y SHA-256 fijados y lo extrae de forma segura dentro del perfil local del usuario.

Esto evita redistribuir dentro del binario paquetes con licencias heterogéneas.

## GitHub Actions

- `CI`: tests, bytecode y dependencias.
- `Windows build`: valida un PR y genera el paquete Windows como artefacto.
- `Release`: al publicar un tag `v*`, reconstruye desde cero y crea la GitHub Release con ZIP + `SHA256SUMS.txt`.

GitHub genera automáticamente los archivos de código fuente de cada release.

## Publicar una versión

Antes del tag:

1. actualiza versión y `CHANGELOG.md`;
2. comprueba CI y build Windows;
3. revisa las notas `.github/release-notes/vX.Y.Z.md`;
4. verifica que `main` sea la única rama de publicación necesaria;
5. crea `vX.Y.Z`.

```powershell
git tag v1.0.0
git push origin v1.0.0
```
