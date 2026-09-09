"""Quest obtain guides from catalog + eqlwiki (never invent steps).

Decoded items expose quest_source / rewardFromQuests as names only.
When a real quest name is present (not a "Drops From:" blob), we best-effort
fetch the eqlwiki page, extract dialogue/handoff steps + component tables,
and cache under data/quest-guides/. If fetch fails, return the quest name +
wiki URL only — never fabricate steps.

Collection steps resolve zone + drop mobs from local catalog and/or the
component item's eqlwiki "Drops From" section. Plane of Sky table tags like
"(4-KoS)" are expanded only via the documented island-boss legend on
eqlwiki Plane of Sky — never invented. When mobs are unknown, steps say so.
"""
from __future__ import annotations

import hashlib
import json
import re
import urllib.error
import urllib.parse
import urllib.request
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

from .paths import APP_ROOT

GUIDES_DIR = APP_ROOT / "data" / "quest-guides"
USER_AGENT = "EQ-Legends-BiS/1.0.5 (local; Josh Monroe)"
# Keep cache filenames well under common OS PATH_MAX / NAME_MAX limits.
_MAX_SLUG_LEN = 120
# Bump when step/component wording schema changes so stale caches refresh.
GUIDE_FORMAT_VERSION = 5

_DROP_PREFIX = re.compile(r"^\s*drops?\s+from\s*:", re.I)
# Catalog sometimes stores "Zone: mob; Zone: mob2; ..." as source (not a quest).
_ZONE_MOB_DROP = re.compile(
    r"^[A-Za-z][\w' .\-]{1,60}:\s*[A-Za-z][\w' .\-]{1,80}"
    r"(?:\s*;\s*[A-Za-z][\w' .\-]{1,60}:\s*[A-Za-z][\w' .\-]{1,80})+\s*$"
)
_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")
# Wiki sky-table tags: "Woven Skull Cap (4-KoS)" / "Gem of Invigoration (7-Trash)"
_SKY_REQ_TAG = re.compile(
    r"^(?P<item>.+?)\s*\((?P<tag>\d+\s*-\s*[A-Za-z][A-Za-z0-9]*)\)\s*$"
)
_PREREQ_LINE = re.compile(
    r"(?:prerequisite|prerequisites|previous\s+quest|requires?\s+quest|"
    r"must\s+(?:first\s+)?complete)\s*:?\s*(.+)",
    re.I,
)

# Documented eqlwiki Plane of Sky island bosses (same abbreviations used in class-test tables).
# Keys are normalized lowercase without spaces: "4-kos", "7-trash", etc.
_SKY_DROP_TAGS: dict[str, dict[str, Any]] = {
    "2-pos": {
        "island": 2,
        "island_name": "Azarack Island",
        "mobs": ["Protector of Sky"],
    },
    "3-gorga": {
        "island": 3,
        "island_name": "Harpy Island",
        "mobs": ["Gorgalosk"],
    },
    "4-kos": {
        "island": 4,
        "island_name": "Pegasus Island",
        "mobs": ["Keeper of Souls"],
    },
    "5-sl": {
        "island": 5,
        "island_name": "Spiroc Island",
        "mobs": ["The Spiroc Lord"],
    },
    "6-bz": {
        "island": 6,
        "island_name": "Bee Island",
        "mobs": ["Bazzt Zzzt"],
    },
    "7-sots": {
        "island": 7,
        "island_name": "Drake Island",
        "mobs": ["Sister of the Spire"],
    },
    "7-trash": {
        "island": 7,
        "island_name": "Drake Island",
        "mobs": [],
        "trash": True,
    },
    "8-eov": {
        "island": 8,
        "island_name": "Veeshan Island",
        "mobs": ["Eye of Veeshan"],
    },
}


def _slug(name: str) -> str:
    s = (name or "").strip().lower()
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    if not s:
        return "quest"
    if len(s) <= _MAX_SLUG_LEN:
        return s
    digest = hashlib.sha1(s.encode("utf-8")).hexdigest()[:12]
    keep = max(16, _MAX_SLUG_LEN - 13)
    return f"{s[:keep].rstrip('-')}-{digest}"


def is_drop_source(quest_source: str | None) -> bool:
    """True when quest_source is actually a drop line, not a quest name."""
    s = (quest_source or "").strip()
    if not s:
        return False
    if bool(_DROP_PREFIX.match(s)) or s.lower().startswith("craft") or s.lower().startswith("bought"):
        return True
    # Multi "Zone: mob; Zone: mob" lists from catalog source fields
    if ";" in s and _ZONE_MOB_DROP.match(s):
        return True
    # Extremely long blobs are never a single quest title
    if len(s) > 160 and ";" in s:
        return True
    return False


def quest_name_from_source(quest_source: str | None) -> str | None:
    """Extract a quest title from quest_source / source strings."""
    s = (quest_source or "").strip()
    if not s or is_drop_source(s):
        return None
    # "Reward from Plane of Sky Quest: Wizard Test of Focus"
    m = re.search(r"quest:\s*(.+)$", s, re.I)
    if m:
        title = m.group(1).strip()
        return title if title and not is_drop_source(title) and len(title) <= 160 else None
    m = re.search(r"reward from(?:\s+[\w\s]+)?\s+quest:\s*(.+)$", s, re.I)
    if m:
        title = m.group(1).strip()
        return title if title and not is_drop_source(title) and len(title) <= 160 else None
    # Bare quest title
    if "drops from" in s.lower():
        return None
    if len(s) > 160:
        return None
    return s


def wiki_urls_for_quest(quest_name: str) -> list[str]:
    name = (quest_name or "").strip()
    if not name:
        return []
    title = name.replace(" ", "_")
    urls = [
        f"https://eqlwiki.com/{urllib.parse.quote(title)}",
        f"https://eqlwiki.com/{urllib.parse.quote(name)}",
    ]
    # Plane of Sky class tests often live on class test pages
    if "test of" in name.lower() or "plane of sky" in name.lower():
        for cls in (
            "Wizard", "Magician", "Enchanter", "Necromancer", "Cleric", "Druid",
            "Shaman", "Warrior", "Paladin", "Shadow_Knight", "Ranger", "Bard",
            "Monk", "Rogue", "Beastlord", "Berserker",
        ):
            if name.lower().startswith(cls.lower().replace("_", " ")) or cls.lower().replace("_", " ") in name.lower():
                urls.insert(0, f"https://eqlwiki.com/{cls}_Plane_of_Sky_Tests")
                break
        urls.append("https://eqlwiki.com/Plane_of_Sky")
    seen, out = set(), []
    for u in urls:
        if u not in seen:
            seen.add(u)
            out.append(u)
    return out


