"""Line classifier for EverQuest Legends combat, loot, and progression text.

Patterns follow Josh's ``eqlog_Zasariz_qeynos`` log where it disagrees with the
design notes. In particular, zone lines look like ``You have entered Befallen
3 (Fused).`` and ``You have entered The Plane of Hate - Group 2 (Adaptive).``,
heals print ``actual (full)`` and sometimes omit the spell, ``You died.`` is a
real death line, and manual merge lines have no trailing period.
"""

from __future__ import annotations

import re
from datetime import datetime

from .models import ParsedEvent
from .sources import coin_to_copper, is_mote, is_wind_rune, item_tier, parse_item_qty

_TS_RE = re.compile(
    r"^\[(?P<ts>[A-Za-z]{3} [A-Za-z]{3} \d{2} \d{2}:\d{2}:\d{2} \d{4})\] ?(?P<msg>.*)$"
)
_TS_FMT = "%a %b %d %H:%M:%S %Y"
_TRAIL_MOD = re.compile(r" \(([A-Za-z][^)]*)\)\s*$")

# Longest first so "frenzy on" / "frenzies on" win over shorter verbs.
_BASE_VERBS = (
    "frenzy on", "backstab", "crush", "slash", "pierce", "bash", "kick",
    "bite", "claw", "gore", "maul", "punch", "strike", "slice", "slam",
    "sting", "rend", "smash", "gnaw", "lash", "smite", "cleave", "reave",
    "shoot", "flurry", "hit",
)
_THIRD_VERBS = (
    "frenzies on", "backstabs", "crushes", "slashes", "pierces", "bashes",
    "kicks", "bites", "claws", "gores", "mauls", "punches", "strikes",
    "slices", "slams", "stings", "rends", "smashes", "gnaws", "lashes",
    "smites", "cleaves", "reaves", "shoots", "flurries", "hits", "hit",
)

