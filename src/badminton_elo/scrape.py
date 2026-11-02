"""Download results of the Prague badminton league from vaseliga.cz.

Data layout:
  data/rounds.json       list of rounds (id, label, year, month, order)
  data/raw/<round>.json  groups + matches of one round, as shown on the portal

Only what the portal shows publicly is stored. Hidden player names
(e.g. "M***** V******") are kept hidden; the player's id from the profile
link (/hrac/<id>) is used to tell players apart.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
from datetime import date
from pathlib import Path

import requests
from bs4 import BeautifulSoup

BASE = "https://www.vaseliga.cz"
RESULTS = f"{BASE}/vysledky/badminton/praha"
DATA = Path(__file__).resolve().parents[2] / "data"
RAW = DATA / "raw"
USER_AGENT = "badminton-elo scraper (hobby project; contact via GitHub)"
DELAY = 0.5  # seconds between requests, to be gentle to the portal

MONTHS = {
    "leden": 1, "únor": 2, "březen": 3, "duben": 4, "květen": 5, "červen": 6,
    "červenec": 7, "srpen": 8, "září": 9, "říjen": 10, "listopad": 11, "prosinec": 12,
}

_session: requests.Session | None = None


def session() -> requests.Session:
    global _session
    if _session is None:
        s = requests.Session()
        s.headers["User-Agent"] = USER_AGENT
        # first plain page load gives us the session cookie the AJAX calls need
        s.get(RESULTS, timeout=30).raise_for_status()
        _session = s
    return _session


def get(url: str, ajax: bool = False, retries: int = 3) -> requests.Response:
    headers = {"X-Requested-With": "XMLHttpRequest"} if ajax else {}
    last: Exception | None = None
    for attempt in range(retries):
        try:
            r = session().get(url, headers=headers, timeout=30)
            time.sleep(DELAY)
            r.raise_for_status()
            return r
        except requests.RequestException as e:  # pragma: no cover - network
            last = e
            time.sleep(5 * (attempt + 1))
    raise RuntimeError(f"failed to fetch {url}: {last}")


# --------------------------------------------------------------------------- rounds

def parse_round_label(label: str) -> tuple[int | None, int | None]:
    """'Podzimní sezóna 2025 - 4. kolo (leden)' -> (2026, 1)."""
    m = re.search(r"(Jarní|Letní|Podzimní|Zimní)\D*(\d{4}).*?\(([^)]+)\)", label)
    if not m:
        return None, None
    season, year = m.group(1), int(m.group(2))
    month_name = re.split(r"[-–\s]", m.group(3).strip().lower())[0]  # "březen-duben" -> březen
    month = MONTHS.get(month_name)
    if month is None:
        return None, None
    if season == "Podzimní" and month == 1:
        year += 1
    return year, month


def fetch_rounds() -> list[dict]:
    """All rounds from the round selector, oldest first."""
    html = get(RESULTS).text
    soup = BeautifulSoup(html, "lxml")
    select = soup.find("select", id="fn_round_result-select")
    if select is None:
        raise RuntimeError("round selector not found on the results page")
    options = select.find_all("option")
    rounds = []
    for order, opt in enumerate(reversed(options)):
        label = " ".join(opt.get_text().split())
        year, month = parse_round_label(label)
        rounds.append({
            "id": int(opt["value"]),
            "label": label,
            "year": year,
            "month": month,
            "order": order,
        })
    return rounds


# --------------------------------------------------------------------------- groups

SCORE_RE = re.compile(r"^([0-9S]):([0-9S])$")


def parse_group_links(html: str, round_id: int) -> list[tuple[int, str]]:
    """(resultId, groupId) for every group in the round page."""
    soup = BeautifulSoup(html, "lxml")
    out = []
    for a in soup.select("a[href*='do=loadScore']"):
        href = a["href"]
        m = re.search(r"/praha/(\d+)\?resultId=(\d+)&(?:amp;)?groupId=(\w+)", href)
        if m:
            if int(m.group(1)) != round_id:
                continue
            out.append((int(m.group(2)), m.group(3)))
            continue
        m2 = re.search(r"resultId=(\d+)&(?:amp;)?groupId=(\w+)", href)
        if m2:
            out.append((int(m2.group(1)), m2.group(2)))
    return out


def cell_score(td) -> str | None:
    """Return '3:1', '3:S' ... or None for an unplayed match."""
    for a in td.find_all("a"):  # comment popovers; their text is not the score
        a.decompose()
    text = " ".join(td.get_text().split())
    return text if SCORE_RE.match(text) else None


def parse_scoreboard(html: str) -> dict | None:
    soup = BeautifulSoup(html, "lxml")
    title_el = soup.select_one(".modal-title")
    table = soup.select_one("table")
    if table is None:
        return None
    title = " ".join(title_el.get_text().split()) if title_el else ""
    rows = table.find_all("tr")
    header = rows[0].find_all("td")
    n = len(header) - 6  # gray, empty, n players, 4 stat columns
    players, matrix = [], []
    for tr in rows[1:]:
        tds = tr.find_all("td")
        user = tr.select_one("td.c_table__tr__td--user a")
        if user is None:
            continue
        href = user.get("href", "")
        pid = href.rsplit("/", 1)[-1]
        name_el = user.select_one(".c_media__body")
        name = " ".join((name_el or user).get_text().split())
        place_el = tr.select_one("td.c_table__tr__td--num")
        place_txt = place_el.get_text().strip().rstrip(".") if place_el else ""
        place = int(place_txt) if place_txt.isdigit() else None
        hover = [td for td in tds if "c_table__tr__td--hover" in (td.get("class") or [])]
        scores = [cell_score(td) for td in hover[:n]]
        stats = [" ".join(td.get_text().split()) for td in hover[n:n + 4]]
        stats += [None] * (4 - len(stats))
        players.append({"id": pid, "name": name, "place": place,
                        "points_matches": stats[0], "points_place": stats[1],
                        "points_total": stats[2], "sets": stats[3]})
        matrix.append(scores)
    if len(players) != n:
        n = len(players)
        matrix = [row[:n] + [None] * (n - len(row)) for row in matrix]
    matches = []
    for i in range(n):
        for j in range(i + 1, n):
            s = matrix[i][j]
            if s is None:
                continue
            a, b = s.split(":")
            if a == "S" and b == "S":
                continue  # neither player showed up
            if "S" in (a, b):
                winner = players[i]["id"] if a != "S" else players[j]["id"]
                matches.append({"a": players[i]["id"], "b": players[j]["id"],
                                "sets_a": None, "sets_b": None,
                                "winner": winner, "walkover": True})
            else:
                sa, sb = int(a), int(b)
                if sa == sb:
                    continue
                matches.append({"a": players[i]["id"], "b": players[j]["id"],
                                "sets_a": sa, "sets_b": sb,
                                "winner": players[i]["id"] if sa > sb else players[j]["id"],
                                "walkover": False})
    return {"title": title, "players": players, "matches": matches}


def fetch_round(rnd: dict) -> dict:
    round_id = rnd["id"]
    page = get(f"{RESULTS}/{round_id}").text
    groups = []
    for result_id, group_id in parse_group_links(page, round_id):
        url = f"{RESULTS}/{round_id}?resultId={result_id}&groupId={group_id}&do=loadScore"
        r = get(url, ajax=True)
        try:
            payload = r.json()
        except ValueError:
            print(f"  round {round_id} group {result_id}{group_id}: not JSON, skipped", file=sys.stderr)
            continue
        html = payload.get("snippets", {}).get("snippet--resultsModal")
        if not html:
            print(f"  round {round_id} group {result_id}{group_id}: no snippet ({list(payload)})", file=sys.stderr)
            continue
        parsed = parse_scoreboard(html)
        if parsed is None:
            continue
        level_m = re.match(r"(\d+)\. úroveň", parsed["title"])
        groups.append({
            "result_id": result_id,
            "group": group_id,
            "level": int(level_m.group(1)) if level_m else None,
            "title": parsed["title"],
            "players": parsed["players"],
            "matches": parsed["matches"],
        })
    return {"round": rnd, "scraped": date.today().isoformat(), "groups": groups}


# --------------------------------------------------------------------------- main

def save_json(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(path)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--from-year", type=int, default=2016, help="oldest year to download")
    ap.add_argument("--refresh-latest", type=int, default=2,
                    help="always re-download this many most recent rounds")
    ap.add_argument("--refresh-all", action="store_true", help="re-download every round")
    ap.add_argument("--only", type=int, nargs="*", help="only these round ids")
    args = ap.parse_args(argv)

    rounds = fetch_rounds()
    save_json(DATA / "rounds.json", rounds)
    wanted = [r for r in rounds if r["year"] and r["year"] >= args.from_year]
    if args.only:
        wanted = [r for r in wanted if r["id"] in set(args.only)]
    latest_ids = {r["id"] for r in wanted[-args.refresh_latest:]}
    done = 0
    for rnd in wanted:
        path = RAW / f"{rnd['id']}.json"
        if path.exists() and not args.refresh_all and rnd["id"] not in latest_ids:
            continue
        print(f"round {rnd['id']}: {rnd['label']}", flush=True)
        data = fetch_round(rnd)
        n_matches = sum(len(g["matches"]) for g in data["groups"])
        print(f"  {len(data['groups'])} groups, {n_matches} matches", flush=True)
        save_json(path, data)
        done += 1
    print(f"downloaded {done} rounds, {len(wanted)} rounds in range")
    return 0


if __name__ == "__main__":
    sys.exit(main())