def _http_get(url: str, timeout: float = 20.0) -> bytes | None:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read()
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, ValueError):
        return None


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []
        self._skip = 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style", "noscript"):
            self._skip += 1

    def handle_endtag(self, tag):
        if tag in ("script", "style", "noscript") and self._skip:
            self._skip -= 1

    def handle_data(self, data):
        if self._skip:
            return
        t = data.strip()
        if t:
            self.parts.append(t)


def _html_to_text(html: str) -> str:
    p = _TextExtractor()
    try:
        p.feed(html or "")
    except Exception:
        return _TAG_RE.sub(" ", html or "")
    return _WS_RE.sub(" ", " ".join(p.parts))


def _extract_quest_section(html: str, quest_name: str) -> str:
    """Pull the heading section matching quest_name when page covers many tests."""
    if not html or not quest_name:
        return html or ""
    # Prefer == Wiki heading == style if present in raw; mediawiki often uses h2/h3
    pattern = re.compile(
        rf"(<h[23][^>]*>\s*{re.escape(quest_name)}\s*</h[23]>)(.*?)(?=<h[23]\b|\Z)",
        re.I | re.S,
    )
    m = pattern.search(html)
    if m:
        return m.group(1) + m.group(2)
    # Fallback: case-insensitive contains
    low = html.lower()
    key = quest_name.lower()
    idx = low.find(key)
    if idx >= 0:
        return html[max(0, idx - 200): idx + 6000]
    return html


def _extract_mw_section(html: str, section_id: str) -> str:
    """Extract MediaWiki body after <h2 id="Section"> / mw-heading until the next h2/h3."""
    if not html or not section_id:
        return ""
    m = re.search(rf'\bid=["\']{re.escape(section_id)}["\']', html, re.I)
    if not m:
        # Title text fallback (e.g. Walkthrough without id)
        m = re.search(
            rf'<h([23])\b[^>]*>\s*(?:<span[^>]*>)?\s*{re.escape(section_id)}\s*(?:</span>)?\s*</h\1>',
            html,
            re.I,
        )
        if not m:
            return ""
        start = m.start()
    else:
        start = m.start()
    hm = re.search(r"</h[23]>", html[start : start + 800], re.I)
    body_start = start + (hm.end() if hm else 0)
    rest = html[body_start:]
    # Skip closing </div> of mw-heading wrapper when present.
    stripped = rest.lstrip()
    lead_ws = len(rest) - len(stripped)
    if stripped.lower().startswith("</div>"):
        body_start += lead_ws + len("</div>")
        rest = html[body_start:]
    nm = re.search(r'<div[^>]*class="[^"]*mw-heading|<h[23]\b', rest, re.I)
    body_end = body_start + (nm.start() if nm else min(len(rest), 16000))
    return html[body_start:body_end]


def _clean_step_line(text: str) -> str:
    line = _WS_RE.sub(" ", (text or "").strip())
    line = re.sub(r"\s*\[edit(?:\s+source)?\]\s*", " ", line, flags=re.I)
    return _WS_RE.sub(" ", line).strip(" .-")


def _looks_like_item_tooltip_blob(text: str) -> bool:
    low = (text or "").lower()
    return (
        "lore item" in low
        or "magic item" in low
        or "slot: head" in low
        or "slot: " in low and "ac:" in low
        or ("class: all" in low and "wt:" in low)
    )


def _list_items_from_html(section_html: str) -> list[str]:
    out: list[str] = []
    for m in re.finditer(r"<li\b[^>]*>([\s\S]*?)</li>", section_html or "", re.I):
        line = _clean_step_line(_html_to_text(m.group(1)))
        if not line or len(line) < 6 or len(line) > 600:
            continue
        if _looks_like_item_tooltip_blob(line) and not re.match(
            r"^(requires|obtain|turn in|go to|kill|hail|find|collect)\b", line, re.I
        ):
            continue
        if line not in out:
            out.append(line)
    return out


def _paragraph_steps_from_html(section_html: str) -> list[str]:
    out: list[str] = []
    for m in re.finditer(r"<p\b[^>]*>([\s\S]*?)</p>", section_html or "", re.I):
        line = _clean_step_line(_html_to_text(m.group(1)))
        if not line or len(line) < 20 or len(line) > 500:
            continue
        if _looks_like_item_tooltip_blob(line):
            continue
        low = line.lower()
        if any(
            k in low
            for k in (
                "note:",
                "may be found",
                "to obtain",
                "go to",
                "turn in",
                "kill ",
                "hail ",
                "talk to",
                "requires ",
                "start zone",
                "quest giver",
                "bring ",
                "return ",
                "hand ",
            )
        ):
            if line not in out:
                out.append(line)
    # Definition / indented walkthrough lines
    for m in re.finditer(r"<dd\b[^>]*>([\s\S]*?)</dd>", section_html or "", re.I):
        line = _clean_step_line(_html_to_text(m.group(1)))
        if not line or len(line) < 20 or len(line) > 500:
            continue
        if _looks_like_item_tooltip_blob(line):
            continue
        if line not in out:
            out.append(line)
    return out


def _quest_header_facts(html: str) -> list[str]:
    """Start zone / quest giver from eqlwiki questTopTable when present."""
    facts: list[str] = []
    table_m = re.search(
        r'class="[^"]*questTopTable[^"]*"[\s\S]*?</table>',
        html or "",
        re.I,
    )
    if not table_m:
        return facts
    table = table_m.group(0)
    for label, prefix in (
        ("Start Zone", "Start in"),
        ("Quest Giver", "Talk to"),
        ("Minimum Level", "Minimum level"),
    ):
        m = re.search(
            rf"<th>\s*<b>\s*{re.escape(label)}\s*:\s*</b>\s*</th>\s*<td>([\s\S]*?)</td>",
            table,
            re.I,
        )
        if not m:
            continue
        val = _clean_step_line(_html_to_text(m.group(1)))
        if val:
            facts.append(f"{prefix} {val}.")
    return facts


