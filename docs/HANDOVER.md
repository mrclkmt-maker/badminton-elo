# Badminton ELO Praha – handover

Stav k 2. 11. 2026. Pro navazující práci (člověk i Claude).

## Co to je

Neoficiální ELO žebříček hráčů badmintonové ligy VAŠE LIGA Praha
(https://www.vaseliga.cz/vysledky/badminton/praha). Data se stahují z veřejných
výsledkových stránek portálu, ELO se počítá lokálně, web je statický a běží na
GitHub Pages. Majitel: Marcel (mrclkmt-maker), repozitář github.com/mrclkmt-maker/badminton-elo.

Rozhodnutí Marcela (2. 11. 2026):
- hosting GitHub Pages, později vlastní doména;
- historie od roku 2016 (zahrnuto i kolo leden 2016, které patří do podzimní sezóny 2015);
- hráči se skrytým jménem zůstávají skrytí i na webu (portál ukazuje jméno po přihlášení, to nepoužíváme);
- vzhled a název webu se řeší až nakonec, zatím co nejjednodušší;
- u každého hráče graf vývoje ELO v čase.

## Struktura

```
src/badminton_elo/scrape.py       stahování (requests + BeautifulSoup)
src/badminton_elo/elo.py          výpočet ELO -> data/elo.json
src/badminton_elo/build_site.py   generování webu (Jinja2) -> site/
src/badminton_elo/templates/      base.html, index.html, player.html (CSS je v base.html)
data/rounds.json                  seznam všech kol z rozbalovací nabídky portálu (id, label, rok, měsíc, pořadí)
data/raw/<round_id>.json          skupiny, hráči a zápasy jednoho kola
data/elo.json                     výsledek výpočtu (hráči, historie, zápasy) – generovaný, ale verzovaný
.github/workflows/update.yml      denní aktualizace + nasazení na Pages
```

Python přes `uv` (`uv sync`, `uv run ...`). Na Windows spouštět s `python -X utf8`, jinak padá výpis českých znaků.

## Jak portál funguje (zjištěno 2. 11. 2026)

- Seznam kol je v `<select id="fn_round_result-select">` na stránce výsledků; hodnota option = id kola
  (např. 824 = Podzimní sezóna 2026, 1. kolo, říjen). Id nejsou souvislá, pořadí bereme z nabídky.
- Stránka kola: `/vysledky/badminton/praha/<round_id>` – obsahuje odkazy na skupiny
  `?resultId=<úroveň-1>&groupId=<A|B|C>&do=loadScore`.
- Výsledky skupiny: stejný odkaz s hlavičkou `X-Requested-With: XMLHttpRequest` vrací JSON (Nette snippet
  `snippet--resultsModal`) s tabulkou každý s každým. Bez session cookie vrací jen `redirect`, proto se nejdřív
  načte obyčejná stránka výsledků (cookie se pak hodí pro všechna kola).
- Buňka tabulky: `3:0`, `3:1`, `3:2` (sety), `3:S`/`S:3` = skreč, `S:S` = nedostavili se oba, prázdná = neodehráno.
  Pokud je u zápasu komentář, je skóre zabalené v `<div title="Zobrazit komentáře">` – komentáře nestahujeme.
- Id hráče = poslední část odkazu `/hrac/<id>`: slug (`stanislav-sipka`) u veřejných jmen, číslo (`12408`)
  u hráčů se skrytým jménem. Vedle skrytého jména portál v popoveru (`data-content`) uvádí plné jméno – záměrně
  ho ignorujeme.
- Skupiny mají typicky 5 hráčů, výjimečně 4 nebo 6. Úrovně 1–23, skupiny A–C.
- robots.txt zakazuje jen `/api/`. Stahujeme s prodlevou 0,5 s mezi požadavky; celé kolo ≈ 1 minuta,
  10 let historie ≈ 2 hodiny.
- Kola 360 (březen-duben 2020) a 501 (říjen-prosinec 2020) mají v názvu rozsah měsíců; bere se první měsíc.

## Metoda ELO (elo.py)

- start = 1500 + (12 − úroveň první skupiny) × 30 (1. úroveň 1830, 23. úroveň 1170);
- zápasy po kolech, v rámci kola se počítá se vstupním hodnocením ze začátku kola (data zápasů portál neuvádí);
- K = 48 pro prvních 20 hodnocených zápasů, pak 32;
- násobek podle setů: 3:0 × 1,0, 3:1 × 0,9, 3:2 × 0,8;
- skreče se nehodnotí, jen počítají ve statistice;
- „aktivní“ hráč = hrál v posledních 12 měsících; jen ti jsou v hlavním žebříčku (index.html),
  všichni jsou ve vsichni.html.

Změna parametrů = upravit konstanty v elo.py a text v sekci „O žebříčku“ v index.html (čísla se tam doplňují
z `method`, slovní popis násobků je napevno).

## Automatizace

Workflow `update.yml`: denně 03:17 UTC, ručně (workflow_dispatch) a při pushi do main.
Kroky: stáhnout chybějící kola + znovu 2 poslední → ELO → web → commit změn v `data/` zpět do main
(push přes GITHUB_TOKEN nespouští další běh) → nasazení na Pages (`actions/deploy-pages`).
Pages je nastaveno na zdroj „GitHub Actions“ (build_type workflow). Bez tajných klíčů.

Pokud by portál změnil HTML, spadne krok stahování a Marcelovi přijde e-mail o neúspěšném běhu.

## Známá omezení

- Pokud si hráč skryje jméno až později, dostane na portálu jiný (číselný) id a u nás vznikne nový hráč;
  spojit je bez skrytého jména neumíme.
- Jméno hráče se bere z posledního staženého kola, kde hrál. Starší kola se znovu nestahují
  (`--refresh-all` to umí, trvá to ale 2 hodiny).
- Výsledky doplněné do starších kol se zpětně dostanou do dat jen při `--refresh-all`
  (denně se obnovují jen 2 poslední kola).
- Portál neuvádí data zápasů, proto jsou všechny zápasy kola brány „současně“.

## Další kroky

1. Vlastní doména: v repozitáři přidat soubor `site/CNAME` (generovat v build_site.py) a nastavit DNS
   (CNAME na mrclkmt-maker.github.io), v nastavení Pages zadat doménu.
2. Vzhled a název webu (zatím „Badminton ELO Praha“ – konstanta SITE_NAME v build_site.py).
3. Případně: žebříček žen/mužů (portál pohlaví neuvádí, musel by se brát z jeho žebříčku), srovnání s body portálu.
