# Muj akcni letak

Osobní filtr nad kupi.cz: sleduješ jen svoje položky, ve svých obchodech.
Backend parsuje stránky Kupi.cz přímo, včetně obrázků produktů. Frontend je Vite +
React + TS + Tailwind v4, se stejným designem jako náhled v chatu, ale
napojený na skutečná data z backendu (žádná mock pole).

## Ověření scraperu

Tento příkaz ověří připojení ke Kupi.cz a parsování nabídek i jejich obrázků:

```bash
cd backend
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python -c "from app.kupi_service import _fetch_one_sync; import json; print(json.dumps(_fetch_one_sync('vejce'), ensure_ascii=False, indent=2))"
```

- **Vrátí nabídky** → Kupi scraper funguje; adresy dostupných obrázků jsou v poli
  `image_url`.
- **Vrátí `[]` nebo chybu** → ověř přístup k `kupi.cz`. Pokud Kupi změnilo HTML,
  uprav parser v `backend/app/kupi_service.py`.

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

Poběží na `http://localhost:3000`, volá backend na `http://localhost:8000`
(nastavitelné v `.env` přes `VITE_API_URL`).

## Ověřeno vs. neověřeno

Backendové testy pokrývají parsování nabídek a obrázků, FE ověřuje
`npm run build`.

## Co má smysl vědět, než na to navážeš

- **Ikony obchodů**: Kupi vrací jen textový název obchodu (např. "Albert
  hypermarket"), žádné logo/ID. `storeColors` je barevná tečka podle
  přibližné brand barvy obchodu (`components/storeColors.ts`) - ne skutečné
  logo. Reálná loga by šlo dodat, ale hotlinkování cizích brand assetů má
  vlastní rizika (rozbije se, když si to přesunou); zatím jsem to neřešil.
- **`validity` se neparsuje na datum**: kupi.cz k tomu používá nekonzistentní
  fráze ("dnes končí", "po 10. 8. - ne 16. 8.", "platí do úterý 11. 8.").
  Posílám to na frontend jako čitelný text tak, jak ho vrátí Kupi, místo
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
- Parser je závislý na HTML struktuře kupi.cz (třídy jako
  `discount_price_value`, `discount_amount`...) – když ji Kupi změní, uprav
  `backend/app/kupi_service.py`.