def _steps_from_wiki_sections(html: str, quest_name: str) -> list[str]:
    """Build walkthrough steps from Checklist + Walkthrough (+ header facts).

    Prefer structured eqlwiki sections over thin dialogue heuristics.
    """
    steps: list[str] = []
    for fact in _quest_header_facts(html):
        if fact not in steps:
            steps.append(fact)

    checklist = _extract_mw_section(html, "Checklist")
    for line in _list_items_from_html(checklist):
        if line not in steps:
            steps.append(line)

    walkthrough = _extract_mw_section(html, "Walkthrough")
    # Prefer concrete how-to paragraphs / list items from Walkthrough.
    for line in _paragraph_steps_from_html(walkthrough) + _list_items_from_html(walkthrough):
        # Avoid duplicating short checklist lines already present.
        if any(line.lower() == s.lower() or line.lower() in s.lower() for s in steps):
            continue
        if line not in steps:
            steps.append(line)

    # If still thin, fold in instructional dialogue lines.
    if len(steps) < 4:
        dialogue = _extract_mw_section(html, "Dialogue")
        for line in _steps_from_text(_html_to_text(dialogue), quest_name):
            if line.lower().startswith("quest:"):
                continue
            if line not in steps:
                steps.append(line)

    # Drop lone title stub if we somehow only have it.
    steps = [s for s in steps if not (s.lower().startswith("quest:") and len(steps) == 1)]
    return steps[:40]


def _is_stub_guide(guide: dict[str, Any] | None) -> bool:
    if not guide:
        return True
    steps = [str(s).strip() for s in (guide.get("steps") or []) if str(s).strip()]
    if guide.get("components"):
        return False
    if not steps:
        return True
    if len(steps) == 1 and (
        steps[0].lower().startswith("quest:")
        or steps[0].lower().startswith("see walkthrough")
    ):
        return True
    return False


def _steps_from_text(text: str, quest_name: str) -> list[str]:
    """Heuristic step list from wiki prose — only keeps lines that look instructional."""
    steps: list[str] = []
    if not text:
        return steps
    # Split on say / hand / bring / return cues
    chunks = re.split(
        r"(?<=[.!?])\s+|(?=You say,)|(?=Hand )|(?=Bring )|(?=Return )|(?=Travel )|(?=Go to )|(?=Obtain )|(?=Turn in )",
        text,
    )
    for chunk in chunks:
        line = _WS_RE.sub(" ", (chunk or "").strip())
        if len(line) < 20 or len(line) > 400:
            continue
        low = line.lower()
        if any(
            k in low
            for k in (
                "you say",
                "says '",
                "says \"",
                "bring",
                "hand ",
                "return to",
                "travel",
                "prove",
                "reward you",
                "hail ",
                "collect",
                "turn in",
                "obtain",
                "go to",
                "kill ",
                "talk to",
                "find ",
            )
        ):
            if line not in steps:
                steps.append(line)
        if len(steps) >= 20:
            break
    return steps


_BRING_ITEMS_RE = re.compile(
    r"(?:bring(?:\s+to\s+me|\s+me)?|return(?:\s+to\s+me)?|hand\s+me)\s+"
    r"(?:(?:,\s*)?(?:from\s+[^,]+,\s*)?)?"
    r"(?:some\s+|a\s+|an\s+|the\s+)?(.+?)(?:[.!]|$)",
    re.I,
)
_AND_SPLIT_RE = re.compile(r"\s+and\s+", re.I)
_JUNK_ITEM_RE = re.compile(
    r"^(?:me|him|her|them|your|quest|items?|reward|proof|yourself|to\s+me|from\s+|mist\b|of\s+)\b",
    re.I,
)


def _looks_like_item_name(name: str) -> bool:
    s = _WS_RE.sub(" ", (name or "").strip())
    if len(s) < 4 or len(s) > 64:
        return False
    if "," in s or ")" in s:
        return False
    if re.search(r"\b(quest start|talk to|hail|you say|reward:|magic item)\b", s, re.I):
        return False
    if _JUNK_ITEM_RE.match(s):
        return False
    # Prefer names that look like item titles (at least one letter token).
    if not re.search(r"[A-Za-z]", s):
        return False
    return True


def _extract_bring_item_names(line: str) -> list[str]:
    """Pull candidate item names from 'bring/return … X and Y' dialogue lines."""
    raw_line = _WS_RE.sub(" ", (line or "").strip())
    low = raw_line.lower()
    if not any(k in low for k in ("bring", "return to me", "hand me")):
        return []
    # Normalize "return to me, from this place of air and mist, a fine cloth…"
    cleaned = re.sub(
        r"(return to me|bring(?: to me| me)?|hand me),?\s+from\s+[^,]+,\s*",
        r"\1 ",
        raw_line,
        flags=re.I,
    )
    m = _BRING_ITEMS_RE.search(cleaned)
    if not m:
        return []
    blob = _WS_RE.sub(" ", m.group(1)).strip(" .,;:")
    blob = re.split(
        r"\s+to\s+(?:reap|receive|claim|earn|prove)\b|\s+and\s+you\s+shall\b",
        blob,
        maxsplit=1,
        flags=re.I,
    )[0].strip(" .,;:")
    parts = [p.strip(" .,;:") for p in _AND_SPLIT_RE.split(blob) if p.strip()]
    out: list[str] = []
    for p in parts:
        p = re.sub(r"^(?:some|a|an|the)\s+", "", p, flags=re.I).strip()
        if not _looks_like_item_name(p):
            continue
        out.append(p)
    return out[:6]

def _append_collect_steps_from_dialogue(
    steps: list[str],
    *,
    fetch: bool = False,
    default_zone: str = "",
) -> tuple[list[str], list[dict[str, Any]]]:
    """After dialogue steps, add explicit Collect lines with zone/mobs when known."""
    out_steps = list(steps or [])
    components: list[dict[str, Any]] = []
    seen: set[str] = set()
    for line in steps or []:
        for raw in _extract_bring_item_names(line):
            key = raw.strip().lower()
            if not key or key in seen:
                continue
            seen.add(key)
            resolved = resolve_component_drop(raw, fetch=fetch, default_zone=default_zone)
            components.append({
                "item": resolved["item"],
                "who": resolved["who"],
                "where": resolved["where"],
                "mobs": resolved.get("mobs") or [],
                "wiki_tag": resolved.get("wiki_tag") or "",
                "drop_known": resolved.get("drop_known"),
                "kind": "dialogue_required",
            })
            step = resolved["collect_step"]
            if step not in out_steps:
                out_steps.append(step)
    return out_steps, components


