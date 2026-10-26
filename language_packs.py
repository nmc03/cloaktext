"""Secure management of CloakText's optional language packs."""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import importlib.util
import os
from pathlib import Path, PurePosixPath
import shutil
import tempfile
from typing import Callable
from urllib.request import Request, urlopen
import zipfile

from key_store import application_directory

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

SPACY_MODELS = {code: info.package for code, info in MODEL_INFO.items()}
SUPPORTED_LANGUAGES = frozenset(MODEL_INFO)


def data_directory() -> Path:
    """Portable root for data downloaded by the application.

    In production it is the folder that contains CloakText.exe.
    CLOAKTEXT_DATA_DIR is kept only as an override for tests and
    automated development.
    """
    override = os.environ.get("CLOAKTEXT_DATA_DIR")
    if override:
        return Path(override).expanduser().resolve()
    return application_directory()


def models_directory() -> Path:
    return data_directory() / "models"


def model_info(language: str) -> ModelInfo:
    try:
        return MODEL_INFO[language]
    except KeyError as exc:
        raise ValueError(f"Unsupported language: {language}") from exc


def local_model_path(language: str) -> Path | None:
    info = model_info(language)
    file_path = models_directory() / info.package / info.package / f"{info.package}-{MODEL_VERSION}"
    return file_path if (file_path / "meta.json").is_file() else None


def model_available(language: str) -> bool:
    info = model_info(language)
    return importlib.util.find_spec(info.package) is not None or local_model_path(language) is not None


def install_model(language: str, progress: Callable[[int, int], None] | None = None) -> Path:
    """Download, verify and install an official model in the user's profile."""
    info = model_info(language)
    destination = models_directory() / info.package
    existing = local_model_path(language)
    if existing:
        return existing

    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="cloaktext-model-") as tmp:
        temp_dir = Path(tmp)
        wheel = temp_dir / info.filename
        req = Request(
            info.url,
            headers={"User-Agent": "CloakText/1.0 (+https://github.com/nmc03/cloaktext)"},
        )
        digest = sha256()
        downloaded = 0
        with urlopen(req, timeout=60) as response, wheel.open("wb") as output:
            total = int(response.headers.get("Content-Length") or info.size_bytes)
            while True:
                chunk = response.read(1024 * 256)
                if not chunk:
                    break
                output.write(chunk)
                digest.update(chunk)
                downloaded += len(chunk)
                if progress:
                    progress(downloaded, total)

        if downloaded != info.size_bytes:
            raise ValueError("The downloaded package does not have the expected size. Nothing was installed.")
        if digest.hexdigest().lower() != info.sha256:
            raise ValueError("The SHA-256 check of the package failed. Nothing was installed.")

        extracted = temp_dir / "extracted"
        _safe_extract_wheel(wheel, extracted)
        model_path = extracted / info.package / f"{info.package}-{MODEL_VERSION}"
        if not (model_path / "meta.json").is_file():
            raise ValueError("The language pack does not contain a valid spaCy model.")

        if destination.exists():
            shutil.rmtree(destination)
        shutil.move(str(extracted), str(destination))

    installed = local_model_path(language)
    if installed is None:
        raise ValueError("The package was downloaded but could not be activated correctly.")
    return installed


def _safe_extract_wheel(wheel: Path, destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    base = destination.resolve()
    with zipfile.ZipFile(wheel) as zf:
        for member in zf.infolist():
            file_path = PurePosixPath(member.filename)
            if file_path.is_absolute() or ".." in file_path.parts:
                raise ValueError("The language pack contains an unsafe path.")
            target_path = (destination / Path(*file_path.parts)).resolve()
            if base != target_path and base not in target_path.parents:
                raise ValueError("The language pack tries to write outside its folder.")
        zf.extractall(destination)
