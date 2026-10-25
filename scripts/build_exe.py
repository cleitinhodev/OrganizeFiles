"""Gera o executável com PyInstaller (Windows .exe, macOS .app zipado, Linux binário).

Uso:  python scripts/build_exe.py
Saída: dist/  (+ arquivo .sha256 ao lado de cada artefato)
"""

from __future__ import annotations

import hashlib
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path

import PyInstaller.__main__

ROOT = Path(__file__).resolve().parents[1]
NAME = "OrganizeFiles"
EXCLUDES = ["tkinter", "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets", "PySide6.Qt3DCore",
            "PySide6.QtQuick", "PySide6.QtQml", "PySide6.QtMultimedia", "PySide6.QtPdf"]


def sha256(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def main() -> int:
    sep = os.pathsep
    is_mac = sys.platform == "darwin"
    args = [
        str(ROOT / "launcher.py"), "--noconfirm", "--clean", "--windowed", "--name", NAME,
        "--icon", str(ROOT / "Design" / "icone.ico"),
        "--add-data", f"{ROOT / 'Design' / 'icone.ico'}{sep}Design",
        "--add-data", f"{ROOT / 'organizefiles' / 'resources'}{sep}organizefiles/resources",
        "--distpath", str(ROOT / "dist"), "--workpath", str(ROOT / "build"), "--specpath", str(ROOT / "build"),
    ]
    if not is_mac:
        args.append("--onefile")
    for mod in EXCLUDES:
        args += ["--exclude-module", mod]
    PyInstaller.__main__.run(args)

    dist = ROOT / "dist"
    arch = platform.machine().lower() or "x64"
    if is_mac:
        artifact = dist / f"{NAME}-macos-{arch}.zip"
        subprocess.run(["ditto", "-c", "-k", "--keepParent", str(dist / f"{NAME}.app"), str(artifact)], check=True)
    elif sys.platform.startswith("win"):
        artifact = dist / f"{NAME}-windows-{arch}.exe"
        shutil.move(str(dist / f"{NAME}.exe"), artifact)
    else:
        artifact = dist / f"{NAME}-linux-{arch}"
        shutil.move(str(dist / NAME), artifact)
    digest = sha256(artifact)
    (artifact.parent / f"{artifact.name}.sha256").write_text(f"{digest}  {artifact.name}\n", encoding="utf-8")
    print(f"Artefato: {artifact}\nSHA-256: {digest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
