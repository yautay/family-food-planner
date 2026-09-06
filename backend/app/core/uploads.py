"""Uploady obrazów — jeden pipeline dla całego systemu (07_SECURITY §6).

Powstaje w BATCH_05 (zdjęcia przepisów), reużywany w B09 (zdjęcia produktów
retail). Zasady, wszystkie z 07_SECURITY §6 i 03_DATABASE §11:

1. **Limit rozmiaru** (`IMAGE_MAX_UPLOAD_MB`, domyślnie 10 MB) — powyżej 413,
   zanim cokolwiek dotknie Pillow.
2. **Sniffing treści** (Pillow `verify()`), nie rozszerzenia — plik, który nie
   jest obrazem, kończy się 422 niezależnie od nazwy.
3. **Re-encode** przez Pillow do JPEG — obraz jest renderowany od nowa, więc
   EXIF (w tym GPS) i ewentualne doklejone payloady nie przeżywają zapisu.
4. **Miniatura obok oryginału** (`<nazwa>_thumb.jpg`, dłuższy bok ≤ 512 px —
   wystarcza kartom gridu także na ekranach 2x).
5. **Losowa nazwa** `uuid4().hex` + stałe rozszerzenie `.jpg` (po re-encode
   format jest zawsze jeden); oryginalna nazwa pliku nigdy nie ląduje na dysku.
6. Zapis na bind mount poza web-rootem (`UPLOADS_DIR`); serwowanie WYŁĄCZNIE
   przez endpoint z sesją (`/uploads/*` w `app/main.py`), nie StaticFiles.

Funkcje są synchroniczne i CPU-bound — wołający (serwis) opakowuje je
w `run_in_threadpool`, żeby nie blokować pętli zdarzeń (ADR-015).
"""

from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
from pathlib import Path, PurePosixPath
from uuid import uuid4

from PIL import Image, UnidentifiedImageError

from app.core.errors import AppError, NotFoundError, PayloadTooLargeError

#: Domyślny limit obrazu z 07_SECURITY §6 (paczka transferu ma własny limit,
#: B14). Instancja przestawia go zmienną `IMAGE_MAX_UPLOAD_MB` (BATCH_17) —
#: serwisy przekazują `max_bytes` do `save_image`, ta stała jest wartością
#: domyślną i punktem odniesienia testów.
DEFAULT_IMAGE_MAX_MB = 10
MAX_IMAGE_BYTES = DEFAULT_IMAGE_MAX_MB * 1024 * 1024
#: Prefiks URL endpointu serwującego uploady (`app/main.py::build_uploads_router`).
#: Ścieżki w bazie są WZGLĘDNE, a URL powstaje wyłącznie tutaj — dzięki temu
#: żaden moduł nie skleja go po swojemu i nie wystawi ścieżki z dysku.
UPLOADS_URL_PREFIX = "/uploads"
#: Podkatalogi uploadów, które endpoint `/uploads/*` W OGÓLE serwuje —
#: ALLOWLISTA, nie lista zakazanych (odwrócone w BATCH_20).
#: Dokładnie te trzy katalogi zapisują dziś serwisy: `recipes` (zdjęcia
#: przepisów, B05), `retail` (zdjęcia wariantów sklepowych, B09) i
#: `transfer-import` (zdjęcia rozpakowane z paczki, B14). Paczki transferu
#: (`transfer/`) świadomie NIE są tu wymienione: to KOMPLET danych jednego
#: konta, a `/uploads/{path}` sprawdza wyłącznie sesję, więc każdy zalogowany,
#: który poznałby `import_id`, pobrałby cudzy eksport.
#: Lista zakazanych była pułapką: plik pozostawiony w katalogu, o którym kod
#: już nie wie (np. po wycofaniu funkcji), stawał się pobieralny dla dowolnego
#: zalogowanego konta. Przy allowliście katalog nieznany kodowi jest ZAMKNIĘTY
#: z definicji, a `task uploads-report` pokazuje jego pliki jako sieroty.
#: **Nowy podkatalog uploadów = wpis TUTAJ w tym samym batchu** — bez niego
#: zdjęcia z niego nie wyświetlą się w ogóle.
SERVED_SUBDIRS = ("recipes", "retail", "transfer-import")

#: Dłuższy bok miniatury; jakość JPEG dobrana wg proporcji rozmiar/wygląd.
THUMBNAIL_MAX_PX = 512
JPEG_QUALITY = 85

INVALID_IMAGE_MESSAGE = (
    "Przesłany plik nie jest poprawnym obrazem. Obsługiwane są zdjęcia (np. JPG, PNG, WEBP)."
)
TOO_LARGE_MESSAGE = "Plik jest za duży — zdjęcie może mieć najwyżej {limit} MB."
FILE_NOT_FOUND_MESSAGE = "Nie znaleziono pliku."


class InvalidUploadError(AppError):
    """422 — treść pliku nie jest obrazem (sniffing, nie rozszerzenie)."""

    status_code = 422
    code = "validation_error"


class UploadTooLargeError(PayloadTooLargeError):
    """413 — plik ponad limit; komunikat mówi, jaki limit obowiązuje.

    Podklasa `PayloadTooLargeError` (sufit ciała żądania, `core/body_limit.py`):
    jeden kontrakt HTTP = jedna hierarchia wyjątków.
    """


@dataclass(frozen=True)
class SavedImage:
    """Ścieżki WZGLĘDNE (POSIX) zapisanych plików — dokładnie to, co trafia do DB."""

    path: str
    thumbnail_path: str