def _expand_island_where(where: str, *, default_zone: str = "Plane of Sky") -> dict[str, Any]:
    """Turn 'Island 3' / 'Plane of Sky Island 4' into zone + island metadata."""
    s = _WS_RE.sub(" ", (where or "").strip())
    out: dict[str, Any] = {"zone": "", "island": None, "island_name": "", "where": s}
    if not s:
        return out
    if re.search(r"\bany\s+island\b", s, re.I):
        return {
            "zone": "Plane of Sky",
            "island": None,
            "island_name": "",
            "where": "Plane of Sky (any island)",
            "mobs": [],
            "trash": True,
        }
    m = re.search(r"(?:plane\s+of\s+sky\s+)?island\s+(\d+)\b", s, re.I)
    if m:
        num = int(m.group(1))
        meta = None
        for _tag, info in _SKY_DROP_TAGS.items():
            if info.get("island") == num and not info.get("trash"):
                meta = info
                break
        zone = "Plane of Sky"
        island_name = (meta or {}).get("island_name") or ""
        label = f"{zone} Island {num}"
        if island_name:
            label += f" ({island_name})"
        return {
            "zone": zone,
            "island": num,
            "island_name": island_name,
            "where": label,
            "mobs": list((meta or {}).get("mobs") or []),
        }
    if re.search(r"plane\s+of\s+sky", s, re.I):
        out["zone"] = "Plane of Sky"
        out["where"] = "Plane of Sky"
        return out
    out["zone"] = s
    return out


def _component_collect_step(c: dict[str, Any]) -> str:
    """Build a clear Collect line from an enriched component row."""
    item = (c.get("item") or "").strip() or "required item"
    where_raw = (c.get("where") or "").strip()
    who = (c.get("who") or "").strip()
    mobs = [m for m in (c.get("mobs") or []) if m]
    if not mobs and who and who.lower() not in {
        "see wiki", "unknown", "?", "n/a", "npc", "mob", "mobs", "random drop",
        "drop mob unknown in available data", "drop source unknown in available data",
    } and "unknown" not in who.lower() and "trash" not in who.lower():
        # Component table "who" is often the mob name.
        mobs = [who]

    expanded = _expand_island_where(where_raw)
    where = expanded.get("where") or where_raw or "location unknown"
    if expanded.get("trash") and not mobs:
        info = {
            "zone": expanded.get("zone") or "Plane of Sky",
            "island": expanded.get("island"),
            "island_name": expanded.get("island_name") or "",
            "mobs": [],
            "wiki_tag": c.get("wiki_tag") or "",
            "trash": True,
        }
        return _format_collect_step(item, info)

    info = {
        "zone": expanded.get("zone") or ("Plane of Sky" if "Island" in where else where),
        "island": expanded.get("island"),
        "island_name": expanded.get("island_name") or "",
        "mobs": mobs,
        "wiki_tag": c.get("wiki_tag") or "",
        "trash": "trash" in who.lower(),
    }
    return _format_collect_step(item, info)

def _prefer_clear_steps(
    steps: list[str],
    components: list[dict[str, Any]],
) -> list[str]:
    """If we have resolved collect components, keep a short clear step list."""
    # Dedupe components by normalized item name; prefer rows with known mobs.
    best: dict[str, dict[str, Any]] = {}
    for c in components or []:
        item = (c.get("item") or "").strip()
        if not item:
            continue
        key = item.lower()
        cur = best.get(key)
        score = (2 if c.get("mobs") else 0) + (1 if c.get("drop_known") else 0) + (
            1 if (c.get("who") or "").lower() not in {"", "random drop", "see wiki"} else 0
        )
        if not cur or score >= cur.get("_score", -1):
            best[key] = {**c, "_score": score}

    collect_steps = []
    for c in best.values():
        collect_steps.append(_component_collect_step(c))

    if not collect_steps:
        return steps

    # Keep quest title / hail / hand-in cues; drop long dialogue walls.
    kept: list[str] = []
    turn_ins: list[str] = []
    for s in steps or []:
        low = s.lower()
        if s.startswith("Quest:") or s.startswith("Collect ") or s.startswith("See walkthrough"):
            # Drop prior Collect lines; we rebuild from best components.
            if s.startswith("Collect "):
                continue
            kept.append(s)
            continue
        if re.match(r"^(start in|talk to|minimum level|requires)\b", low):
            if s not in kept:
                kept.append(s)
            continue
        if "may be found" in low or "can be found" in low:
            if s not in kept:
                kept.append(s)
            continue
        if low.startswith("turn in") or (low.startswith("hand ") and "marshal" in low):
            if s not in turn_ins:
                turn_ins.append(s)
            continue
        # Keep the short "Go to Rivervale bank… give skins…" handoff summary when present.
        if "give" in low and ("skullcap" in low or "dirk" in low) and len(s) < 280:
            if s not in turn_ins:
                turn_ins.append(s)
            continue
        if any(k in low for k in ("hail", "hand the required", "efreeti", "teleport pad", "key master")):
            if not low.startswith("you say"):
                kept.append(s)
            continue
        if low.startswith("you say") or " says," in low or " says '" in low:
            continue
        if "bring" in low or "return to me" in low or "return to me," in low:
            continue
        if "proceed upward" in low:
            continue
    for cs in collect_steps:
        if cs not in kept:
            kept.append(cs)
    for t in turn_ins:
        if t not in kept:
            kept.append(t)
    if not any("hand" in s.lower() and "reward" in s.lower() for s in kept) and not turn_ins:
        kept.append("Hand the required items to the quest NPC for the reward.")
    return kept[:24]

def _parse_component_rows(html: str) -> list[dict[str, str]]:
    """Best-effort parse simple wiki tables of Item | Who | Where."""
    rows: list[dict[str, str]] = []
    # Very loose: consecutive <td> triplets after a header containing Item
    tables = re.findall(r"<table[^>]*>(.*?)</table>", html or "", re.I | re.S)
    for table in tables:
        if not re.search(r">\s*Item\s*<", table, re.I):
            continue
        trs = re.findall(r"<tr[^>]*>(.*?)</tr>", table, re.I | re.S)
        for tr in trs[1:]:
            cells = re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", tr, re.I | re.S)
            if len(cells) < 2:
                continue
            clean = [_WS_RE.sub(" ", _TAG_RE.sub(" ", c)).strip() for c in cells]
            if not clean[0] or clean[0].lower() == "item":
                continue
            rows.append({
                "item": clean[0],
                "who": clean[1] if len(clean) > 1 else "",
                "where": clean[2] if len(clean) > 2 else "",
            })
        if rows:
            break
    return rows[:20]


def _norm_sky_tag(tag: str) -> str:
    return re.sub(r"\s+", "", (tag or "").strip().lower())


def _split_item_and_sky_tag(raw: str) -> tuple[str, str | None]:
    """Split 'Woven Skull Cap (4-KoS)' → ('Woven Skull Cap', '4-KoS')."""
    s = _WS_RE.sub(" ", (raw or "").strip())
    if not s:
        return "", None
    m = _SKY_REQ_TAG.match(s)
    if m:
        return m.group("item").strip(), m.group("tag").replace(" ", "")
    # Parenthetical that is not an N-Abbr tag — keep full string as item name
    return s, None


