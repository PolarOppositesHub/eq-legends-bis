"""Actor names, source kinds, and pet-name forms.

The log uses a backtick for the possessive inside names (``Zasariz`s warder``,
``Teir`Dal``) and an ASCII apostrophe for English possessives (``ranger's thorns``,
``Garrison's Mighty Mana Shock``).
"""

from __future__ import annotations

import re

from .models import ParsedEvent

_ARTICLE = re.compile(r"^(?P<art>A|An|a|an) (?P<rest>.+)$")
_WARDER = re.compile(r"^(?P<owner>.+)[`']s warder$", re.IGNORECASE)
_YOU = {"you", "your", "yourself"}

MOTE_NAMES = (
    "Mote of Infinitesimal Potential",
    "Mote of Minor Potential",
    "Mote of Lesser Potential",
    "Mote of Potential",
    "Mote of Major Potential",
    "Mote of Greater Potential",
    "Mote of Superior Potential",
    "Mote of Grand Potential",
    "Mote of Ascendant Potential",
    "Mote of Infinite Potential",
    "Void-Touched Potential",
)
MOTE_NAME_SET = set(MOTE_NAMES)

WIND_RUNES = tuple(f"Wind Rune {suffix}" for suffix in (
    "Azia", "Beza", "Caza", "Dena", "Ena", "Fana", "Geza", "Heda",
    "Izah", "Jaka", "Kala", "Lena", "Meda", "Neza", "Ozah",
))
WIND_RUNE_SET = set(WIND_RUNES)

_COIN_RE = re.compile(r"(\d+)\s+(platinum|gold|silver|copper)s?\b", re.IGNORECASE)
_COIN_MULT = {"platinum": 1000, "gold": 100, "silver": 10, "copper": 1}
_TIER_RE = re.compile(r" \+(\d+)$")


def is_you(name: str | None) -> bool:
    return bool(name) and name.strip().lower() in _YOU


def canonical_name(name: str | None, character: str) -> str | None:
    """Map You/YOU/you onto the log character. Normalize a/an article case."""
    if name is None:
        return None
    text = name.strip()
    if not text:
        return None
    if text.lower() in _YOU or text.lower() == character.lower():
        return character
    if text.lower() in {"himself", "herself", "itself"}:
        return text.lower()
    return normalize_article(text)


def normalize_article(name: str) -> str:
    match = _ARTICLE.match(name.strip())
    if not match:
        return name.strip()
    return f"{match.group('art').lower()} {match.group('rest')}"


def warder_owner(name: str | None) -> str | None:
    if not name:
        return None
    match = _WARDER.match(name.strip())
    if not match:
        return None
    return match.group("owner")


def is_npc_pet_name(name: str | None) -> bool:
    """Mobs named ``<mob> pet`` are NPC pets, not a player's warder."""
    if not name:
        return False
    return name.strip().lower().endswith(" pet")


def parse_item_qty(text: str) -> tuple[int, str]:
    raw = text.strip()
    qty_match = re.match(r"^(\d+)\s+(.+)$", raw)
    if qty_match:
        return int(qty_match.group(1)), qty_match.group(2).strip()
    art = re.match(r"^(?:a|an)\s+(.+)$", raw, re.IGNORECASE)
    if art:
        return 1, art.group(1).strip()
    return 1, raw


def item_tier(name: str | None) -> int | None:
    if not name:
        return None
    match = _TIER_RE.search(name.strip())
    if not match:
        return None
    return int(match.group(1))


def coin_to_copper(text: str | None) -> int | None:
    if text is None:
        return None
    lowered = text.strip().lower().rstrip(".")
    if lowered == "free" or lowered.startswith("free"):
        return 0
    total = 0
    found = False
    for amount, unit in _COIN_RE.findall(text):
        found = True
        total += int(amount) * _COIN_MULT[unit.lower()]
    return total if found else None


def is_mote(name: str | None) -> bool:
    return bool(name) and name.strip() in MOTE_NAME_SET


def is_wind_rune(name: str | None) -> bool:
    return bool(name) and name.strip() in WIND_RUNE_SET


