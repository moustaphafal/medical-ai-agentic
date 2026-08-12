"""
Extraction des valeurs à partir de la transcription.

Deux stratégies :
  - wolof   : appariement phonétique sur lexique (fiable malgré un WER élevé)
  - français: appariement d'abord, modèle de langage en secours

Le modèle de langage n'a qu'un rôle : remplir un champ. Il ne décide jamais
de la question suivante ni de la conclusion — c'est le rôle de l'orchestrateur.
"""

import json
import os
import re
import unicodedata
import urllib.request
from rapidfuzz import fuzz

SEUIL = 85


# --------------------------------------------------------------------------
# Normalisation phonétique
# Neutralise les confusions sourde/sonore et les géminées, qui constituent
# l'essentiel des écarts observés entre la transcription et l'orthographe.
# --------------------------------------------------------------------------

_SONORES = str.maketrans("bdgvzj", "ptkfsc")


def phonetiser(s: str) -> str:
    s = str(s).lower().strip().replace("ŋ", "n").replace("ñ", "n")
    s = unicodedata.normalize("NFD", s)
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    s = re.sub(r"[^a-z0-9\s]", " ", s)
    s = s.translate(_SONORES)
    s = re.sub(r"(.)\1+", r"\1", s)
    return re.sub(r"\s+", " ", s).strip()

def _simplifier(s: str) -> str:
    """Normalisation SANS substitution phonétique.
    phonetiser() est fait pour l'appariement flou de mots-clés :
    il transforme 'deux jours' en 'teux cours' et casse toute regex."""
    s = str(s).lower().strip().replace("ŋ", "n").replace("ñ", "n")
    s = unicodedata.normalize("NFD", s)
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    s = re.sub(r"[^a-z0-9\s]", " ", s)
    return re.sub(r"\s+", " ", s).strip()

def contient(mot_cle: str, transcription: str, seuil: int = SEUIL) -> bool:
    """Appariement token à token, avec récupération des coupures de mots."""
    cible = phonetiser(mot_cle).replace(" ", "")
    toks = phonetiser(transcription).split()
    if not toks:
        return False
    candidats = toks + ["".join(toks[i:i + 2]) for i in range(len(toks) - 1)]
    return max(fuzz.ratio(cible, c) for c in candidats) >= seuil


# --------------------------------------------------------------------------
# Lexique — À COMPLÉTER avec les formes réellement produites par le modèle,
# et non avec l'orthographe normée du wolof.
# --------------------------------------------------------------------------

LEXIQUE = {
    # clé          formes wolof                    + formes françaises
    "oui":        ["waaw", "wau", "oui", "voila"],
    "non":        ["deedeet", "dedet", "non"],
    "douleur":    ["metti", "metit", "mettit", "mal", "douleur", "souffre"],
    "tete":       ["bopp", "bob", "tete", "crane", "migraine"],
    "ventre":     ["biir", "bir", "ventre", "estomac", "abdomen"],
    "poitrine":   ["denn", "den", "poitrine", "thorax"],
    "gorge":      ["put", "gorge"],
    "fievre":     ["tangaay", "tangoor", "tang", "sibbiru",
                   "fievre", "chaud", "temperature", "palu", "paludisme"],
    "toux":       ["seqet", "sekhet", "tousse", "toux", "tousser"],
    "vomir":      ["waccu", "wacu", "vomi", "vomis", "vomit", "vomissement"],
    "diarrhee":   ["daw", "diare", "diarrhee", "selles", "sellesliquides"],
    "respirer":   ["noyyi", "noyi", "respire", "respirer", "souffle"],
    "difficile":  ["jafe", "difficile", "mal"],
    "enceinte":   ["emb", "enceinte", "grossesse"],
    "enfant":     ["xale", "enfant", "bebe", "nourrisson"],
    "tension":    ["tension", "hypertension"],
    "diabete":    ["diabet", "sukkar", "diabete"],
    "sang":       ["deret", "sang", "saigne"],
    "fatigue":    ["sonn", "fatigue", "faible"],
    "malade":     ["feebar", "febar", "wopp", "malade"],
}

NOMBRES_WO = {
    "benn": 1, "naar": 2, "nett": 3, "nent": 4, "juroom": 5,
    "juroom benn": 6, "juroom naar": 7, "fukk": 10, "ayubes": 7,
    "tey": 0, "demb": 1,
}


def _detecte(cle: str, texte: str) -> bool:
    return any(contient(f, texte) for f in LEXIQUE.get(cle, []))


# --------------------------------------------------------------------------
# Extraction par type de champ
# --------------------------------------------------------------------------

def extraire_binaire(texte: str) -> str | None:
    if _detecte("oui", texte):
        return "oui"
    if _detecte("non", texte):
        return "non"
    t = phonetiser(texte)
    if re.search(r"\b(oui|ouais|yes|voila|exact)\b", t):
        return "oui"
    if re.search(r"\bnon\b", t):
        return "non"
    return None


