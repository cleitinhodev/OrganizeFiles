"""Camadas de segurança: pastas proibidas, arquivos de sistema e arquivos sensíveis."""

from __future__ import annotations

import os
import re
import stat
import sys
import unicodedata
from pathlib import Path, PurePath, PurePosixPath, PureWindowsPath

from ..paths import app_data_dir


class UnsafeFolderError(Exception):
    """A pasta escolhida não pode ser organizada (sistema, raiz do disco...)."""

    def __init__(self, code: str, path: Path | str | None = None):
        super().__init__(code)
        self.code = code
        self.path = path


# --------------------------------------------------------------------------
# Pastas perigosas
# --------------------------------------------------------------------------
OK, CONFIRM, BLOCKED = "ok", "confirm", "blocked"

# POSIX: bloqueia a pasta e tudo dentro dela.
_POSIX_BLOCK_TREE = [
    "/bin", "/boot", "/dev", "/etc", "/lib", "/lib32", "/lib64", "/libx32", "/proc", "/run",
    "/sbin", "/sys", "/usr", "/snap", "/opt", "/System", "/Library", "/Applications",
    "/private/etc", "/var/lib", "/var/log", "/var/cache", "/var/spool", "/var/db",
]
# POSIX: bloqueia apenas a própria pasta (pontos de montagem, raiz das homes...).
_POSIX_BLOCK_EXACT = ["/var", "/private", "/tmp", "/mnt", "/media", "/Volumes", "/home", "/Users", "/srv", "/root"]

# Subpastas da home que guardam configurações/segredos de programas.
_HOME_BLOCK_TREE = [".ssh", ".gnupg", ".config", ".local", ".cache", "AppData", "Library", ".mozilla", "snap"]


def _norm_parts(p: PurePath, nt: bool) -> tuple[str, ...]:
    parts = p.parts
    return tuple(x.casefold().rstrip("\\/") for x in parts) if nt else parts


def _is_within(p: PurePath, base: PurePath, nt: bool) -> bool:
    a, b = _norm_parts(p, nt), _norm_parts(base, nt)
    return len(a) >= len(b) and a[: len(b)] == b


def _same(p: PurePath, base: PurePath, nt: bool) -> bool:
    return _norm_parts(p, nt) == _norm_parts(base, nt)


def windows_system_dirs(env: dict[str, str]) -> list[PureWindowsPath]:
    drive = env.get("SystemDrive", "C:")
    dirs = [
        env.get("SystemRoot") or env.get("windir") or f"{drive}\\Windows",
        env.get("ProgramFiles") or f"{drive}\\Program Files",
        env.get("ProgramFiles(x86)") or f"{drive}\\Program Files (x86)",
        env.get("ProgramW6432") or f"{drive}\\Program Files",
        env.get("ProgramData") or f"{drive}\\ProgramData",
        f"{drive}\\$Recycle.Bin",
        f"{drive}\\System Volume Information",
        f"{drive}\\Recovery",
        f"{drive}\\PerfLogs",
    ]
    return [PureWindowsPath(d) for d in dirs]


def classify_pure(p: PurePath, home: PurePath, data_dir: PurePath | None, nt: bool,
                  env: dict[str, str] | None = None) -> tuple[str, str]:
    """Classificação sem acesso ao disco (testável para Windows e POSIX)."""
    if len(p.parts) <= 1 or p.parent == p:
        return BLOCKED, "root"
    if data_dir is not None and _is_within(p, data_dir, nt):
        return BLOCKED, "app_data"
    if _same(p, home, nt):
        return CONFIRM, "home"
    if _is_within(home, p, nt):
        return BLOCKED, "above_home"
    if _is_within(p, home, nt):
        for sub in _HOME_BLOCK_TREE:
            if _is_within(p, home / sub, nt):
                return BLOCKED, "app_config"
        return OK, ""
    if nt:
        for d in windows_system_dirs(env or {}):
            if _is_within(p, d, nt):
                return BLOCKED, "system"
        if len(p.parts) == 2 and p.parts[1].casefold() in ("users", "documents and settings"):
            return BLOCKED, "above_home"
        return OK, ""
    for d in _POSIX_BLOCK_TREE:
        if _is_within(p, PurePosixPath(d), nt):
            return BLOCKED, "system"
    for d in _POSIX_BLOCK_EXACT:
        if _same(p, PurePosixPath(d), nt):
            return BLOCKED, "system"
    return OK, ""


def classify_folder(path: Path | str) -> tuple[str, str]:
    """Retorna ``(nível, código)``; nível é ``ok``, ``confirm`` ou ``blocked``."""
    try:
        p = Path(path).expanduser().resolve()
    except (OSError, RuntimeError):
        return BLOCKED, "not_a_dir"
    if not p.is_dir():
        return BLOCKED, "not_a_dir"
    nt = os.name == "nt"
    try:
        home = Path.home().resolve()
    except (OSError, RuntimeError):  # pragma: no cover
        home = PurePosixPath("/nonexistent-home")
    return classify_pure(p, home, app_data_dir().resolve(), nt, dict(os.environ))


def ensure_folder_allowed(path: Path) -> None:
    level, code = classify_folder(path)
    if level == BLOCKED:
        raise UnsafeFolderError(code, path)


# --------------------------------------------------------------------------
# Arquivos que nunca devem ser movidos
# --------------------------------------------------------------------------
SYSTEM_NAMES = {
    "desktop.ini", "thumbs.db", "ehthumbs.db", "ehthumbs_vista.db", ".ds_store", ".localized",
    "icon\r", ".directory", ".spotlight-v100", ".trashes", ".fseventsd", "$recycle.bin",
    "pagefile.sys", "hiberfil.sys", "swapfile.sys", "ntuser.dat", "iconcache.db",
}
TEMP_SUFFIXES = {".crdownload", ".part", ".partial", ".download", ".tmp", ".temp", ".!ut",
                 ".opdownload", ".swp", ".lock"}
