"""Generate the static site from data/elo.json into site/."""
from __future__ import annotations

import json
import re
import shutil
import sys
from datetime import date
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data"
SITE = ROOT / "site"
TEMPLATES = Path(__file__).resolve().parent / "templates"

SITE_NAME = "Badminton ELO Praha"
ACTIVE_MONTHS = 12  # a player is "active" if they played within the last 12 months

MONTH_NAMES = ["", "leden", "únor", "březen", "duben", "květen", "červen", "červenec",
               "srpen", "září", "říjen", "listopad", "prosinec"]


def month_index(r: dict) -> int:
    return r["year"] * 12 + (r["month"] - 1)


def safe_id(pid: str) -> str:
    return re.sub(r"[^A-Za-z0-9_-]", "_", pid)


def chart_svg(points: list[tuple[int, float]], rounds_by_order: dict[int, dict]) -> str:
    """Inline SVG line chart: x = time (months), y = rating."""
    if len(points) < 2:
        return ""
    xs = [month_index(rounds_by_order[o]) for o, _ in points]
    ys = [r for _, r in points]
    W, H, L, R, T, B = 760, 280, 48, 16, 12, 28
    x0, x1 = min(xs), max(xs)
    if x1 == x0:
        x1 = x0 + 1
    y0 = (min(ys) // 50) * 50 - 25
    y1 = (max(ys) // 50 + 1) * 50 + 25
    sx = lambda x: L + (x - x0) / (x1 - x0) * (W - L - R)
    sy = lambda y: T + (y1 - y) / (y1 - y0) * (H - T - B)
    out = [f'<svg class="chart" viewBox="0 0 {W} {H}" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="Vývoj ELO">']
    # horizontal grid every 50 or 100 points
    step = 50 if (y1 - y0) <= 400 else 100
    y = (y0 // step + 1) * step
    while y < y1:
        out.append(f'<line class="grid" x1="{L}" y1="{sy(y):.1f}" x2="{W - R}" y2="{sy(y):.1f}"/>')
        out.append(f'<text class="tick" x="{L - 6}" y="{sy(y) + 4:.1f}" text-anchor="end">{int(y)}</text>')
        y += step
    # vertical ticks at Januaries
    first_year, last_year = x0 // 12, x1 // 12
    for yr in range(first_year, last_year + 2):
        x = yr * 12
        if x0 <= x <= x1:
            out.append(f'<line class="grid" x1="{sx(x):.1f}" y1="{T}" x2="{sx(x):.1f}" y2="{H - B}"/>')
            out.append(f'<text class="tick" x="{sx(x):.1f}" y="{H - B + 16}" text-anchor="middle">{yr}</text>')
    pts = " ".join(f"{sx(x):.1f},{sy(y):.1f}" for x, y in zip(xs, ys))
    out.append(f'<polyline class="line" fill="none" points="{pts}"/>')
    for x, y in zip(xs, ys):
        out.append(f'<circle class="dot" cx="{sx(x):.1f}" cy="{sy(y):.1f}" r="2.5"><title>{int(round(y))}</title></circle>')
    out.append("</svg>")
    return "\n".join(out)


def main() -> int:
    elo = json.loads((DATA / "elo.json").read_text(encoding="utf-8"))
    rounds = elo["rounds"]
    rounds_by_order = {r["order"]: r for r in rounds}
    last_round = rounds[-1]
    cutoff = month_index(last_round) - ACTIVE_MONTHS

    players = list(elo["players"].values())
    for p in players:
        p["file"] = safe_id(p["id"]) + ".html"
        p["hidden"] = "*" in p["name"] or p["id"].isdigit()
        lr = rounds_by_order[p["last_round"]]
        p["active"] = month_index(lr) >= cutoff
        p["last_label"] = f"{lr['month']}/{lr['year']}"
        p["first_label"] = f"{rounds_by_order[p['first_round']]['month']}/{rounds_by_order[p['first_round']]['year']}"
        h = p["history"]
        p["trend"] = round(h[-1][1] - h[-2][1], 1) if len(h) >= 2 else 0.0
        p["win_pct"] = round(100 * p["wins"] / p["matches"]) if p["matches"] else None
        p["rating_int"] = int(round(p["rating"]))

    by_id = {p["id"]: p for p in players}
    ranked = sorted(players, key=lambda p: (-p["rating"], -p["matches"], p["name"]))
    active = [p for p in ranked if p["active"] and p["matches"] > 0]
    for i, p in enumerate(active, 1):
        p["rank"] = i
    everyone = [p for p in ranked if p["matches"] > 0]

    env = Environment(loader=FileSystemLoader(str(TEMPLATES)), autoescape=select_autoescape(["html"]))
    env.globals.update(site_name=SITE_NAME, generated=elo["generated"], last_round=last_round,
                       active_months=ACTIVE_MONTHS, method=elo["method"], n_rounds=len(rounds),
                       n_players=len(everyone), first_round=rounds[0])

    if SITE.exists():
        shutil.rmtree(SITE)
    (SITE / "hrac").mkdir(parents=True)
    (SITE / ".nojekyll").write_text("")

    index_t = env.get_template("index.html")
    (SITE / "index.html").write_text(index_t.render(players=active, all_players=False, root=""), encoding="utf-8")
    (SITE / "vsichni.html").write_text(index_t.render(players=everyone, all_players=True, root=""), encoding="utf-8")

    player_t = env.get_template("player.html")
    for p in players:
        games = []
        for g in reversed(p["games"]):
            r = rounds_by_order[g["round"]]
            opp = by_id[g["opp"]]
            games.append({**g, "round_label": f"{MONTH_NAMES[r['month']]} {r['year']}",
                          "opp_name": opp["name"], "opp_file": opp["file"],
                          "score": "skreč" if g["walkover"] else f"{g['sets_for']}:{g['sets_against']}"})
        html = player_t.render(p=p, games=games, root="../",
                               chart=chart_svg([tuple(x) for x in p["history"]], rounds_by_order))
        (SITE / "hrac" / p["file"]).write_text(html, encoding="utf-8")

    print(f"site: {len(active)} active players, {len(everyone)} total, {len(players)} player pages")
    return 0


if __name__ == "__main__":
    sys.exit(main())
