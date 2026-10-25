import os
import json

import pytest

from conftest import make
from organizefiles import cli
from organizefiles.core import Mode, PlanOptions, build_plan
from organizefiles.core.rules import Rules, RulesError
from organizefiles.i18n import STRINGS, set_language, tr
from organizefiles.paths import resource_path


def test_i18n_keys_match():
    assert set(STRINGS["pt_BR"]) == set(STRINGS["en"])


def test_tr_and_fallback():
    set_language("en")
    assert tr("btn.undo") == "Undo last organization"
    set_language("xx")
    assert tr("btn.undo") == "Desfazer última organização"
    assert tr("chave.inexistente") == "chave.inexistente"


def test_custom_rules(folder, tmp_path):
    rules_file = tmp_path / "rules.json"
    rules_file.write_text(json.dumps({"categories": [
        {"id": "roms", "names": {"pt_BR": "ROMs"}, "extensions": ["iso", ".cue", "bin"]}]}))
    rules = Rules.load(rules_file)
    make(folder, "jogo.cue")
    make(folder, "outro.pdf")
    plan = build_plan(folder, PlanOptions(mode=Mode.CATEGORY), rules)
    dests = {i.src.name: i.dst.parent.name for i in plan.moves}
    assert dests == {"jogo.cue": "ROMs", "outro.pdf": "Outros"}


def test_invalid_rules(tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_text("{nope")
    with pytest.raises(RulesError):
        Rules.load(bad)


def test_resource_path_finds_icon():
    assert resource_path("Design", "icone.ico").is_file()


def test_cli_dry_run_moves_nothing(folder, capsys):
    make(folder, "a.jpg")
    assert cli.main([str(folder), "--modo", "tipo", "--dry-run"]) == 0
    out = capsys.readouterr().out
    assert os.path.join("JPG", "a.jpg") in out
    assert (folder / "a.jpg").exists()


def test_cli_apply_and_undo(folder):
    make(folder, "a.jpg")
    assert cli.main([str(folder), "--sim"]) == 0
    assert (folder / "Imagens/a.jpg").exists()
    assert cli.main(["--desfazer", "--sim"]) == 0
    assert (folder / "a.jpg").exists()


def test_cli_blocks_root():
    from pathlib import Path
    assert cli.main([Path.cwd().anchor, "-n"]) == 3
