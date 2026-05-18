from datetime import datetime

from app.extensions import db

_PROMPT_STANDARD = """\
Esti un expert in identificarea si potrivirea produselor tehnice/comerciale.
Sarcina ta este sa analizezi un produs sursa si sa identifici produsele identice sau echivalente.

REGULI STRICTE:
1. SKU este criteriul PRINCIPAL. Potrivire SKU peste 90% => potrivire SIGURA.
2. Daca SKU nu e concludent, analizeaza: titlu + brand + specificatii tehnice.
3. Deducere din context: extrage modelul tehnic din titlu si cauta-l in candidati.
4. Un produs poate avea 1, 2 sau 3 potriviri (acelasi produs la competitori diferiti).
5. Daca nu esti sigur (confidence < 0.6), returneaza lista goala. NU ghici.

PRODUS SURSA: SKU: {sku} | Titlu: {title} | Brand: {brand} | Descriere: {descriere}
CANDIDATI: {candidates}

Returneaza DOAR JSON:
{{"matched_ids": [id1, id2], "confidence": 0.0-1.0, "reason": "explicatie"}}\
"""

_PROMPT_IMBUNATATIT = """\
Esti un expert in identificarea produselor tehnice/comerciale (HVAC, climatizare, echipamente).

SARCINA: Identifica produsele IDENTICE sau ECHIVALENTE cu produsul sursa din lista de candidati.

ALGORITM DE MATCHING (in ordine de prioritate):
1. SKU EXACT — potrivire SKU identic => confidence >= 0.95 (SIGUR).
2. SKU IN TEXT — SKU-ul sursei apare in titlul/descrierea candidatului sau invers => confidence 0.90.
3. SKU COMPUS — daca SKU e de forma "A/B", cauta "A" si "B" separat in candidati.
4. MODEL TEHNIC — extrage codul de model din titlu (elimina: "Aer conditionat", "Kit",
   "inverter", "BTU", "unitate", "aparat", "set"). Cauta codul extras in SKU/titlu/descriere candidati.
5. BRAND + MODEL + CAPACITATE — potrivire brand + model + BTU/kW => confidence 0.75-0.88.
   Diferenta de capacitate (BTU/kW) = produs DIFERIT, nu varianta aceluiasi produs.

REGULI STRICTE:
- Returneaza NUMAI ID-uri din lista de candidati de mai jos. Nu inventa ID-uri.
- Un produs sursa poate avea 1-3 potriviri (acelasi produs la competitori diferiti).
- Daca confidence < 0.6, returneaza lista goala. NU ghici.
- Diferentele de ambalaj sau accesorii minore NU descalifica o potrivire.

PRODUS SURSA:
SKU: {sku} | Titlu: {title} | Brand: {brand} | Descriere: {descriere}

CANDIDATI:
{candidates}

Returneaza DOAR JSON valid (fara markdown, fara text in afara JSON-ului):
{{"matched_ids": [id1, id2], "confidence": 0.0-1.0, "reason": "explicatie concisa"}}\
"""


class PromptTemplate(db.Model):
    __tablename__ = "prompt_templates"

    id          = db.Column(db.Integer, primary_key=True)
    name        = db.Column(db.String(100), nullable=False)
    description = db.Column(db.String(255), nullable=True)
    body        = db.Column(db.Text, nullable=False)
    is_system   = db.Column(db.Boolean, default=False, nullable=False)
    created_at  = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    def as_dict(self):
        return {
            "id":          self.id,
            "name":        self.name,
            "description": self.description or "",
            "body":        self.body,
            "is_system":   self.is_system,
            "created_at":  self.created_at.strftime("%d.%m.%Y"),
        }

    @classmethod
    def seed_defaults(cls):
        if cls.query.count() > 0:
            return
        db.session.add_all([
            cls(
                name="Standard",
                description="Potrivire pe SKU, titlu, brand si specificatii tehnice.",
                body=_PROMPT_STANDARD,
                is_system=True,
            ),
            cls(
                name="Imbunatatit HVAC",
                description="SKU bidirectional, SKU compus, extragere model tehnic, validare BTU/kW. "
                            "Recomandat pentru climatizare si echipamente tehnice.",
                body=_PROMPT_IMBUNATATIT,
                is_system=True,
            ),
        ])
        db.session.commit()
