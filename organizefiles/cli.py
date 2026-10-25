"""Interface de linha de comando.

Exemplos::

    python -m organizefiles ~/Downloads --modo categoria --dry-run
    python -m organizefiles ~/Downloads --modo data --recursivo --backup zip --sim
    python -m organizefiles --desfazer
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import __version__
from .core import (Action, BackupMode, DupStrategy, Mode, PlanOptions, UnsafeFolderError,
                   build_plan, classify_folder, execute_plan, latest_undoable_journal, undo_journal)
from .core.backup import BackupError
from .core.models import human_size
from .core.rules import Rules, RulesError
from .core.safety import CONFIRM
from .i18n import set_language, tr
from .paths import setup_logging

STATUS_TAG = {"move": "MOVER", "renamed": "RENOMEAR", "duplicate": "DUPLIC.", "sensitive": "SENSÍVEL",
              "skip": "IGNORAR"}


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="organizefiles", description="Organize Files — organiza pastas com segurança.")
    p.add_argument("pasta", nargs="?", help="pasta a organizar")
    p.add_argument("--modo", "-m", default="categoria",
                   help="categoria | extensao (alias: tipo) | data | abc  (padrão: categoria)")
    p.add_argument("--recursivo", "-r", action="store_true", help="inclui subpastas")
    p.add_argument("--dry-run", "-n", action="store_true", help="apenas mostra a prévia, não move nada")
    p.add_argument("--sim", "-y", action="store_true", help="não pergunta antes de mover")
    p.add_argument("--duplicados", choices=[d.value for d in DupStrategy], default="none")
    p.add_argument("--backup", choices=[b.value for b in BackupMode], default="none")
    p.add_argument("--incluir-sensiveis", action="store_true", help="também move arquivos sensíveis")
    p.add_argument("--permitir-lixeira-sensiveis", action="store_true",
                   help="permite enviar arquivos sensíveis duplicados para a lixeira")
    p.add_argument("--incluir-ocultos", action="store_true")
    p.add_argument("--sem-exif", action="store_true", help="no modo data, usa só a data de modificação")
    p.add_argument("--regras", help="arquivo JSON de categorias personalizado")
    p.add_argument("--lang", default="pt_BR", choices=["pt_BR", "en"])
    p.add_argument("--desfazer", action="store_true", help="desfaz a última organização")
    p.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    return p


def _print_plan(plan, limit: int = 200) -> None:
    root = plan.root
    for n, item in enumerate(sorted(plan.items, key=lambda i: (i.status, str(i.src)))):
        if n >= limit:
            print(f"  … (+{len(plan.items) - limit})")
            break
        src = item.src.relative_to(root)
        tag = STATUS_TAG[item.status]
        if item.dst is not None:
            print(f"  [{tag:9}] {src}  ->  {item.dst.relative_to(root)}")
        else:
            note = tr("sens." + item.sensitive_reason) if item.sensitive_reason else (
                tr("reason." + item.skip_reason) if item.skip_reason else "")
            if item.action is Action.TRASH:
                note = tr("reason.trash_duplicate", name=item.duplicate_of.name if item.duplicate_of else "")
            elif item.duplicate_of is not None:
                note = tr("reason.duplicate", name=item.duplicate_of.name)
            print(f"  [{tag:9}] {src}  ({note})")
    s = plan.summary()
    print(f"\n{s['total']} arquivos | mover: {s['move']} ({human_size(s['move_size'])}) | renomear: "
          f"{s['renamed']} | lixeira: {s['trash']} | ignorados: {s['skip']} | sensíveis: {s['sensitive']}")
    print("Por categoria:", ", ".join(f"{k}: {c} ({human_size(b)})" for k, (c, b) in plan.stats_by_category().items()))


def _safe_console() -> None:
    """Evita UnicodeEncodeError em consoles/pipes que não são UTF-8 (ex.: cp1252 no Windows)."""
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            try:
                reconfigure(errors="replace")
            except (ValueError, OSError):
                pass


def main(argv: list[str] | None = None) -> int:
    _safe_console()
    args = build_parser().parse_args(argv)
    set_language(args.lang)
    setup_logging()

    if args.desfazer:
        j = latest_undoable_journal()
        if j is None:
            print(tr("undo.none"))
            return 1
        print(tr("undo.body", date=j.data["started_at"], folder=j.data["root"], n=len(j.moves)))
        if not args.sim and not _ask():
            return 1
        r = undo_journal(j)
        print(tr("undo.result", restored=r.restored, renamed=r.renamed, modified=r.modified,
                 missing=len(r.missing), errors=len(r.errors)))
        if r.trashed:
            print(tr("undo.trash_note", n=len(r.trashed)).strip())
        return 0 if not r.errors else 2

    if not args.pasta:
        build_parser().print_help()
        return 1

    try:
        mode = Mode.parse(args.modo)
        rules = Rules.load(args.regras) if args.regras else Rules.load()
    except (ValueError, RulesError) as exc:
        print(tr("msg.error", error=exc), file=sys.stderr)
        return 1
    folder = Path(args.pasta).expanduser()
    level, code = classify_folder(folder)
    options = PlanOptions(mode=mode, recursive=args.recursivo, include_sensitive=args.incluir_sensiveis,
                          include_hidden=args.incluir_ocultos, duplicates=DupStrategy(args.duplicados),
                          use_exif=not args.sem_exif, lang=args.lang)
    try:
        plan = build_plan(folder, options, rules)
    except UnsafeFolderError as exc:
        print(tr("unsafe." + exc.code), file=sys.stderr)
        return 3
    _print_plan(plan)
    if args.dry_run:
        print("\n(dry-run) Nada foi movido.")
        return 0
    if not plan.has_work:
        print(tr("msg.nothing"))
        return 0
    if level == CONFIRM and code == "home" and not args.sim:
        word = tr("confirm.home_word")
        print(tr("confirm.home_body", folder=plan.root))
        if input("> ").strip() != word:
            return 1
    if not args.sim and not _ask():
        return 1
    try:
        res = execute_plan(plan, BackupMode(args.backup), allow_sensitive_trash=args.permitir_lixeira_sensiveis)
    except BackupError as exc:
        print(tr("backup.error", error=exc), file=sys.stderr)
        return 4
    print(tr("result.body", moved=res.moved, renamed=res.renamed, trashed=res.trashed,
             skipped=res.skipped, errors=len(res.errors)))
    if res.backup_path:
        print(tr("result.backup", path=res.backup_path).strip())
    for path, err in res.errors:
        print(f"  ! {path}: {err}", file=sys.stderr)
    return 0 if not res.errors else 2


def _ask() -> bool:
    if not sys.stdin.isatty():
        print("Use --sim para confirmar em modo não interativo.", file=sys.stderr)
        return False
    return input("Confirmar? [s/N] ").strip().lower() in ("s", "sim", "y", "yes")


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