_SPELL_RE = re.compile(
    r"^(?P<source>.+?) hit (?P<target>.+?) for (?P<amt>\d+) points of "
    r"(?P<dtype>[a-z]+) damage by (?P<spell>.+)\.$"
)
_DOT_YOUR = re.compile(
    r"^(?P<target>.+?) has taken (?P<amt>\d+) damage from your (?P<spell>.+)\.$"
)
_DOT_YOU = re.compile(
    r"^You have taken (?P<amt>\d+) damage from (?P<spell>.+?) by (?P<source>.+)\.$"
)
_DOT_BY = re.compile(
    r"^(?P<target>.+?) has taken (?P<amt>\d+) damage from (?P<spell>.+?) by (?P<source>.+)\.$"
)
_DOT_NONE = re.compile(
    r"^(?P<target>.+?) has taken (?P<amt>\d+) damage by (?P<spell>.+)\.$"
)
_DS_RE = re.compile(
    r"^(?P<target>.+?) (?:is|are) (?P<how>\w+) by (?P<owner>.+?)'s (?P<what>\w+) "
    r"for (?P<amt>\d+) points? of non-melee damage!?(?:\.)?$"
)
_DS_YOUR = re.compile(
    r"^(?P<target>.+?) (?:is|are) (?P<how>\w+) by (?P<owner>YOUR|Your|your) "
    r"(?P<what>\w+) for (?P<amt>\d+) points? of non-melee damage!?(?:\.)?$"
)
_DS_PLAIN = re.compile(
    r"^You were hit by non-melee for (?P<amt>\d+) damage\.?$"
)
_MELEE_RE = re.compile(
    r"^(?P<body>.+) for (?P<amt>\d+) points? of damage\.$"
)
_ABSORB_DMG = re.compile(
    r"^(?P<target>.+?)'s magical skin absorbs the damage of (?P<what>.+)\.$"
)
_HEAL_RE = re.compile(
    r"^(?P<source>.+?) healed (?P<target>.+?)(?P<hot> over time)? for "
    r"(?P<actual>\d+)(?: \((?P<full>\d+)\))? hit points"
    r"(?: by (?P<spell>.+?))?\.?$"
)
_SELF_HURT = re.compile(
    r"^You hurt yourself for (?P<amt>\d+) points? of damage\.?$"
)
_SLAIN_YOU = re.compile(r"^You have slain (?P<target>.+)!$")
_SLAIN_BY = re.compile(r"^\*?(?P<target>.+) has been slain by (?P<killer>.+)!$")
_YOU_SLAIN = re.compile(r"^You have been slain by (?P<killer>.+)!$")
_DIED = re.compile(r"^(?P<name>.+) died\.$")
_CAST_YOU = re.compile(r"^You begin casting (?P<spell>.+)\.$")
_CAST_OTHER = re.compile(r"^(?P<source>.+) begins casting (?P<spell>.+)\.$")
_INTERRUPT_YOUR = re.compile(r"^Your (?P<spell>.+) spell is interrupted\.$")
_INTERRUPT_OTHER = re.compile(r"^(?P<source>.+?)'s (?P<spell>.+) spell is interrupted\.$")
_FIZZLE_YOUR = re.compile(r"^Your (?P<spell>.+) spell fizzles!$")
_FIZZLE_OTHER = re.compile(r"^(?P<source>.+?)'s (?P<spell>.+) spell fizzles!$")
_LOOT_BANNER = re.compile(
    r"^--You have looted (?P<item>.+?) from (?P<mob>.+)'s corpse\.--$"
)
_LOOT_AUTO = re.compile(
    r"^You looted (?P<item>.+?) from (?P<mob>.+)'s corpse"
    r"(?: and sold it for (?P<price>.+)| to create an? (?P<result>.+)"
    r"| and stored it in your (?P<where>.+))?$"
)
_GIVEN = re.compile(r"^You have been given:\s*(?P<item>.+?)\.?$")
_COIN = re.compile(r"^You receive (?P<coins>.+) from the corpse\.?$")
_COIN_NPC = re.compile(r"^You receive (?P<coins>.+) from (?P<who>.+?)\.?$")
_MERGE = re.compile(
    r"^You have successfully merged two items together to create a new item:\s*(?P<item>.+?)\.?$"
)
_OFFER = re.compile(r"^You offered (?P<qty>[\d,]+) (?P<item>.+) to (?P<npc>.+)\.?$")
_MOTE_WEAK = "The item you are trying to add will not work, this mote is not sufficiently powerful to upgrade this item."
_XP_RE = re.compile(
    r"^You gain (?P<party>party )?experience(?: \(with a bonus\))?!?"
    r"(?: \((?P<pct>\d+(?:\.\d+)?)%\))?$"
)
_LEVEL_RE = re.compile(r"^You have gained a level! Welcome to level (?P<level>\d+)!$")
_WELCOME_RE = re.compile(r"^Welcome to level (?P<level>\d+)!$")
_AA_ONE = re.compile(
    r"^You have gained an ability point!\s+You now have (?P<now>\d+) ability points?\.$"
)
_AA_N = re.compile(
    r"^You have gained (?P<n>\d+) ability points?!\s+You now have (?P<now>\d+) ability points?\.$"
)
_ZONE_RE = re.compile(r"^You have entered (?P<zone>.+)\.$")
_ZONE_TIER = re.compile(
    r"^(?P<name>.+?)(?: - (?P<scope>Solo|Group))?(?: (?P<num>\d+))? "
    r"\((?P<tier>Awakened|Adaptive|Refined|Fused|Normal)\)$"
)
_ZONE_SCOPE = re.compile(r"^(?P<name>.+?) - (?P<scope>Solo|Group)$")
_GROUP_YOU = re.compile(r"^You have joined the group\.$")
_GROUP_OTHER = re.compile(r"^(?P<name>.+) has joined the group\.$")
_GROUP_LEAD = re.compile(r"^You are now the leader of your group\.$")
_GROUP_YOU_LEFT = re.compile(r"^You have been removed from the group\.$")
_GROUP_LEFT = re.compile(r"^(?P<name>.+) (?:has left the group|has been removed from the group)\.$")
_GROUP_INVITE = re.compile(r"^You invite (?P<name>.+) to join your group\.$")
_GROUP_INVITED = re.compile(r"^(?P<name>.+) invites you to join a group\.$")
_GROUP_AGREE = re.compile(r"^You notify (?P<name>.+) that you agree to join the group\.$")
_RESIST_YOUR = re.compile(r"^(?P<target>.+) resisted your (?P<spell>.+)!$")
_RESIST_YOU = re.compile(r"^You resist (?P<source>.+)'s (?P<spell>.+)!$")
_RESIST_OTHER = re.compile(r"^(?P<target>.+) resisted (?P<source>.+)'s (?P<spell>.+)!$")
_DID_NOT_HOLD = re.compile(
    r"^Your (?P<spell>.+?) spell did not take hold on (?P<target>.+)\.$"
)
_RUNE = re.compile(r"^You gain a rune for (?P<amt>\d+) points of absorption\.$")
_PROC = re.compile(
    r"^Your (?P<item>.+) (?:shimmers briefly|feels alive with power)\.$"
)
_PET_TELL = re.compile(
    r"^(?P<pet>.+) told you, 'Attacking (?P<tgt>.+) Master\.'$",
    re.IGNORECASE,
)
_PET_LEADER = re.compile(
    r"^(?P<pet>.+) says, 'My leader is (?P<owner>.+)\.'$",
    re.IGNORECASE,
)
_SAY = re.compile(r"^(?P<speaker>.+) says, '(?P<body>.*)'$")
_CHARM = re.compile(r"^(?P<mob>.+) has been charmed\.$")
_CHARM_BREAK = re.compile(r"^Your Charm spell has worn off(?: of (?P<mob>.+))?\.$")
_WHO = re.compile(
    r"^\[(?P<level>\d+) (?P<classes>[A-Z]{3}(?:/[A-Z]{3}){0,5})\] "
    r"(?P<name>\S+) \((?P<race>[^)]+)\)"
)
_PROTECTED = re.compile(
    r"^(?P<source>.+) tries to cast a spell on (?P<target>.+), but (?P<why>.+)\.$"
)
_TAUNT_OK = re.compile(r"^(?P<source>.+) has captured (?P<target>.+)'s attention")
_TAUNT_FAIL = re.compile(r"^(?P<source>.+) failed to taunt (?P<target>.+)\.$")
_KNOCKOUT = "You have been knocked unconscious!"

