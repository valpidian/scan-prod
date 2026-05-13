# Sistem de Import CSV cu Mapare Coloane - Ghid Implementare

## Overview
Sistem de import CSV îmbunătățit cu:
- ✅ Interfață de mapare coloane (stil WooCommerce)
- ✅ Preview date din CSV
- ✅ Sugestii automate de mapare
- ✅ Timestamp de import (`imported_at`) pentru tracking evoluție preț

## Fișiere Modificate/Adăugate

### 1. Model Database (`app/models/competitor_product.py`)
**Modificări:**
- Adăugat coloană `imported_at: DateTime` - înregistrează când a fost importat fiecare produs
- Actualizat `as_dict()` pentru a include `imported_at`

### 2. Serviciu CSV Mapping (`app/services/csv_mapping_service.py`) - NOI
**Funcții principale:**
- `parse_csv_preview()` - citește CSV și returnează preview cu coloane și sample rows
- `suggest_mapping()` - sugerează maparea automată pe baza numelor coloane
- `validate_mapping()` - validează mappingul introdus de user
- `save_mapping_session()` / `load_mapping_session()` - persistă sesiunea de mapare

### 3. Serviciu Import CSV (`app/services/csv_import_service.py`)
**Modificări:**
- Adăugat parametru `mapping` în funcția `import_csv()`
- Adăugat `imported_at` timestamp pentru fiecare produs
- Backward compatible (dacă nu e mapping, foloseștecoloanele directe)

### 4. Rute Import/Export (`app/routes/import_export.py`)
**Modificări:**
- Ruta `/import` [GET/POST] - acum afișează interfața de mapare după upload
- Adăugat ruta nouă `/import/confirm-mapping` [POST] - finalizează importul cu mappingul confirmat
- Validare mapare înainte de import

### 5. Template Mapare (`app/templates/import_export/mapping.html`) - NOI
**Caracteristici:**
- Tabel cu coloane CSV și dropdown-uri pentru mapare
- Previzualizare date din CSV
- Validare client-side pentru campuri obligatorii
- Indicatoare pentru sugestii automate
- Informații despre numărul de randuri

## Workflow-ul Utilizatorului

```
1. User merge la /import
   ↓
2. Selectează competitor și încarcă CSV
   ↓
3. Sistemul îi arată interfața de mapare:
   - Detectează coloane CSV
   - Sugerează mapări automate
   - Afișează preview date
   ↓
4. User confirmă mappingul
   ↓
5. Produsele sunt importate cu:
   - Timestamp `imported_at`
   - Campuri mapate corect
```

## Campuri Obligatorii pentru Mapare

- **SKU** - identificatorul unic al produsului
- **Title** - titlu produs
- **Preț** - prețul produsului
- **Brand** - marca/producătorul
- **Descriere** - descrierea produsului

## Sugestii Automate de Mapare

Sistemul detectează automat coloane pe baza cuvintelor cheie:

| Câmp | Cuvinte Cheie |
|------|---------------|
| SKU | sku, cod, product_id, product_code, article, article_number |
| Title | title, name, product_name, product, denumire, descriere_scurta |
| Preț | pret, price, cost, preț, cost_price, unit_price, precio |
| Brand | brand, marca, manufacturer, producer, fabrica, supplier |
| Descriere | descriere, description, details, detail |

## Tracking Evoluție Preț

Cu timestamp-ul `imported_at`, poți:
```sql
-- Vezi evolutia pretului unui SKU
SELECT sku, pret, imported_at 
FROM competitor_products 
WHERE sku = 'XXX'
ORDER BY imported_at DESC;

-- Compara preturi între importuri
SELECT 
  imported_at,
  COUNT(*) as count_products,
  AVG(pret) as avg_price,
  MIN(pret) as min_price,
  MAX(pret) as max_price
FROM competitor_products 
WHERE cod_competitor = 'CODE'
GROUP BY imported_at
ORDER BY imported_at DESC;
```

## Migrare Database

Pentru actualizarea unui database existent:

```sql
-- Adaugă coloana imported_at dacă nu există
ALTER TABLE competitor_products 
ADD COLUMN imported_at TIMESTAMP NULL AFTER updated_at;

-- Creează index pentru performanță
CREATE INDEX idx_imported_at ON competitor_products(imported_at);
```

Sau folosind SQLAlchemy migration (Alembic):

```bash
flask db migrate -m "Add imported_at column to competitor_products"
flask db upgrade
```

## Backward Compatibility

Funcția `import_csv()` este backward compatible:
- Dacă nu este furnizat parametrul `mapping`, funcția va căuta coloanele direct în CSV
- Produsele existente vor continua să funcționeze și fără `imported_at`

## Validări

Sistemul validează:
✅ Existența competitorului
✅ Existența coloanelor necesare în CSV
✅ Mapare completă a campurilor obligatorii
✅ Validitate rânduri CSV (SKU și Title non-goale)
✅ Prețuri corecte (normalizare)

## Erori Comune

| Eroare | Soluție |
|--------|---------|
| "Campuri obligatorii nemapate" | Mapează toate 5 campurile obligatorii |
| "Coloana 'X' nu există în fisier" | Verifică dacă coloana e redenumită în CSV |
| "Lipsesc valori pentru SKU/Title" | CSV-ul are rânduri cu SKU sau Title goale |

## Următoarele Evoluții Posibile

- [ ] Export CSV cu coloane personalizate
- [ ] Sincronizare periodică cu colecție preț histórice
- [ ] Grafice cu evoluția prețurilor
- [ ] Alertare schimbări de preț
- [ ] Comparator automativ preț între competitori
