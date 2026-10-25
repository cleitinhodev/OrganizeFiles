"""Ponto de entrada: ``python -m organizefiles`` abre a interface; com argumentos, usa a CLI."""

from __future__ import annotations

import sys


def main() -> int:
    args = sys.argv[1:]
    if args and args != ["--gui"]:
        from .cli import main as cli_main

        return cli_main(args)
    from .gui.app import run

    return run()


if __name__ == "__main__":
    raise SystemExit(main())
