"""Resolve Item Search quest labels to Quest Hub entries.

Quest names, Plane of Sky class tests, and eqlwiki Category:Quests titles are
loaded from data files transcribed from eqlwiki (CC BY-SA). Nothing in those
files is invented: names, givers, trigger phrases, runes, items, and rewards
are copied from the wiki.

Item Search used to read the wiki link ``title`` attribute (the target page,
e.g. "Plane of Sky") instead of the visible quest name ("Wizard Test of Focus"),
and it treated nested component links as quests. Resolution uses the visible
label, then the target page, then sourced aliases.
"""
from __future__ import annotations

import json
import re
import unicodedata
import urllib.parse
from functools import lru_cache
from html import unescape
from pathlib import Path
from typing import Any

from .paths import APP_ROOT

# Shipped next to other app data. Packaging must copy these into resources/data.
PACKAGED_DATA_FILES = (
    "pos_class_tests.json",
    "eqlwiki_quest_names.json",
    "eqlwiki_item_related_quests.json",
)

EQLWIKI_ATTRIBUTION = (
    "EverQuest Legends Wiki (eqlwiki.com) under CC BY-SA. "
    "https://eqlwiki.com/Plane_of_Sky and https://eqlwiki.com/Category:Quests."
)

_LINK_RE = re.compile(
    r"\[\[([^\]|#]+)(?:#([^\]|]+))?\|([^\]]+)\]\]|\[\[([^\]|#]+)(?:#([^\]|]+))?\]\]"
)
_PAREN_RE = re.compile(r"\s*\([^)]*\)")
_TRAILING_QUEST_RE = re.compile(r"\s+quests?$", re.I)
_LEADING_THE_RE = re.compile(r"^the\s+(.+)$", re.I)


def quest_name_key(name: str) -> str:
    """Match key for quest titles. Underscores are wiki spaces."""
    s = unicodedata.normalize("NFKC", name or "")
    s = s.replace("\xa0", " ").replace("\u200b", "").replace("_", " ")
    s = s.strip().lower()
    for ch in ("’", "‘", "`", "ʼ", "´"):
        s = s.replace(ch, "'")
    s = re.sub(r"\s+", " ", s)
    return s


def item_name_key(name: str) -> str:
    """Same folding as item_catalog._name_key (does not rewrite underscores)."""
    s = unicodedata.normalize("NFKC", name or "")
    s = s.replace("\xa0", " ").replace("\u200b", "").strip().lower()
    for ch in ("’", "‘", "`", "ʼ", "´"):
        s = s.replace(ch, "'")
    s = re.sub(r"\s+", " ", s)
    return s


def lookup_keys(name: str) -> list[str]:
    """Keys to try.

    Shadow Knight / Shadowknight and Froglok / Frogloc are spellings that
    already appear on eqlwiki and in the decoded catalog for the same titles.
    """
    key = quest_name_key(name)
    if not key:
        return []
    keys = [key]
    if "shadowknight" in key:
        keys.append(key.replace("shadowknight", "shadow knight"))
    if "shadow knight" in key:
        keys.append(key.replace("shadow knight", "shadowknight"))
    if "frogloc" in key:
        keys.append(key.replace("frogloc", "froglok"))
    if "froglok" in key:
        keys.append(key.replace("froglok", "frogloc"))
    out: list[str] = []
    seen: set[str] = set()
    for k in keys:
        if k and k not in seen:
            seen.add(k)
            out.append(k)
    return out


def data_path(name: str) -> Path | None:
    """Locate a shipped JSON file in dev, Electron resources, or a frozen bundle."""
    here = Path(__file__).resolve()
    roots = [
        here.parents[2],
        APP_ROOT,
        here.parents[2] / "desktop" / "resources",
        APP_ROOT / "desktop" / "resources",
        APP_ROOT / "resources",
    ]
    seen: set[str] = set()
    for root in roots:
        try:
            key = str(root.resolve())
        except Exception:
            key = str(root)
        if key in seen:
            continue
        seen.add(key)
        cand = root / "data" / name
        if cand.is_file():
            return cand
    return None


def _load_json(name: str) -> dict[str, Any]:
    path = data_path(name)
    if path is None:
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


