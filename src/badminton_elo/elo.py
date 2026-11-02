"""Compute ELO ratings from the downloaded rounds.

Method (documented on the site as well):
  * every player starts with a rating derived from the level of their first
    group: 1500 + (12 - level) * 30, i.e. level 1 = 1830, level 23 = 1170;
  * matches are processed round by round; within a round all matches use the
    ratings valid at the start of the round (the portal gives no match dates);
  * K = 48 for a player's first 20 rated matches, 32 afterwards;
  * the rating change is scaled by the set score: 3:0 x 1.0, 3:1 x 0.9, 3:2 x 0.8;
  * walkovers (skreč) are not rated; they are only counted in the statistics.

Output: data/elo.json
"""
from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path

DATA = Path(__file__).resolve().parents[2] / "data"
RAW = DATA / "raw"

START = 1500
LEVEL_STEP = 30
LEVEL_CENTER = 12
K_NEW, K_NEW_MATCHES, K = 48, 20, 32


def seed(level: int | None) -> float:
    if level is None:
        return START
    return START + (LEVEL_CENTER - level) * LEVEL_STEP


def margin(sets_w: int, sets_l: int) -> float:
    return max(0.5, 1.0 - 0.1 * sets_l)


def expected(ra: float, rb: float) -> float:
    return 1.0 / (1.0 + 10 ** ((rb - ra) / 400.0))


def load_rounds() -> list[dict]:
    rounds = json.loads((DATA / "rounds.json").read_text(encoding="utf-8"))
    out = []
    for r in sorted(rounds, key=lambda r: r["order"]):
        path = RAW / f"{r['id']}.json"
        if not path.exists():
            continue
        raw = json.loads(path.read_text(encoding="utf-8"))
        out.append({**r, "groups": raw["groups"], "scraped": raw.get("scraped")})
    return out


def compute(rounds: list[dict]) -> dict:
    players: dict[str, dict] = {}

    def player(pid: str, name: str, level: int | None, rnd: dict) -> dict:
        p = players.get(pid)
        if p is None:
            p = players[pid] = {
                "id": pid, "name": name, "rating": seed(level), "peak": seed(level),
                "matches": 0, "wins": 0, "losses": 0,
                "wo_wins": 0, "wo_losses": 0,
                "first_round": rnd["order"], "last_round": rnd["order"],
                "last_level": level, "history": [], "games": [],
            }
        p["name"] = name  # latest name shown by the portal (may become hidden)
        p["last_round"] = rnd["order"]
        p["last_level"] = level
        return p

    for rnd in rounds:
        deltas: dict[str, float] = {}
        seen: set[str] = set()
        for g in rnd["groups"]:
            level = g.get("level")
            for pl in g["players"]:
                player(pl["id"], pl["name"], level, rnd)
                seen.add(pl["id"])
            for m in g["matches"]:
                a, b = players[m["a"]], players[m["b"]]
                a_won = m["winner"] == m["a"]
                if m["walkover"]:
                    w, l = (a, b) if a_won else (b, a)
                    w["wo_wins"] += 1
                    l["wo_losses"] += 1
                    for me, opp, won in ((a, b, a_won), (b, a, not a_won)):
                        me["games"].append({"round": rnd["order"], "level": level, "group": g["group"],
                                            "opp": opp["id"], "sets_for": None, "sets_against": None,
                                            "won": won, "walkover": True, "delta": 0.0})
                    continue
                ra, rb = a["rating"], b["rating"]
                ea = expected(ra, rb)
                sa = 1.0 if a_won else 0.0
                sw, sl = (m["sets_a"], m["sets_b"]) if a_won else (m["sets_b"], m["sets_a"])
                mult = margin(sw, sl)
                ka = K_NEW if a["matches"] < K_NEW_MATCHES else K
                kb = K_NEW if b["matches"] < K_NEW_MATCHES else K
                da = ka * mult * (sa - ea)
                db = kb * mult * ((1 - sa) - (1 - ea))
                deltas[a["id"]] = deltas.get(a["id"], 0.0) + da
                deltas[b["id"]] = deltas.get(b["id"], 0.0) + db
                for me, opp, won, d, sf, sg in ((a, b, a_won, da, m["sets_a"], m["sets_b"]),
                                                (b, a, not a_won, db, m["sets_b"], m["sets_a"])):
                    me["matches"] += 1
                    me["wins" if won else "losses"] += 1
                    me["games"].append({"round": rnd["order"], "level": level, "group": g["group"],
                                        "opp": opp["id"], "sets_for": sf, "sets_against": sg,
                                        "won": won, "walkover": False, "delta": round(d, 1)})
        for pid in seen:
            p = players[pid]
            p["rating"] += deltas.get(pid, 0.0)
            p["peak"] = max(p["peak"], p["rating"])
            p["history"].append([rnd["order"], round(p["rating"], 1)])

    for p in players.values():
        p["rating"] = round(p["rating"], 1)
        p["peak"] = round(p["peak"], 1)
    return players


def main() -> int:
    rounds = load_rounds()
    if not rounds:
        print("no rounds downloaded yet", file=sys.stderr)
        return 1
    players = compute(rounds)
    out = {
        "generated": date.today().isoformat(),
        "method": {"start": START, "level_step": LEVEL_STEP, "level_center": LEVEL_CENTER,
                   "k": K, "k_new": K_NEW, "k_new_matches": K_NEW_MATCHES},
        "rounds": [{k: r[k] for k in ("id", "label", "year", "month", "order")} for r in rounds],
        "players": players,
    }
    (DATA / "elo.json").write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8", newline="
")
    n_matches = sum(p["matches"] for p in players.values()) // 2
    print(f"{len(rounds)} rounds, {len(players)} players, {n_matches} rated matches")
    return 0


if __name__ == "__main__":
    sys.exit(main())
