"""Estruturas de dados do plano de organização."""

from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path


class Mode(str, Enum):
    CATEGORY = "categoria"
    EXTENSION = "extensao"
    DATE = "data"
    ALPHABET = "abc"

    @classmethod
    def parse(cls, value: str) -> "Mode":
        aliases = {
            "categoria": cls.CATEGORY, "category": cls.CATEGORY, "cat": cls.CATEGORY,
            "inteligente": cls.CATEGORY, "smart": cls.CATEGORY,
            "extensao": cls.EXTENSION, "extensão": cls.EXTENSION, "extension": cls.EXTENSION,
            "ext": cls.EXTENSION, "tipo": cls.EXTENSION, "type": cls.EXTENSION,
            "data": cls.DATE, "date": cls.DATE,
            "abc": cls.ALPHABET, "alfabeto": cls.ALPHABET, "alphabet": cls.ALPHABET,
        }
        try:
            return aliases[value.strip().lower()]
        except KeyError:
            raise ValueError(f"Modo desconhecido: {value}") from None


class DupStrategy(str, Enum):
    NONE = "none"            # não procura duplicados
    SKIP = "skip"            # mantém o mais antigo, os outros ficam onde estão
    KEEP_NEWEST = "newest"   # mantém o mais novo, os outros vão para a lixeira
    TRASH = "trash"          # mantém o mais antigo, os outros vão para a lixeira


class BackupMode(str, Enum):
    NONE = "none"
    ZIP = "zip"
    FOLDER = "folder"


class Action(str, Enum):
    MOVE = "move"
    TRASH = "trash"
    SKIP = "skip"


@dataclass
class PlanOptions:
    mode: Mode = Mode.CATEGORY
    recursive: bool = False
    include_sensitive: bool = False
    include_hidden: bool = False
    duplicates: DupStrategy = DupStrategy.NONE
    use_exif: bool = True
    lang: str = "pt_BR"


@dataclass
class PlanItem:
    src: Path
    size: int
    mtime: float
    category_id: str
    category_name: str
    action: Action = Action.MOVE
    dst: Path | None = None
    skip_reason: str | None = None       # código: symlink, system_file, hidden, temp, own_app, ...
    sensitive_reason: str | None = None  # código: private_key, password_db, ...
    renamed: bool = False                # destino renomeado para evitar sobrescrita
    duplicate_of: Path | None = None
    sha256: str | None = None

    @property
    def is_sensitive(self) -> bool:
        return self.sensitive_reason is not None

    @property
    def status(self) -> str:
        """Status resumido para a interface: move, renamed, duplicate, sensitive, skip."""
        if self.action is Action.TRASH or (self.duplicate_of is not None and self.action is Action.SKIP):
            return "duplicate"
        if self.is_sensitive and self.action is Action.SKIP:
            return "sensitive"
        if self.action is Action.SKIP:
            return "skip"
        if self.renamed:
            return "renamed"
        return "move"


@dataclass
class Plan:
    root: Path
    options: PlanOptions
    items: list[PlanItem] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.now)
    category_colors: dict[str, str] = field(default_factory=dict)
    skipped_dirs: list[Path] = field(default_factory=list)
    scan_errors: list[tuple[str, str]] = field(default_factory=list)
    root_is_project: bool = False

    # --------------------------------------------------------------- filtros
    def with_action(self, action: Action) -> list[PlanItem]:
        return [i for i in self.items if i.action is action]

    @property
    def moves(self) -> list[PlanItem]:
        return self.with_action(Action.MOVE)

    @property
    def trashes(self) -> list[PlanItem]:
        return self.with_action(Action.TRASH)

    @property
    def skipped(self) -> list[PlanItem]:
        return self.with_action(Action.SKIP)

    @property
    def renamed(self) -> list[PlanItem]:
        return [i for i in self.items if i.renamed and i.action is Action.MOVE]

    @property
    def sensitive(self) -> list[PlanItem]:
        return [i for i in self.items if i.is_sensitive]

    @property
    def sensitive_in_action(self) -> list[PlanItem]:
        """Arquivos sensíveis que SERÃO movidos ou enviados para a lixeira."""
        return [i for i in self.items if i.is_sensitive and i.action is not Action.SKIP]

    @property
    def duplicates(self) -> list[PlanItem]:
        return [i for i in self.items if i.duplicate_of is not None]

    @property
    def total_size(self) -> int:
        return sum(i.size for i in self.items)

    @property
    def has_work(self) -> bool:
        return any(i.action is not Action.SKIP for i in self.items)

    def destination_folders(self) -> set[Path]:
        return {i.dst.parent for i in self.moves if i.dst is not None}

    def exclude_sensitive(self) -> int:
        """Remove do plano as ações sobre arquivos sensíveis. Retorna quantos foram excluídos."""
        n = 0
        for i in self.items:
            if i.is_sensitive and i.action is not Action.SKIP:
                i.action = Action.SKIP
                i.dst = None
                i.renamed = False
                i.skip_reason = i.skip_reason or "sensitive"
                n += 1
        return n

    def stats_by_category(self) -> "OrderedDict[str, tuple[int, int]]":
        """{nome da categoria: (quantidade, bytes)} ordenado por quantidade."""
        acc: dict[str, list[int]] = {}
        for i in self.items:
            if i.skip_reason in ("symlink", "system_file", "temp", "own_app"):
                continue
            c = acc.setdefault(i.category_name, [0, 0])
            c[0] += 1
            c[1] += i.size
        return OrderedDict(sorted(((k, (v[0], v[1])) for k, v in acc.items()), key=lambda kv: -kv[1][0]))

    def summary(self) -> dict[str, int]:
        return {
            "total": len(self.items),
            "move": len(self.moves),
            "renamed": len(self.renamed),
            "trash": len(self.trashes),
            "skip": len(self.skipped),
            "sensitive": len(self.sensitive),
            "duplicates": len(self.duplicates),
            "folders": len(self.destination_folders()),
            "size": self.total_size,
            "move_size": sum(i.size for i in self.moves),
        }


def human_size(n: float) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if abs(n) < 1024 or unit == "TB":
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} TB"  # pragma: no cover
