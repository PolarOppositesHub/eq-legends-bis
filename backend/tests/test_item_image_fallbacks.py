"""Bare craft-name image fallbacks — wiki parentheticals, no invented items."""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from app import item_catalog as ic  # noqa: E402


# Minimal 1×1 8-bit RGBA PNG (no Pillow required).
_PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01"
    b"\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
)
WIKI_ICON_URL = "https://eqlwiki.com/images/6/61/Item_641.png"


def _png() -> bytes:
    return _PNG


def _wiki_html(title: str, icon: str = WIKI_ICON_URL) -> bytes:
    pad = "item page content " * 20
    html = (
        f"<!DOCTYPE html><html><head><title>{title}</title></head>"
        f'<body><div class="itemicon"><img src="{icon}" alt=""></div>'
        f"<p>{pad}</p></body></html>"
    )
    return html.encode("utf-8")


def _missing_html(title: str) -> bytes:
    pad = "you can create the page " * 20
    html = (
        f"<!DOCTYPE html><html><head><title>{title}</title></head>"
        f"<body><p>This page does not exist. You can {pad}</p></body></html>"
    )
    return html.encode("utf-8")


class ImageNameCandidateTests(unittest.TestCase):
    def test_shaped_darkwood_compound_bow_gets_material_suffixes(self):
        names = ic.image_name_candidates("Shaped Darkwood Compound Bow")
        self.assertEqual(names[0], "Shaped Darkwood Compound Bow")
        self.assertIn("Shaped Darkwood Compound Bow (Silk)", names)
        self.assertIn("Shaped Darkwood Compound Bow (Linen)", names)
        self.assertIn("Shaped Darkwood Compound Bow (Hemp)", names)
        self.assertTrue(
            names.index("Shaped Darkwood Compound Bow (Silk)")
            < names.index("Shaped Darkwood Compound Bow (Linen)")
        )
        self.assertNotIn("Curved Darkwood Compound Bow", names)
        self.assertFalse(any("Curved" in n for n in names))

    def test_carved_darkwood_compound_bow_gets_material_suffixes(self):
        names = ic.image_name_candidates("Carved Darkwood Compound Bow")
        self.assertIn("Carved Darkwood Compound Bow (Silk)", names)
        self.assertIn("Carved Darkwood Compound Bow (Linen)", names)
        self.assertIn("Carved Darkwood Compound Bow (Hemp)", names)

    def test_oak_craft_bows_same_pattern(self):
        for bare in (
            "Shaped Oak Recurve Bow",
            "Carved Oak Recurve Bow",
            "Shaped Oak 1-Cam Bow",
            "Carved Oak 1-Cam Bow",
        ):
            names = ic.image_name_candidates(bare)
            self.assertIn(f"{bare} (Silk)", names, bare)
            self.assertIn(f"{bare} (Linen)", names, bare)
            self.assertIn(f"{bare} (Hemp)", names, bare)

    def test_suffixed_name_strips_parenthetical(self):
        names = ic.image_name_candidates("Shaped Darkwood Compound Bow (Silk)")
        self.assertEqual(names[0], "Shaped Darkwood Compound Bow (Silk)")
        self.assertIn("Shaped Darkwood Compound Bow", names)
        self.assertIn("Shaped Darkwood Compound Bow (Hemp)", names)

    def test_does_not_invent_materials_for_unrelated_items(self):
        names = ic.image_name_candidates("Fine Silk Turban")
        self.assertEqual(names, ["Fine Silk Turban"])
        self.assertNotIn("Fine Silk Turban (Silk)", names)

    def test_fuzzy_add_existing_parenthetical_only(self):
        names = ic.image_name_candidates("Crystalline Silk Mask")
        self.assertIn("Crystalline Silk Mask", names)
        self.assertIn("Crystalline Silk Mask (Lore)", names)
        self.assertNotIn("Crystalline Silk Mask (Silk)", names)

    def test_enrichment_urls_stay_exact_name(self):
        urls = ic._wiki_urls_for_item({"name": "Shaped Darkwood Compound Bow"})
        joined = " ".join(urls)
        self.assertIn("Shaped_Darkwood_Compound_Bow", joined)
        self.assertNotIn("(Silk)", joined)
        self.assertNotIn("eqlegendstools", joined)

    def test_image_urls_include_wiki_fallback_and_eqlegendstools(self):
        urls = ic._wiki_image_page_urls("Shaped Darkwood Compound Bow", {"name": "Shaped Darkwood Compound Bow"})
        self.assertTrue(urls[0].endswith("/Shaped_Darkwood_Compound_Bow"))
        self.assertIn("https://eqlwiki.com/Shaped_Darkwood_Compound_Bow_%28Silk%29", urls)
        self.assertIn("https://eqlegendstools.com/items/shaped-darkwood-compound-bow/", urls)

    def test_catalog_source_url_is_first(self):
        it = {
            "name": "Shaped Darkwood Compound Bow",
            "sourceUrl": "https://eqlwiki.com/Shaped_Darkwood_Compound_Bow_%28Silk%29",
        }
        urls = ic._wiki_image_page_urls("Shaped Darkwood Compound Bow", it)
        self.assertEqual(urls[0], it["sourceUrl"])


