"""Regras de categorias (Imagens, Documentos, ...) carregadas de um arquivo JSON.

O arquivo padrão fica em ``organizefiles/resources/default_rules.json``. Para
personalizar, copie-o para ``<pasta de dados>/rules.json`` (veja README).
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path

from ..paths import package_resource, user_rules_path

log = logging.getLogger(__name__)


class RulesError(ValueError):
    pass


@dataclass(frozen=True)
class Category:
    id: str
    names: dict[str, str]
    color: str = "#8A8FA3"
    extensions: frozenset[str] = field(default_factory=frozenset)

    def display(self, lang: str = "pt_BR") -> str:
        return self.names.get(lang) or self.names.get("pt_BR") or self.names.get("en") or self.id


def _clean_name(name: str) -> str:
    bad = '<>:"/\\|?*'
    cleaned = "".join("_" if ch in bad or ord(ch) < 32 else ch for ch in name).strip(" .")
    return cleaned or "_"


@dataclass
class Rules:
    categories: list[Category]
    other: Category
    source: Path | None = None
    _ext_map: dict[str, Category] = field(default_factory=dict, repr=False)

    def __post_init__(self) -> None:
        self._ext_map = {}
        for cat in self.categories:
            for ext in cat.extensions:
                self._ext_map.setdefault(ext, cat)

    @property
    def all_categories(self) -> list[Category]:
        return [*self.categories, self.other]

    def by_id(self, cat_id: str) -> Category:
        for c in self.all_categories:
            if c.id == cat_id:
                return c
        return self.other

    def category_for(self, path: Path | str) -> Category:
        name = Path(path).name.lower()
        parts = name.split(".")
        if len(parts) >= 3:  # ex.: arquivo.tar.gz
            double = ".".join(parts[-2:])
            if double in self._ext_map:
                return self._ext_map[double]
        if len(parts) >= 2 and parts[-1]:
            return self._ext_map.get(parts[-1], self.other)
        return self.other

    # ------------------------------------------------------------------ load
    @classmethod
    def from_dict(cls, data: dict, source: Path | None = None) -> "Rules":
        if not isinstance(data, dict) or not isinstance(data.get("categories"), list):
            raise RulesError("O arquivo de regras precisa ter uma lista 'categories'.")
        cats: list[Category] = []
        seen: set[str] = set()
        for raw in data["categories"]:
            if not isinstance(raw, dict) or "id" not in raw:
                raise RulesError("Cada categoria precisa de um 'id'.")
            cid = str(raw["id"])
            if cid in seen:
                raise RulesError(f"Categoria duplicada: {cid}")
            seen.add(cid)
            names = raw.get("names") or {"pt_BR": raw.get("name", cid)}
            names = {k: _clean_name(str(v)) for k, v in names.items()}
            exts = frozenset(str(e).lower().lstrip(".") for e in raw.get("extensions", []))
            cats.append(Category(cid, names, str(raw.get("color", "#8A8FA3")), exts))
        raw_other = data.get("other") or {}
        other_names = raw_other.get("names") or {"pt_BR": "Outros", "en": "Others"}
        other = Category(
            str(raw_other.get("id", "other")),
            {k: _clean_name(str(v)) for k, v in other_names.items()},
            str(raw_other.get("color", "#8A8FA3")),
        )
        return cls(cats, other, source)

    @classmethod
    def load(cls, path: Path | str | None = None) -> "Rules":
        """Carrega regras de ``path``, do arquivo do usuário ou do padrão embutido."""
        candidates: list[Path] = []
        if path:
            candidates.append(Path(path))
        else:
            candidates.append(user_rules_path())
        candidates.append(package_resource("default_rules.json"))
        last_error: Exception | None = None
        for c in candidates:
            if not c.is_file():
                continue
            try:
                with open(c, encoding="utf-8") as fh:
                    return cls.from_dict(json.load(fh), source=c)
            except (OSError, ValueError) as exc:
                last_error = exc
                log.warning("Regras inválidas em %s: %s", c, exc)
                if path:  # o usuário pediu esse arquivo explicitamente
                    raise RulesError(f"{c}: {exc}") from exc
        raise RulesError(f"Nenhum arquivo de regras válido encontrado ({last_error})")