TEMP_PREFIXES = ("~$", ".~lock")


def is_hidden(path: Path, st: os.stat_result | None = None) -> bool:
    if path.name.startswith("."):
        return True
    attrs = getattr(st, "st_file_attributes", 0) if st is not None else 0
    return bool(attrs & stat.FILE_ATTRIBUTE_HIDDEN)


def skip_reason(path: Path, st: os.stat_result, own_paths: set[Path] | None = None) -> str | None:
    """Código do motivo para nunca mover este arquivo (ou ``None``)."""
    if stat.S_ISLNK(st.st_mode) or (hasattr(path, "is_junction") and path.is_junction()):
        return "symlink"
    name = path.name.casefold()
    attrs = getattr(st, "st_file_attributes", 0)
    if name in SYSTEM_NAMES or attrs & stat.FILE_ATTRIBUTE_SYSTEM:
        return "system_file"
    if name.startswith(TEMP_PREFIXES) or any(name.endswith(s) for s in TEMP_SUFFIXES):
        return "temp"
    if own_paths:
        try:
            if path.resolve() in own_paths:
                return "own_app"
        except OSError:
            pass
    return None


# --------------------------------------------------------------------------
# Arquivos sensíveis
# --------------------------------------------------------------------------
_SENSITIVE_EXT = {
    # chaves privadas / criptografia
    ".pem": "private_key", ".key": "private_key", ".ppk": "private_key", ".p8": "private_key",
    ".gpg": "private_key", ".pgp": "private_key", ".asc": "private_key", ".jks": "private_key",
    ".keystore": "private_key", ".sec": "private_key",
    # certificados com chave
    ".pfx": "certificate", ".p12": "certificate",
    # cofres de senha
    ".kdbx": "password_db", ".kdb": "password_db", ".1pif": "password_db", ".opvault": "password_db",
    ".psafe3": "password_db", ".agilekeychain": "password_db", ".bitwarden": "password_db",
    # carteiras de criptomoedas
    ".wallet": "crypto_wallet",
    # configs que costumam guardar credenciais
    ".ovpn": "credentials", ".rdp": "credentials",
}
_SENSITIVE_NAMES = {
    "id_rsa": "private_key", "id_dsa": "private_key", "id_ecdsa": "private_key",
    "id_ed25519": "private_key", "id_ecdsa_sk": "private_key", "id_ed25519_sk": "private_key",
    "wallet.dat": "crypto_wallet", "electrum.dat": "crypto_wallet",
    ".npmrc": "credentials", ".pypirc": "credentials", ".netrc": "credentials", "_netrc": "credentials",
    ".git-credentials": "credentials", ".pgpass": "credentials", ".htpasswd": "credentials",
    "credentials": "credentials", "credentials.json": "credentials", "credentials.csv": "credentials",
    "client_secret.json": "credentials", "service-account.json": "credentials",
    "secrets.json": "credentials", "secrets.yml": "credentials", "secrets.yaml": "credentials",
    ".dockercfg": "credentials", "kubeconfig": "credentials", "known_hosts": "credentials",
    # bancos de dados de navegadores (Chrome/Edge/Firefox)
    "cookies": "browser_data", "login data": "browser_data", "web data": "browser_data",
    "history": "browser_data", "local state": "browser_data", "cookies.sqlite": "browser_data",
    "places.sqlite": "browser_data", "formhistory.sqlite": "browser_data", "key3.db": "browser_data",
    "key4.db": "browser_data", "logins.json": "browser_data", "cert9.db": "browser_data",
    "signons.sqlite": "browser_data", "login data for account": "browser_data",
}
_LONG_KEYWORDS = (
    "senha", "password", "passwd", "credencia", "credential", "secret", "segredo", "apikey",
    "api_key", "api-key", "privatekey", "private_key", "private-key", "chaveprivada",
    "chave_privada", "chave-privada", "recovery_code", "recovery-code", "recoverycode",
    "codigos_de_recuperacao", "codigos de recuperacao", "codigo de recuperacao", "backup_codes",
    "backup-codes", "backup codes", "mnemonic", "seed phrase", "seedphrase", "seed_phrase",
    "frase de recuperacao", "frase_semente", "keystore", "bitwarden", "lastpass", "1password",
    "keepass", "authenticator",
)
_SHORT_KEYWORDS = re.compile(r"(?<![a-z0-9])(pwd|pass|token|tokens|2fa|otp|pin|seed|cpf|rg)(?![a-z0-9])")


def _normalize(text: str) -> str:
    text = unicodedata.normalize("NFKD", text)
    return "".join(ch for ch in text if not unicodedata.combining(ch)).casefold()


def sensitive_reason(path: Path | str) -> str | None:
    """Detecta arquivos com cara de segredo. Retorna um código ou ``None``."""
    p = Path(path)
    name = p.name.casefold()
    if name in _SENSITIVE_NAMES:
        return _SENSITIVE_NAMES[name]
    if name.endswith(".pub"):
        return None  # chave pública não é segredo
    if name == ".env" or name.startswith(".env.") or name.endswith(".env"):
        return "env_file"
    suffix = p.suffix.casefold()
    if suffix in _SENSITIVE_EXT:
        return _SENSITIVE_EXT[suffix]
    stem = _normalize(p.stem if suffix else p.name)
    if any(k in stem for k in _LONG_KEYWORDS) or _SHORT_KEYWORDS.search(stem):
        return "name_keyword"
    return None


def is_windows() -> bool:
    return sys.platform.startswith("win")
