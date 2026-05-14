# Scan Pret

Aplicatie web pentru monitorizarea si compararea preturilor produselor de la competitori, cu suport pentru asociere automata bazata pe AI.

## Functionalitati

- **Import CSV** — importa produse de la competitori cu mapare flexibila a coloanelor
- **Cautare avansata** — cauta produse dupa SKU, titlu, brand, descriere cu highlighting
- **Asociere manuala** — asociaza produse intre competitori direct din rezultatele cautarii
- **Asociere AI** — potrivire automata a produselor folosind OpenAI, Anthropic sau DeepSeek
- **Procesare in masa** — asociere AI pentru mai multe produse simultan
- **Preluare pret** — preia pretul unui produs asociat cu un singur click
- **Curatare date** — detecteaza si curata HTML, URL-uri, formate gresite de pret din datele importate
- **Export CSV** — exporta produsele cu asocierile si preturile preluate
- **Notificari** — sistem de notificari pentru actiunile importante
- **Configurare sensibilitate cautare** — ajusteaza parametrii de matching

## Tehnologii

- **Backend**: Python 3.13, Flask 3.0
- **Baza de date**: SQLite (via SQLAlchemy + Flask-Migrate)
- **AI**: OpenAI GPT, Anthropic Claude, DeepSeek
- **Frontend**: Bootstrap 5.3, Font Awesome 6.5
- **Securitate**: Flask-WTF (CSRF), Flask-Limiter (rate limiting)

## Instalare (Windows)

```bash
# Cloneaza repo-ul
git clone https://github.com/valpidian/scan-prod.git
cd scan-prod

# Creeaza si activeaza virtual environment
python -m venv venv
venv\Scripts\activate

# Instaleaza dependentele
pip install -r requirements.txt

# Configureaza variabilele de mediu
copy .env.example .env
# Editeaza .env cu valorile tale

# Ruleaza migrarile
python migrate_db.py

# Porneste aplicatia
python run.py
```

## Instalare (Linux / Mac)

```bash
# Cloneaza repo-ul
git clone https://github.com/valpidian/scan-prod.git
cd scan-prod

# Creeaza si activeaza virtual environment
python3 -m venv venv
source venv/bin/activate

# Instaleaza dependentele
pip install -r requirements.txt

# Configureaza variabilele de mediu
cp .env.example .env
# Editeaza .env cu valorile tale

# Ruleaza migrarile
python migrate_db.py

# Porneste aplicatia
python run.py
```

## Configurare `.env`

```env
SECRET_KEY=cheia-ta-secreta
DEBUG=false
HOST=127.0.0.1
PORT=5055
DATABASE_URL=sqlite:///instance/scan_pret.db
```

> **Nota:** fisierul `.env` nu este inclus in repository (ignorat prin `.gitignore`).
> Trebuie creat manual pe fiecare server dupa clonare.

## Deployment productie (Linux + Gunicorn)

```bash
# Instaleaza Gunicorn
pip install gunicorn

# Ruleaza cu 4 workeri
gunicorn -w 4 -b 0.0.0.0:5055 "app:create_app()"
```

Pentru productie seteaza in `.env`:

```env
DEBUG=false
HOST=0.0.0.0
SECRET_KEY=cheie-lunga-si-aleatoare
```

## Flux de lucru

1. **Competitori** — adauga URL-urile si codurile interne ale competitorilor
2. **Import CSV** — incarca fisierele CSV cu produsele fiecarui competitor
3. **Curatare date** — elimina HTML, URL-uri si formate gresite
4. **Cautare** — gaseste produse similare dupa SKU, titlu sau brand
5. **Asociere** — asociaza manual sau prin AI produsele identice intre competitori
6. **Preluare pret** — preia pretul dorit din produsele asociate
7. **Export CSV** — descarca datele finale cu preturile comparate

## Structura proiect

```
scan-pret/
├── app/
│   ├── models/          # Modele SQLAlchemy
│   ├── routes/          # Blueprint-uri Flask
│   ├── services/        # Logica de business
│   ├── templates/       # Template-uri Jinja2
│   ├── static/          # CSS, JS
│   └── utils/           # Utilitare (normalizers, validators, helpers)
├── scripts/             # Scripturi utilitare
├── config.py            # Configurare aplicatie
├── migrate_db.py        # Script migrare baza de date
└── run.py               # Entry point
```

## Licenta

Proiect privat — toate drepturile rezervate.