@lru_cache(maxsize=1)
def pos_tests() -> tuple[dict[str, Any], ...]:
    data = _load_json("pos_class_tests.json")
    rows = data.get("tests") if isinstance(data, dict) else None
    if not isinstance(rows, list):
        return ()
    out = [r for r in rows if isinstance(r, dict) and (r.get("quest") or "").strip()]
    return tuple(out)


@lru_cache(maxsize=1)
def eqlwiki_quest_records() -> tuple[dict[str, Any], ...]:
    data = _load_json("eqlwiki_quest_names.json")
    rows = data.get("quests") if isinstance(data, dict) else None
    if not isinstance(rows, list):
        return ()
    out = [r for r in rows if isinstance(r, dict) and (r.get("name") or "").strip()]
    return tuple(out)


def _wiki_page_url(page: str, section: str = "") -> str:
    title = (page or "").strip().replace(" ", "_")
    if not title:
        return "https://eqlwiki.com/Plane_of_Sky"
    url = f"https://eqlwiki.com/{urllib.parse.quote(title)}"
    if section:
        url += "#" + urllib.parse.quote(section.replace(" ", "_"))
    return url


def apply_sourced_quests(by_key: dict[str, dict[str, Any]], name_key) -> None:
    """Merge Plane of Sky tests and eqlwiki quest titles into the hub index.

    ``name_key`` is quest_hub._name_key (the dict's existing key function).
    Catalog spellings stay reachable as aliases. The displayed name for a
    Plane of Sky test is the wiki table name so the guide parser can find
    that row on https://eqlwiki.com/Plane_of_Sky.
    """
    def find_row(*names: str) -> dict[str, Any] | None:
        wanted = {quest_name_key(n) for n in names if n and quest_name_key(n)}
        if not wanted:
            return None
        for row in by_key.values():
            if quest_name_key(row.get("name") or "") in wanted:
                return row
            for alias in row.get("aliases") or []:
                if quest_name_key(alias) in wanted:
                    return row
        return None

    def add_alias(row: dict[str, Any], alias: str) -> None:
        alias = (alias or "").strip()
        if not alias:
            return
        if quest_name_key(alias) == quest_name_key(row.get("name") or ""):
            return
        aliases = row.setdefault("aliases", [])
        if not any(quest_name_key(a) == quest_name_key(alias) for a in aliases):
            aliases.append(alias)

    def add_reward(row: dict[str, Any], item: str) -> None:
        item = (item or "").strip()
        if not item:
            return
        rewards = row.setdefault("reward_items", [])
        if item not in rewards:
            rewards.append(item)
        row["item_count"] = len(rewards)
        samples = row.setdefault("sample_items", [])
        if item not in samples and len(samples) < 8:
            samples.append(item)

    for test in pos_tests():
        wiki_name = (test.get("quest") or "").strip()
        if not wiki_name:
            continue
        aliases = [a for a in (test.get("aliases") or []) if isinstance(a, str)]
        row = find_row(wiki_name, *aliases)
        if row is None:
            row = {
                "name": wiki_name,
                "item_count": 0,
                "sample_items": [],
                "reward_items": [],
                "aliases": [],
            }
            by_key[name_key(wiki_name)] = row
        else:
            old = (row.get("name") or "").strip()
            if old and quest_name_key(old) != quest_name_key(wiki_name):
                add_alias(row, old)
                row["name"] = wiki_name
        for alias in aliases:
            add_alias(row, alias)
        add_reward(row, test.get("reward") or "")
        row["source"] = "eqlwiki Plane of Sky"
        row["license"] = "CC BY-SA"
        row["url"] = "https://eqlwiki.com/Plane_of_Sky"
        section = (test.get("section") or "").strip()
        if section:
            row["url"] = _wiki_page_url("Plane of Sky", section)

    for rec in eqlwiki_quest_records():
        name = (rec.get("name") or "").strip()
        if not name or find_row(name):
            continue
        url = (rec.get("url") or "").strip() or _wiki_page_url(name)
        by_key[name_key(name)] = {
            "name": name,
            "item_count": 0,
            "sample_items": [],
            "reward_items": [],
            "aliases": [],
            "source": (rec.get("source") or "eqlwiki Category:Quests"),
            "license": "CC BY-SA",
            "url": url,
        }


