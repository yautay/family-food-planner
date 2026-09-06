"""Raport plików uploadów bez referencji (BATCH_17, D10) — klasyfikacja bez bazy."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.core.uploads_report import (
    FileEntry,
    classify,
    expand_references,
    format_size,
    render_report,
    scan_files,
)

pytestmark = pytest.mark.unit


def test_referencja_zdjecia_obejmuje_miniature_z_konwencji_nazwy() -> None:
    """`recipes.photo_path` wskazuje oryginał; `_thumb.jpg` wynika z konwencji, nie z kolumny."""
    assert expand_references(["recipes/abc.jpg", None, ""]) == {
        "recipes/abc.jpg",
        "recipes/abc_thumb.jpg",
    }


def test_plik_ktory_nie_jest_jpg_nie_ma_miniatury() -> None:
    """Konwencja `_thumb` dotyczy tylko zdjęć — pozostałe pliki wchodzą pojedynczo."""
    assert expand_references(["wycofany-modul/x.pdf"]) == {"wycofany-modul/x.pdf"}


def test_klasyfikacja_rozdziela_referencjonowane_osierocone_i_tymczasowe() -> None:
    """Scratch transferu (TTL 24 h) nie jest „osierocony" — kasuje go serwis transferu.

    `wycofany-modul/` stoi tu za KAŻDY katalog, który został na dysku po funkcji
    usuniętej z aplikacji (BATCH_20 zrobił tak z katalogiem wgranych jadłospisów):
    nie ma już kolumny, która by go trzymał, więc wszystko w nim to sieroty —
    i dokładnie po to raport istnieje, bo sam nic nie kasuje (D10).
    """
    files = [
        FileEntry("recipes/a.jpg", 10),
        FileEntry("recipes/a_thumb.jpg", 2),
        FileEntry("recipes/zgubione.jpg", 30),
        FileEntry("wycofany-modul/plik.pdf", 100),
        FileEntry("wycofany-modul/drugi.pdf", 200),
        FileEntry("transfer/export-1.zip", 5),
    ]
    references = expand_references(["recipes/a.jpg", "retail/brak.jpg"])

    report = classify(files, references)

    assert [e.path for e in report.referenced] == [
        "recipes/a.jpg",
        "recipes/a_thumb.jpg",
    ]
    assert [e.path for e in report.orphans] == [
        "recipes/zgubione.jpg",
        "wycofany-modul/plik.pdf",
        "wycofany-modul/drugi.pdf",
    ]
    assert [e.path for e in report.scratch] == ["transfer/export-1.zip"]
    assert report.dead_references == ["retail/brak.jpg", "retail/brak_thumb.jpg"]
    assert report.orphans_size == 330
    assert report.total_size == 347


def test_skan_daje_sciezki_wzgledne_posix(tmp_path: Path) -> None:
    (tmp_path / "recipes").mkdir()
    (tmp_path / "recipes" / "a.jpg").write_bytes(b"12345")
    (tmp_path / "wycofany-modul").mkdir()
    (tmp_path / "wycofany-modul" / "j.pdf").write_bytes(b"1")

    entries = scan_files(tmp_path)

    assert entries == [FileEntry("recipes/a.jpg", 5), FileEntry("wycofany-modul/j.pdf", 1)]


def test_skan_nieistniejacego_katalogu_jest_pusty(tmp_path: Path) -> None:
    assert scan_files(tmp_path / "nie-ma") == []


def test_rozmiar_po_polsku_z_przecinkiem() -> None:
    assert format_size(512) == "512 B"
    assert format_size(1536) == "1,5 KB"
    assert format_size(4_613_734) == "4,4 MB"


def test_raport_wymienia_osierocone_i_deklaruje_ze_nic_nie_usunal(tmp_path: Path) -> None:
    """D10: komenda raportuje, człowiek decyduje — tekst musi to mówić wprost."""
    report = classify([FileEntry("wycofany-modul/x.pdf", 1024)], set())

    text = render_report(report, uploads_root=tmp_path)

    assert "BEZ REFERENCJI (osierocone): 1, 1,0 KB" in text
    assert "wycofany-modul/x.pdf" in text
    assert "nic nie zostało usunięte" in text