def _parse_drops_from_source_blob(blob: str) -> tuple[str, list[str]]:
    """Parse 'Drops From: Plane of Sky: Mob A, Mob B' → zone, mobs."""
    s = _WS_RE.sub(" ", (blob or "").strip())
    if not s:
        return "", []
    s = re.sub(r"^\s*drops?\s+from\s*:\s*", "", s, flags=re.I).strip()
    if ":" in s:
        zone, rest = s.split(":", 1)
        zone = zone.strip()
        mobs = [p.strip() for p in re.split(r"\s*,\s*", rest) if p.strip()]
        return zone, mobs
    return s, []


def _catalog_drop_info(item_name: str) -> dict[str, Any]:
    """Zone + drop mobs from local decoded catalog only (no invention)."""
    name = (item_name or "").strip()
    if not name:
        return {}
    try:
        from . import item_catalog as item_catalog_mod

        it = item_catalog_mod.get_item_by_name(name)
    except Exception:
        it = None
    if not it:
        return {}
    zone = (it.get("zone") or "").strip()
    mobs_raw = (it.get("drops_mobs") or "").strip()
    mobs = [p.strip() for p in re.split(r"\s*,\s*", mobs_raw) if p.strip()] if mobs_raw else []
    if not zone or not mobs:
        src = (it.get("quest_source") or it.get("source") or "").strip()
        if src and is_drop_source(src):
            z2, m2 = _parse_drops_from_source_blob(src)
            zone = zone or z2
            if not mobs and m2:
                mobs = m2
    if not zone and not mobs:
        return {}
    return {"zone": zone, "mobs": mobs, "source": "catalog"}


def _parse_wiki_item_drops(html: str) -> dict[str, Any]:
    """Extract zone + mobs from an eqlwiki item page 'Drops From' section."""
    if not html:
        return {}
    m = re.search(
        r"Drops From(.*?)(?:Sold by|Used in|Retrieved from|Categories|Quest Reward|Reward from)",
        html,
        re.I | re.S,
    )
    if not m:
        return {}
    chunk = m.group(1)
    # Prefer visible link text (natural casing) over title= attributes.
    link_names: list[str] = []
    for title, inner in re.findall(
        r'<a[^>]+title="([^"]+)"[^>]*>(.*?)</a>',
        chunk,
        re.I | re.S,
    ):
        text = _WS_RE.sub(" ", _TAG_RE.sub(" ", inner)).strip()
        name = text or _WS_RE.sub(" ", title).strip()
        if name:
            link_names.append(name)
    if not link_names:
        link_names = [
            _WS_RE.sub(" ", t).strip()
            for t in re.findall(r'<a[^>]+title="([^"]+)"', chunk, re.I)
            if t.strip()
        ]
    zone = ""
    mobs: list[str] = []
    for t in link_names:
        low = t.lower()
        if not zone and (
            low.startswith("plane of ")
            or "plane of" in low
            or low.endswith(" hills")
            or "dungeon" in low
            or low in {
                "nagafen's lair",
                "the hole",
                "kedge keep",
                "old sebilis",
                "velketor's labyrinth",
                "crushbone",
                "guk",
                "lower guk",
                "upper guk",
            }
        ):
            zone = t
            continue
        if zone and t.lower() == zone.lower():
            continue
        if t not in mobs:
            mobs.append(t)
    if not zone and not mobs:
        plain = _WS_RE.sub(" ", _TAG_RE.sub(" ", chunk)).strip()
        if plain and plain.lower() not in {"none", "unknown", "n/a"}:
            # Last resort: whole plain text as zone-ish note — do not invent mobs
            return {"zone": plain, "mobs": [], "source": "eqlwiki-item"}
    if not zone and not mobs:
        return {}
    return {"zone": zone, "mobs": mobs, "source": "eqlwiki-item"}


def _fetch_item_drop_info(item_name: str) -> dict[str, Any]:
    """Best-effort eqlwiki item page drop lookup."""
    name = (item_name or "").strip()
    if not name:
        return {}
    for title in (name.replace(" ", "_"), name):
        url = f"https://eqlwiki.com/{urllib.parse.quote(title)}"
        blob = _http_get(url)
        if not blob:
            continue
        try:
            html = blob.decode("utf-8", errors="ignore")
        except Exception:
            continue
        if "does not exist" in html.lower() and "create the page" in html.lower():
            continue
        info = _parse_wiki_item_drops(html)
        if info:
            info["url"] = url
            return info
    return {}


def _sky_tag_info(tag: str | None) -> dict[str, Any]:
    """Expand a documented Plane of Sky table tag (e.g. 4-KoS)."""
    if not tag:
        return {}
    hit = _SKY_DROP_TAGS.get(_norm_sky_tag(tag))
    if not hit:
        return {}
    return {
        "zone": "Plane of Sky",
        "island": hit.get("island"),
        "island_name": hit.get("island_name") or "",
        "mobs": list(hit.get("mobs") or []),
        "trash": bool(hit.get("trash")),
        "source": "eqlwiki-sky-tag",
        "wiki_tag": tag,
    }


def _merge_drop_info(*parts: dict[str, Any]) -> dict[str, Any]:
    """Merge drop sources; prefer explicit mobs/zone; never invent."""
    out: dict[str, Any] = {
        "zone": "",
        "mobs": [],
        "island": None,
        "island_name": "",
        "trash": False,
        "sources": [],
        "wiki_tag": "",
    }
    for p in parts:
        if not p:
            continue
        if p.get("zone") and not out["zone"]:
            out["zone"] = p["zone"]
        if p.get("mobs") and not out["mobs"]:
            out["mobs"] = list(p["mobs"])
        if p.get("island") and not out["island"]:
            out["island"] = p["island"]
            out["island_name"] = p.get("island_name") or ""
        if p.get("trash"):
            out["trash"] = True
        if p.get("wiki_tag") and not out["wiki_tag"]:
            out["wiki_tag"] = p["wiki_tag"]
        src = p.get("source")
        if src and src not in out["sources"]:
            out["sources"].append(src)
    return out


def _where_label(info: dict[str, Any]) -> str:
    zone = (info.get("zone") or "").strip() or "zone unknown"
    island = info.get("island")
    island_name = (info.get("island_name") or "").strip()
    if island:
        label = f"{zone} Island {island}"
        if island_name:
            label += f" ({island_name})"
        return label
    return zone