@lru_cache(maxsize=1)
def _resolution_index() -> dict[str, str]:
    from .quest_hub import list_quests

    index: dict[str, str] = {}
    derived: dict[str, set[str]] = {}
    for row in list_quests():
        canon = (row.get("name") or "").strip()
        if not canon:
            continue
        labels = [canon, *(row.get("aliases") or [])]
        for label in labels:
            text = str(label)
            for key in lookup_keys(text):
                index.setdefault(key, canon)
            for extra in (_paren_stripped(text), _paren_unwrapped(text), _namespace_stripped(text)):
                if not extra:
                    continue
                for key in lookup_keys(extra):
                    if key in index and index[key] == canon:
                        continue
                    if key in index and index[key] != canon:
                        derived.setdefault(key, set()).add(canon)
                        derived[key].add(index[key])
                        continue
                    derived.setdefault(key, set()).add(canon)
    for key, canons in derived.items():
        if key in index or len(canons) != 1:
            continue
        index[key] = next(iter(canons))
    return index


def clear_resolution_cache() -> None:
    _resolution_index.cache_clear()
    pos_quests_for_item.cache_clear()
    _pos_by_item.cache_clear()
    _related_by_item.cache_clear()


def clear_data_caches() -> None:
    """Drop loaded JSON and the hub index. Used after the data files are rewritten."""
    pos_tests.cache_clear()
    eqlwiki_quest_records.cache_clear()
    clear_resolution_cache()


def _collapse_ws(value: str) -> str:
    return re.sub(r"\s+", " ", (value or "")).strip()


def _paren_stripped(value: str) -> str:
    return _collapse_ws(_PAREN_RE.sub("", value or ""))


def _paren_unwrapped(value: str) -> str:
    """``Bone Chips (Kaladim)`` → ``Bone Chips Kaladim`` (keep the text inside)."""
    return _collapse_ws(re.sub(r"[()]", " ", value or ""))


def _namespace_stripped(value: str) -> str:
    """MediaWiki ``Quest:Druid Spells`` → ``Druid Spells``."""
    raw = _collapse_ws(value)
    if raw.lower().startswith("quest:"):
        return _collapse_ws(raw.split(":", 1)[1])
    return ""


def _strict_variants(raw: str) -> list[str]:
    """Spellings that are the same title: case, underscores, parentheses, trailing Quest(s)."""
    raw = _collapse_ws(raw)
    if not raw:
        return []
    variants = [raw]
    stripped = _paren_stripped(raw)
    if stripped and quest_name_key(stripped) != quest_name_key(raw):
        variants.append(stripped)
    if "(" in raw:
        before = _collapse_ws(raw.split("(", 1)[0])
        if before and quest_name_key(before) != quest_name_key(raw):
            variants.append(before)
    base = _collapse_ws(_TRAILING_QUEST_RE.sub("", raw))
    if base and quest_name_key(base) != quest_name_key(raw):
        variants.append(base)
        base_stripped = _paren_stripped(base)
        if base_stripped and quest_name_key(base_stripped) not in {quest_name_key(v) for v in variants}:
            variants.append(base_stripped)
    out: list[str] = []
    seen: set[str] = set()
    for variant in variants:
        key = quest_name_key(variant)
        if key and key not in seen:
            seen.add(key)
            out.append(variant)
    return out


def _index_hit(index: dict[str, str], raw: str) -> str | None:
    for variant in _strict_variants(raw):
        for key in lookup_keys(variant):
            hit = index.get(key)
            if hit:
                return hit
            folded = _paren_stripped(key)
            if folded and folded != key:
                hit = index.get(folded)
                if hit:
                    return hit
    return None


def _loose_hit(index: dict[str, str], raw: str) -> str | None:
    """Map a short label onto an existing hub title. Never creates a quest name.

    Tries ``Name Quest`` before dropping a leading ``the``, and returns the
    first existing title. ``The Harvester`` → ``Harvester Quest``.
    """
    bases = _strict_variants(raw)
    if not bases:
        return None
    trials: list[str] = []
    for base in bases:
        trials.append(f"{base} Quest")
        lead = _LEADING_THE_RE.match(base)
        if lead:
            rest = _collapse_ws(lead.group(1))
            if rest:
                trials.append(f"{rest} Quest")
                trials.append(rest)
    seen: set[str] = set()
    for trial in trials:
        key = quest_name_key(trial)
        if not key or key in seen:
            continue
        seen.add(key)
        hit = _index_hit(index, trial)
        if hit:
            return hit
    return None


