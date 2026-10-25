import unicodedata
from datetime import datetime
from pathlib import Path

from conftest import make
from organizefiles.core import Action, Mode, PlanOptions, build_plan


def rel(plan, item):
    if not item.dst:
        return None
    return unicodedata.normalize("NFC", item.dst.relative_to(plan.root).as_posix())


def by_name(plan):
    return {unicodedata.normalize("NFC", i.src.name): i for i in plan.items}


def test_preview_does_not_touch_disk(folder):
    make(folder, "foto.jpg")
    make(folder, "nota.pdf")
    before = sorted(p.name for p in folder.iterdir())
    build_plan(folder, PlanOptions(mode=Mode.CATEGORY))
    assert sorted(p.name for p in folder.iterdir()) == before


def test_category_mode(folder):
    for n in ["foto.JPG", "doc.pdf", "musica.mp3", "filme.mkv", "pacote.tar.gz", "setup.exe",
              "script.py", "estranho.xyz", "semextensao"]:
        make(folder, n)
    plan = build_plan(folder, PlanOptions(mode=Mode.CATEGORY))
    items = by_name(plan)
    assert rel(plan, items["foto.JPG"]) == "Imagens/foto.JPG"
    assert rel(plan, items["doc.pdf"]) == "Documentos/doc.pdf"
    assert rel(plan, items["musica.mp3"]) == "Músicas/musica.mp3"
    assert rel(plan, items["filme.mkv"]) == "Vídeos/filme.mkv"
    assert rel(plan, items["pacote.tar.gz"]) == "Compactados/pacote.tar.gz"
    assert rel(plan, items["setup.exe"]) == "Instaladores/setup.exe"
    assert rel(plan, items["script.py"]) == "Código/script.py"
    assert rel(plan, items["estranho.xyz"]) == "Outros/estranho.xyz"
    assert rel(plan, items["semextensao"]) == "Outros/semextensao"


def test_category_mode_english(folder):
    make(folder, "a.png")
    plan = build_plan(folder, PlanOptions(mode=Mode.CATEGORY, lang="en"))
    assert rel(plan, plan.items[0]) == "Images/a.png"


def test_extension_mode(folder):
    make(folder, "a.Mp3")
    make(folder, "LEIAME")
    plan = build_plan(folder, PlanOptions(mode=Mode.EXTENSION))
    items = by_name(plan)
    assert rel(plan, items["a.Mp3"]) == "MP3/a.Mp3"
    assert rel(plan, items["LEIAME"]) == "Sem extensão/LEIAME"


def test_date_mode_uses_mtime(folder):
    ts = datetime(2021, 3, 15, 12, 0).timestamp()
    make(folder, "velho.txt", mtime=ts)
    plan = build_plan(folder, PlanOptions(mode=Mode.DATE))
    assert rel(plan, plan.items[0]) == "2021/03/velho.txt"


def test_date_mode_uses_exif(folder):
    PIL = __import__("pytest").importorskip("PIL.Image")
    img = PIL.new("RGB", (4, 4))
    exif = img.getexif()
    exif[306] = "2019:07:04 10:00:00"
    p = folder / "foto.jpg"
    img.save(p, exif=exif)
    plan = build_plan(folder, PlanOptions(mode=Mode.DATE))
    assert rel(plan, plan.items[0]) == "2019/07/foto.jpg"


def test_alphabet_mode_accents_digits_symbols(folder):
    for n in ["Ágata.txt", "banana.txt", "2024.txt", "_x.txt"]:
        make(folder, n)
    plan = build_plan(folder, PlanOptions(mode=Mode.ALPHABET))
    items = by_name(plan)
    assert rel(plan, items["Ágata.txt"]) == "A/Ágata.txt"
    assert rel(plan, items["banana.txt"]) == "B/banana.txt"
    assert rel(plan, items["2024.txt"]) == "0-9/2024.txt"
    assert rel(plan, items["_x.txt"]) == "Outros/_x.txt"


def test_alphabet_folder_colliding_with_existing_file(folder):
    """Bug antigo: um arquivo chamado 'A' impedia a criação da pasta 'A'."""
    make(folder, "A")
    make(folder, "abacate.txt")
    plan = build_plan(folder, PlanOptions(mode=Mode.ALPHABET))
    items = by_name(plan)
    assert rel(plan, items["abacate.txt"]) == "A (2)/abacate.txt"
    assert rel(plan, items["A"]) == "A (2)/A"


def test_recursive_and_already_organized(folder):
    make(folder, "Imagens/ja.jpg")
    make(folder, "sub/novo.jpg")
    make(folder, "projeto/.git/config")
    make(folder, "projeto/main.py")
    flat = build_plan(folder, PlanOptions(mode=Mode.CATEGORY))
    assert flat.items == []
    plan = build_plan(folder, PlanOptions(mode=Mode.CATEGORY, recursive=True))
    items = by_name(plan)
    assert items["ja.jpg"].action is Action.SKIP
    assert items["ja.jpg"].skip_reason == "already_organized"
    assert rel(plan, items["novo.jpg"]) == "Imagens/novo.jpg"
    assert "main.py" not in items  # pasta de projeto não é desmontada
    assert any(d.name == "projeto" for d in plan.skipped_dirs)


def test_root_project_flag(folder):
    make(folder, ".git/HEAD")
    make(folder, "a.txt")
    assert build_plan(folder).root_is_project