def _format_collect_step(item_name: str, info: dict[str, Any]) -> str:
    """Human-readable collect step with zone + mobs, or an explicit unknown."""
    item = (item_name or "").strip() or "required item"
    where = _where_label(info)
    mobs = [m for m in (info.get("mobs") or []) if m]
    tag = (info.get("wiki_tag") or "").strip()
    if mobs:
        return f"Collect {item} — {where}; drops from {', '.join(mobs)}."
    if info.get("trash"):
        msg = (
            f"Collect {item} — {where}; Island trash drop "
            "(specific mob unknown in available data)."
        )
        if tag:
            msg = msg[:-1] + f"; wiki tag {tag}."
        return msg
    if (info.get("zone") or info.get("island")) and not mobs:
        msg = f"Collect {item} — {where}; specific drop mob unknown in available data."
        if tag:
            msg = msg[:-1] + f"; wiki tag {tag}."
        return msg
    if tag:
        return (
            f"Collect {item} — drop source unknown in available data "
            f"(wiki tag {tag}; not in documented sky-tag map)."
        )
    return f"Collect {item} — drop source unknown in available data."


def resolve_component_drop(
    raw: str,
    *,
    fetch: bool = False,
    default_zone: str = "",
) -> dict[str, Any]:
    """Resolve a required/rune item string to zone + mobs from real data only."""
    item, tag = _split_item_and_sky_tag(raw)
    cat = _catalog_drop_info(item)
    wiki = _fetch_item_drop_info(item) if fetch else {}
    sky = _sky_tag_info(tag)
    # Prefer catalog/wiki mobs over tag abbreviations; tag still supplies island.
    info = _merge_drop_info(cat, wiki, sky)
    if not info.get("zone") and default_zone:
        info["zone"] = default_zone
    if tag and not info.get("wiki_tag"):
        info["wiki_tag"] = tag
    who = ", ".join(info.get("mobs") or [])
    if not who:
        if info.get("trash"):
            who = "Island trash (specific mob unknown in available data)"
        elif info.get("zone"):
            who = "drop mob unknown in available data"
        else:
            who = "drop source unknown in available data"
        if tag and "wiki tag" not in who.lower():
            who = f"{who} (wiki tag {tag})"
    return {
        "item": item,
        "raw": raw,
        "who": who,
        "where": _where_label(info) if (info.get("zone") or info.get("island")) else (
            f"location unknown (wiki tag {tag})" if tag else "location unknown"
        ),
        "zone": info.get("zone") or "",
        "mobs": list(info.get("mobs") or []),
        "island": info.get("island"),
        "island_name": info.get("island_name") or "",
        "wiki_tag": tag or "",
        "drop_known": bool(info.get("mobs")),
        "sources": list(info.get("sources") or []),
        "collect_step": _format_collect_step(item, info),
    }


def _enrich_component_rows(
    rows: list[dict[str, Any]],
    *,
    fetch: bool = False,
) -> list[dict[str, Any]]:
    """Fill vague who/where on generic wiki component tables when possible."""
    out: list[dict[str, Any]] = []
    for row in rows or []:
        item = (row.get("item") or "").strip()
        who = (row.get("who") or "").strip()
        where = (row.get("where") or "").strip()
        vague_who = (not who) or who.lower() in {
            "see wiki", "unknown", "?", "n/a", "npc", "mob", "mobs", "random drop",
        }
        vague_where = (not where) or where.lower() in {"see wiki", "unknown", "?", "n/a"}
        expanded = _expand_island_where(where)
        if item and (vague_who or vague_where):
            resolved = resolve_component_drop(
                item,
                fetch=fetch,
                default_zone=expanded.get("zone") or where or "Plane of Sky",
            )
            out.append({
                **row,
                "item": resolved["item"],
                "who": resolved["who"] if vague_who else who,
                "where": resolved["where"] if vague_where else (expanded.get("where") or where),
                "mobs": resolved.get("mobs") or (
                    [] if vague_who else ([who] if who and not vague_who else [])
                ),
                "drop_known": resolved.get("drop_known") or (not vague_who),
                "wiki_tag": resolved.get("wiki_tag") or "",
                "island": expanded.get("island") or resolved.get("island"),
                "island_name": expanded.get("island_name") or resolved.get("island_name") or "",
            })
        else:
            mobs = []
            if who and not vague_who and "trash" not in who.lower():
                mobs = [who]
            where_label = expanded.get("where") or where
            out.append({
                **row,
                "item": item,
                "who": who,
                "where": where_label,
                "mobs": mobs,
                "drop_known": bool(mobs),
                "island": expanded.get("island"),
                "island_name": expanded.get("island_name") or "",
            })
    return out


def _prerequisites_from_html(html: str, quest_name: str) -> list[dict[str, Any]]:
    """Named prerequisite quests explicitly listed on eqlwiki (never invented)."""
    if not html:
        return []
    section = _extract_quest_section(html, quest_name) if quest_name else html
    scan = _TAG_RE.sub(" ", section or html)
    scan = _WS_RE.sub(" ", scan)
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    qkey = (quest_name or "").strip().lower()
    for m in _PREREQ_LINE.finditer(scan):
        rest = m.group(1).strip()
        parts = re.split(r"\s*(?:,|;|\||/| and )\s*", rest)
        for part in parts[:8]:
            name = part.strip(" .")
            name = re.split(r"\.\s+|!\s+|\?\s+", name)[0].strip()
            if len(name) < 4 or len(name) > 90:
                continue
            if name.lower().startswith("http"):
                continue
            key = name.lower()
            if key in seen or key == qkey:
                continue
            seen.add(key)
            out.append({"name": name, "kind": "quest", "source": "eqlwiki"})
    return out


def _sky_island_from_payload(components: list[dict[str, Any]], steps: list[str]) -> int | None:
    for c in components or []:
        tag = (c.get("wiki_tag") or "").strip().lower().replace(" ", "")
        if re.match(r"^\d+-", tag):
            try:
                return int(tag.split("-", 1)[0])
            except ValueError:
                pass
        where = c.get("where") or ""
        m = re.search(r"Island\s+(\d+)", where, re.I)
        if m:
            try:
                return int(m.group(1))
            except ValueError:
                pass
    for step in steps or []:
        m = re.search(r"Island\s+(\d+)", str(step), re.I)
        if m:
            try:
                return int(m.group(1))
            except ValueError:
                pass
    return None