_NOMINATE = (
    "following you, master",
    "now regrouping, master",
    "sorry, master",
    "now holding, master",
    "now greater holding master",
    "as you wish, oh great one",
    "i beg forgiveness, master",
    "not a legal target",
    "will not start new attacks",
    "will only attack something new",
    "percent of my hit points left",
    "calming down",
)

_AVOID = {
    "miss": "miss",
    "misses": "miss",
    "parry": "parry",
    "parries": "parry",
    "dodge": "dodge",
    "dodges": "dodge",
    "block": "block",
    "blocks": "block",
    "riposte": "riposte",
    "ripostes": "riposte",
}

_STORE_WHERE = {
    "dragon hoard": "stored_hoard",
    "currency": "stored_currency",
    "tradeskill depot": "stored_depot",
}


def parse_timestamp(text: str) -> datetime | None:
    try:
        return datetime.strptime(text, _TS_FMT)
    except ValueError:
        return None


def split_log_line(line: str) -> tuple[datetime | None, str]:
    """Return ``(timestamp, message)``. Message is the whole line when unstamped."""
    raw = line.rstrip("\r\n")
    match = _TS_RE.match(raw)
    if not match:
        return None, raw.strip()
    return parse_timestamp(match.group("ts")), match.group("msg").strip()


def _split_mods(message: str) -> tuple[str, tuple[str, ...]]:
    match = _TRAIL_MOD.search(message)
    if not match:
        return message, ()
    return message[: match.start()], tuple(match.group(1).split())


def _split_verb(text: str, verbs: tuple[str, ...]) -> tuple[str, str] | None:
    for verb in verbs:
        prefix = verb + " "
        if text.startswith(prefix):
            return verb, text[len(prefix):]
    return None