class ActorContext:
    """Per-character roster used while a log is ingested."""

    def __init__(self, character: str) -> None:
        self.character = character
        self.group: dict[str, str] = {}
        self.allowlist: dict[str, str] = {}
        self.pets: dict[str, str | None] = {}
        self.pet_evidence: dict[str, str] = {}
        self.manual_pets: set[str] = set()
        self.players: set[str] = set()
        self.charmed: set[str] = set()
        # Rule 5 nominations. These are prompts only and never an owner binding.
        self.candidates: dict[str, str] = {}
        self.dismissed: set[str] = set()

    def set_group(self, members: dict[str, str]) -> None:
        self.group = dict(members)

    def add_group(self, name: str) -> None:
        display = name.strip()
        if not display or is_you(display) or display.lower() == self.character.lower():
            return
        self.group[display.lower()] = display

    def clear_group(self) -> None:
        self.group.clear()

    def remove_group(self, name: str) -> None:
        self.group.pop(name.strip().lower(), None)

    def note_player(self, name: str) -> None:
        display = name.strip()
        if display and not is_you(display):
            self.players.add(display)

    def add_allow(self, name: str) -> None:
        display = name.strip()
        if not display or is_you(display) or display.lower() == self.character.lower():
            return
        self.allowlist[display.lower()] = display

    def remove_allow(self, name: str) -> None:
        self.allowlist.pop(name.strip().lower(), None)

    def note_candidate(self, pet: str, evidence: str) -> bool:
        """Remember a nominating say. Never writes an owner binding.

        Returns True the first time this pet becomes an open prompt.
        """
        pet = pet.strip()
        if not pet or is_you(pet) or pet.lower() == self.character.lower():
            return False
        if is_npc_pet_name(pet):
            return False
        if pet in self.manual_pets or pet in self.dismissed:
            return False
        if self.pets.get(pet):
            return False
        if pet in self.candidates:
            self.candidates[pet] = evidence
            return False
        self.candidates[pet] = evidence
        return True

    def dismiss_candidate(self, pet: str) -> None:
        pet = pet.strip()
        if not pet:
            return
        self.candidates.pop(pet, None)
        self.dismissed.add(pet)

    def bind_pet(self, pet: str, owner: str | None, evidence: str, *, manual: bool = False) -> bool:
        """Return True when the binding changed. Manual wins over auto."""
        pet = pet.strip()
        if not pet:
            return False
        if manual:
            self.manual_pets.add(pet)
            self.pets[pet] = owner
            self.pet_evidence[pet] = evidence
            if owner:
                self.candidates.pop(pet, None)
                self.dismissed.discard(pet)
            else:
                self.dismiss_candidate(pet)
            if owner is None:
                self.charmed.discard(pet)
            return True
        if pet in self.manual_pets:
            return False
        if self.pets.get(pet) == owner and self.pet_evidence.get(pet) == evidence:
            return False
        self.pets[pet] = owner
        self.pet_evidence[pet] = evidence
        if owner:
            self.candidates.pop(pet, None)
        return True

    def note_name_pets(self, *names: str | None) -> list[tuple[str, str, str]]:
        """Bind ``<owner>`s warder`` from the name. Returns new auto bindings."""
        found: list[tuple[str, str, str]] = []
        for name in names:
            if not name:
                continue
            owner = warder_owner(name)
            if not owner:
                continue
            if self.bind_pet(name.strip(), owner, "warder_name"):
                found.append((name.strip(), owner, "warder_name"))
        return found

    def owner_of(self, name: str | None) -> str | None:
        if not name:
            return None
        if name in self.pets:
            return self.pets[name]
        owner = warder_owner(name)
        return owner

    def kind_of(self, name: str | None) -> str:
        if not name:
            return "unknown"
        if is_you(name) or name == self.character or name.lower() == self.character.lower():
            return "self"
        if name in self.manual_pets and self.pets.get(name) is None:
            return "other"
        if name in self.pets and self.pets.get(name):
            return "pet"
        if warder_owner(name):
            return "pet"
        if is_npc_pet_name(name):
            return "npc"
        key = name.lower()
        if key in self.group or name in self.group.values():
            return "group"
        if key in self.allowlist or name in self.allowlist.values():
            return "group"
        if name in self.players:
            return "other"
        if name in self.candidates:
            return "candidate"
        return "npc"

    def in_group_name(self, name: str | None) -> str | None:
        if not name:
            return None
        return self.group.get(name.lower())


def involve_friendly(source_kind: str, target_kind: str) -> bool:
    friendly = {"self", "group", "pet"}
    return source_kind in friendly or target_kind in friendly


def event_actor_names(event: ParsedEvent) -> list[str]:
    names = [event.source, event.target, event.pet]
    return [n for n in names if n]