def thumbnail_path_for(path: str) -> str:
    """Ścieżka miniatury wynika z konwencji nazwy, nie z osobnej kolumny."""
    pure = PurePosixPath(path)
    return str(pure.with_name(f"{pure.stem}_thumb{pure.suffix}"))


def image_urls(path: str | None) -> tuple[str | None, str | None]:
    """Ścieżka względna z DB → URL-e endpointu `/uploads/*` (oryginał, miniatura).

    Brak zdjęcia daje `(None, None)`, nie pusty string: `null` w odpowiedzi API
    znaczy „nie ma zdjęcia", a `""` byłoby URL-em prowadzącym w nikąd.
    """
    if not path:
        return None, None
    return (
        f"{UPLOADS_URL_PREFIX}/{path}",
        f"{UPLOADS_URL_PREFIX}/{thumbnail_path_for(path)}",
    )


def image_too_large_message(limit_mb: int) -> str:
    """Komunikat 413 dla zdjęcia — limit jest konfiguracją instancji, nie stałą."""
    return TOO_LARGE_MESSAGE.format(limit=limit_mb)


def save_image(
    data: bytes, *, uploads_root: Path, subdir: str, max_bytes: int = MAX_IMAGE_BYTES
) -> SavedImage:
    """Zwaliduj, re-enkoduj i zapisz obraz + miniaturę. Zwraca ścieżki względne.

    Kolejność jest częścią kontraktu bezpieczeństwa: limit rozmiaru PRZED
    parsowaniem (nie karmimy Pillow gigabajtami), sniffing PRZED zapisem
    (na dysk trafia wyłącznie obraz, który sami wyrenderowaliśmy).
    """
    if len(data) > max_bytes:
        raise UploadTooLargeError(image_too_large_message(max_bytes // (1024 * 1024)))

    try:
        with Image.open(BytesIO(data)) as probe:
            probe.verify()
        # `verify()` unieważnia obiekt — do renderu plik otwiera się ponownie.
        with Image.open(BytesIO(data)) as image:
            rendered = _flatten_to_rgb(image)
    except (UnidentifiedImageError, OSError, ValueError, SyntaxError) as exc:
        raise InvalidUploadError(INVALID_IMAGE_MESSAGE) from exc

    name = uuid4().hex
    relative = PurePosixPath(subdir) / f"{name}.jpg"
    target_dir = uploads_root / subdir
    target_dir.mkdir(parents=True, exist_ok=True)

    # `save` bez `exif=`/`icc_profile=` — metadane źródła nie są przenoszone.
    rendered.save(target_dir / f"{name}.jpg", format="JPEG", quality=JPEG_QUALITY)

    thumbnail = rendered.copy()
    thumbnail.thumbnail((THUMBNAIL_MAX_PX, THUMBNAIL_MAX_PX))
    thumbnail.save(target_dir / f"{name}_thumb.jpg", format="JPEG", quality=JPEG_QUALITY)

    return SavedImage(path=str(relative), thumbnail_path=thumbnail_path_for(str(relative)))


def delete_image(path: str, *, uploads_root: Path) -> None:
    """Usuń obraz i jego miniaturę; brak pliku nie jest błędem (idempotentne)."""
    for relative in (path, thumbnail_path_for(path)):
        try:
            resolve_upload_path(relative, uploads_root=uploads_root).unlink(missing_ok=True)
        except NotFoundError:
            # Ścieżka spoza katalogu uploadów nie wskazuje niczego do usunięcia.
            continue


def resolve_upload_path(path: str, *, uploads_root: Path) -> Path:
    """Ścieżka względna → bezpieczna ścieżka absolutna wewnątrz katalogu uploadów.

    Wszystko podejrzane (separatory absolutne, `..`, wyjście poza katalog)
    kończy się 404 — odpowiedź identyczna jak dla pliku, którego nie ma,
    żeby nie zdradzać struktury dysku (07_SECURITY §4).
    """
    candidate = PurePosixPath(path.replace("\\", "/"))
    if candidate.is_absolute() or ".." in candidate.parts:
        raise NotFoundError(FILE_NOT_FOUND_MESSAGE)
    # `lower()`: na systemie plików bez rozróżniania wielkości liter (Windows,
    # macOS) `Recipes/...` trafia w ten sam plik co `recipes/...` — porównanie
    # musi być niezależne od systemu (ustalenie REVIEW R4 pkt 8).
    if len(candidate.parts) < 2 or candidate.parts[0].lower() not in SERVED_SUBDIRS:
        raise NotFoundError(FILE_NOT_FOUND_MESSAGE)

    root = uploads_root.resolve()
    resolved = (root / candidate).resolve()
    if not resolved.is_relative_to(root):
        raise NotFoundError(FILE_NOT_FOUND_MESSAGE)
    return resolved


def _flatten_to_rgb(image: Image.Image) -> Image.Image:
    """Obraz w dowolnym trybie → RGB pod zapis JPEG (przezroczystość na białym).

    JPEG nie zna kanału alfa; wklejenie na białe tło zamiast `convert("RGB")`
    chroni przed czarnymi prostokątami z przezroczystych PNG.
    """
    if image.mode in ("RGBA", "LA", "P"):
        converted = image.convert("RGBA")
        background = Image.new("RGB", converted.size, (255, 255, 255))
        background.paste(converted, mask=converted.getchannel("A"))
        return background
    return image.convert("RGB")
