# Badminton ELO Praha

Neoficiální ELO žebříček hráčů pražské badmintonové ligy na portálu
[VAŠE LIGA](https://www.vaseliga.cz/vysledky/badminton/praha), počítaný z veřejně
zobrazených výsledků jednotlivých kol od ledna 2016.

Web se generuje jako statické stránky a publikuje na GitHub Pages. Jednou denně
(GitHub Actions) se stáhnou nové výsledky, přepočítá se ELO a web se znovu nasadí.

## Jak to funguje

| Krok | Příkaz | Co dělá |
|---|---|---|
| 1 | `uv run python -X utf8 -m badminton_elo.scrape` | stáhne chybějící kola (a vždy znovu 2 poslední) do `data/raw/` |
| 2 | `uv run python -X utf8 -m badminton_elo.elo` | spočítá ELO ze všech stažených kol do `data/elo.json` |
| 3 | `uv run python -X utf8 -m badminton_elo.build_site` | vygeneruje web do `site/` |

Lokální náhled: `python -m http.server 8765 --directory site` a otevřít http://localhost:8765.

Podrobnosti (metoda výpočtu, rozhodnutí, známá omezení) jsou v [docs/HANDOVER.md](docs/HANDOVER.md).
