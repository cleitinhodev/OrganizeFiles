import pytest

from conftest import make
from organizefiles.core import Mode, PlanOptions, build_plan, execute_plan
from organizefiles.core.naming import split_name, unique_path


def test_unique_path(tmp_path):
    (tmp_path / "foto.jpg").write_text("1")
    (tmp_path / "foto (1).jpg").write_text("2")
    assert unique_path(tmp_path / "foto.jpg").name == "foto (2).jpg"
    assert unique_path(tmp_path / "livre.jpg").name == "livre.jpg"
    assert split_name("x.tar.gz") == ("x", ".tar.gz")
    assert split_name(".bashrc") == (".bashrc", "")


def test_existing_destination_is_never_overwritten(folder):
    make(folder, "Imagens/foto.jpg", "ANTIGA")
    make(folder, "foto.jpg", "NOVA")
    plan = build_plan(folder, PlanOptions(mode=Mode.CATEGORY))
    [item] = plan.moves
    assert item.renamed and item.dst.name == "foto (1).jpg"
    res = execute_plan(plan)
    assert res.moved == 1 and not res.errors
    assert (folder / "Imagens/foto.jpg").read_text() == "ANTIGA"
    assert (folder / "Imagens/foto (1).jpg").read_text() == "NOVA"


def test_case_insensitive_collisions_inside_plan(folder):
    make(folder, "foto.JPG", "1")
    if (folder / "FOTO.jpg").exists():
        pytest.skip("sistema de arquivos não diferencia maiúsculas/minúsculas")
    make(folder, "Foto.jpg", "2")
    plan = build_plan(folder, PlanOptions(mode=Mode.CATEGORY))
    names = sorted(i.dst.name for i in plan.moves)
    assert len({n.casefold() for n in names}) == 2
    execute_plan(plan)
    contents = sorted(p.read_text() for p in (folder / "Imagens").iterdir())
    assert contents == ["1", "2"]


def test_recursive_same_name_from_two_subfolders(folder):
    make(folder, "a/rel.pdf", "A")
    make(folder, "b/rel.pdf", "B")
    plan = build_plan(folder, PlanOptions(mode=Mode.CATEGORY, recursive=True))
    res = execute_plan(plan)
    assert res.moved == 2
    assert sorted(p.read_text() for p in (folder / "Documentos").iterdir()) == ["A", "B"]


def test_rerun_is_idempotent(folder):
    make(folder, "x.png")
    execute_plan(build_plan(folder))
    plan2 = build_plan(folder, PlanOptions(recursive=True))
    assert not plan2.has_work


def test_file_changed_after_preview_is_not_moved(folder):
    p = make(folder, "a.txt", "1")
    plan = build_plan(folder)
    p.write_text("conteudo maior")
    res = execute_plan(plan)
    assert res.moved == 0 and len(res.errors) == 1
    assert p.exists()