def _sky_access_prerequisites(island: int) -> list[dict[str, Any]]:
    """Documented Plane of Sky island progression (eqlwiki Plane of Sky)."""
    out = [{
        "name": "Enter Plane of Sky (Island 1) — buy Efreeti's Key from the Key Master",
        "kind": "access",
        "source": "eqlwiki Plane of Sky",
        "island": 1,
    }]
    if island and island >= 2:
        out.append({
            "name": (
                f"Progress Plane of Sky access through Island {island - 1} "
                "(keys / teleports per eqlwiki Plane of Sky)"
            ),
            "kind": "access",
            "source": "eqlwiki Plane of Sky",
            "island": island - 1,
        })
    return out


def _attach_prerequisites(
    guide: dict[str, Any],
    *,
    html: str | None = None,
) -> dict[str, Any]:
    g = dict(guide or {})
    quest = (g.get("quest") or "").strip()
    prereqs = list(g.get("prerequisites") or [])
    if html:
        for p in _prerequisites_from_html(html, quest):
            if not any((x.get("name") or "").lower() == (p.get("name") or "").lower() for x in prereqs):
                prereqs.append(p)
    island = _sky_island_from_payload(g.get("components") or [], g.get("steps") or [])
    blob = " ".join(
        str(x) for x in (
            g.get("url") or "",
            g.get("source") or "",
            g.get("note") or "",
            *(g.get("steps") or [])[:3],
        )
    ).lower()
    if island is not None or "plane of sky" in blob or "sky" in (quest or "").lower():
        if island is None:
            island = 1
        for a in _sky_access_prerequisites(island):
            if not any((x.get("name") or "").lower() == (a.get("name") or "").lower() for x in prereqs):
                prereqs.append(a)
    g["prerequisites"] = prereqs
    g["prerequisites_note"] = (
        ""
        if prereqs
        else "No prerequisite quests listed in available eqlwiki/source text for this quest."
    )
    return g


def cache_path(quest_name: str) -> Path:
    try:
        GUIDES_DIR.mkdir(parents=True, exist_ok=True)
    except OSError:
        pass
    return GUIDES_DIR / f"{_slug(quest_name)}.json"


def load_cached_guide(quest_name: str) -> dict[str, Any] | None:
    try:
        path = cache_path(quest_name)
        if not path.is_file():
            return None
        data = json.loads(path.read_text(encoding="utf-8"))
        # Stale schema (pre zone/mob collect wording) — force refresh
        if int(data.get("format_version") or 0) != GUIDE_FORMAT_VERSION:
            return None
        return data
    except Exception:
        return None


def _write_cached_guide(quest_name: str, guide: dict[str, Any]) -> None:
    """Best-effort cache write — never raise (path length / permissions / disk)."""
    try:
        payload = {**guide, "format_version": GUIDE_FORMAT_VERSION}
        cache_path(quest_name).write_text(json.dumps(payload, indent=2), encoding="utf-8")
    except Exception:
        pass


def _parse_sky_quest_row(
    html: str,
    quest_name: str,
    *,
    fetch: bool = False,
) -> dict[str, Any] | None:
    """Parse EQL Plane of Sky class-test table row for quest_name."""
    if not html or not quest_name:
        return None
    # Row cells after reward item cell: Quest | Keyword | Wind Rune(s) | Required item(s)
    # Match the quest title cell then following tds
    pat = re.compile(
        rf"<td>\s*{re.escape(quest_name)}\s*</td>\s*"
        rf"<td>(.*?)</td>\s*"
        rf"<td>(.*?)</td>\s*"
        rf"<td>(.*?)</td>",
        re.I | re.S,
    )
    m = pat.search(html or "")
    if not m:
        return None
    keyword = _WS_RE.sub(" ", _TAG_RE.sub(" ", m.group(1))).strip()
    runes = [
        _WS_RE.sub(" ", _TAG_RE.sub(" ", x)).strip()
        for x in re.findall(r"<li[^>]*>(.*?)</li>", m.group(2), re.I | re.S)
    ]
    reqs = [
        _WS_RE.sub(" ", _TAG_RE.sub(" ", x)).strip()
        for x in re.findall(r"<li[^>]*>(.*?)</li>", m.group(3), re.I | re.S)
    ]
    runes = [r for r in runes if r]
    reqs = [r for r in reqs if r]
    steps = [
        "Enter Plane of Sky Island 1; buy Efreeti's Key from the Key Master (saved to keyring once).",
        "Use the north teleport pad (~1600, 520) into the Efreeti Chamber (quest NPCs + banker).",
        f"Hail the class Efreeti quest NPC and use the keyword '{keyword}' to confirm turn-ins."
        if keyword else "Hail the class Efreeti quest NPC to confirm turn-ins.",
    ]
    components: list[dict[str, Any]] = []
    for raw in runes:
        resolved = resolve_component_drop(raw, fetch=fetch, default_zone="Plane of Sky")
        steps.append(resolved["collect_step"])
        components.append({
            "item": resolved["item"],
            "who": resolved["who"],
            "where": resolved["where"],
            "mobs": resolved.get("mobs") or [],
            "wiki_tag": resolved.get("wiki_tag") or "",
            "drop_known": resolved.get("drop_known"),
            "kind": "wind_rune",
        })
    for raw in reqs:
        resolved = resolve_component_drop(raw, fetch=fetch, default_zone="Plane of Sky")
        steps.append(resolved["collect_step"])
        components.append({
            "item": resolved["item"],
            "who": resolved["who"],
            "where": resolved["where"],
            "mobs": resolved.get("mobs") or [],
            "wiki_tag": resolved.get("wiki_tag") or "",
            "drop_known": resolved.get("drop_known"),
            "kind": "required",
        })
    steps.append(f"Hand the required items to the quest NPC to receive the {quest_name} reward.")
    return {
        "keyword": keyword,
        "steps": steps,
        "components": components,
    }