def _find_verb(body: str, verbs: tuple[str, ...]) -> tuple[str, str, str] | None:
    for verb in verbs:
        needle = f" {verb} "
        idx = body.find(needle)
        if idx > 0:
            return body[:idx], verb, body[idx + len(needle):]
    return None


def _event(kind: str, **kwargs) -> ParsedEvent:
    mods = kwargs.pop("modifiers", ())
    return ParsedEvent(kind=kind, modifiers=tuple(mods), **kwargs)


def _spell(msg: str, mods: tuple[str, ...]) -> ParsedEvent | None:
    match = _SPELL_RE.match(msg)
    if not match:
        return None
    return _event(
        "spell",
        source=match.group("source"),
        target=match.group("target"),
        amount=int(match.group("amt")),
        spell=match.group("spell"),
        verb="hit",
        damage_type=match.group("dtype"),
        modifiers=mods,
    )


def _dot(msg: str, mods: tuple[str, ...]) -> ParsedEvent | None:
    match = _DOT_YOUR.match(msg)
    if match:
        return _event(
            "dot",
            source="You",
            target=match.group("target"),
            amount=int(match.group("amt")),
            spell=match.group("spell"),
            damage_type="dot",
            modifiers=mods,
        )
    match = _DOT_YOU.match(msg)
    if match:
        return _event(
            "dot",
            source=match.group("source"),
            target="you",
            amount=int(match.group("amt")),
            spell=match.group("spell"),
            damage_type="dot",
            modifiers=mods,
        )
    match = _DOT_BY.match(msg)
    if match:
        return _event(
            "dot",
            source=match.group("source"),
            target=match.group("target"),
            amount=int(match.group("amt")),
            spell=match.group("spell"),
            damage_type="dot",
            modifiers=mods,
        )
    match = _DOT_NONE.match(msg)
    if match:
        return _event(
            "dot",
            source=None,
            target=match.group("target"),
            amount=int(match.group("amt")),
            spell=match.group("spell"),
            damage_type="dot",
            modifiers=mods,
        )
    return None


def _ds(msg: str, mods: tuple[str, ...]) -> ParsedEvent | None:
    match = _DS_YOUR.match(msg)
    if match:
        return _event(
            "ds",
            source="You",
            target=match.group("target"),
            amount=int(match.group("amt")),
            verb=match.group("how"),
            spell=match.group("what"),
            damage_type="ds",
            modifiers=mods,
        )
    match = _DS_RE.match(msg)
    if match:
        return _event(
            "ds",
            source=match.group("owner"),
            target=match.group("target"),
            amount=int(match.group("amt")),
            verb=match.group("how"),
            spell=match.group("what"),
            damage_type="ds",
            modifiers=mods,
        )
    match = _DS_PLAIN.match(msg)
    if match:
        return _event(
            "ds",
            source=None,
            target="You",
            amount=int(match.group("amt")),
            verb="hit",
            damage_type="ds",
            modifiers=mods,
        )
    match = _ABSORB_DMG.match(msg)
    if match:
        what = match.group("what")
        owner = what[:-2] if what.lower().endswith("'s") else what
        # "Amop's thorns" -> Amop; "YOUR thorns" -> You
        if what.upper().startswith("YOUR "):
            owner = "You"
        elif "'s " in what:
            owner = what.split("'s ", 1)[0]
        return _event(
            "avoid",
            source=owner,
            target=match.group("target"),
            amount=0,
            avoidance="absorb",
            spell=what,
            damage_type="ds",
            modifiers=mods,
        )
    return None


def _melee(msg: str, mods: tuple[str, ...]) -> ParsedEvent | None:
    match = _MELEE_RE.match(msg)
    if not match:
        return None
    body = match.group("body")
    amount = int(match.group("amt"))
    if body.startswith("You "):
        split = _split_verb(body[4:], _BASE_VERBS)
        if split:
            verb, target = split
            return _event(
                "melee",
                source="You",
                target=target,
                amount=amount,
                verb=verb,
                damage_type="melee",
                modifiers=mods,
            )
    found = _find_verb(body, _THIRD_VERBS)
    if not found:
        return None
    source, verb, target = found
    if not source or not target:
        return None
    return _event(
        "melee",
        source=source,
        target=target,
        amount=amount,
        verb=verb,
        damage_type="melee",
        modifiers=mods,
    )