def resolve_quest_label(name: str, *, loose: bool = True) -> str | None:
    """Return the Quest Hub display name for a wiki/catalog label, if any."""
    raw = (name or "").strip()
    if not raw:
        return None
    index = _resolution_index()
    hit = _index_hit(index, raw)
    if hit or not loose:
        return hit
    return _loose_hit(index, raw)


def resolve_quest_link(name: str, page: str = "") -> str | None:
    """Resolve a related-quest link.

    The visible label wins when it is already a hub title. The target page is
    tried next, so ``Trooper Scale Pauldron`` on ``Trooper Scale Armor Quests``
    stays on Trooper Scale Armor instead of a different ``… Pauldron Quest``.
    A trailing ``Quest`` / leading ``the`` fold runs only after both miss.
    """
    label = (name or "").strip()
    target = (page or "").strip()
    if label:
        hit = resolve_quest_label(label, loose=False)
        if hit:
            return hit
    if target and quest_name_key(target) != quest_name_key(label):
        hit = resolve_quest_label(target, loose=False)
        if hit:
            return hit
    if label:
        hit = resolve_quest_label(label, loose=True)
        if hit:
            return hit
    if target:
        return resolve_quest_label(target, loose=True)
    return None


@lru_cache(maxsize=1)
def _pos_by_item() -> dict[str, tuple[str, ...]]:
    buckets: dict[str, list[str]] = {}
    for test in pos_tests():
        quest = (test.get("quest") or "").strip()
        if not quest:
            continue
        names = [test.get("reward") or ""]
        for item in test.get("items") or []:
            if isinstance(item, dict):
                names.append(item.get("name") or "")
            elif isinstance(item, str):
                names.append(item)
        for raw in names:
            key = item_name_key(raw)
            if not key:
                continue
            bucket = buckets.setdefault(key, [])
            if quest not in bucket:
                bucket.append(quest)
    return {k: tuple(v) for k, v in buckets.items()}


@lru_cache(maxsize=1)
def pos_quests_for_item(name: str) -> tuple[str, ...]:
    return _pos_by_item().get(item_name_key(name), ())


@lru_cache(maxsize=1)
def _related_by_item() -> dict[str, tuple[dict[str, str], ...]]:
    data = _load_json("eqlwiki_item_related_quests.json")
    items = data.get("items") if isinstance(data, dict) else None
    if not isinstance(items, dict):
        return {}
    out: dict[str, tuple[dict[str, str], ...]] = {}
    for item_name, links in items.items():
        if not isinstance(item_name, str) or not isinstance(links, list):
            continue
        cleaned: list[dict[str, str]] = []
        for link in links:
            if isinstance(link, str):
                name = link.strip()
                page = ""
            elif isinstance(link, dict):
                name = str(link.get("name") or "").strip()
                page = str(link.get("page") or "").strip()
            else:
                continue
            if name:
                cleaned.append({"name": name, "page": page})
        if cleaned:
            out[item_name_key(item_name)] = tuple(cleaned)
    return out


def related_links_for_item(name: str) -> tuple[dict[str, str], ...]:
    return _related_by_item().get(item_name_key(name), ())


