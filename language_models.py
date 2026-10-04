"""Gestión segura de los paquetes de idioma opcionales de CloakText."""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import importlib.util
import os
from pathlib import Path, PurePosixPath
import shutil
import sys
import tempfile
from typing import Callable
from urllib.request import Request, urlopen
import zipfile

MODEL_VERSION = "3.8.0"


@dataclass(frozen=True)
class ModelInfo:
    language: str
    package: str
    license: str
    size_bytes: int
    sha256: str

    @property
    def tag(self) -> str:
        return f"{self.package}-{MODEL_VERSION}"

    @property
    def filename(self) -> str:
        return f"{self.package}-{MODEL_VERSION}-py3-none-any.whl"

    @property
    def url(self) -> str:
        return (
            "https://github.com/explosion/spacy-models/releases/download/"
            f"{self.tag}/{self.filename}"
        )


MODEL_INFO: dict[str, ModelInfo] = {
    "es": ModelInfo("es", "es_core_news_lg", "GNU GPL 3.0", 567_975_270, "7c6c212715a12f31aacde3361754436945ff7376fb24cde57d0c277c9c9b050b"),
    "en": ModelInfo("en", "en_core_web_lg", "MIT", 400_658_291, "293e9547a655b25499198ab15a525b05b9407a75f10255e405e8c3854329ab63"),
    "fr": ModelInfo("fr", "fr_core_news_lg", "LGPL-LR", 571_831_376, "da5bf7fc860af64293d88638b4416b3de3a29005b785bfff67d09b06c77345de"),
    "de": ModelInfo("de", "de_core_news_lg", "MIT", 567_843_151, "36fda650e476b54d5e87803635e36dadd1e8e034c4b5962088586d684f4c9fed"),
    "it": ModelInfo("it", "it_core_news_lg", "CC BY-NC-SA 3.0", 567_872_943, "b78582d0b2d05fd6509995f68ab7452efed7a27c6fbc5a071e9a9787a58c1e87"),
    "pt": ModelInfo("pt", "pt_core_news_lg", "CC BY-SA 4.0", 568_207_147, "2561c9a72a938d37141e9694e1a36d25061a44ce7e4f3bad2d3fa3bb836191af"),
    "ca": ModelInfo("ca", "ca_core_news_lg", "GNU GPL 3.0", 574_014_041, "6cee39a577ebee3a170154efdd67b7d8c290e6cfd5b8c6a243dff3fbbee14766"),
}

MODELOS_SPACY = {codigo: info.package for codigo, info in MODEL_INFO.items()}
IDIOMAS_SOPORTADOS = frozenset(MODEL_INFO)


def directorio_datos() -> Path:
    override = os.environ.get("CLOAKTEXT_DATA_DIR")
    if override:
        return Path(override).expanduser()
    if sys.platform == "win32":
        base = Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local")
        return base / "CloakText"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "CloakText"
    base = Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share")
    return base / "CloakText"


def directorio_modelos() -> Path:
    return directorio_datos() / "models"


def info_modelo(idioma: str) -> ModelInfo:
    try:
        return MODEL_INFO[idioma]
    except KeyError as exc:
        raise ValueError(f"Idioma no soportado: {idioma}") from exc


def ruta_modelo_local(idioma: str) -> Path | None:
    info = info_modelo(idioma)
    ruta = directorio_modelos() / info.package / info.package / f"{info.package}-{MODEL_VERSION}"
    return ruta if (ruta / "meta.json").is_file() else None


def modelo_disponible(idioma: str) -> bool:
    info = info_modelo(idioma)
    return importlib.util.find_spec(info.package) is not None or ruta_modelo_local(idioma) is not None


def instalar_modelo(idioma: str, progreso: Callable[[int, int], None] | None = None) -> Path:
    """Descarga, verifica e instala un modelo oficial en el perfil del usuario."""
    info = info_modelo(idioma)
    destino = directorio_modelos() / info.package
    existente = ruta_modelo_local(idioma)
    if existente:
        return existente

    destino.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="cloaktext-model-") as tmp:
        temporal = Path(tmp)
        wheel = temporal / info.filename
        req = Request(
            info.url,
            headers={"User-Agent": "CloakText/1.0 (+https://github.com/nmc03/cloaktext)"},
        )
        digest = sha256()
        descargado = 0
        with urlopen(req, timeout=60) as respuesta, wheel.open("wb") as salida:
            total = int(respuesta.headers.get("Content-Length") or info.size_bytes)
            while True:
                bloque = respuesta.read(1024 * 256)
                if not bloque:
                    break
                salida.write(bloque)
                digest.update(bloque)
                descargado += len(bloque)
                if progreso:
                    progreso(descargado, total)

        if descargado != info.size_bytes:
            raise ValueError("El paquete descargado no tiene el tamaño esperado. No se ha instalado nada.")
        if digest.hexdigest().lower() != info.sha256:
            raise ValueError("La verificación SHA-256 del paquete ha fallado. No se ha instalado nada.")

        extraido = temporal / "extracted"
        _extraer_wheel_seguro(wheel, extraido)
        ruta_modelo = extraido / info.package / f"{info.package}-{MODEL_VERSION}"
        if not (ruta_modelo / "meta.json").is_file():
            raise ValueError("El paquete de idioma no contiene un modelo spaCy válido.")

        if destino.exists():
            shutil.rmtree(destino)
        shutil.move(str(extraido), str(destino))

    instalado = ruta_modelo_local(idioma)
    if instalado is None:
        raise ValueError("El paquete se descargó, pero no pudo activarse correctamente.")
    return instalado


def _extraer_wheel_seguro(wheel: Path, destino: Path) -> None:
    destino.mkdir(parents=True, exist_ok=True)
    base = destino.resolve()
    with zipfile.ZipFile(wheel) as zf:
        for miembro in zf.infolist():
            ruta = PurePosixPath(miembro.filename)
            if ruta.is_absolute() or ".." in ruta.parts:
                raise ValueError("El paquete de idioma contiene una ruta no segura.")
            objetivo = (destino / Path(*ruta.parts)).resolve()
            if base != objetivo and base not in objetivo.parents:
                raise ValueError("El paquete de idioma intenta escribir fuera de su carpeta.")
        zf.extractall(destino)