def _avoidance_word(outcome: str) -> str | None:
    text = outcome.strip()
    if text.endswith("!"):
        text = text[:-1]
    lowered = text.lower()
    if "magical skin absorbs" in lowered:
        return "absorb"
    if "invulnerable" in lowered:
        return "invulnerable"
    last = lowered.split()[-1] if lowered else ""
    return _AVOID.get(last)


def _miss(msg: str, mods: tuple[str, ...]) -> ParsedEvent | None:
    if ", but " not in msg:
        return None
    left, outcome = msg.rsplit(", but ", 1)
    avoidance = _avoidance_word(outcome)
    if not avoidance:
        return None
    source: str | None = None
    verb: str | None = None
    target: str | None = None
    if left.startswith("You try to "):
        split = _split_verb(left[len("You try to "):], _BASE_VERBS)
        if not split:
            return None
        verb, target = split
        source = "You"
    elif " tries to " in left:
        source, rest = left.split(" tries to ", 1)
        split = _split_verb(rest, _BASE_VERBS)
        if not split or not source.strip():
            return None
        verb, target = split
    else:
        return None
    if outcome.strip().endswith("!"):
        pass
    return _event(
        "miss",
        source=source.strip(),
        target=target.strip() if target else None,
        amount=0,
        verb=verb,
        avoidance=avoidance,
        damage_type="melee",
        modifiers=mods,
    )


def _heal(msg: str, mods: tuple[str, ...]) -> ParsedEvent | None:
    # Flavour lines carry no amount. They are classified so they are not
    # reported as unknown combat text, and they do not enter healing totals.
    # "The heal within you effloresces." has no "healed", so this runs first.
    lowered = msg.lower()
    if (
        "healed from within" in lowered
        or "healed by the spirit" in lowered
        or lowered.startswith("you being to feel healed")
        or "effloresces" in lowered
        or "the heal within" in lowered
        or "mend your wounds" in lowered
    ):
        return _event("flavour", text=msg)
    if "healed" not in msg:
        return None
    match = _HEAL_RE.match(msg)
    if not match:
        return None
    full = match.group("full")
    spell = match.group("spell")
    return _event(
        "heal",
        source=match.group("source"),
        target=match.group("target"),
        amount=int(match.group("actual")),
        amount_full=int(full) if full is not None else None,
        spell=spell.strip() if spell else None,
        over_time=bool(match.group("hot")),
        verb="heal",
        modifiers=mods,
    )


def _death(msg: str) -> ParsedEvent | None:
    if msg == _KNOCKOUT:
        return _event("knockout", target="You")
    if msg == "You died.":
        return _event("death", target="You", source=None)
    match = _YOU_SLAIN.match(msg)
    if match:
        return _event("death", target="You", source=match.group("killer"))
    match = _SLAIN_YOU.match(msg)
    if match:
        return _event("slain", source="You", target=match.group("target"))
    match = _SLAIN_BY.match(msg)
    if match:
        return _event("slain", source=match.group("killer"), target=match.group("target"))
    match = _DIED.match(msg)
    if match and match.group("name") != "You":
        return _event("death", target=match.group("name"))
    return None


def _cast(msg: str) -> ParsedEvent | None:
    match = _CAST_YOU.match(msg)
    if match:
        return _event("cast", source="You", spell=match.group("spell"))
    match = _CAST_OTHER.match(msg)
    if match:
        return _event("cast", source=match.group("source"), spell=match.group("spell"))
    match = _INTERRUPT_YOUR.match(msg)
    if match:
        return _event("interrupt", source="You", spell=match.group("spell"))
    match = _INTERRUPT_OTHER.match(msg)
    if match:
        return _event("interrupt", source=match.group("source"), spell=match.group("spell"))
    match = _FIZZLE_YOUR.match(msg)
    if match:
        return _event("fizzle", source="You", spell=match.group("spell"))
    match = _FIZZLE_OTHER.match(msg)
    if match:
        return _event("fizzle", source=match.group("source"), spell=match.group("spell"))
    return None


