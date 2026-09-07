"""Quest obtain guides from catalog + eqlwiki (never invent steps).

Decoded items expose quest_source / rewardFromQuests as names only.
When a real quest name is present (not a "Drops From:" blob), we best-effort
fetch the eqlwiki page, extract dialogue/handoff steps + component tables,
and cache under data/quest-guides/. If fetch fails, return the quest name +
wiki URL only — never fabricate steps.
"""
from __future__ import annotations

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

_DROP_PREFIX = re.compile(r"^\s*drops?\s+from\s*:", re.I)
_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")


def _slug(name: str) -> str:
    s = (name or "").strip().lower()
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return s or "quest"


def is_drop_source(quest_source: str | None) -> bool:
    """True when quest_source is actually a drop line, not a quest name."""
    s = (quest_source or "").strip()
    if not s:
        return False
    return bool(_DROP_PREFIX.match(s)) or s.lower().startswith("craft") or s.lower().startswith("bought")


def quest_name_from_source(quest_source: str | None) -> str | None:
    """Extract a quest title from quest_source / source strings."""
    s = (quest_source or "").strip()
    if not s or is_drop_source(s):
        return None
    # "Reward from Plane of Sky Quest: Wizard Test of Focus"
    m = re.search(r"quest:\s*(.+)$", s, re.I)
    if m:
        return m.group(1).strip()
    m = re.search(r"reward from(?:\s+[\w\s]+)?\s+quest:\s*(.+)$", s, re.I)
    if m:
        return m.group(1).strip()
    # Bare quest title
    if "drops from" in s.lower():
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


def _steps_from_text(text: str, quest_name: str) -> list[str]:
    """Heuristic step list from wiki prose — only keeps lines that look instructional."""
    steps: list[str] = []
    if not text:
        return steps
    # Split on say / hand / bring / return cues
    chunks = re.split(r"(?<=[.!?])\s+|(?=You say,)|(?=Hand )|(?=Bring )|(?=Return )|(?=Travel )", text)
    for chunk in chunks:
        line = _WS_RE.sub(" ", (chunk or "").strip())
        if len(line) < 25 or len(line) > 400:
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
            )
        ):
            if line not in steps:
                steps.append(line)
        if len(steps) >= 12:
            break
    # Item table lines: "Iron Disc an azarack Island 2"
    if quest_name and quest_name.lower() not in " ".join(steps).lower():
        steps.insert(0, f"Quest: {quest_name}")
    return steps


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


def cache_path(quest_name: str) -> Path:
    GUIDES_DIR.mkdir(parents=True, exist_ok=True)
    return GUIDES_DIR / f"{_slug(quest_name)}.json"


def load_cached_guide(quest_name: str) -> dict[str, Any] | None:
    path = cache_path(quest_name)
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _parse_sky_quest_row(html: str, quest_name: str) -> dict[str, Any] | None:
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
    if runes:
        steps.append("Collect wind rune(s): " + ", ".join(runes) + " (drop from Plane of Sky mobs).")
    if reqs:
        steps.append("Collect required item(s): " + ", ".join(reqs) + ".")
    steps.append(f"Hand the required items to the quest NPC to receive the {quest_name} reward.")
    components = []
    for r in runes:
        components.append({"item": r, "who": "Plane of Sky trash / mobs", "where": "Plane of Sky"})
    for r in reqs:
        # e.g. "Woven Skull Cap (4-KoS)"
        who_where = ""
        if "(" in r and ")" in r:
            who_where = r[r.find("(") + 1:r.rfind(")")]
        components.append({
            "item": r.split("(")[0].strip(),
            "who": who_where or "see wiki",
            "where": "Plane of Sky",
        })
    return {
        "keyword": keyword,
        "steps": steps,
        "components": components,
    }


def ensure_quest_guide(quest_name: str, *, fetch: bool = True) -> dict[str, Any]:
    """Return quest guide payload; optionally fetch/cache from eqlwiki."""
    name = (quest_name or "").strip()
    if not name:
        return {"quest": "", "steps": [], "components": [], "url": None, "error": "empty quest"}
    cached = load_cached_guide(name)
    # Ignore stub caches that only stored the quest title line
    if cached and (cached.get("components") or len(cached.get("steps") or []) > 1):
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

        sky = _parse_sky_quest_row(html, name)
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
                "note": "Steps from eqlwiki Plane of Sky class-test table (EQL simplified turn-ins).",
            }
            cache_path(name).write_text(json.dumps(guide, indent=2), encoding="utf-8")
            return guide

        section = _extract_quest_section(html, name)
        text = _html_to_text(section)
        steps = _steps_from_text(text, name)
        components = _parse_component_rows(section)
        if not steps and not components:
            last_err = f"no steps parsed from {url}"
            if name.lower().replace(" ", "_") in url.lower():
                guide = {
                    "quest": name,
                    "steps": [f"See walkthrough: {url}"],
                    "components": [],
                    "url": url,
                    "cached": True,
                    "fetched": True,
                    "source": url,
                }
                cache_path(name).write_text(json.dumps(guide, indent=2), encoding="utf-8")
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
            "note": "Steps extracted from eqlwiki; verify in-game. Never invented.",
        }
        cache_path(name).write_text(json.dumps(guide, indent=2), encoding="utf-8")
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
    }
    try:
        cache_path(name).write_text(json.dumps(guide, indent=2), encoding="utf-8")
    except Exception:
        pass
    return guide


def obtain_path_for_item(item: dict[str, Any] | None, *, fetch_quest: bool = True) -> dict[str, Any]:
    """Build obtain path from item catalog fields (+ optional quest guide)."""
    it = item or {}
    zone = (it.get("zone") or "").strip()
    drops = (it.get("drops_mobs") or "").strip()
    quest_source = (it.get("quest_source") or it.get("source") or "").strip()
    qname = quest_name_from_source(quest_source)
    if not qname and quest_source and not is_drop_source(quest_source):
        qname = quest_source

    how = "unknown"
    if drops or (quest_source and is_drop_source(quest_source)):
        how = "drop"
    elif qname:
        how = "quest"
    elif zone:
        how = "zone"

    guide = ensure_quest_guide(qname, fetch=fetch_quest) if qname else None
    return {
        "how": how,
        "zone": zone,
        "drops_mobs": drops,
        "quest_source": quest_source,
        "quest_name": qname,
        "quest_guide": guide,
        "item_url": it.get("url") or "",
    }
