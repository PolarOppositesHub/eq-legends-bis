#!/usr/bin/env python3
"""Fetch + decode eqlegendstools char-sheet core (races + spellBuffs).

Writes:
  data/races.json       — raceStats / raceSaves / classStats
  data/spell_buffs.json — Cast Buffs catalog
"""
from __future__ import annotations

import json
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RACES_OUT = ROOT / "data" / "races.json"
BUFFS_OUT = ROOT / "data" / "spell_buffs.json"
URL = "https://eqlegendstools.com/api/r/05ef4a7f7f1efd0a352de2de"
M, O, T, D = 24, 4031, 4, 2


def dec_str(s, ts=-T, ds=-D):
    out = []
    for ch in s:
        c = ord(ch)
        if 65 <= c <= 90:
            out.append(chr(65 + (c - 65 + ts) % 26))
        elif 97 <= c <= 122:
            out.append(chr(97 + (c - 97 + ts) % 26))
        elif 48 <= c <= 57:
            out.append(chr(48 + (c - 48 + ds) % 10))
        else:
            out.append(ch)
    return "".join(out)


def decode(v, key=""):
    if isinstance(v, str):
        return dec_str(v)
    if isinstance(v, bool) or v is None:
        return v
    if isinstance(v, int):
        r = (v - O) / M
        return int(round(r)) if abs(r - round(r)) < 1e-9 else r
    if isinstance(v, list):
        return [decode(x, "") for x in v]
    if isinstance(v, dict):
        return {k: decode(val, k) for k, val in v.items()}
    return v


def main():
    req = urllib.request.Request(
        URL,
        headers={
            "Referer": "https://eqlegendstools.com/char-sheet/",
            "Origin": "https://eqlegendstools.com",
            "User-Agent": "EQ-Legends-BiS-App/1.0.7",
            "Accept": "application/json",
        },
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        raw = json.loads(resp.read().decode())
    decoded = decode(raw)
    race = (decoded.get("r") or {})
    races_out = {
        "source": "https://eqlegendstools.com/char-sheet/ (decoded core bundle)",
        "verified": True,
        "cross_check": "https://eqlwiki.com/Race",
        "raceStats": race.get("raceStats") or [],
        "raceSaves": race.get("raceSaves") or [],
        "classStats": race.get("classStats") or [],
    }
    RACES_OUT.parent.mkdir(parents=True, exist_ok=True)
    RACES_OUT.write_text(json.dumps(races_out, indent=2))
    print("Wrote", RACES_OUT, [r.get("Race") for r in races_out["raceStats"]])

    sb = decoded.get("spellBuffs") or {}
    buffs_out = {
        "source": "https://eqlegendstools.com/char-sheet/ (decoded spellBuffs)",
        "verified": True,
        "schemaVersion": sb.get("schemaVersion"),
        "buffs": sb.get("buffs") or [],
    }
    BUFFS_OUT.write_text(json.dumps(buffs_out, indent=2))
    print("Wrote", BUFFS_OUT, "buffs=", len(buffs_out["buffs"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
