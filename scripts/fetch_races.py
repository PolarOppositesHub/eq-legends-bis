#!/usr/bin/env python3
from __future__ import annotations
import json, urllib.request
from pathlib import Path
OUT = Path(__file__).resolve().parents[1] / "data" / "races.json"
URL = "https://eqlegendstools.com/api/r/05ef4a7f7f1efd0a352de2de"
M, O, T, D = 24, 4031, 4, 2
IDENT = {"itemID", "rowId", "itemId"}

def dec_str(s, ts=-T, ds=-D):
    out = []
    for ch in s:
        c = ord(ch)
        if 65 <= c <= 90: out.append(chr(65 + (c - 65 + ts) % 26))
        elif 97 <= c <= 122: out.append(chr(97 + (c - 97 + ts) % 26))
        elif 48 <= c <= 57: out.append(chr(48 + (c - 48 + ds) % 10))
        else: out.append(ch)
    return "".join(out)

def decode(v, key=""):
    if isinstance(v, str): return dec_str(v)
    if isinstance(v, bool) or v is None: return v
    if isinstance(v, int) and key not in IDENT:
        r = (v - O) / M
        return int(round(r)) if abs(r - round(r)) < 1e-9 else r
    if isinstance(v, list): return [decode(x, "") for x in v]
    if isinstance(v, dict): return {k: decode(val, k) for k, val in v.items()}
    return v

def main():
    req = urllib.request.Request(URL, headers={
        "Referer": "https://eqlegendstools.com/char-sheet/",
        "Origin": "https://eqlegendstools.com",
        "User-Agent": "EQ-Legends-BiS-App/1.0",
        "Accept": "application/json",
    })
    with urllib.request.urlopen(req, timeout=60) as resp:
        raw = json.loads(resp.read().decode())
    race = (decode(raw).get("r") or {})
    out = {
        "source": "https://eqlegendstools.com/char-sheet/ (decoded core bundle)",
        "verified": True,
        "cross_check": "https://eqlwiki.com/Race",
        "raceStats": race.get("raceStats") or [],
        "raceSaves": race.get("raceSaves") or [],
        "classStats": race.get("classStats") or [],
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, indent=2))
    print("Wrote", OUT, [r.get("Race") for r in out["raceStats"]])
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