def extraire_entier(texte: str) -> int | None:
    m = re.search(r"\b(\d{1,3})\b", str(texte))
    if m:
        return int(m.group(1))
    t = phonetiser(texte)
    for mot, val in NOMBRES_WO.items():
        if contient(mot, t):
            return val
    mots_fr = {"un": 1, "deux": 2, "trois": 3, "quatre": 4, "cinq": 5,
               "six": 6, "sept": 7, "huit": 8, "neuf": 9, "dix": 10,
               "aujourd hui": 0, "hier": 1, "semaine": 7}
    for mot, val in mots_fr.items():
        if mot in t:
            return val
    return None


REGLES_MOTIF = {
    "cephalee":     [("tete", 1), ("douleur", 1)],
    "fievre_palu":  [("fievre", 2)],
    "diarrhee":     [("diarrhee", 2), ("ventre", 1)],
    "respiratoire": [("toux", 2), ("respirer", 1)],
    "abdominal":    [("ventre", 2), ("douleur", 1)],
}


def extraire_motif(texte: str) -> str | None:
    scores = {}
    for motif, cles in REGLES_MOTIF.items():
        scores[motif] = sum(poids for cle, poids in cles if _detecte(cle, texte))
    meilleur = max(scores, key=scores.get)
    return meilleur if scores[meilleur] >= 2 else None


def extraire_choix(texte: str, options: list) -> str | None:
    t = phonetiser(texte)
    meilleur, score = None, 0
    for opt in options:
        s = fuzz.partial_ratio(phonetiser(opt), t)
        if s > score:
            meilleur, score = opt, s
    return meilleur if score >= SEUIL else None


def extraire(champ, texte: str, langue: str = "fr"):
    """Point d'entrée unique. Retourne la valeur ou None."""
    if champ.nom == "motif_principal":
        return extraire_motif(texte)
    if champ.nom == "age_tranche":
        return extraire_age(texte, champ.options)
    if champ.type == "entier":
        return extraire_entier(texte)
    if champ.type == "choix":
        if set(champ.options) <= {"oui", "non", "je ne sais pas"}:
            return extraire_binaire(texte)
        return extraire_choix(texte, champ.options)
    if champ.type == "texte":
        return texte.strip() or None
    return None


# --------------------------------------------------------------------------
# Secours par modèle de langage — à brancher par le membre 2.
# Ne doit être appelé que si extraire() a renvoyé None, et uniquement
# pour renvoyer une valeur du domaine du champ. Jamais pour décider.
# --------------------------------------------------------------------------

_TRANCHES = [(5, "moins de 5 ans"), (15, "5 a 15 ans"),
             (60, "15 a 60 ans"), (200, "plus de 60 ans")]
_MOTS_AGE = {"un":1,"deux":2,"trois":3,"quatre":4,"cinq":5,"six":6,"sept":7,
             "huit":8,"neuf":9,"dix":10,"vingt":20,"trente":30,"quarante":40,
             "cinquante":50,"soixante":60,
             "benn":1,"naar":2,"nett":3,"nent":4,"juroom":5}


def extraire_age(texte: str, options: list) -> str | None:
    """L'âge pilote la règle d'alerte la plus importante (< 5 ans).
    On lit un nombre puis on le range dans une tranche, plutôt que
    d'apparier la phrase au libellé de l'option."""
    t = _simplifier(texte)
    for opt in options:                    # libellé exact : pastille ou saisie
        if _simplifier(opt) in t:
            return opt
    if re.search(r"\b(bebe|nourrisson)\b", t):
        return "moins de 5 ans"
    if re.search(r"\b\d{1,2}\s*(mois|weer)\b", t):
        return "moins de 5 ans"
    m = re.search(r"\b(\d{1,3})\s*(ans?|at)\b", t) or re.search(r"\b(\d{1,3})\b", t)
    n = int(m.group(1)) if m else None
    if n is None:
        for mot, val in _MOTS_AGE.items():
            if re.search(rf"\b{mot}\s+(ans?|at)\b", t):
                n = val
                break
    if n is None:
        return None
    for seuil, label in _TRANCHES:
        if n < seuil:
            return label
    return "plus de 60 ans"

_GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
_GROQ_MODELE = "llama-3.1-8b-instant"
_GROQ_TIMEOUT = 6

# Valeurs renvoyées par le modèle mais refusées par le garde-fou.
# Diagnostic uniquement : rien dans le triage ne lit cette liste.
REJETS_LLM: list = []
_MAX_REJETS = 50

