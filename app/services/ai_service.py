import json


DEFAULT_PROMPT = """Esti un expert in identificarea si potrivirea produselor tehnice/comerciale.
Sarcina ta este sa analizezi un produs sursa si sa identifici produsele identice sau echivalente din lista de candidati.

REGULI STRICTE:
1. SKU este criteriul PRINCIPAL. Daca SKU-ul sursa se regaseste in SKU-ul candidatului cu o potrivire de peste 90% (ignorand prefixe, sufixe, spatii, cratime) => potrivire SIGURA.
2. Daca SKU-ul nu se potriveste suficient, analizeaza contextul: titlu + brand + specificatii tehnice din descriere.
3. Deducere din context: extrage modelul tehnic din titlu (ex: "FTXP25" din "Daikin FTXP25 Inverter") si cauta-l in candidati.
4. Un produs poate avea 1, 2 sau 3 potriviri (acelasi produs la competitori diferiti).
5. IMPORTANT: Daca nu esti sigur (confidence < 0.6), returneaza lista goala. NU ghici.

PRODUS SURSA:
- SKU: {sku}
- Titlu: {title}
- Brand: {brand}
- Descriere: {descriere}

CANDIDAT (produse din alti competitori, fiecare cu ID unic):
{candidates}

ANALIZA:
1. Extrage modelul tehnic din SKU-ul sursa
2. Cauta modelul in SKU-urile candidatilor (potrivire >= 90%)
3. Verifica brand si titlu pentru confirmare
4. Daca SKU nu e concludent, deduce din titlu si descriere

Returneaza DOAR JSON, fara text suplimentar:
{{"matched_ids": [<id1>, <id2>], "confidence": <0.0-1.0>, "reason": "<explicatie concisa: ce a determinat potrivirea>"}}

Daca nu exista potrivire sigura:
{{"matched_ids": [], "confidence": 0.0, "reason": "<de ce nu s-a gasit potrivire>"}}
"""


def build_prompt(source_product, candidates, prompt_template=None):
    template = prompt_template or DEFAULT_PROMPT
    candidate_lines = "\n".join([
        f"- ID: {c['product'].id} | SKU: {c['product'].sku} | Titlu: {c['product'].title} | Brand: {c['product'].brand} | Pret: {c['product'].pret}"
        for c in candidates
    ])
    return template.format(
        sku=source_product.sku or "",
        title=source_product.title or "",
        brand=source_product.brand or "",
        descriere=(source_product.descriere or "")[:300],
        candidates=candidate_lines,
    )


def call_ai(prompt, config):
    provider = (config.provider or "openai").lower()

    if provider == "openai":
        return _call_openai(prompt, config)
    elif provider == "anthropic":
        return _call_anthropic(prompt, config)
    elif provider == "deepseek":
        return _call_deepseek(prompt, config)
    else:
        raise ValueError(f"Provider necunoscut: {provider}")


def _call_openai(prompt, config):
    try:
        from openai import OpenAI
    except ImportError:
        raise ImportError("Instaleaza openai: pip install openai")

    client = OpenAI(api_key=config.api_key)
    response = client.chat.completions.create(
        model=config.model or "gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.1,
        max_tokens=200,
    )
    return response.choices[0].message.content.strip()


def _call_anthropic(prompt, config):
    try:
        import anthropic
    except ImportError:
        raise ImportError("Instaleaza anthropic: pip install anthropic")

    client = anthropic.Anthropic(api_key=config.api_key)
    response = client.messages.create(
        model=config.model or "claude-3-haiku-20240307",
        max_tokens=200,
        messages=[{"role": "user", "content": prompt}],
    )
    return response.content[0].text.strip()


def _call_deepseek(prompt, config):
    try:
        from openai import OpenAI
    except ImportError:
        raise ImportError("Instaleaza openai: pip install openai")

    client = OpenAI(
        api_key=config.api_key,
        base_url="https://api.deepseek.com",
    )
    response = client.chat.completions.create(
        model=config.model or "deepseek-chat",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.1,
        max_tokens=200,
    )
    return response.choices[0].message.content.strip()


def parse_ai_response(raw_response):
    """Parseaza raspunsul JSON de la AI. Accepta matched_id (singular) sau matched_ids (array)."""
    try:
        start = raw_response.find("{")
        end = raw_response.rfind("}") + 1
        if start >= 0 and end > start:
            data = json.loads(raw_response[start:end])
            # Normalizeaza matched_ids
            matched_ids = data.get("matched_ids") or []
            if not matched_ids and data.get("matched_id"):
                matched_ids = [data["matched_id"]]
            matched_ids = [str(x) for x in matched_ids if x is not None]
            return {
                "matched_id": matched_ids[0] if matched_ids else None,
                "matched_ids": matched_ids,
                "confidence": float(data.get("confidence", 0)),
                "reason": data.get("reason", ""),
                "raw": raw_response,
            }
    except Exception:
        pass
    return {"matched_id": None, "matched_ids": [], "confidence": 0, "reason": "", "raw": raw_response}
