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
    "es": ModelInfo("es", "es_core_news_sm", "GNU GPL 3.0", 12_884_212, "e451a83d6df79b87e9eed0cb553f03e99e36a3bab18a7b79f0dcfd1fdf875e12"),
    "en": ModelInfo("en", "en_core_web_sm", "MIT", 12_806_118, "1932429db727d4bff3deed6b34cfc05df17794f4a52eeb26cf8928f7c1a0fb85"),
    "fr": ModelInfo("fr", "fr_core_news_sm", "LGPL-LR", 16_271_721, "7d6ad14cd5078e53147bfbf70fb9d433c6a3865b695fda2657140bbc59a27e29"),
    "de": ModelInfo("de", "de_core_news_sm", "MIT", 14_639_490, "fec69fec52b1780f2d269d5af7582a5e28028738bd3190532459aeb473bfa3e7"),
    "it": ModelInfo("it", "it_core_news_sm", "CC BY-NC-SA 3.0", 13_030_943, "3f617bf9a8ae0418953cf1fbf014e10272684c4229e882a7fd748b637d0100bf"),
    "pt": ModelInfo("pt", "pt_core_news_sm", "CC BY-SA 4.0", 12_985_007, "c304fa04db3af73cd08a250feacf560506e15a2ec2469bd1b09f06847f6b455c"),
    "ca": ModelInfo("ca", "ca_core_news_sm", "GNU GPL 3.0", 19_566_606, "e214211aa8da91c24ebdc453c2aa5f54fac09f44e01e65bcbdd3b0a5cb94d809"),
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