def ensure_quest_guide(quest_name: str, *, fetch: bool = True) -> dict[str, Any]:
    """Return quest guide payload; optionally fetch/cache from eqlwiki.

    Never raises — missing wiki / cache / OS errors degrade to empty steps.
    """
    name = (quest_name or "").strip()
    if not name:
        return {"quest": "", "steps": [], "components": [], "url": None, "error": "empty quest"}
    try:
        cached = load_cached_guide(name)
        # Ignore stub caches that only stored the quest title line
        if cached and not _is_stub_guide(cached):
            if "prerequisites" not in cached:
                return _attach_prerequisites(cached, html=None)
            return cached

        urls = wiki_urls_for_quest(name)
        if not fetch:
            return {
                "quest": name,
                "steps": [],
                "components": [],
                "url": urls[0] if urls else None,
                "cached": False,
                "error": "not fetched",
                "format_version": GUIDE_FORMAT_VERSION,
            }

        last_err = "no wiki page found"
        for url in urls:
            blob = _http_get(url)
            if not blob:
                last_err = f"failed fetch {url}"
                continue
            try:
                html = blob.decode("utf-8", errors="ignore")
            except Exception:
                continue
            if "does not exist" in html.lower() and "create the page" in html.lower():
                last_err = f"missing page {url}"
                continue

            sky = _parse_sky_quest_row(html, name, fetch=fetch)
            if sky and sky.get("steps"):
                guide = {
                    "quest": name,
                    "steps": sky["steps"],
                    "components": sky.get("components") or [],
                    "keyword": sky.get("keyword") or "",
                    "url": url,
                    "cached": True,
                    "fetched": True,
                    "source": url,
                    "note": (
                        "Steps from eqlwiki Plane of Sky class-test table "
                        "(EQL simplified turn-ins). Collect steps use catalog/"
                        "eqlwiki item drops and documented sky island tags only."
                    ),
                    "format_version": GUIDE_FORMAT_VERSION,
                }
                guide = _attach_prerequisites(guide, html=html)
                _write_cached_guide(name, guide)
                return guide

            # Prefer Checklist + Walkthrough sections (real quest pages).
            steps = _steps_from_wiki_sections(html, name)
            section = _extract_quest_section(html, name)
            components = _enrich_component_rows(
                _parse_component_rows(section) or _parse_component_rows(html),
                fetch=fetch,
            )
            # Also pull Obtain … links from checklist as components when table missing.
            checklist = _extract_mw_section(html, "Checklist")
            if checklist:
                for m in re.finditer(
                    r"Obtain\s+(?:a|an|the)?\s*<a[^>]+title=\"([^\"]+)\"",
                    checklist,
                    re.I,
                ):
                    item = (m.group(1) or "").strip()
                    if not item:
                        continue
                    if not any((c.get("item") or "").lower() == item.lower() for c in components):
                        components.append({"item": item, "who": "", "where": ""})
                components = _enrich_component_rows(components, fetch=fetch)

            # Dialogue often says "bring me X and Y" without zone/mobs — expand those.
            steps, dialogue_comps = _append_collect_steps_from_dialogue(
                steps,
                fetch=fetch,
                default_zone="Plane of Sky" if "sky" in (name + _html_to_text(html)).lower() else "",
            )
            if dialogue_comps:
                have = {(c.get("item") or "").strip().lower() for c in components}
                for c in dialogue_comps:
                    key = (c.get("item") or "").strip().lower()
                    if key and key not in have:
                        components.append(c)
                        have.add(key)
            if components:
                steps = _prefer_clear_steps(steps, components)

            # Last-resort prose scrape if structured sections were empty.
            if _is_stub_guide({"steps": steps, "components": components}):
                text = _html_to_text(section if section else html)
                prose = _steps_from_text(text, name)
                for line in prose:
                    if line not in steps:
                        steps.append(line)

            if _is_stub_guide({"steps": steps, "components": components}):
                last_err = f"no steps parsed from {url}"
                if name.lower().replace(" ", "_") in url.lower():
                    guide = {
                        "quest": name,
                        "steps": [f"See walkthrough on eqlwiki (steps could not be parsed automatically): {url}"],
                        "components": components,
                        "url": url,
                        "cached": True,
                        "fetched": True,
                        "source": url,
                        "format_version": GUIDE_FORMAT_VERSION,
                    }
                    guide = _attach_prerequisites(guide, html=html)
                    _write_cached_guide(name, guide)
                    return guide
                continue
            guide = {
                "quest": name,
                "steps": steps,
                "components": components,
                "url": url,
                "cached": True,
                "fetched": True,
                "source": url,
                "note": (
                    "Steps from eqlwiki Checklist/Walkthrough when present "
                    "(plus dialogue collect hints). Zone/mobs from catalog or "
                    "item wiki drops only — never invented."
                ),
                "format_version": GUIDE_FORMAT_VERSION,
            }
            guide = _attach_prerequisites(guide, html=html)
            _write_cached_guide(name, guide)
            return guide

        guide = {
            "quest": name,
            "steps": [],
            "components": [],
            "url": urls[0] if urls else None,
            "cached": False,
            "fetched": False,
            "error": last_err,
            "note": "Quest name known from item DB; steps not available locally. Open wiki URL if present.",
            "format_version": GUIDE_FORMAT_VERSION,
        }
        guide = _attach_prerequisites(guide, html=None)
        _write_cached_guide(name, guide)
        return guide
    except Exception as e:
        return {
            "quest": name,
            "steps": [],
            "components": [],
            "url": None,
            "cached": False,
            "fetched": False,
            "error": f"quest guide unavailable: {e}",
            "note": "Quest wiki/cache unavailable; no invented steps.",
            "format_version": GUIDE_FORMAT_VERSION,
            "prerequisites": [],
            "prerequisites_note": "Quest wiki/cache unavailable; prerequisites unknown.",
        }


def obtain_path_for_item(item: dict[str, Any] | None, *, fetch_quest: bool = True) -> dict[str, Any]:
    """Build obtain path from item catalog fields (+ optional quest guide)."""
    it = item or {}
    zone = (it.get("zone") or "").strip()
    drops = (it.get("drops_mobs") or "").strip()
    quest_source = (it.get("quest_source") or it.get("source") or "").strip()
    qname = quest_name_from_source(quest_source)
    if not qname and quest_source and not is_drop_source(quest_source):
        # Bare title only when short enough to be a real quest name
        if len(quest_source) <= 160:
            qname = quest_source

    how = "unknown"
    if drops or (quest_source and is_drop_source(quest_source)):
        how = "drop"
        # Prefer mob list from Zone: mob; Zone: mob source when drops_mobs empty
        if not drops and quest_source and is_drop_source(quest_source) and not _DROP_PREFIX.match(quest_source):
            drops = quest_source
            if not zone and ":" in quest_source:
                zone = quest_source.split(":", 1)[0].strip()
    elif qname:
        how = "quest"
    elif zone:
        how = "zone"

    guide = None
    if qname:
        try:
            guide = ensure_quest_guide(qname, fetch=fetch_quest)
        except Exception:
            guide = {
                "quest": qname,
                "steps": [],
                "components": [],
                "url": None,
                "error": "quest guide unavailable",
            }
    return {
        "how": how,
        "zone": zone,
        "drops_mobs": drops,
        "quest_source": quest_source,
        "quest_name": qname,
        "quest_guide": guide,
        "item_url": it.get("url") or "",
    }