_INSTRUCTION = """Tu es un extracteur pour un agent de triage médical au Sénégal.
Le patient parle wolof, français, ou un mélange des deux.

Ton unique rôle : RANGER la réponse du patient dans une liste fermée d'options.
Tu ne décides rien, tu ne donnes aucun avis médical, tu ne reformules pas.

Réponds uniquement par un objet JSON : {"valeur": "<une option exacte>"}
ou {"valeur": null} si tu n'es pas certain.

Règles absolues :
- La valeur doit être RECOPIÉE À L'IDENTIQUE depuis la liste d'options fournie.
- Si la réponse du patient ne correspond à aucune option, réponds null.
- Si la réponse est ambiguë, hors sujet, ou incompréhensible, réponds null.
- NE JAMAIS déduire une négation d'un silence. Si le patient ne mentionne pas
  un symptôme, ce n'est PAS un "non" : c'est null. L'absence d'information
  n'est jamais une réponse négative.

Exemples.

Question : Quel âge a le patient ?
Options : ["moins de 5 ans", "5 a 15 ans", "15 a 60 ans", "plus de 60 ans"]
Patient : "fukki at"
Réponse : {"valeur": "5 a 15 ans"}

Question : Le patient est-il un homme ou une femme ?
Options : ["homme", "femme"]
Patient : "jigéen laa"
Réponse : {"valeur": "femme"}

Question : Avez-vous de la fièvre ?
Options : ["oui", "non", "je ne sais pas"]
Patient : "sama yaram tàng na"
Réponse : {"valeur": "oui"}

Question : Avez-vous de la fièvre ?
Options : ["oui", "non", "je ne sais pas"]
Patient : "sama bopp dafa metti"
Réponse : {"valeur": null}"""


def extraire_par_llm(champ, texte: str, langue: str = "fr") -> str | None:
    """Secours lexical : range une réponse libre dans champ.options.

    Retourne None à la moindre incertitude — clé absente, réseau, timeout,
    JSON invalide, ou valeur hors domaine. Ne lève jamais d'exception :
    l'orchestrateur doit pouvoir relancer sa question normalement.
    """
    cle = os.environ.get("GROQ_API_KEY")
    if not cle or not texte or not str(texte).strip() or not champ.options:
        return None

    question = champ.question_wo if langue == "wo" else champ.question_fr
    demande = (
        f"Question : {question}\n"
        f"Options : {json.dumps(champ.options, ensure_ascii=False)}\n"
        f"Patient : \"{str(texte).strip()}\"\n"
        "Réponse :"
    )

    corps = json.dumps({
        "model": _GROQ_MODELE,
        "temperature": 0,
        "max_tokens": 40,
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": _INSTRUCTION},
            {"role": "user", "content": demande},
        ],
    }).encode("utf-8")

    requete = urllib.request.Request(
        _GROQ_URL, data=corps, method="POST",
        headers={"Content-Type": "application/json",
                 "Authorization": f"Bearer {cle}"},
    )

    try:
        with urllib.request.urlopen(requete, timeout=_GROQ_TIMEOUT) as reponse:
            charge = json.loads(reponse.read().decode("utf-8"))
        contenu = charge["choices"][0]["message"]["content"]
        valeur = json.loads(contenu).get("valeur")
    except Exception:
        # Panne réseau, quota, timeout, JSON malformé : on relance la question.
        return None

    # Garde-fou : la sortie du modèle n'est jamais crue sur parole.
    if valeur in champ.options:
        return valeur
    if valeur is not None and len(REJETS_LLM) < _MAX_REJETS:
        REJETS_LLM.append({"champ": champ.nom, "brut": texte, "refuse": valeur})
    return None

# Une durée n'est déduite que si elle est explicitement exprimée :
# un nombre suivi d'une unité de temps.
_MOTIF_DUREE = re.compile(
    r"\b(\d{1,3})\s*(jour|jours|semaine|semaines|mois|fan|bes|ayubes)\b"
)


def extraire_duree_explicite(texte: str) -> int | None:
    t = _simplifier(texte)
    m = _MOTIF_DUREE.search(t)
    if m:
        n = int(m.group(1))
        unite = m.group(2)
        if unite.startswith(("semaine", "ayubes")):
            n *= 7
        elif unite.startswith("mois"):
            n *= 30
        return n
    # Formes en toutes lettres, avec unité obligatoire.
    _MOTS = {"benn": 1, "naar": 2, "nett": 3, "nent": 4, "juroom": 5,
                "un": 1, "une": 1, "deux": 2, "trois": 3, "quatre": 4, "cinq": 5,
                "six": 6, "sept": 7, "huit": 8, "neuf": 9, "dix": 10}
    for mot, val in _MOTS.items():
        mm = re.search(
            rf"\b{mot}\s+(jour|jours|semaine|semaines|mois|fan|bes)\b", t)
        if mm:
            unite = mm.group(1)
            if unite.startswith("semaine"):
                val *= 7
            elif unite.startswith("mois"):
                val *= 30
            return val


def extraire_tout(texte: str, dossier: dict, champs) -> dict:
    """Déduction opportuniste, volontairement conservatrice.
    N'écrase jamais un champ existant et exige un indice explicite."""
    trouves = {}

    if "duree_jours" not in dossier:
        d = extraire_duree_explicite(texte)
        if d is not None:
            trouves["duree_jours"] = d

    if "motif_principal" not in dossier:
        m = extraire_motif(texte)
        if m is not None:
            trouves["motif_principal"] = m

    return trouves
