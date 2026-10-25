import os
import sys
from pathlib import Path, PurePosixPath, PureWindowsPath

import pytest

from conftest import make
from organizefiles.core import Action, PlanOptions, UnsafeFolderError, build_plan, classify_folder
from organizefiles.core.safety import BLOCKED, CONFIRM, OK, classify_pure, sensitive_reason

HOME_P = PurePosixPath("/home/ana")
DATA_P = PurePosixPath("/home/ana/.local/share/organizefiles")


@pytest.mark.parametrize("p,level", [
    ("/", BLOCKED), ("/usr", BLOCKED), ("/usr/share/x", BLOCKED), ("/etc", BLOCKED),
    ("/home", BLOCKED), ("/tmp", BLOCKED), ("/System/Library", BLOCKED),
    ("/home/ana", CONFIRM), ("/home/ana/Downloads", OK), ("/home/ana/.ssh", BLOCKED),
    ("/home/ana/.config/app", BLOCKED), ("/home/ana/.local/share/organizefiles", BLOCKED),
    ("/tmp/pasta", OK), ("/mnt/hd/fotos", OK), ("/media", BLOCKED),
])
def test_posix_rules(p, level):
    assert classify_pure(PurePosixPath(p), HOME_P, DATA_P, nt=False)[0] == level


ENV = {"SystemDrive": "C:", "SystemRoot": "C:\\Windows", "ProgramFiles": "C:\\Program Files",
       "ProgramFiles(x86)": "C:\\Program Files (x86)", "ProgramData": "C:\\ProgramData"}
HOME_W = PureWindowsPath("C:/Users/Ana")


@pytest.mark.parametrize("p,level", [
    ("C:\\", BLOCKED), ("D:\\", BLOCKED), ("c:\\windows", BLOCKED), ("C:\\Windows\\System32", BLOCKED),
    ("C:\\Program Files\\App", BLOCKED), ("C:\\Program Files (x86)", BLOCKED),
    ("C:\\ProgramData", BLOCKED), ("C:\\Users", BLOCKED), ("C:\\Users\\Ana", CONFIRM),
    ("c:\\users\\ana\\Downloads", OK), ("C:\\Users\\Ana\\AppData\\Roaming", BLOCKED),
    ("D:\\Fotos", OK),
])
def test_windows_rules(p, level):
    assert classify_pure(PureWindowsPath(p), HOME_W, None, nt=True, env=ENV)[0] == level


def test_real_root_blocked_and_plan_refuses():
    root = Path(Path.cwd().anchor)
    assert classify_folder(root)[0] == BLOCKED
    with pytest.raises(UnsafeFolderError):
        build_plan(root)


def test_missing_folder_blocked(tmp_path):
    assert classify_folder(tmp_path / "nao-existe") == (BLOCKED, "not_a_dir")


def test_system_hidden_temp_files_are_skipped(folder):
    for n in ["desktop.ini", "Thumbs.db", ".DS_Store", ".oculto.txt", "baixando.crdownload",
              "~$planilha.xlsx", "ok.txt"]:
        make(folder, n)
    plan = build_plan(folder)
    reasons = {i.src.name: i.skip_reason for i in plan.items}
    assert reasons["desktop.ini"] == reasons["Thumbs.db"] == reasons[".DS_Store"] == "system_file"
    assert reasons[".oculto.txt"] == "hidden"
    assert reasons["baixando.crdownload"] == reasons["~$planilha.xlsx"] == "temp"
    assert reasons["ok.txt"] is None
    assert [i.src.name for i in plan.moves] == ["ok.txt"]


@pytest.mark.skipif(sys.platform.startswith("win"), reason="symlink exige privilégio no Windows")
def test_symlinks_are_skipped(folder, tmp_path):
    target = tmp_path / "fora.txt"
    target.write_text("x")
    os.symlink(target, folder / "link.txt")
    plan = build_plan(folder)
    assert plan.items[0].skip_reason == "symlink"
    assert plan.items[0].action is Action.SKIP


def test_own_executable_is_skipped(folder, monkeypatch):
    exe = make(folder, "OrganizeFiles.exe")
    monkeypatch.setattr(sys, "argv", [str(exe)])
    plan = build_plan(folder)
    assert plan.items[0].skip_reason == "own_app"


@pytest.mark.parametrize("name,expected", [
    (".env", "env_file"), (".env.local", "env_file"), ("prod.env", "env_file"),
    ("server.pem", "private_key"), ("chave.key", "private_key"), ("id_rsa", "private_key"),
    ("id_ed25519", "private_key"), ("cofre.kdbx", "password_db"), ("wallet.dat", "crypto_wallet"),
    ("cert.pfx", "certificate"), ("cert.P12", "certificate"), ("Login Data", "browser_data"),
    ("cookies.sqlite", "browser_data"), ("key4.db", "browser_data"), ("credentials.json", "credentials"),
    ("minhas_senhas.txt", "name_keyword"), ("Senhas do Banco.xlsx", "name_keyword"),
    ("passwords.csv", "name_keyword"), ("codigos de recuperação.pdf", "name_keyword"),
    ("api_key.txt", "name_keyword"), ("meu token.txt", "name_keyword"),
])
def test_sensitive_detection(name, expected):
    assert sensitive_reason(name) == expected


@pytest.mark.parametrize("name", ["id_rsa.pub", "ferias.jpg", "relatorio.pdf", "tokenizer.py",
                                  "passaro.png", "compass.svg"])
def test_not_sensitive(name):
    assert sensitive_reason(name) is None


def test_sensitive_files_excluded_by_default(folder):
    make(folder, "senhas.txt")
    make(folder, "id_rsa")
    make(folder, "normal.txt")
    plan = build_plan(folder)
    assert {i.src.name for i in plan.moves} == {"normal.txt"}
    assert {i.status for i in plan.sensitive} == {"sensitive"}
    plan2 = build_plan(folder, PlanOptions(include_sensitive=True))
    assert len(plan2.sensitive_in_action) == 2
    assert plan2.exclude_sensitive() == 2
    assert {i.src.name for i in plan2.moves} == {"normal.txt"}
