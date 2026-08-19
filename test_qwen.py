import config, os, json, time, urllib.request, re

# Appel API KEY GROQ depuis .env
CLE = os.getenv("GROQ_API_KEY")
URL = "https://api.groq.com/openai/v1/chat/completions"

CANDIDATS = [
    ("qwen/qwen3.6-27b", {"_format_libre": True, "max_tokens": 800}),
    ("openai/gpt-oss-20b", {"reasoning_effort": "low"}),
    ("openai/gpt-oss-120b", {"reasoning_effort": "low"}),
    ("allam-2-7b", {}),
]

SYSTEME = ('Tu extrais une valeur. Reponds UNIQUEMENT en JSON : '
           '{"valeur": "<option exacte>"} ou {"valeur": null}. '
           'La valeur doit etre copiee caractere pour caractere depuis les options.')

CAS = [
    ('Naata at la am ?',
     ["moins de 5 ans", "5 a 9 ans", "10 a 14 ans", "15 a 60 ans", "plus de 60 ans"],
     "fukki at", "10 a 14 ans"),
    ('Goor la walla jigeen ?', ["homme", "femme"], "jigeen laa", "femme"),
    ('Am nga tangaay ?', ["oui", "non", "je ne sais pas"], "sama yaram tang na", "oui"),
    ('Am nga tangaay ?', ["oui", "non", "je ne sais pas"], "xamuma", "je ne sais pas"),
    # cas de silence : le patient repond a cote -> doit donner null
    ('Am nga tangaay ?', ["oui", "non", "je ne sais pas"], "sama bopp dafa metti", None),
]

def appel(modele, extra, question, options, patient):
    corps = {
        "model": modele,
        "messages": [
            {"role": "system", "content": SYSTEME},
            {"role": "user", "content":
                f"Question: {question}\n"
                f"Options: {json.dumps(options, ensure_ascii=False)}\n"
                f'Patient: "{patient}"'},
        ],
        "temperature": 0,
        "max_tokens": 400,
    }
    # Qwen émet son raisonnement avant le JSON, ce qui casse response_format.
    # On le laisse répondre librement et on extrait le JSON nous-mêmes.
    libre = extra.pop("_format_libre", False)
    if not libre:
        corps["response_format"] = {"type": "json_object"}
    corps.update(extra)

    req = urllib.request.Request(
        URL, data=json.dumps(corps).encode(),
        headers={"Authorization": f"Bearer {CLE}",
                 "Content-Type": "application/json",
                 "User-Agent": "agent-triage/1.0"})
    t = time.time()
    try:
        with urllib.request.urlopen(req, timeout=25) as r:
            rep = json.loads(r.read())
        brut = rep["choices"][0]["message"]["content"]
        m = re.search(r'\{[^{}]*\}', brut)          # premier objet JSON
        valeur = json.loads(m.group()).get("valeur") if m else None
        return valeur, round(time.time() - t, 2), None
    except urllib.error.HTTPError as e:
        return None, round(time.time() - t, 2), f"HTTP {e.code} {e.read()[:120]}"
    except Exception as e:
        return None, round(time.time() - t, 2), f"{type(e).__name__}: {e}"

for modele, extra in CANDIDATS:
    print(f"\n=== {modele} ===")
    for question, options, patient, attendu in CAS:
        val, dt, err = appel(modele, extra, question, options, patient)
        if err:
            print(f"  ERREUR  {patient[:24]:26} {err}")
        else:
            ok = "ok  " if val == attendu else "DIFF"
            print(f"  {ok}    {patient[:24]:26} -> {val!r}  (attendu {attendu!r})  {dt}s")
        time.sleep(8)          # cadencement : 6000 tokens/minute