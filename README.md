# Scan Pret — Price Intelligence Platform

Platformă web pentru monitorizarea și compararea prețurilor produselor de la competitori, cu motor de asociere AI și scraping automatizat.

---

## Cuprins

1. [Prezentare generală](#1-prezentare-generală)
2. [Arhitectură](#2-arhitectură)
3. [Flux de lucru](#3-flux-de-lucru)
4. [Instalare](#4-instalare)
5. [Configurare](#5-configurare)
6. [Module principale](#6-module-principale)
7. [Web Scraping](#7-web-scraping)
8. [Asociere AI](#8-asociere-ai)
9. [Motor de matching](#9-motor-de-matching)
10. [API intern](#10-api-intern)
11. [Optimizări recomandate](#11-optimizări-recomandate)
12. [Troubleshooting](#12-troubleshooting)

---

## 1. Prezentare generală

**Scan Pret** este o aplicație Flask care rezolvă problema fundamentală a retailerilor: *"Cu cât vinde competitorul același produs?"*

### Ce face

```
Competitori (URL/CSV/Scraping)
        ↓
  Date brute importate
        ↓
  Curatare + Normalizare
        ↓
  Matching automat (regex + AI)
        ↓
  Asocieri confirmate → Preț preluat
        ↓
  Export CSV / Dashboard
```

### Funcționalități cheie

| Funcție | Descriere |
|---------|-----------|
| **Import CSV** | Import flexibil cu mapare automată a coloanelor |
| **Web Scraping** | Extrage date din sitemap-uri XML + CSS selectors cu anti-bot |
| **Curățare date** | Detectează și elimină HTML, URL-uri, caractere invalide din câmpuri |
| **Curățare SKU** | Elimină prefixe gen `COD:`, `SKU:`, `Cod produs:` în batch |
| **Matching regex** | Motor de scoring pe SKU, model tehnic, brand, categorie |
| **Asociere AI** | OpenAI / Anthropic / DeepSeek pentru potrivire automată |
| **Procesare batch** | Asociere AI pentru sute de produse simultan |
| **Alerte preț** | Notificare când prețul scade sub un prag setat |
| **Istoric prețuri** | Grafic evoluție preț per produs |
| **Export CSV** | Export cu prețuri preluate și asocieri confirmate |

---

## 2. Arhitectură

### Stack tehnic

| Layer | Tehnologie |
|-------|-----------|
| Backend | Python 3.13 + Flask 3.0 (Blueprint architecture) |
| ORM | SQLAlchemy 3.1 + Flask-Migrate |
| Baza de date | SQLite (prod: recomandăm PostgreSQL) |
| Web Scraping | requests + BeautifulSoup4 + lxml + price_parser |
| AI | OpenAI SDK, Anthropic SDK, DeepSeek (API compatibil OpenAI) |
| Date | pandas (import/export CSV) |
| Securitate | Flask-WTF (CSRF) + Flask-Limiter (rate limiting) |
| Frontend | Bootstrap 5.3 + Font Awesome 6.5 + Vanilla JS |
| Logging | Python RotatingFileHandler (4 fișiere separate) |

### Structura proiectului

```
scan-pret/
├── app/
│   ├── __init__.py              # create_app(), blueprint registration
│   ├── extensions.py            # db, csrf, limiter, migrate
│   ├── logging_setup.py         # 4 log streams: app, access, error, audit
│   ├── models/
│   │   ├── competitor.py        # Competitor (cod, URL, display_name, price_selector)
│   │   ├── competitor_product.py# Produse (SKU, titlu, pret, brand, asociere, alerte)
│   │   ├── price_history.py     # Istoric prețuri (product_id, pret, recorded_at, sursa)
│   │   ├── notification.py      # Notificări (titlu, mesaj, nivel, read)
│   │   ├── ai_config.py         # Configurare AI (provider, model, API key, prompt)
│   │   ├── search_config.py     # Parametri matching (scoruri, threshold-uri)
│   │   ├── scraping_config.py   # Config scraping per competitor (CSS, delay, retry)
│   │   ├── scraping_url.py      # Queue URL-uri (status: pending/scraped/error)
│   │   ├── scraping_log.py      # Jurnal job-uri scraping
│   │   └── excluded_association.py # Perechi produse excluse din asociere
│   ├── routes/
│   │   ├── dashboard.py         # GET / → statistici
│   │   ├── competitors.py       # CRUD competitori + test selector
│   │   ├── import_export.py     # Import CSV (pandas) + Export CSV
│   │   ├── products.py          # CRUD produse + asociere + alerte + history
│   │   ├── search.py            # Căutare full-text + asociere manuală
│   │   ├── search_config.py     # Configurare parametri matching
│   │   ├── ai_association.py    # Workbench AI + batch processing + config AI
│   │   ├── cleanup.py           # Curățare date + curățare prefix SKU
│   │   ├── scraping.py          # Config scraping + job management + logs
│   │   └── notifications.py     # Listare + marcare citite
│   ├── services/
│   │   ├── competitor_service.py    # Normalizare URL, generare cod intern
│   │   ├── csv_import_service.py    # Parse CSV, validare, import cu deduplicare
│   │   ├── csv_export_service.py    # Export per competitor
│   │   ├── ai_service.py            # Interfață unificată AI (build_prompt, call_ai, parse)
│   │   ├── association_service.py   # find_candidates(), sync_pret_preluat()
│   │   ├── matching_service.py      # Motor scoring: SKU, model tehnic, brand
│   │   ├── product_search_service.py# build_query() cu filtre multiple
│   │   ├── cleanup_service.py       # Detectare HTML/URL/filepath în câmpuri
│   │   ├── scraper_service.py       # Scraping simplu CSS selector
│   │   ├── web_scraping_service.py  # Scraping avansat: sitemap, session, retry, anti-bot
│   │   └── notification_service.py  # CRUD notificări
│   └── utils/
│       ├── normalizers.py       # normalize_price() cu price_parser + fallback regex
│       ├── helpers.py           # normalize_text(), safe_filename()
│       └── logging_helpers.py   # audit(), app_log() wrappers
├── config.py                    # Configurare aplicație (din .env)
├── run.py                       # Entry point
├── requirements.txt
└── .env.example
```

### Schema baza de date

```
competitors
  id, internal_code*, source_url*, source_host*, display_name, price_selector, is_active

competitor_products
  id, cod_competitor[idx], sku[idx], title[idx], pret, brand[idx], descriere
  url, asociere (TEXT: "1;2;3"), pret_alerta, pret_preluat, pret_preluat_sursa
  pret_preluat_asociat_id, categorie[idx], imported_at[idx], created_at, updated_at

price_history
  id, product_id[idx], pret, recorded_at[idx], sursa (import|scraper|manual)

scraping_configs
  id, competitor_code*, sources (JSON), url_filter
  sel_sku, sel_title, sel_pret, sel_brand, sel_descriere, sel_categorie
  delay, randomize_delay, timeout, max_retries, retry_delay, user_agent
  respect_robots, block_resources

scraping_urls
  id, competitor_code[idx], url*, status (pending|scraped|error)
  product_id, error_msg, scraped_at

scraping_logs
  id, competitor_code[idx], job_id[idx], status, message, url, duration_ms, created_at

excluded_associations
  id, product_id[idx], excluded_product_id[idx], created_at

ai_config, search_config, notifications  ← tabele de configurare/utilitate
```

---

## 3. Flux de lucru

### Pasul 1 — Adăugare competitori

```
/competitors → Adaugă URL competitor
  ↓
competitor_service.py normalizează URL-ul, extrage host
  ↓
Generează cod intern: CMP001, CMP002, ...
  ↓
Salvare în DB
```

### Pasul 2 — Import date (CSV sau Scraping)

**Via CSV:**
```
/io/import → Upload fișier CSV (max 25MB)
  ↓
pandas parsează + detectează encoding
  ↓
Mapare flexibilă coloane (sku, title, pret, brand, url, etc.)
  ↓
csv_import_service: validare, normalizare preț, deduplicare SKU
  ↓
Dacă prețul s-a schimbat față de import anterior → PriceHistory entry
  ↓
Dacă pret <= pret_alerta → Notificare warning
```

**Via Web Scraping:**
```
/scraping/<code> → Tab 1: Analizează sitemap XML
  ↓
fetch_sitemap_urls(): parsează XML, filtrează imagini/media
  ↓
Salvare în scraping_urls (status: pending)
  ↓
Tab 3: Configurează CSS selectors (sau auto-discover cu JSON-LD/microdata)
  ↓
Tab 4: Pornește job → background thread
  ↓
Pentru fiecare URL: scrape_product_page() cu session HTTP persistentă
  ↓
Creează/actualizează CompetitorProduct + PriceHistory
```

### Pasul 3 — Curățare date

```
/cleanup → Scanează toate câmpurile
  ↓
Detectează: taguri HTML, URL-uri brute, cale fișier, entități HTML
  ↓
Preview diff înainte/după per produs
  ↓
Aplicare selectivă (per produs) sau bulk

/cleanup → Secțiunea "Curățare prefix SKU"
  ↓
Preseturi: COD, COD PRODUS, SKU, Cod articol, Nr. art, Ref, ...
  ↓
sau câmp custom → regex case-insensitive + separatori automați
  ↓
Preview câte SKU-uri sunt afectate + exemple
  ↓
Aplicare cu confirmare
```

### Pasul 4 — Asociere produse

**Manuală:**
```
/search → Caută produs din competitorul tău
  ↓
Selectează un rezultat → buton "Asociază"
  ↓
association_service: scrie ID-ul în câmpul asociere al ambelor produse
```

**AI (per produs):**
```
/ai/associate/<id> → Workbench
  ↓
find_candidates(): OR ILIKE pe title/sku/brand → candidați brut
  ↓
rank_candidates(): scoring SKU exact/partial + model tehnic + brand + categorie
  ↓
Build prompt cu sursa + candidați rankaști + template custom
  ↓
call_ai() → OpenAI / Anthropic / DeepSeek
  ↓
parse_ai_response(): extrage matched_ids, confidence, reason
  ↓
User confirmă → salvare asocieri
```

**AI batch:**
```
/products/ai-batch → Selectează produse din tabel
  ↓
/products/ai-batch/run → pentru fiecare produs, apel AI individual
  ↓
UI agregat cu rezultate + confidence per produs
  ↓
/products/ai-batch/confirm → salvează asocierile confirmate
```

### Pasul 5 — Preluare preț

```
Deschide produs → tab "Asociate"
  ↓
Listează produsele asociate cu prețurile lor
  ↓
Click "Preia preț" pe produsul dorit
  ↓
product.pret_preluat = asociat.pret
product.pret_preluat_sursa = asociat.cod_competitor
```

### Pasul 6 — Export

```
/io/export → Selectează competitor
  ↓
Exportă CSV cu: sku, title, pret, pret_preluat, pret_preluat_sursa,
                brand, descriere, url, asociere, imported_at
```

---

## 4. Instalare

### Cerințe

- Python 3.11+
- pip
- Git

### Windows

```bash
git clone <repo-url>
cd scan-pret

python -m venv venv
venv\Scripts\activate

pip install -r requirements.txt

copy .env.example .env
# Editează .env cu setările tale

python migrate_db.py     # inițializează schema DB
python run.py            # pornește serverul
```

### Linux / macOS

```bash
git clone <repo-url>
cd scan-pret

python3 -m venv venv
source venv/bin/activate

pip install -r requirements.txt

cp .env.example .env
nano .env

python migrate_db.py
python run.py
```

Aplicația pornește la `http://127.0.0.1:5055`

---

## 5. Configurare

### `.env`

```ini
SECRET_KEY=schimba-asta-cu-o-cheie-aleatoare-lunga
DEBUG=false
HOST=127.0.0.1
PORT=5055
DATABASE_URL=sqlite:///instance/scan_pret.db
LOG_LEVEL=INFO
```

### Configurare AI (`/ai/config`)

| Câmp | Descriere |
|------|-----------|
| Provider | `openai` / `anthropic` / `deepseek` |
| Model | `gpt-4o-mini`, `claude-3-haiku-20240307`, `deepseek-chat` |
| API Key | Cheia API a providerului |
| Prompt template | Template Jinja2 pentru construirea promptului AI |
| Confidence threshold | Scor minim acceptat (default: 0.6) |

### Configurare Matching (`/search-config`)

| Parametru | Default | Descriere |
|-----------|---------|-----------|
| `min_score_filter` | 0.3 | Scor minim pentru a include un candidat |
| `sure_match_threshold` | 0.85 | Scor pentru potrivire sigură (fără confirmare AI) |
| `sku_exact_score` | 1.0 | Scor pentru SKU identic |
| `sku_partial_score` | 0.85 | Scor pentru SKU parțial |
| `model_match_score` | 0.80 | Scor pentru model tehnic comun |
| `brand_bonus` | 0.10 | Bonus brand identic |
| `category_bonus` | 0.05 | Bonus categorie identică |
| `candidate_limit` | 10 | Număr maxim candidați trimiși la AI |

### Configurare Scraping (`/scraping/<code>`)

| Parametru | Default | Descriere |
|-----------|---------|-----------|
| Delay | 1.0s | Pauza între requesturi |
| Randomize delay | Da | Variație ±50% a delay-ului |
| Timeout | 15s | Timeout per request |
| Max retries | 2 | Reîncercări la 429/5xx |
| Retry delay | 5s | Pauza între reîncercări |
| User-Agent | rotație auto | 5 UA-uri reale de browser |
| Respect robots.txt | Nu | Respectă regulile robots.txt |
| Blochează resurse | Da | Header Accept: text/html only |

---

## 6. Module principale

### `normalize_price()` — `app/utils/normalizers.py`

Normalizează orice format de preț românesc/internațional la `float`:

```python
normalize_price("40,00 lei")    # → 40.0
normalize_price("1.234,56")     # → 1234.56
normalize_price("4.999 lei")    # → 4999.0  (punct = separator mii în RO)
normalize_price("€ 1,234.56")   # → 1234.56 (format american)
```

Folosește `price_parser` (библиотеca specializată) cu fallback regex.

### `_is_page_url()` — `app/services/web_scraping_service.py`

Filtrează URL-urile non-HTML dintr-un sitemap:

```python
_is_page_url("https://site.ro/produs/ventilator")  # → True
_is_page_url("https://site.ro/img/foto.jpg")        # → False
_is_page_url("https://site.ro/doc.pdf")             # → False
```

Recunoaște 40+ extensii de fișiere media, documente, arhive, scripturi.

### `make_session()` — `app/services/web_scraping_service.py`

Creează o sesiune HTTP cu headers browser-like complete:

```python
session = make_session(
    user_agent="Mozilla/5.0 ...",   # None = rotație automată
    base_url="https://site.ro",      # Setează Referer
    block_resources=True,            # Accept: text/html only
)
```

Include: `Sec-Fetch-*`, `DNT`, `Cache-Control`, `Upgrade-Insecure-Requests`, `Referer`.

### `find_candidates()` — `app/services/association_service.py`

Găsește candidați pentru asociere AI:

```python
candidates = find_candidates(
    source_product,
    target_competitors=["CMP001", "CMP002"],  # None = toți
)
# Returnează lista de {product, competitor, match_score}
# Rankatstă descrescător după score
```

### `score_pair()` — `app/services/matching_service.py`

Calculează scorul de similaritate între două produse:

```
SKU exact → 1.0
SKU parțial (după normalizare) → 0.85
Model tehnic comun (regex extracție) → 0.80
Brand identic → +0.10
Categorie identică → +0.05
```

---

## 7. Web Scraping

### Fluxul complet

```
1. Adaugă URL sitemap în Tab 1
2. "Analizează" → fetch_sitemap_urls()
   - Parse XML cu lxml
   - Exclude <image:loc>, <video:loc> (namespace)
   - Filtrează extensii media cu _is_page_url()
   - Aplică regex filtru URL dacă e setat
3. URL-urile trec în scraping_urls (status: pending)
4. Tab 2 → "Curăță media" → șterge resturile dacă e nevoie
5. Tab 3 → Configurează selectori CSS
   - Manual: introduci selectorul
   - Auto-discover: extrage din JSON-LD/microdata/OpenGraph + CSS hints
6. Tab 4 → Pornește job
   - Opțiuni: include erori, ordine aleatoare
   - Job rulează în background thread
   - Polling la 1.5s → log live + progress bar
7. Post-job: verificare automată
   - Detectează titluri generice (Home, 404, Blocked, Captcha...)
   - Detectează produse fără preț
   - Propune re-coadare suspecte → pending
```

### Tehnici anti-bot implementate

| Tehnică | Implementare |
|---------|-------------|
| User-Agent rotație | 5 UA-uri reale de browser |
| Headers browser-like | Sec-Fetch-*, DNT, Cache-Control, Upgrade-Insecure-Requests |
| Referer | Setat la rădăcina site-ului |
| Delay randomizat | delay × uniform(0.5, 1.5) |
| Session persistentă | TCP keep-alive + cookie retention per job |
| Retry inteligent | Backoff la 429, reîncercare la 5xx |
| Block resources | Accept: text/html → reduce 404 imagini |

### CSS Selectors — Auto-discover

Auto-discover funcționează în 2 nivele:
1. **JSON-LD / Microdata / OpenGraph** via `extruct` — cel mai precis
2. **CSS hints** — o listă de selectori candidați per câmp, validați cu `price_parser`

---

## 8. Asociere AI

### Prompt template

Promptul implicit trimite AI-ului:
- Produsul sursă (SKU, titlu, brand, descriere)
- Lista de candidați rankaști (cu scoruri)
- Instrucțiuni de răspuns JSON strict

Răspunsul așteptat:
```json
{
  "matched_ids": ["42", "87"],
  "confidence": 0.92,
  "reason": "SKU identic normalizat, brand confirmat"
}
```

### Providers suportați

| Provider | Model recomandat | Note |
|----------|-----------------|-------|
| OpenAI | gpt-4o-mini | Cel mai rapid și ieftin |
| Anthropic | claude-3-haiku-20240307 | Context lung, înțelegere bună |
| DeepSeek | deepseek-chat | API compatibil OpenAI, ieftin |

### Rate limiting

- `/ai/associate/<id>/run` — 20 req/min per IP
- Recomandare: adaugă delay de 1-2s între apeluri batch

---

## 9. Motor de matching

### Extracție model tehnic

```python
extract_model("Ventilator FTXP25M/RXP25M 9000 BTU")
# → ["FTXP25M", "RXP25M", "9000BTU"]
```

Pattern-uri recunoscute:
- Modele HVAC: `FTXP25`, `KFR-35GW`, `MSZ-AP25VGK`
- Modele cu cifre+litere: `35GW`, `25VGK`
- Capacitate: `18000BTU`, `2.5kW`

### Normalizare SKU

```python
normalize_sku("RO-FTXP25M/EU")  # → "FTXP25M"
normalize_sku("SKU_ITEM-B2B")   # → "SKUITEM"
```

Elimină:
- Prefixe distribuitor: `RO-`, `EU-`, `INT-`, `B2B-`
- Sufixe: `-A`, `-NEW`, `-V2`, `-RO`
- Separatori: `-`, `/`, `_`, `.`, spații

---

## 10. API intern

Toate endpoint-urile AJAX returnează JSON. Principalele:

### Produse

```
GET  /products/                           # Listare paginată
POST /products/bulk-delete                # {"ids": [1,2,3]}
POST /products/<id>/edit                  # {...câmpuri...}
GET  /products/<id>/asociate              # Produse asociate + meta
GET  /products/<id>/price-history         # Istoric prețuri
POST /products/<id>/scrape                # Scrape preț manual
POST /products/<id>/pret-preluat          # {"asociat_id": 42}
POST /products/<id>/exclude               # {"excluded_id": 87}
POST /products/ai-batch/run              # {"product_id": 1, "target_competitors": [...]}
POST /products/ai-batch/confirm          # {"results": [{product_id, matched_ids}]}
```

### Scraping

```
POST /scraping/<code>/analyze-sitemap    # {"sitemap_url": "...", "url_filter": "...", "replace": false}
GET  /scraping/<code>/urls               # ?page=1&status=pending
POST /scraping/<code>/urls/reset         # {"which": "errors|scraped|all|suspicious"}
POST /scraping/<code>/urls/clean-media   # Șterge URL-uri media din DB
GET  /scraping/<code>/verify             # Verificare post-job
POST /scraping/<code>/start              # {"include_errors": true, "random_order": false}
POST /scraping/<code>/stop               # Oprire job
GET  /scraping/<code>/status             # ?offset=N → {status, progress[], stats}
GET  /scraping/<code>/logs               # ?job_id=...&limit=500
POST /scraping/<code>/logs/delete        # {"job_id": "..."} sau {} pentru toate
GET  /scraping/<code>/logs/jobs          # Lista job-uri
POST /scraping/<code>/test               # {"url": "...", "sel_title": "...", ...}
POST /scraping/<code>/discover           # {"url": "..."} → selectori auto
```

### Curățare

```
POST /cleanup/sku-strip/preview          # {"prefix": "COD", "competitor": "CMP001"}
POST /cleanup/sku-strip/apply            # {"prefix": "COD", "competitor": ""}
```

---

## 11. Optimizări recomandate

Acestea sunt limitări arhitecturale cunoscute, specifice sistemelor de tip price intelligence:

### 🔴 Critice (impact direct pe funcționalitate la scală)

#### 1. Baza de date: SQLite → PostgreSQL

**Problema**: SQLite nu suportă scrieri concurente. Thread-ul de scraping + requesturile web concurente generează `database is locked`.

**Soluție**:
```bash
pip install psycopg2-binary
# În .env:
DATABASE_URL=postgresql://user:pass@localhost/scan_pret
```

SQLite rămâne ok pentru < 50K produse și utilizator singur.

#### 2. `asociere` ca string delimiter

**Problema**: `asociere = "1;2;3"` este un anti-pattern relational.
- Query-urile `IN` necesită split Python → nu se pot face JOIN-uri native
- Nu există integritate referențială (un produs șters lasă ID mort în string)
- `sync_pret_preluat()` face query separat pentru fiecare produs

**Soluție**: Tabel de asociere `product_associations(product_id, associated_id, created_at)`.

#### 3. Job state in-memory

**Problema**: `_jobs = {}` în `scraping.py` se pierde la restart server. Un job activ devine orfan.

**Soluție**: Persistă starea job-ului în DB (`scraping_jobs` tabel cu status, started_at, last_heartbeat).

---

### 🟡 Importante (impact la 10K+ produse)

#### 4. Query-uri N+1 în cleanup

**Problema**: `/cleanup/` face `CompetitorProduct.query.all()` → toate în memorie → `clean_product()` per produs.

**Soluție**: Paginare server-side + procesare streaming, sau index pe câmpuri cu probleme frecvente.

#### 5. `find_candidates()` cu OR ILIKE

**Problema**: La 100K+ produse, OR ILIKE pe title/sku/brand este lent (full table scan).

**Soluție**:
- **SQLite**: Activează FTS5 (full-text search) cu trigger pe `competitor_products`
- **PostgreSQL**: `tsvector` + `GIN index` pe `(title, sku, brand)`

#### 6. Index compus lipsă

```sql
-- Adaugă acestea:
CREATE INDEX idx_cp_competitor_sku ON competitor_products(cod_competitor, sku);
CREATE INDEX idx_cp_competitor_status ON scraping_urls(competitor_code, status);
```

#### 7. Polling la 1.5s pentru scraping

**Problema**: Fiecare client face 1 request la 1.5s → 40 req/min per utilizator.

**Soluție**: Server-Sent Events (SSE) — serverul împinge update-uri, clientul ascultă:
```python
@app.route('/scraping/<code>/stream')
def stream(code):
    def generate():
        while job_running:
            yield f"data: {json.dumps(get_progress())}\n\n"
            time.sleep(2)
    return Response(generate(), mimetype='text/event-stream')
```

---

### 🟢 Nice-to-have

#### 8. Criptare API keys AI

**Problema**: Cheile AI sunt stocate plaintext în DB.

**Soluție**: Folosește `cryptography` (deja în requirements):
```python
from cryptography.fernet import Fernet
key = Fernet.generate_key()  # stochează în .env
fernet = Fernet(key)
encrypted = fernet.encrypt(api_key.encode())
```

#### 9. Proxy rotation pentru scraping agresiv

Pentru site-uri cu detectare IP:
```python
proxies = {"http": "http://proxy:port", "https": "http://proxy:port"}
session.get(url, proxies=proxies)
```

#### 10. JavaScript rendering

Unele site-uri randează prețul în JS (React, Vue). `requests` nu execută JS.

**Soluție**: `playwright` pentru pagini JS-heavy:
```python
from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    browser = p.chromium.launch()
    page = browser.new_page()
    page.goto(url)
    price = page.locator(selector).text_content()
```

#### 11. Celery pentru job-uri asincrone

**Problema**: Scraping rulează în thread daemon → crash aplicație = job pierdut.

**Soluție**: Celery + Redis:
```python
@celery.task
def scrape_competitor(code):
    ...
```

#### 12. Debounce frontend

**Problema**: Filtrele din tabelul de produse trimit request la fiecare keystroke.

**Soluție**:
```javascript
let debounceTimer;
input.addEventListener('input', () => {
    clearTimeout(debounceTimer);
    debounceTimer = setTimeout(() => loadProducts(), 300);
});
```

#### 13. Logging structurat (JSON)

**Problema**: Log-urile text sunt greu de analizat programatic.

**Soluție**:
```python
import json, logging
class JsonFormatter(logging.Formatter):
    def format(self, record):
        return json.dumps({
            "ts": self.formatTime(record),
            "level": record.levelname,
            "msg": record.getMessage(),
            "module": record.module,
        })
```

---

## 12. Troubleshooting

### `database is locked`

Cauză: scraping thread + request web scriu simultan.

```python
# În config.py, adaugă:
SQLALCHEMY_ENGINE_OPTIONS = {
    "connect_args": {"timeout": 30},
    "pool_timeout": 30,
}
```

Soluție permanentă: migrează la PostgreSQL.

### Prețul apare greșit (ex: 4.999 → 5.0)

Cauza era în `normalize_price()` care interpreta `.` ca separator zecimal în loc de mii.  
**Rezolvat** în versiunea curentă prin `price_parser`.

### URL-uri de imagini în coada de scraping

Cauza: sitemap importat înainte de adăugarea filtrului `_is_page_url()`.

**Rezolvare**:
```
/scraping/<code> → Tab 2 → butonul "Curăță media"
```

sau din linie de comandă:
```python
from app.services.web_scraping_service import _is_page_url
from app.models.scraping_url import ScrapingUrl
for u in ScrapingUrl.query.all():
    if not _is_page_url(u.url):
        db.session.delete(u)
db.session.commit()
```

### Job scraping dispărut după restart

Cauza: `_jobs` dict în memorie se resetează la restart.

**Workaround**: Verifică logurile în Tab 4 → "Istoric job-uri". Job-ul anterior a înregistrat progresul în `scraping_logs`.

### AI returnează `confidence: 0`

Verifică:
1. API key valid în `/ai/config`
2. Formatul răspunsului — unele modele nu returnează JSON pur; ajustează promptul
3. `parse_ai_response()` din `ai_service.py` extrage JSON din markdown code blocks

### SKU-uri duplicate după import

Cauza: același produs importat de două ori cu SKU-uri ușor diferite (ex: `ABC-123` vs `ABC123`).

**Rezolvare**: Folosește curățarea prefix SKU din `/cleanup/` + normalizare manuală.

---

## Licență

Uz intern. Nu redistribui fără acord.
