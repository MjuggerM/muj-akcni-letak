# Muj akcni letak

Osobní filtr nad kupi.cz: sleduješ jen svoje položky, ve svých obchodech.
Backend staví na knihovně `kupiapi` (scraper kupi.cz). Frontend je Vite +
React + TS + Tailwind v4, se stejným designem jako náhled v chatu, ale
napojený na skutečná data z backendu (žádná mock pole).

## Než spustíš: ověř samotný scraper

Tohle je nejrychlejší způsob, jak zjistit, jestli kupiapi pořád umí
scrapovat kupi.cz - úplně mimo FastAPI a frontend:

```bash
cd backend
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python3 -c "from kupiapi.scraper import KupiScraper; import json; print(json.dumps(KupiScraper().get_discounts_by_search('vejce', max_pages=1), ensure_ascii=False, indent=2))"
```

- **Vrátí neprázdný JSON** → scraper žije, FastAPI a frontend níž ho jen
  přeposílají/zobrazují, spusť je normálně.
- **Spadne / vrátí `[]`** → buď síť (zkontroluj, že se z tvého stroje dá
  otevřít kupi.cz), nebo si kupi.cz mezitím předělalo HTML strukturu,
  kterou kupiapi parsuje (třídy jako `discount_price_value` v
  `kupiapi/scraper.py` - `pip show -f kupiapi` ti ukáže, kam se
  nainstalovala). To je oprava v kupiapi samotném, ne v tomhle projektu.

Tohle jsem ověřit nemohl - sandbox, ve kterém jsem tenhle projekt stavěl,
nemá do kupi.cz síťový přístup - takže tenhle krok je na tobě a je první
věc, kterou bych zkusil, kdyby appka po spuštění nic neukazovala.

## Spuštění backendu

```bash
cd backend
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

Endpointy: `GET /api/health`, `GET /api/stores`, `GET /api/offers?items=...&stores=...`.

## Spuštění frontendu

```bash
cd frontend
cp .env.example .env
npm install
npm run dev
```

Poběží na `http://localhost:5173`, volá backend na `http://localhost:8000`
(nastavitelné v `.env` přes `VITE_API_URL`).

## Ověřeno vs. neověřeno

Reálně otestováno v sandboxu: backend (import, `/api/stores`, `/api/offers`
s mockovaným scraperem, zip/flatten logika, souběžné stahování), a
frontend (`npm run build` přes Tailwind v4 + TS, žádné typové chyby).
Jediná věc, kterou jsem odsud nemohl ověřit, je živé volání
`KupiScraper` → kupi.cz (síť v sandboxu tam nepustí) - proto sekce výše.

## Co má smysl vědět, než na to navážeš

- **Ikony obchodů**: kupiapi vrací jen textový název obchodu (např. "Albert
  hypermarket"), žádné logo/ID. `StoreIcon` je barevná tečka podle
  přibližné brand barvy obchodu (`components/StoreIcon.tsx`) - ne skutečné
  logo. Reálná loga by šlo dodat, ale hotlinkování cizích brand assetů má
  vlastní rizika (rozbije se, když si to přesunou); zatím jsem to neřešil.
- **`validity` se neparsuje na datum**: kupi.cz k tomu používá nekonzistentní
  fráze ("dnes končí", "po 10. 8. - ne 16. 8.", "platí do úterý 11. 8.").
  Posílám to na frontend jako čitelný text tak, jak to vrátí kupiapi, místo
  abych to nespolehlivě parsoval na `Date`.
- **"Upozornění" je zatím jen banner v appce** (kolik sledovaných položek
  je právě v akci), ne push notifikace mimo prohlížeč – to by chtělo
  Notification API / service worker navíc, což jsem do "základního
  zapojení" nepočítal.
- **Preference (sledované položky, vybrané obchody) žijí jen v
  `localStorage`** prohlížeče – žádný účet, žádná DB. Stačí to pro
  jednoho uživatele na jednom zařízení; pro víc zařízení by to chtělo
  backendové úložiště.
- **Cache**: výsledky hledání se drží 20 minut v paměti backendu
  (`CACHE_TTL_SECONDS` v `config.py`), aby se kupi.cz nescrapoval při
  každém refreshi frontendu.
- Scraper je závislý na HTML struktuře kupi.cz (třídy jako
  `discount_price_value`, `discount_amount`...) – když si kupi.cz předělá
  frontend, `kupiapi` se rozbije a je to mimo tenhle projekt opravit.
