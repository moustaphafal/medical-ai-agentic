"""
Extraction des valeurs à partir de la transcription.

Deux stratégies :
  - wolof   : appariement phonétique sur lexique (fiable malgré un WER élevé)
  - français: appariement d'abord, modèle de langage en secours

Le modèle de langage n'a qu'un rôle : remplir un champ. Il ne décide jamais
de la question suivante ni de la conclusion — c'est le rôle de l'orchestrateur.
"""

import re
import unicodedata
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

def extraire_par_llm(champ, texte: str) -> str | None:
    """
    Doit retourner exclusivement une valeur de champ.options, ou None.
    Prompt attendu, sortie JSON contrainte :
        {"valeur": "<option exacte ou null>"}
    """
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
    # Formes wolof et françaises en toutes lettres, avec unité obligatoire.
    for mot, val in {"benn": 1, "naar": 2, "nett": 3, "nent": 4, "juroom": 5,
                     "un": 1, "deux": 2, "trois": 3, "quatre": 4, "cinq": 5}.items():
        if re.search(rf"\b{mot}\s+(jour|jours|fan|bes)\b", t):
            return val
    if re.search(r"\b(aujourd hui|tey)\b", t):
        return 0
    if re.search(r"\b(hier|demb)\b", t):
        return 1
    return None


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