class BareNameCoverageTests(unittest.TestCase):
    def test_wiki_index_bare_bases_gain_parenthetical_fallbacks(self):
        """Measurable: wiki titles exist only as ``Base (Tag)``, not as bare ``Base``."""
        wiki = ic._wiki_display_names()
        bases: dict[str, list[str]] = {}
        for display in wiki.values():
            m = ic._TRAILING_PAREN_RE.search(display)
            if not m:
                continue
            base = ic._strip_trailing_paren(display)
            if not base:
                continue
            bases.setdefault(base, []).append(display)
        gained = [
            base for base, variants in bases.items()
            if ic._name_key(base) not in wiki and len(variants) >= 1
        ]
        craft_bows = [
            b for b in gained
            if any(b.endswith(suf) for suf in ("Compound Bow", "Recurve Bow", "1-Cam Bow"))
        ]
        self.assertGreaterEqual(len(gained), 100, len(gained))
        self.assertGreaterEqual(len(craft_bows), 20, craft_bows)
        self.assertIn("Shaped Darkwood Compound Bow", craft_bows)
        self.assertIn("Carved Darkwood Compound Bow", craft_bows)
        self.assertIn("Shaped Oak Recurve Bow", craft_bows)
        print(f"\nbare_wiki_bases_with_parenthetical_fallback={len(gained)}")
        print(f"bare_craft_bow_bases={len(craft_bows)}")


class EnsureImageFallbackTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.img_dir = Path(self.tmp.name)
        self.http_calls: list[str] = []

    def tearDown(self):
        self.tmp.cleanup()

    def _http(self, url: str, timeout: float = 20.0) -> bytes | None:
        self.http_calls.append(url)
        if url == WIKI_ICON_URL:
            return _png()
        if url.rstrip("/").endswith("Shaped_Darkwood_Compound_Bow"):
            return _missing_html("Shaped Darkwood Compound Bow")
        if "Shaped_Darkwood_Compound_Bow_%28Silk%29" in url:
            return _wiki_html("Shaped Darkwood Compound Bow (Silk)")
        if "eqlegendstools.com" in url:
            return None
        return _missing_html(url)

    def test_bare_name_fetches_silk_page_and_aliases_cache(self):
        with (
            patch.object(ic, "_images_dir", return_value=self.img_dir),
            patch.object(ic, "image_seed_dirs", return_value=[]),
            patch.object(ic, "_http_get", side_effect=self._http),
        ):
            info = ic.ensure_item_image("Shaped Darkwood Compound Bow", fetch=True)
        self.assertTrue(info.get("cached"), info)
        self.assertEqual(info.get("resolved_name"), "Shaped Darkwood Compound Bow (Silk)")
        self.assertEqual(info.get("source"), WIKI_ICON_URL)
        requested = self.img_dir / "shaped-darkwood-compound-bow.png"
        resolved = self.img_dir / "shaped-darkwood-compound-bow-silk.png"
        self.assertTrue(requested.is_file(), requested)
        self.assertTrue(resolved.is_file(), resolved)
        self.assertGreater(requested.stat().st_size, 0)
        self.assertTrue(any("Shaped_Darkwood_Compound_Bow_%28Silk%29" in u for u in self.http_calls))

    def test_alias_from_existing_fallback_slug_without_http(self):
        silk = self.img_dir / "shaped-darkwood-compound-bow-silk.png"
        silk.write_bytes(_png())
        with (
            patch.object(ic, "_images_dir", return_value=self.img_dir),
            patch.object(ic, "image_seed_dirs", return_value=[]),
            patch.object(ic, "_http_get", side_effect=self._http),
        ):
            info = ic.ensure_item_image("Shaped Darkwood Compound Bow", fetch=False)
        self.assertTrue(info.get("cached"), info)
        self.assertTrue((self.img_dir / "shaped-darkwood-compound-bow.png").is_file())
        self.assertEqual(self.http_calls, [])

    def test_fail_cleanly_when_no_asset(self):
        def empty(url: str, timeout: float = 20.0) -> bytes | None:
            self.http_calls.append(url)
            if "eqlwiki.com" in url and "Bow" in url:
                return _missing_html(url)
            return None

        with (
            patch.object(ic, "_images_dir", return_value=self.img_dir),
            patch.object(ic, "image_seed_dirs", return_value=[]),
            patch.object(ic, "_http_get", side_effect=empty),
        ):
            info = ic.ensure_item_image("Shaped Darkwood Compound Bow", fetch=True)
        self.assertFalse(info.get("cached"))
        self.assertEqual(info.get("error"), "no wiki image found")
        self.assertIsNone(info.get("path"))
        self.assertGreater(info.get("wiki_tried") or 0, 1)

    def test_eqlegendstools_used_when_wiki_blocked(self):
        tools_html = _wiki_html(
            "Shaped Darkwood Compound Bow",
            icon="https://eqlwiki.com/images/a/ab/Item_999.png",
        )

        def blocked(url: str, timeout: float = 20.0) -> bytes | None:
            self.http_calls.append(url)
            if url.endswith("Item_999.png"):
                return _png()
            if "eqlwiki." in url:
                return b"<html><head><title>One moment, please</title></head><body>" + (b"x" * 220)
            if "eqlegendstools.com/items/shaped-darkwood-compound-bow" in url:
                return tools_html
            return None

        with (
            patch.object(ic, "_images_dir", return_value=self.img_dir),
            patch.object(ic, "image_seed_dirs", return_value=[]),
            patch.object(ic, "_http_get", side_effect=blocked),
        ):
            info = ic.ensure_item_image("Shaped Darkwood Compound Bow", fetch=True)
        self.assertTrue(info.get("cached"), info)
        self.assertEqual(info.get("source"), "https://eqlwiki.com/images/a/ab/Item_999.png")
        self.assertTrue(any("eqlegendstools.com" in u for u in self.http_calls))


if __name__ == "__main__":
    unittest.main()