def _loot_event(item_text: str, mob: str, mode: str, **kwargs) -> ParsedEvent:
    qty, item = parse_item_qty(item_text)
    kwargs.pop("result_tier", None)
    result = kwargs.get("result_item")
    return _event(
        "loot",
        source="You",
        target=mob,
        item=item,
        qty=qty,
        mode=mode,
        result_tier=item_tier(result) if result else item_tier(item),
        extra={"is_mote": is_mote(item), "is_wind_rune": is_wind_rune(item)},
        **kwargs,
    )


def _loot(msg: str) -> ParsedEvent | None:
    match = _LOOT_BANNER.match(msg)
    if match:
        return _loot_event(match.group("item"), match.group("mob"), "bag")
    if msg.startswith("You looted "):
        stripped = msg[:-1] if msg.endswith(".") else msg
        match = _LOOT_AUTO.match(stripped)
        if not match:
            return None
        where = (match.group("where") or "").strip()
        price = match.group("price")
        result = match.group("result")
        if price is not None:
            price = price.strip().rstrip(".")
            mode = "autosold"
            return _loot_event(
                match.group("item"),
                match.group("mob"),
                mode,
                coin_text=price,
                coin_copper=coin_to_copper(price),
            )
        if result is not None:
            result = result.strip().rstrip(".")
            return _loot_event(
                match.group("item"),
                match.group("mob"),
                "merged",
                result_item=result,
                result_tier=item_tier(result),
            )
        if where:
            mode = _STORE_WHERE.get(where.lower(), "stored")
            return _loot_event(match.group("item"), match.group("mob"), mode)
        return _loot_event(match.group("item"), match.group("mob"), "bag")
    match = _GIVEN.match(msg)
    if match:
        qty, item = parse_item_qty(match.group("item"))
        return _event(
            "loot",
            source="You",
            item=item,
            qty=qty,
            mode="given",
            extra={"is_mote": is_mote(item), "is_wind_rune": is_wind_rune(item)},
        )
    match = _COIN.match(msg)
    if match:
        coins = match.group("coins").strip().rstrip(".")
        return _event(
            "loot",
            source="You",
            mode="coin",
            item=coins,
            qty=1,
            coin_text=coins,
            coin_copper=coin_to_copper(coins),
        )
    match = _COIN_NPC.match(msg)
    if match:
        coins = match.group("coins").strip().rstrip(".")
        copper = coin_to_copper(coins)
        if copper is None:
            return None
        return _event(
            "loot",
            source="You",
            target=match.group("who").strip().rstrip("."),
            mode="payment",
            item=coins,
            qty=1,
            coin_text=coins,
            coin_copper=copper,
        )
    match = _MERGE.match(msg)
    if match:
        item = match.group("item").strip()
        return _event(
            "merge",
            source="You",
            item=item,
            result_item=item,
            result_tier=item_tier(item),
        )
    match = _OFFER.match(msg)
    if match:
        item = match.group("item").strip().rstrip(".")
        return _event(
            "give",
            source="You",
            target=match.group("npc").strip().rstrip("."),
            item=item,
            qty=int(match.group("qty").replace(",", "")),
            extra={"is_mote": is_mote(item), "is_wind_rune": is_wind_rune(item)},
        )
    if msg.rstrip(".") == _MOTE_WEAK.rstrip("."):
        return _event("mote_reject", source="You")
    return None


