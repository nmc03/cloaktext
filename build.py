"""Build the Windows distribution of CloakText.

spaCy models are not redistributed inside the ZIP. Each language pack is
installed on demand from the official releases, verified by SHA-256,
and stored locally in the user's profile.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
import shutil
import subprocess
import sys
import zipfile

from version import __version__

ROOT = Path(__file__).resolve().parent
DIST = ROOT / "dist"
APP_DIR = DIST / "CloakText"
EXE = APP_DIR / "CloakText.exe"
ARCHIVE = DIST / f"CloakText-{__version__}-windows-x64.zip"


def run(command: list[str]) -> None:
    print("+", " ".join(command), flush=True)
    subprocess.run(command, cwd=ROOT, check=True)


def build() -> Path:
    if sys.platform != "win32":
        raise SystemExit(
            "The Windows executable must be built on Windows. "
            "Use the 'Windows build' workflow or run build.py on Windows."
        )

    flet = shutil.which("flet")
    if not flet:
        raise SystemExit("The flet command was not found. Install requirements-dev.txt first.")

    if APP_DIR.exists():
        shutil.rmtree(APP_DIR)
    ARCHIVE.unlink(missing_ok=True)

    run(
        [
            flet,
            "pack",
            "main.py",
            "--name",
            "CloakText",
            "--onedir",
            "--icon",
            str(ROOT / "assets" / "cloaktext.ico"),
            "--product-name",
            "CloakText",
            "--file-description",
            "CloakText",
            "--product-version",
            __version__,
            "--file-version",
            f"{__version__}.0",
            "--company-name",
            "Nahúm",
            "--copyright",
            "Copyright (c) 2026 Nahúm",
            "--distpath",
            str(DIST),
            "--yes",
            "--pyinstaller-build-args=--clean",
        ]
    )

    if not EXE.is_file():
        raise SystemExit(f"Incomplete build: {EXE} does not exist")

    shutil.copy2(ROOT / "LICENSE", APP_DIR / "LICENSE.txt")
    shutil.copy2(ROOT / "THIRD_PARTY_NOTICES.md", APP_DIR / "THIRD_PARTY_NOTICES.md")
    bundled_licenses = APP_DIR / "licenses"
    if bundled_licenses.exists():
        shutil.rmtree(bundled_licenses)
    shutil.copytree(ROOT / "licenses", bundled_licenses)

    with zipfile.ZipFile(ARCHIVE, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for path in sorted(APP_DIR.rglob("*")):
            if path.is_file():
                zf.write(path, Path(APP_DIR.name) / path.relative_to(APP_DIR))

    digest = hashlib.sha256(ARCHIVE.read_bytes()).hexdigest()
    (DIST / "SHA256SUMS.txt").write_text(
        f"{digest}  {ARCHIVE.name}\n",
        encoding="utf-8",
    )

    print(f"\nEXE: {EXE}")
    print(f"ZIP: {ARCHIVE}")
    print(f"SHA256: {digest}")
    return ARCHIVE


if __name__ == "__main__":
    build()
