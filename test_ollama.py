import json, time, urllib.request, re

URL = "http://localhost:11434/v1/chat/completions"
MODELE = "llama3.2:3b"

SYSTEME = ("Tu extrais une valeur. Reponds UNIQUEMENT en JSON : "
           '{"valeur": "<option exacte>"} ou {"valeur": null}. '
           "La valeur doit etre copiee caractere pour caractere depuis les options. "
           "Si le patient ne repond pas a la question posee, renvoie null. "
           "Le silence n'est jamais une negation : si le patient ne parle pas "
           "d'un symptome, ce n'est pas un 'non'.")

# Le patient repond A COTE : tous ces cas doivent donner null
SILENCE = [
    ("Noyyi dafa la jafe ?", ["oui","non","je ne sais pas"], "sama biir dafa metti"),
    ("Noyyi dafa la jafe ?", ["oui","non","je ne sais pas"], "j'ai mal a la tete"),
    ("Am na deret ?",        ["oui","non","je ne sais pas"], "dama am tangaay"),
    ("Xel mi dafa jaxasoo ?",["oui","non","je ne sais pas"], "je tousse depuis trois jours"),
    ("Sa denn dafa metti ?", ["oui","non","je ne sais pas"], "sama bopp dafay metti"),
    ("Am nga tangaay ?",     ["oui","non","je ne sais pas"], "sama bopp dafa metti"),
    ("Goor la walla jigeen ?", ["homme","femme"],            "waaw"),
]

# Le patient repond VRAIMENT : non-regression
POSITIFS = [
    ("Am nga tangaay ?", ["oui","non","je ne sais pas"], "sama yaram tang na", "oui"),
    ("Am nga tangaay ?", ["oui","non","je ne sais pas"], "xamuma", "je ne sais pas"),
    ("Goor la walla jigeen ?", ["homme","femme"], "jigeen laa", "femme"),
]


def appel(question, options, patient):
    corps = json.dumps({
        "model": MODELE,
        "messages": [
            {"role": "system", "content": SYSTEME},
            {"role": "user", "content":
                f"Question: {question}\nOptions: {json.dumps(options, ensure_ascii=False)}\n"
                f'Patient: "{patient}"'},
        ],
        "temperature": 0,
        "max_tokens": 60,
    }).encode()
    req = urllib.request.Request(URL, data=corps,
                                 headers={"Content-Type": "application/json"})
    t = time.time()
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            brut = json.loads(r.read())["choices"][0]["message"]["content"]
        m = re.search(r'\{[^{}]*\}', brut)
        val = json.loads(m.group()).get("valeur") if m else None
        return val, round(time.time() - t, 2), None
    except Exception as e:
        return None, round(time.time() - t, 2), f"{type(e).__name__}: {e}"


print("=== CRITERE ELIMINATOIRE : le silence ===")
fuites = 0
for q, o, p in SILENCE:
    val, dt, err = appel(q, o, p)
    if err:
        print(f"  ERREUR {p[:30]:32} {err}")
    elif val is None:
        print(f"  ok     {p[:30]:32} -> None            {dt}s")
    else:
        fuites += 1
        print(f"  FUITE  {p[:30]:32} -> {val!r}   {dt}s")

print(f"\n{fuites} valeur(s) inventee(s) sur {len(SILENCE)}")
print("VERDICT :", "ELIMINE" if fuites else "candidat retenu")

if not fuites:
    print("\n=== non-regression ===")
    for q, o, p, att in POSITIFS:
        val, dt, err = appel(q, o, p)
        print(f"  {'ok  ' if val == att else 'DIFF'}   {p[:30]:32} -> {val!r} (attendu {att!r}) {dt}s")