def _parse_zone(zone: str) -> tuple[str, dict]:
    """Split a zone announcement into the place name and instance fields.

    Real lines use ``<Zone> <N> (<Tier>)`` and ``<Zone> - Group [N] (<Tier>)``,
    not only the ``- Solo N (Tier)`` shape.
    """
    match = _ZONE_TIER.match(zone)
    if match:
        info = {
            "scope": match.group("scope"),
            "number": int(match.group("num")) if match.group("num") else None,
            "tier": match.group("tier"),
        }
        return match.group("name"), info
    match = _ZONE_SCOPE.match(zone)
    if match:
        return match.group("name"), {"scope": match.group("scope"), "number": None, "tier": None}
    return zone, {"scope": None, "number": None, "tier": None}


def _progress(msg: str) -> ParsedEvent | None:
    match = _XP_RE.match(msg)
    if match:
        pct = match.group("pct")
        return _event(
            "xp",
            source="You",
            xp_pct=float(pct) if pct else None,
            party_xp=bool(match.group("party")) or "(with a bonus)" in msg and "party" in msg,
            extra={"bonus": "(with a bonus)" in msg, "party": bool(match.group("party"))},
        )
    # party_xp above double-counts. Set it only from the party group.
    match = _LEVEL_RE.match(msg) or _WELCOME_RE.match(msg)
    if match:
        # The number is the level of the trio that just dinged. Swapping a
        # class can print a lower level later. This line names no classes.
        return _event("level", source="You", level=int(match.group("level")))
    match = _AA_N.match(msg)
    if match:
        return _event(
            "level",
            source="You",
            ability_points=int(match.group("n")),
            ability_total=int(match.group("now")),
        )
    match = _AA_ONE.match(msg)
    if match:
        return _event(
            "level",
            source="You",
            ability_points=1,
            ability_total=int(match.group("now")),
        )
    match = _ZONE_RE.match(msg)
    if match:
        name, info = _parse_zone(match.group("zone"))
        return _event("zone", source="You", zone=name, instance=info, text=match.group("zone"))
    return None


def _fix_xp_party(event: ParsedEvent, msg: str) -> ParsedEvent:
    if event.kind == "xp":
        event.party_xp = msg.startswith("You gain party experience")
        event.extra["party"] = event.party_xp
        event.extra["bonus"] = "(with a bonus)" in msg
    return event


def _group(msg: str) -> ParsedEvent | None:
    if _GROUP_YOU.match(msg):
        return _event("group_join", source="You", target="You")
    match = _GROUP_OTHER.match(msg)
    if match:
        return _event("group_join", source=match.group("name"), target=match.group("name"))
    if _GROUP_LEAD.match(msg):
        return _event("group_leader", source="You")
    if _GROUP_YOU_LEFT.match(msg):
        return _event("group_leave", source="You", target="You")
    match = _GROUP_LEFT.match(msg)
    if match:
        return _event("group_leave", source=match.group("name"), target=match.group("name"))
    match = _GROUP_INVITE.match(msg)
    if match:
        return _event("group_invite", source="You", target=match.group("name"))
    match = _GROUP_INVITED.match(msg)
    if match:
        return _event("group_invite", source=match.group("name"), target="You")
    match = _GROUP_AGREE.match(msg)
    if match:
        return _event("group_invite", source="You", target=match.group("name"), evidence="agree")
    return None


