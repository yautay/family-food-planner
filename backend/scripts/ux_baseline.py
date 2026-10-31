"""Bezpieczny, wznawialny zestaw UX00 przez prawdziwe API (task ux-baseline).

Nie czyści bazy. Nie używa fabryk testowych ani bezpośrednich zapisów ORM.
Manifest zawiera tylko publiczne identyfikatory; hasła pochodzą ze środowiska.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import os
from collections.abc import Callable
from contextlib import AsyncExitStack
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

import httpx
from PIL import Image
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.engine import make_url

from app.core.config import Settings, get_settings
from app.core.cookies import csrf_cookie_name
from app.core.db import get_engine, selector_loop_factory
from app.main import create_app

PREFIX = "UX00 kontrakty v1"
WEEK_START = date(2029, 6, 4)
EMPTY_DAY = "2029-06-10"
DATA_DIR = Path(__file__).resolve().parents[1] / "data" / "ux-baseline"
MANIFEST_PATH = DATA_DIR / "manifest.json"
EMAILS = {key: f"ux00-{key}@example.com" for key in ("a1", "a2", "b1", "solo")}
DAY_TITLES = ("bez podziału", "częściowy podział", "pełny podział")
MEAL_NAME = "Późny obiad po spacerze"
Json = dict[str, Any]


class FixtureError(RuntimeError):
    """Błąd operatora bez payloadów, haseł i URL-i połączenia."""


def guard_environment(settings: Settings) -> str:
    """Odrzuć produkcję, zdalny host, zwykłą bazę i opcje nadpisujące host."""
    try:
        url = make_url(settings.database_url)
    except Exception:
        raise FixtureError("Niepoprawna konfiguracja bazy UX00.") from None
    if (
        settings.app_env not in {"dev", "test"}
        or url.drivername not in {"postgresql", "postgresql+psycopg"}
        or url.host not in {"localhost", "127.0.0.1", "::1"}
        or url.database not in {"pasnik_ux", "pasnik_ux_test"}
        or url.query
    ):
        raise FixtureError(
            "UX00 wymaga APP_ENV=dev/test, PostgreSQL na localhost i odrębnej bazy "
            "pasnik_ux lub pasnik_ux_test, bez parametrów URL."
        )
    # Bez nazwy użytkownika, hasła i sekretu aplikacji; wiąże manifest z instancją.
    return f"{url.host}:{url.port or 5432}/{url.database}"


class Manifest(BaseModel):
    """Dziennik pojedynczych operacji, odporny na niepewny wynik procesu."""

    model_config = ConfigDict(extra="forbid")
    version: int = 1
    prefix: str = PREFIX
    database: str
    photo_sha256: str
    ids: dict[str, int] = Field(default_factory=dict)
    done: list[str] = Field(default_factory=list)
    pending: str | None = None
    complete: bool = False


class Journal:
    def __init__(self, path: Path, database: str, photo_sha256: str) -> None:
        self.path = path
        self.state = (
            Manifest.model_validate_json(path.read_text(encoding="utf-8"))
            if path.exists()
            else Manifest(database=database, photo_sha256=photo_sha256)
        )
        if (
            self.state.version != 1
            or self.state.prefix != PREFIX
            or self.state.database != database
            or self.state.photo_sha256 != photo_sha256
        ):
            raise FixtureError("Manifest dotyczy innej bazy, wersji lub zdjęcia. Nie nadpisano go.")
        if self.state.pending:
            raise FixtureError(
                f"Niepotwierdzona operacja {self.state.pending}. "
                "Sprawdź jej wynik w izolowanej instancji przed ręcznym uzgodnieniem manifestu."
            )

    def save(self, state: Manifest | None = None) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(".tmp")
        temporary.write_text(
            (state or self.state).model_dump_json(indent=2) + "\n", encoding="utf-8"
        )
        temporary.replace(self.path)

    async def write(
        self,
        api: Api,
        key: str,
        method: str,
        path: str,
        payload: Json | None = None,
        *,
        identifier_from: Callable[[Json], int] | None = None,
    ) -> int:
        if key in self.state.done:
            return self.state.ids.get(key, 0)
        self.state.complete = False
        self.state.pending = key
        self.save()  # PRZED żądaniem: nie ponawiamy niepotwierdzonego POST-a.
        result = await api.call(method, path, payload)
        identifier = identifier_from(result) if identifier_from else int(result.get("id", 0))
        if identifier:
            self.state.ids[key] = identifier
        self.state.done.append(key)
        self.state.pending = None
        self.save()
        return identifier


class Api:
    def __init__(self, client: httpx.AsyncClient, settings: Settings) -> None:
        self.client = client
        self.settings = settings

    async def call(self, method: str, path: str, payload: Json | None = None) -> Json:
        token = self.client.cookies.get(csrf_cookie_name(self.settings))
        headers = {"X-CSRF-Token": token} if token else {}
        response = await self.client.request(
            method, f"/api/v1{path}", json=payload, headers=headers
        )
        if not response.is_success:
            raise FixtureError(f"API: {method} {path}: HTTP {response.status_code}.")
        return response.json() if response.content else {}

    async def all(self, path: str) -> list[Json]:
        items: list[Json] = []
        while True:
            separator = "&" if "?" in path else "?"
            result = await self.call("GET", f"{path}{separator}limit=200&offset={len(items)}")
            batch = result["items"]
            items.extend(batch)
            if len(items) >= result["total"]:
                return items
            if not batch:
                raise FixtureError("API zwróciło pustą stronę przed końcem zbioru.")


def fixture_meal(day: Json, ids: dict[str, int], offset: int) -> Json:
    """Rozpoznaj wyłącznie własny dzień i jego jednoznaczny posiłek UX00."""
    if (
        day.get("id") != ids[f"day-{offset}"]
        or day.get("day") != (WEEK_START + timedelta(days=offset)).isoformat()
        or day.get("title") != f"{PREFIX} — {DAY_TITLES[offset]}"
        or day.get("scope") != "household"
        or day.get("owner_user_id") != ids["user-a1"]
    ):
        raise FixtureError("Dzień UX00 ma obcy marker, datę, ID, właściciela lub scope.")
    meals: list[Json] = day.get("meals", [])
    if (
        len(meals) != 1
        or meals[0].get("name") != MEAL_NAME
        or Decimal(str(meals[0].get("kcal_target"))) != Decimal("600")
    ):
        raise FixtureError("Nie znaleziono jednoznacznego posiłku UX00.")
    return meals[0]


def fixture_recipe_item(day: Json, ids: dict[str, int], offset: int) -> Json:
    """Przepis, liczba porcji i pełny split identyfikują pozycję bez zgadywania."""
    meal = fixture_meal(day, ids, offset)
    items: list[Json] = [
        item for item in meal["items"] if item.get("recipe_id") == ids[f"recipe-{offset}"]
    ]
    suffix = (
        "Pełnoziarnista zapiekanka z pieczoną papryką, cukinią i serem"
        if offset == 0
        else f"Przepis próbny — śniadanie, obiad i kolacja {offset + 1:03}"
    )
    if len(items) != 1:
        raise FixtureError("Nie znaleziono jednoznacznej pozycji przepisu UX00.")
    item = items[0]
    split = item.get("servings_split", [])
    count = (0, 2, 3)[offset]
    if (
        item.get("recipe_name") != f"{PREFIX} — {offset + 1:03} {suffix}"
        or item.get("product_id") is not None
        or Decimal(str(item.get("servings"))) != Decimal("2.20" if offset == 1 else "3.30")
        or len(split) != count
        or {entry["member_profile_id"] for entry in split}
        != {ids[f"profile-{index}"] for index in range(count)}
        or any(Decimal(str(entry["multiplier"])) != Decimal("1.10") for entry in split)
    ):
        raise FixtureError("Pozycja przepisu UX00 ma obcy marker, przepis, porcje lub podział.")
    return item


def fixture_loose_item(day: Json, ids: dict[str, int]) -> Json:
    """API przechowuje 1.5 łyżki produktu jako 15 g, bez podziału porcji."""
    meal = fixture_meal(day, ids, 0)
    items: list[Json] = [
        item for item in meal["items"] if item.get("product_id") == ids["product-0"]
    ]
    if len(items) != 1:
        raise FixtureError("Nie znaleziono jednoznacznego produktu luzem UX00.")
    item = items[0]
    if (
        item.get("recipe_id") is not None
        or item.get("product_name")
        != f"{PREFIX} — 001 Płatki owsiane pełnoziarniste z otrębami i pestkami dyni"
        or Decimal(str(item.get("amount"))) != Decimal("15")
        or item.get("amount_unit") != "g"
        or Decimal(str(item.get("servings"))) != Decimal("1")
        or item.get("servings_split") != []
    ):
        raise FixtureError("Produkt luzem UX00 ma inny marker, ilość lub podział.")
    return item


async def plan_identifiers(a1: Api, journal: Journal, *, household_reader: Api) -> dict[str, int]:
    """Tylko GET: potwierdź kontekst rodziny i wszystkie trzy dni przed zmianą pliku."""
    ids = journal.state.ids
    me = await a1.call("GET", "/auth/me")
    family = await a1.call("GET", "/households/my")
    household = {"id": ids["household-a"], "name": f"{PREFIX} — Dom A"}
    if (
        me.get("id") != ids["user-a1"]
        or me.get("email") != EMAILS["a1"]
        or me.get("display_name") != f"{PREFIX} — konto A1"
        or me.get("role") != "user"
        or me.get("household") != household
        or family.get("household") != household
        or {member["id"] for member in family.get("members", [])}
        != {ids["user-a1"], ids["user-a2"]}
        or {profile["id"] for profile in family.get("profiles", [])}
        != {ids[f"profile-{index}"] for index in range(3)}
        or any(
            profile.get("household_id") != ids["household-a"]
            for profile in family.get("profiles", [])
        )
    ):
        raise FixtureError("Konto lub rodzina UX00 nie odpowiadają manifestowi.")
    reader = await household_reader.call("GET", "/auth/me")
    if (
        reader.get("id") != ids["user-a2"]
        or reader.get("email") != EMAILS["a2"]
        or reader.get("display_name") != f"{PREFIX} — konto A2"
        or reader.get("role") != "user"
        or reader.get("household") != household
    ):
        raise FixtureError("Konto A2 nie potwierdza rodziny UX00.")
    found: dict[str, int] = {}
    for offset in range(3):
        day = await a1.call("GET", f"/plan/days/{WEEK_START + timedelta(days=offset)}")
        # DayRead nie ujawnia household_id. A2 nie jest właścicielem, więc jego
        # dostęp do dokładnie tego day ID potwierdza widoczność w rodzinie A.
        shared_day = await household_reader.call(
            "GET", f"/plan/days/{WEEK_START + timedelta(days=offset)}"
        )
        fixture_meal(shared_day, ids, offset)
        meal = fixture_meal(day, ids, offset)
        recipe = fixture_recipe_item(day, ids, offset)
        if len(meal["items"]) != (2 if offset == 0 else 1):
            raise FixtureError("Dzień UX00 ma nieoczekiwane dodatkowe pozycje.")
        found[f"meal-{offset}"] = meal["id"]
        found[f"plan-item-{offset}"] = recipe["id"]
        if offset == 0:
            found["loose-product"] = fixture_loose_item(day, ids)["id"]
    if any(type(value) is not int or value <= 0 for value in found.values()):
        raise FixtureError("Niepoprawne identyfikatory posiłków lub pozycji UX00.")
    if (
        len({found[f"meal-{i}"] for i in range(3)}) != 3
        or len({found[f"plan-item-{i}"] for i in range(3)} | {found["loose-product"]}) != 4
    ):
        raise FixtureError("Powtórzone identyfikatory posiłków lub pozycji UX00.")
    return found


def guard_identifier_repair(journal: Journal) -> None:
    required = {f"{kind}-{i}" for kind in ("day", "meal", "plan-item") for i in range(3)}
    required.add("loose-product")
    if (
        not journal.path.exists()
        or journal.state.complete is not True
        or journal.state.pending is not None
        or not required.issubset(journal.state.done)
        or not required.issubset(journal.state.ids)
    ):
        raise FixtureError(
            "Naprawa identyfikatorów wymaga istniejącego COMPLETE manifestu bez pending."
        )


async def repair_manifest_identifiers(a1: Api, journal: Journal, *, household_reader: Api) -> None:
    """Opt-in: bez mutacji API, stary manifest zachowany przed atomową zmianą samych ID."""
    guard_identifier_repair(journal)
    original = journal.path.read_bytes()
    if Manifest.model_validate_json(original) != journal.state:
        raise FixtureError("Manifest zmienił się od odczytu; nie nadpisano go.")
    found = await plan_identifiers(a1, journal, household_reader=household_reader)
    for key, identifier in found.items():
        offset = 0 if key == "loose-product" else int(key.rsplit("-", 1)[1])
        if journal.state.ids[key] not in {identifier, journal.state.ids[f"day-{offset}"]}:
            raise FixtureError("Manifest zawiera ID inne niż potwierdzony błąd DayRead; przerwano.")
    if all(journal.state.ids[key] == identifier for key, identifier in found.items()):
        return
    if journal.path.read_bytes() != original:
        raise FixtureError("Manifest zmienił się podczas kontroli; nie nadpisano go.")
    candidate = journal.state.model_copy(deep=True)
    candidate.ids.update(found)
    backup = journal.path.with_suffix(".identifiers.bak")
    try:
        with backup.open("xb") as stream:
            stream.write(original)
    except FileExistsError:
        raise FixtureError(
            "Kopia manifest.identifiers.bak już istnieje; nie nadpisano plików."
        ) from None
    journal.save(candidate)
    journal.state = candidate


async def preflight(admin: Api, journal: Journal) -> None:
    """Nie adoptuj encji o podobnej nazwie po utracie lokalnego manifestu."""
    for path, prefix in (
        ("/admin/users", "user-"),
        ("/admin/households", "household-"),
        ("/products", "product-"),
        ("/recipes", "recipe-"),
    ):
        known = {value for key, value in journal.state.ids.items() if key.startswith(prefix)}
        for item in await admin.all(path):
            own_name = str(item.get("name", item.get("display_name", ""))).startswith(PREFIX)
            own_email = item.get("email") in EMAILS.values()
            if (own_name or own_email) and item["id"] not in known:
                raise FixtureError(f"Znaleziono dane UX00 bez wpisu w manifeście: {path}.")


async def prepare(settings: Settings, photo: Path, *, repair_identifiers: bool = False) -> None:
    database = guard_environment(settings)
    admin_email = os.environ.get("E2E_ADMIN_EMAIL", "")
    admin_password = os.environ.get("E2E_ADMIN_PASSWORD", "")
    fixture_password = os.environ.get("UX_BASELINE_PASSWORD", "")
    if len(fixture_password) < 12 or (
        not repair_identifiers and (not admin_email or not admin_password)
    ):
        raise FixtureError(
            "Wymagane E2E_ADMIN_EMAIL/PASSWORD i UX_BASELINE_PASSWORD (min. 12 znaków)."
        )
    photo_bytes = photo.read_bytes()
    if len(photo_bytes) > settings.image_max_upload_mb * 1024 * 1024:
        raise FixtureError("Zdjęcie przekracza limit uploadu instancji.")
    with Image.open(photo) as image:
        image.verify()
    journal = Journal(MANIFEST_PATH, database, hashlib.sha256(photo_bytes).hexdigest())
    if repair_identifiers:
        guard_identifier_repair(journal)
    app = create_app(settings)
    async with AsyncExitStack() as stack:

        async def login(email: str, password: str) -> Api:
            client = await stack.enter_async_context(
                httpx.AsyncClient(
                    transport=httpx.ASGITransport(app=app), base_url="http://localhost"
                )
            )
            api = Api(client, settings)
            await api.call("POST", "/auth/login", {"email": email, "password": password})
            return api

        if repair_identifiers:
            await repair_manifest_identifiers(
                await login(EMAILS["a1"], fixture_password),
                journal,
                household_reader=await login(EMAILS["a2"], fixture_password),
            )
            print("UX00: zweryfikowano i uzgodniono wyłącznie identyfikatory manifestu.")
            return
        admin = await login(admin_email, admin_password)
        if (await admin.call("GET", "/auth/me"))["role"] != "admin":
            raise FixtureError("Konto E2E musi mieć rolę ADMIN.")
        await preflight(admin, journal)
        write = journal.write
        ids = journal.state.ids
        for key, email in EMAILS.items():
            await write(
                admin,
                f"user-{key}",
                "POST",
                "/admin/users",
                {
                    "email": email,
                    "password": fixture_password,
                    "display_name": f"{PREFIX} — konto {key.upper()}",
                    "role": "user",
                },
            )
        for household, users in (("a", ["a1", "a2"]), ("b", ["b1"])):
            hid = await write(
                admin,
                f"household-{household}",
                "POST",
                "/admin/households",
                {
                    "name": f"{PREFIX} — Dom {household.upper()}",
                },
            )
            await write(
                admin,
                f"members-{household}",
                "PUT",
                f"/admin/households/{hid}/members",
                {
                    "user_ids": [ids[f"user-{key}"] for key in users],
                },
            )
        # Pięć logowań łącznie (ADMIN + cztery USER), bez obchodzenia rate limitu.
        actors = {key: await login(email, fixture_password) for key, email in EMAILS.items()}
        a1, a2 = actors["a1"], actors["a2"]
        for index, name in enumerate(("Łucja", "Michał", "Żaneta")):
            await write(
                a1,
                f"profile-{index}",
                "POST",
                "/households/my/profiles",
                {
                    "name": name,
                    "default_multiplier": "1.10",
                    "kcal_goal": "2100",
                },
            )
        await write(
            actors["b1"],
            "profile-b",
            "POST",
            "/households/my/profiles",
            {
                "name": "Błażej",
                "default_multiplier": "1.10",
            },
        )
        await write(
            a1,
            "goal",
            "POST",
            "/goals",
            {
                "valid_from": WEEK_START.isoformat(),
                "kcal": "2100",
                "protein_g": "90",
                "fat_g": "70",
                "carbs_g": "260",
            },
        )
        categories = (await admin.call("GET", "/categories"))["items"]
        if len(categories) < 2:
            raise FixtureError("Wymagany słownik kategorii po migracjach.")
        for index in range(55):
            suffix = (
                "Płatki owsiane pełnoziarniste z otrębami i pestkami dyni"
                if index == 0
                else f"Produkt próbny z polskimi znakami — żółć {index + 1:03}"
            )
            pid = await write(
                admin,
                f"product-{index}",
                "POST",
                "/products",
                {
                    "name": f"{PREFIX} — {index + 1:03} {suffix}",
                    "category_id": categories[index % 2]["id"],
                    "measure_kind": ("volume" if index == 1 else "piece" if index == 2 else "mass"),
                    "piece_weight_g": "60" if index == 2 else None,
                },
            )
            if index != 3:
                await write(
                    admin,
                    f"nutrition-{index}",
                    "PUT",
                    f"/products/{pid}/nutrition",
                    {
                        "kcal_100": "150",
                        "protein_100": "7.50",
                        "fat_100": "3.20",
                        "carbs_100": "23.10",
                        "fiber_100": "4.50",
                        "sugars_100": "2.10",
                        "glycemic_index": "45",
                        "nutrition_source": "Fikcyjne dane UX00 — nie referencja",
                    },
                )
        await write(
            admin,
            "unit-weight",
            "POST",
            f"/products/{ids['product-0']}/unit-weights",
            {
                "unit_label": "łyżka",
                "grams_per_unit": "10",
                "source": PREFIX,
            },
        )
        tag = await write(a1, "tag", "POST", "/tags", {"name": f"{PREFIX} — na wspólny obiad"})
        tags = (await a1.call("GET", "/tags"))["items"]
        system_tags = [t["id"] for t in tags if t["is_system"]]
        for index in range(55):
            scope = "global" if index == 2 else "private" if index == 1 else "household"
            actor = admin if scope == "global" else a1
            suffix = (
                "Pełnoziarnista zapiekanka z pieczoną papryką, cukinią i serem"
                if index == 0
                else f"Przepis próbny — śniadanie, obiad i kolacja {index + 1:03}"
            )
            await write(
                actor,
                f"recipe-{index}",
                "POST",
                "/recipes",
                {
                    "name": f"{PREFIX} — {index + 1:03} {suffix}",
                    "scope": scope,
                    "base_servings": 1,
                    "prep_time_min": 31 if index == 5 else None if index == 6 else 30,
                    "difficulty": 2,
                    "instructions": (
                        "1. Przygotuj składniki.\n2. Wymieszaj i podgrzej.\n"
                        "3. Podaj na wspólnym stole."
                    ),
                    "tag_ids": [tag, *system_tags[:1]],
                    "ingredients": [
                        {
                            "product_id": ids[f"product-{3 if index == 3 else 0}"],
                            "quantity": "120",
                            "unit": "g",
                        },
                        {"product_id": ids["product-1"], "quantity": "150", "unit": "ml"},
                        {"product_id": ids["product-2"], "quantity": "1", "unit": "szt."},
                    ],
                },
            )
        await write(
            a2,
            "recipe-a2-private",
            "POST",
            "/recipes",
            {
                "name": f"{PREFIX} — prywatny przepis A2",
                "scope": "private",
                "ingredients": [],
            },
        )
        await write(a1, "rating-a1", "PUT", f"/recipes/{ids['recipe-0']}/rating", {"rating": 1})
        await write(a2, "rating-a2", "PUT", f"/recipes/{ids['recipe-0']}/rating", {"rating": 5})
        if "photo" not in journal.state.done:
            journal.state.pending = "photo"
            journal.save()
            token = a1.client.cookies.get(csrf_cookie_name(settings))
            response = await a1.client.post(
                f"/api/v1/recipes/{ids['recipe-0']}/photo",
                files={"file": ("ux00-food.jpg", photo_bytes, "image/jpeg")},
                headers={"X-CSRF-Token": token or ""},
            )
            if not response.is_success:
                raise FixtureError(f"Upload zdjęcia: HTTP {response.status_code}.")
            journal.state.done.append("photo")
            journal.state.pending = None
            journal.save()
        for offset in range(3):
            day = (WEEK_START + timedelta(days=offset)).isoformat()
            current = await a1.call("GET", f"/plan/days/{day}")
            if current["id"] is not None and current["id"] != ids.get(f"day-{offset}"):
                raise FixtureError("Data UX00 jest zajęta przez dzień spoza manifestu.")
            title = DAY_TITLES[offset]
            await write(
                a1,
                f"day-{offset}",
                "PUT",
                f"/plan/days/{day}",
                {
                    "title": f"{PREFIX} — {title}",
                    "scope": "household",
                },
            )
            meal_key = f"meal-{offset}"

            def meal_identifier(result: Json, current_offset: int = offset) -> int:
                return int(fixture_meal(result, ids, current_offset)["id"])

            def item_identifier(result: Json, current_offset: int = offset) -> int:
                return int(fixture_recipe_item(result, ids, current_offset)["id"])

            # DayRead.id identyfikuje dzień, nigdy utworzony posiłek ani pozycję.
            mid = await write(
                a1,
                meal_key,
                "POST",
                f"/plan/days/{day}/meals",
                {
                    "name": MEAL_NAME,
                    "kcal_target": "600",
                },
                identifier_from=meal_identifier,
            )
            current = await a1.call("GET", f"/plan/days/{day}")
            if fixture_meal(current, ids, offset)["id"] != mid:
                raise FixtureError(
                    "Błędne ID posiłku w manifeście; użyj --repair-manifest-identifiers "
                    "wyłącznie dla COMPLETE manifestu."
                )
            count = 0 if offset == 0 else offset + 1
            await write(
                a1,
                f"plan-item-{offset}",
                "POST",
                f"/plan/meals/{mid}/items",
                {
                    "recipe_id": ids[f"recipe-{offset}"],
                    "servings": "2.20" if offset == 1 else "3.30",
                    "servings_split": [
                        {"member_profile_id": ids[f"profile-{p}"], "multiplier": "1.10"}
                        for p in range(count)
                    ],
                },
                identifier_from=item_identifier,
            )
            if offset == 0:
                await write(
                    a1,
                    "loose-product",
                    "POST",
                    f"/plan/meals/{mid}/items",
                    {
                        "product_id": ids["product-0"],
                        "quantity": "1.5",
                        "unit": "łyżka",
                        "servings": "1",
                    },
                    identifier_from=lambda result: fixture_loose_item(result, ids)["id"],
                )
        if (await a1.call("GET", f"/plan/days/{EMPTY_DAY}"))["id"] is not None:
            raise FixtureError("Pusta data UX00 jest zajęta; nie usunięto jej danych.")
        for index in range(105):
            await write(
                a1,
                f"pantry-{index}",
                "POST",
                "/pantry",
                {
                    "product_id": ids[f"product-{index % 4}"],
                    "amount": "0.100" if index % 4 == 2 else "2.500",
                    "expiry_date": (WEEK_START + timedelta(days=index)).isoformat(),
                    "location": "Szafka próbna",
                    "note": f"{PREFIX} — partia {index + 1:03}",
                },
            )
        for index in range(2):
            sid = await write(
                a1,
                f"store-{index}",
                "POST",
                "/stores",
                {
                    "name": f"{PREFIX} — Sklep {index + 1}",
                },
            )
            await write(
                a1,
                f"store-order-{index}",
                "PUT",
                f"/stores/{sid}/category-order",
                {
                    "category_ids": [
                        c["id"] for c in (categories[:2] if index == 0 else categories[:2][::-1])
                    ],
                },
            )
            await write(
                a1,
                f"retail-{index}",
                "POST",
                "/retail-products",
                {
                    "canonical_product_id": ids["product-0"],
                    "name": f"{PREFIX} — płatki {500 * (index + 1)} g",
                    "store_id": sid,
                    "package_amount": str(500 * (index + 1)),
                    "package_unit": "g",
                },
            )
        await write(
            a1,
            "template-day",
            "POST",
            "/templates/days",
            {
                "name": f"{PREFIX} — dzień",
                "scope": "household",
                "from_date": "2029-06-04",
            },
        )
        for index in range(2):
            await write(
                a1,
                f"template-week-{index}",
                "POST",
                "/templates/weeks",
                {
                    "name": f"{PREFIX} — tydzień {index + 1}",
                    "scope": "household",
                    "from_week_start": "2029-06-04",
                },
            )
        await write(
            a1,
            "cycle",
            "POST",
            "/cycles",
            {
                "name": f"{PREFIX} — cykl A → B",
                "scope": "household",
                "start_date": "2029-06-04",
                "template_ids": [ids["template-week-0"], ids["template-week-1"]],
            },
        )
        for use_pantry in (False, True):
            key = f"generation-{'pantry' if use_pantry else 'plain'}"
            gid = await write(
                a1,
                key,
                "POST",
                "/shopping/generate",
                {
                    "date_from": "2029-06-04",
                    "date_to": "2029-06-06",
                    "use_pantry": use_pantry,
                    "round_config_ids": [],
                },
            )
            generation = await a1.call("GET", f"/shopping/generations/{gid}")
            if generation["has_blockers"]:
                raise FixtureError(
                    "Generacja UX00 ma blokery; niczego automatycznie nie pominięto."
                )
            # Finalizacja zwraca envelope bez id. Listę odnajdujemy po generation_id.
            await write(a1, f"finalize-{key}", "POST", f"/shopping/generations/{gid}/finalize")
            lists = await a1.all("/shopping/lists")
            matches = [item for item in lists if item["generation_id"] == gid]
            if len(matches) != 1:
                raise FixtureError("Nie znaleziono jednoznacznej listy własnej generacji UX00.")
            lid = matches[0]["id"]
            ids[f"list-{'pantry' if use_pantry else 'plain'}"] = lid
            await write(
                a1,
                f"name-{key}",
                "PATCH",
                f"/shopping/lists/{lid}",
                {
                    "name": f"{PREFIX} — {'ze spiżarnią' if use_pantry else 'lista offline'}",
                    "store_id": ids["store-0"],
                },
            )
        lid = ids["list-plain"]
        detail = await a1.call("GET", f"/shopping/lists/{lid}")
        items = [item for section in detail["sections"] for item in section["items"]]
        if len(items) < 3:
            raise FixtureError("Lista offline UX00 wymaga co najmniej trzech pozycji.")
        await write(
            a1,
            "list-check-receive",
            "PATCH",
            f"/shopping/lists/{lid}/items/{items[0]['id']}",
            {"checked": True},
        )
        await write(a1, "list-receive", "POST", f"/shopping/lists/{lid}/accept-to-pantry")
        await write(
            a1,
            "list-check-pending",
            "PATCH",
            f"/shopping/lists/{lid}/items/{items[1]['id']}",
            {"checked": True},
        )
        await write(
            a1, "list-share", "POST", f"/shopping/lists/{lid}/share", {"expires_in_days": 365}
        )
        await verify(a1, actors, journal)
        journal.state.complete = True
        journal.save()
    print("UX00: zestaw zweryfikowany; lokalny manifest backend/data/ux-baseline/manifest.json.")


async def verify(a1: Api, actors: dict[str, Api], journal: Journal) -> None:
    """Rzeczywiste odczyty po setupie i po każdym ponownym uruchomieniu."""
    ids = journal.state.ids
    found = await plan_identifiers(a1, journal, household_reader=actors["a2"])
    if any(ids.get(key) != identifier for key, identifier in found.items()):
        raise FixtureError(
            "Błędne ID posiłku lub pozycji w manifeście UX00. "
            "Po kontroli użyj --repair-manifest-identifiers dla COMPLETE manifestu."
        )
    for path, keys in (
        ("/products", [f"product-{i}" for i in range(55)]),
        ("/recipes", [f"recipe-{i}" for i in range(55)]),
        ("/pantry", [f"pantry-{i}" for i in range(105)]),
    ):
        items = await a1.all(path)
        if not {ids[key] for key in keys}.issubset({item["id"] for item in items}):
            raise FixtureError(f"Niekompletny zbiór identyfikatorów UX00: {path}.")
    profiles = (await a1.call("GET", "/households/my"))["profiles"]
    if len(profiles) != 3 or {p["id"] for p in profiles} != {ids[f"profile-{i}"] for i in range(3)}:
        raise FixtureError("Rodzina UX00 nie ma trzech oczekiwanych profili.")
    photo_recipe = await a1.call("GET", f"/recipes/{ids['recipe-0']}")
    if (
        not photo_recipe["photo_url"]
        or not (await a1.client.get(photo_recipe["photo_url"])).is_success
    ):
        raise FixtureError("Zdjęcie UX00 nie jest dostępne przez chroniony endpoint.")
    no_photo = await a1.call("GET", f"/recipes/{ids['recipe-1']}")
    if no_photo["photo_url"]:
        raise FixtureError("Przepis bez zdjęcia UX00 otrzymał zdjęcie.")
    missing = await a1.call("GET", f"/recipes/{ids['recipe-3']}")
    if missing["nutrition"]["complete"]:
        raise FixtureError("Brak oczekiwanego przypadku niepełnych wartości.")
    await actors["b1"].call("GET", f"/recipes/{ids['recipe-2']}")
    private = await a1.client.get(f"/api/v1/recipes/{ids['recipe-a2-private']}")
    if private.status_code != 404 or (await actors["solo"].call("GET", "/auth/me"))["household"]:
        raise FixtureError("Granice dostępu kont UX00 są niezgodne z zestawem.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--photo", type=Path, required=True, help="Publiczne zdjęcie testowe, poza Git"
    )
    parser.add_argument(
        "--repair-manifest-identifiers",
        action="store_true",
        help="Tylko COMPLETE manifest: GET-y planu, kopia .identifiers.bak i atomowa naprawa ID",
    )
    args = parser.parse_args()

    async def run() -> None:
        settings = get_settings()  # To samo cache Settings, którego używa fabryka sesji DB.
        guard_environment(settings)  # Przed utworzeniem app/sesji/manifestu.
        try:
            await prepare(settings, args.photo, repair_identifiers=args.repair_manifest_identifiers)
        finally:
            await get_engine().dispose()

    try:
        asyncio.run(run(), loop_factory=selector_loop_factory())
    except FixtureError as exc:
        parser.exit(1, f"UX00: {exc}\n")
    except Exception as exc:
        # Nie drukuj tracebacku konfiguracji, payloadu logowania ani cookies.
        parser.exit(
            1, f"UX00: przerwano ({type(exc).__name__}); sprawdź manifest i log aplikacji.\n"
        )


if __name__ == "__main__":
    main()