def parse_related_quest_wikitext(wikitext: str) -> list[dict[str, str]]:
    """Top-level related-quest links from an item page's ``|relatedquests=`` field.

    Nested ``*`` lines inside an open ``<li>`` are component items or drop
    NPCs, not quests. The piped label is the quest name; the page is only a
    fallback (``[[Plane of Sky#Wizard Tests|Wizard Test of Focus]]``).
    """
    if not wikitext:
        return []
    m = re.search(
        r"\|\s*relatedquests\s*=(.*?)(?:\n\s*\|\s*[a-zA-Z_]+\s*=|\n\s*\}\})",
        wikitext,
        re.S | re.I,
    )
    if not m:
        return []
    body = m.group(1)
    body = re.sub(r"\{\{[^{}]*\}\}", " ", body)
    links: list[dict[str, str]] = []
    in_li = 0
    took = False

    def add_from(line: str) -> bool:
        mm = _LINK_RE.search(line)
        if not mm:
            return False
        if mm.group(1) is not None:
            page, label = mm.group(1), mm.group(3) or ""
        else:
            page, label = mm.group(4), ""
        page = (page or "").replace("_", " ").strip()
        label = (label or "").replace("_", " ").strip()
        name = label or page
        if not name:
            return False
        links.append({"name": name, "page": page or name})
        return True

    for line in body.splitlines():
        low = line.lower()
        if "<li" in low:
            parts = re.split(r"<li\b[^>]*>", line, flags=re.I)
            in_li = max(0, in_li - parts[0].lower().count("</li>"))
            if in_li == 0:
                took = False
            for part in parts[1:]:
                in_li += 1
                took = add_from(part)
                closes = part.lower().count("</li>")
                if closes:
                    in_li = max(0, in_li - closes)
                    if in_li == 0:
                        took = False
            continue
        if re.match(r"\s*\*\s+", line) and not re.match(r"\s*\*\*", line):
            if in_li and took:
                continue
            add_from(line)
            continue
        if "</li>" in low:
            in_li = max(0, in_li - low.count("</li>"))
            if in_li == 0:
                took = False

    deduped: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for link in links:
        key = (quest_name_key(link["name"]), quest_name_key(link["page"]))
        if key in seen:
            continue
        seen.add(key)
        deduped.append(link)
    return deduped


def _balanced_from(html: str, tag: str) -> str:
    depth = 0
    pattern = re.compile(rf"</?{tag}\b[^>]*>", re.I)
    for m in pattern.finditer(html):
        token = m.group(0).lower()
        if token.startswith("</"):
            depth -= 1
            if depth == 0:
                return html[: m.end()]
        else:
            depth += 1
    return html


def _first_anchor(chunk: str) -> dict[str, str] | None:
    m = re.search(r"<a\b([^>]*)>([\s\S]*?)</a>", chunk or "", re.I)
    if not m:
        return None
    attrs, inner = m.group(1), m.group(2)
    text = unescape(re.sub(r"<[^>]+>", " ", inner))
    text = re.sub(r"\s+", " ", text).strip()
    title_m = re.search(r'\btitle="([^"]*)"', attrs, re.I)
    href_m = re.search(r'\bhref="([^"]*)"', attrs, re.I)
    title = unescape(title_m.group(1)).strip() if title_m else ""
    page = title
    if href_m:
        href = unescape(href_m.group(1))
        path = href.split("#", 1)[0]
        path = path.rsplit("/", 1)[-1]
        path = urllib.parse.unquote(path).replace("_", " ").strip()
        if path and not path.lower().startswith("index.php") and not path.startswith("?"):
            page = path
    name = text or title
    if not name:
        return None
    return {"name": name, "page": page or name}


def parse_related_quests_from_item_html(html: str) -> list[dict[str, str]]:
    """Visible top-level quest links from a rendered eqlwiki item page.

    The ``title`` attribute is the target page ("Plane of Sky"), not the quest.
    Nested lists under a quest are components and are ignored.
    """
    if not html:
        return []
    m = re.search(r'id="Related_quests"', html, re.I)
    if not m:
        m = re.search(r"Related quests", html, re.I)
    if not m:
        return []
    rest = html[m.start():]
    um = re.search(r"<ul\b", rest, re.I)
    if not um:
        return []
    ul = _balanced_from(rest[um.start():], "ul")
    ul = re.sub(r'<span class="hb">[\s\S]*?</span>', "", ul, flags=re.I)
    close = ul.lower().rfind("</ul>")
    open_end = ul.find(">")
    inner = ul[open_end + 1: close if close >= 0 else len(ul)]
    prev = None
    while prev != inner:
        prev = inner
        inner = re.sub(
            r"<ul\b[^>]*>(?:(?!<ul\b).)*?</ul>",
            "",
            inner,
            flags=re.I | re.S,
        )
    links: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for chunk in re.split(r"<li\b[^>]*>", inner, flags=re.I)[1:]:
        chunk = re.split(r"</li>", chunk, maxsplit=1, flags=re.I)[0]
        link = _first_anchor(chunk)
        if not link:
            continue
        key = (quest_name_key(link["name"]), quest_name_key(link["page"]))
        if key in seen:
            continue
        seen.add(key)
        links.append(link)
    return links