def _other(msg: str, mods: tuple[str, ...]) -> ParsedEvent | None:
    match = _DID_NOT_HOLD.match(msg)
    if match:
        return _event(
            "resist",
            source="You",
            target=match.group("target"),
            spell=match.group("spell"),
            avoidance="blocked",
            modifiers=mods,
        )
    match = _RESIST_YOU.match(msg)
    if match:
        return _event("resist", source=match.group("source"), target="You", spell=match.group("spell"))
    match = _RESIST_YOUR.match(msg)
    if match:
        return _event("resist", source="You", target=match.group("target"), spell=match.group("spell"))
    match = _RESIST_OTHER.match(msg)
    if match:
        return _event(
            "resist",
            source=match.group("source"),
            target=match.group("target"),
            spell=match.group("spell"),
        )
    match = _RUNE.match(msg)
    if match:
        return _event("rune", source="You", amount=int(match.group("amt")))
    match = _PROC.match(msg)
    if match:
        return _event("proc", source="You", item=match.group("item"))
    match = _PET_LEADER.match(msg)
    if match:
        return _event(
            "pet_leader",
            pet=match.group("pet"),
            owner=match.group("owner"),
            source=match.group("pet"),
            evidence="leader",
        )
    match = _PET_TELL.match(msg)
    if match:
        return _event(
            "pet_tell",
            pet=match.group("pet"),
            owner="You",
            source=match.group("pet"),
            target=match.group("tgt"),
            evidence="tell",
        )
    match = _SAY.match(msg)
    if match:
        body = match.group("body").lower()
        if any(phrase in body for phrase in _NOMINATE):
            return _event(
                "pet_nominate",
                pet=match.group("speaker"),
                source=match.group("speaker"),
                evidence="nominate",
            )
    match = _CHARM.match(msg)
    if match:
        return _event("charm", source="You", target=match.group("mob"), pet=match.group("mob"), evidence="charm")
    match = _CHARM_BREAK.match(msg)
    if match:
        return _event("charm_break", source="You", target=match.group("mob"), pet=match.group("mob"))
    match = _WHO.match(msg)
    if match:
        return _event(
            "who",
            player_name=match.group("name"),
            player_classes=match.group("classes"),
            player_level=int(match.group("level")),
            source=match.group("name"),
        )
    match = _PROTECTED.match(msg)
    if match:
        return _event(
            "avoid",
            source=match.group("source"),
            target=match.group("target"),
            avoidance="protected",
            spell=match.group("why"),
        )
    match = _TAUNT_OK.match(msg)
    if match:
        return _event("taunt", source=match.group("source"), target=match.group("target"), amount=1)
    match = _TAUNT_FAIL.match(msg)
    if match:
        return _event("taunt", source=match.group("source"), target=match.group("target"), amount=0)
    hurt = _SELF_HURT.match(msg)
    if hurt:
        return _event(
            "self_damage",
            source="You",
            target="You",
            amount=int(hurt.group("amt")),
            damage_type="self",
            modifiers=mods,
        )
    return None


def classify_message(message: str) -> ParsedEvent | None:
    """Classify one log message, without its timestamp prefix."""
    msg = message.strip()
    if not msg:
        return None
    msg, mods = _split_mods(msg)

    if " points of " in msg and " damage by " in msg:
        event = _spell(msg, mods)
        if event:
            return event
    if "has taken " in msg or msg.startswith("You have taken "):
        event = _dot(msg, mods)
        if event:
            return event
    if "non-melee" in msg or "magical skin absorbs the damage" in msg:
        event = _ds(msg, mods)
        if event:
            return event
    if "points of damage" in msg or "point of damage" in msg:
        event = _melee(msg, mods)
        if event:
            return event
    if "try to " in msg or "tries to " in msg:
        event = _miss(msg, mods)
        if event:
            return event
    if "heal" in msg.lower():
        event = _heal(msg, mods)
        if event:
            return event
    if (
        "slain" in msg
        or msg.endswith(" died.")
        or msg == "You died."
        or msg == _KNOCKOUT
    ):
        event = _death(msg)
        if event:
            return event
    if msg.startswith("You looted") or msg.startswith("--You have looted") or msg.startswith("You receive ") or msg.startswith("You have been given") or msg.startswith("You have successfully merged") or msg.startswith("You offered ") or msg.startswith("The item you are trying to add"):
        event = _loot(msg)
        if event:
            return event
    if msg.startswith("You gain ") or msg.startswith("You have gained") or msg.startswith("Welcome to level") or msg.startswith("You have entered "):
        event = _progress(msg)
        if event:
            return _fix_xp_party(event, msg)
    if "group" in msg:
        event = _group(msg)
        if event:
            return event
    if "casting" in msg or "fizzle" in msg or "interrupted" in msg:
        event = _cast(msg)
        if event:
            return event
    return _other(msg, mods)


def classify_log_line(line: str) -> tuple[datetime | None, ParsedEvent | None]:
    ts, msg = split_log_line(line)
    event = classify_message(msg)
    if event is not None:
        event.ts = ts
        event.text = msg
    return ts, event
