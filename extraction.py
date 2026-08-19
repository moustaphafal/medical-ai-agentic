"""
Extraction des valeurs à partir de la transcription.

Deux stratégies :
  - wolof   : appariement phonétique sur lexique (fiable malgré un WER élevé)
  - français: appariement d'abord, modèle de langage en secours

Le modèle de langage n'a qu'un rôle : remplir un champ. Il ne décide jamais
de la question suivante ni de la conclusion — c'est le rôle de l'orchestrateur.
"""

import json
import re
import unicodedata
from rapidfuzz import fuzz

import config  # noqa: F401  — charge .env dans os.environ dès l'import
import llm
from domaine import CHAMPS_CRITIQUES

SEUIL = 85


# --------------------------------------------------------------------------
# Normalisation phonétique
# Neutralise les confusions sourde/sonore et les géminées, qui constituent
# l'essentiel des écarts observés entre la transcription et l'orthographe.
# --------------------------------------------------------------------------

_SONORES = str.maketrans("bdgvzj", "ptkfsc")

# NE NEUTRALISE QUE u/o — mesuré le 2026-08-19.
#
# La table précédente, str.maketrans("aeiou", "aaaaa"), ramenait toutes les
# voyelles à « a ». Elle avait été ajoutée pour rattraper la seule paire
# seqet/seqat, et détruisait au passage l'information de tous les autres
# mots :
#
#     metti  -> mata      bopp   -> pap
#     fukki  -> faka      juroom -> caram
#
# Un mot réduit à son squelette consonantique n'a plus de quoi se
# distinguer de ses voisins : c'est du hasard qui décide.
#
# Trois variantes ont été comparées sur les transcriptions réelles de
# test_lexique.py, sur demo.py test et sur des paires qui doivent rester
# distinctes (tànk/tàngaay, put/bopp, biir/bopp, daw/deret, sonn/sang) :
#
#   aeiou->a   8/8 reconnaissance, 3/3 faux positifs, 7/7 demo
#   u->o       idem, ET rattrape 7 variantes u/o sur 7 (tangoor/tangur,
#              sukkar/sokkar, noyyi/nuyi, wopp/wupp, juroom/jorom,
#              waccu/wacco, bopp/bupp) sans fusionner aucune paire
#   aucune     idem, mais 0 variante u/o sur 7
#
# u/o retenu : l'alternance est réelle en wolof transcrit et ne crée aucune
# confusion mesurée. La paire seqet/seqat, elle, est traitée où elle doit
# l'être — par une variante dans LEXIQUE.
_VOYELLES = str.maketrans("u", "o")
_CLITIQUES = ["bu", "ba", "bi", "la", "na", "ci", "ak", "du", "da", "dafa",
              "ma", "mu", "yi", "ju", "al", "ul"]

def phonetiser(s: str) -> str:
    """Le wolof n'a pas d'orthographe stabilisée et la transcription varie.
    On neutralise : diacritiques, digrammes du [q], opposition sourde/sonore,
    alternance u/o, consonnes géminées.
    Kër et Keur deviennent la même forme.

    Ce qui est volontairement CONSERVÉ : le timbre des autres voyelles.
    C'est lui qui sépare metti de matu et bopp de biir — voir _VOYELLES."""
    s = str(s).lower().strip().replace("ŋ", "n").replace("ñ", "n")
    s = unicodedata.normalize("NFD", s)
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    s = re.sub(r"[^a-z0-9\s]", " ", s)
    s = s.replace("kh", "q").replace("x", "q")
    s = s.translate(_SONORES).translate(_VOYELLES)
    s = re.sub(r"(.)\1+", r"\1", s)
    return re.sub(r"\s+", " ", s).strip()

_CLIT_NORM = sorted({phonetiser(c) for c in _CLITIQUES}, key=len, reverse=True)

def _degluer(tok: str) -> list:
    """Le modèle colle souvent une particule au mot suivant :
    « bu tang » ressort en « butang », « noyyi bu » en « noyibu »."""
    out = [tok]
    for c in _CLIT_NORM:
        if tok.startswith(c) and len(tok) > len(c) + 2:
            out.append(tok[len(c):])
        if tok.endswith(c) and len(tok) > len(c) + 2:
            out.append(tok[:-len(c)])
    return out


def contient(mot_cle: str, transcription: str, seuil: int = SEUIL) -> bool:
    """Appariement flou, token à token."""
    cible = phonetiser(mot_cle).replace(" ", "")
    toks = phonetiser(transcription).split()
    if not toks:
        return False
    # Un mot-clé court risque de matcher à l'intérieur d'un mot plus long :
    # « tànk » (jambe) dans « tàngaay » (fièvre) fausserait le triage.
    s = 92 if len(str(mot_cle).replace(" ", "")) <= 4 else seuil
    candidats = []
    for t in toks:
        candidats += _degluer(t)
    candidats += ["".join(toks[i:i + 2]) for i in range(len(toks) - 1)]
    return max(fuzz.ratio(cible, c) for c in candidats) >= s

def _simplifier(s: str) -> str:
    """Normalisation SANS substitution phonétique.
    phonetiser() est fait pour l'appariement flou de mots-clés :
    il transforme 'deux jours' en 'teux cours' et casse toute regex."""
    s = str(s).lower().strip().replace("ŋ", "n").replace("ñ", "n")
    s = unicodedata.normalize("NFD", s)
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    s = re.sub(r"[^a-z0-9\s]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


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
                   "fievre", "chaud", "temperature", "palu", "paludisme", "palew"],
    # « seqat » / « sëqat » : formes réellement transcrites. Elles étaient
    # rattrapées par la neutralisation vocalique de phonetiser(), qui
    # écrasait AUSSI metti->mata, bopp->pap, fukki->faka. Une variante ici
    # coûte une ligne ; la table coûtait l'information de tous les mots.
    "toux":       ["seqet", "seqat", "sekhet", "sekhat",
                   "tousse", "toux", "tousser"],
    "vomir":      ["waccu", "wacu", "vomi", "vomis", "vomit", "vomissement"],
    "diarrhee":   ["daw", "diare", "diarrhee", "selles", "sellesliquides"],
    "respirer":   ["noyyi", "noyi", "respire", "respirer", "souffle"],
    "difficile":  ["jafe", "difficile", "mal"],
    "enceinte":   ["emb", "enceinte", "grossesse"],
    "enfant":     ["xale", "enfant", "bebe", "nourrisson"],
    "tension":    ["tension", "hypertension"],
    "diabete":    ["diabet", "sukkar", "diabete","jabet"],
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

# Reprendre les mots du symptôme interrogé est une affirmation, en wolof
# comme en français : « noyyi bu jafe laa am » répond oui à
# « Noyyi dafa la jafe ? ». Chaque champ binaire est décrit par les clés du
# LEXIQUE qui le caractérisent.
CLES_PAR_CHAMP = {
    "dyspnee":            ["respirer", "difficile"],
    "fievre":             ["fievre"],
    "vomissements":       ["vomir"],
    "saignement":         ["sang"],
    "douleur_thoracique": ["poitrine", "douleur"],
    "antecedents":        ["tension", "diabete"],
}

# Comment combiner les clés d'un champ.
#
# « toutes » par défaut : les clés décrivent les morceaux d'une même
# expression. « poitrine » seul ne dit pas qu'elle fait mal, il faut aussi
# « douleur ».
#
# « au moins une » quand les clés sont des ALTERNATIVES : déclarer une
# hypertension suffit à répondre oui sur les antécédents, sans diabète.
# Exiger les deux y produisait un faux négatif sur un signe d'alerte.
MODE_PAR_DEFAUT = "toutes"
MODE_CLES = {
    "antecedents": "au moins une",
}


def extraire_reprise(nom_champ: str, texte: str) -> str | None:
    """Réponse déduite de la reprise des mots de la question. Sans modèle.

    Exige TOUTES les clés du champ interrogé : sans quoi un autre symptôme
    déclencherait à tort. « sama biir dafa metti » parle du ventre et ne dit
    rien de la respiration — la clé « respirer » manque, on ne conclut pas.
    """
    cles = CLES_PAR_CHAMP.get(nom_champ)
    if not cles:
        return None

    presentes = [c for c in cles if _detecte(c, texte)]
    mode = MODE_CLES.get(nom_champ, MODE_PAR_DEFAUT)
    if mode == "toutes":
        if len(presentes) < len(cles):
            return None
    elif not presentes:
        return None

    return "non" if _detecte("non", texte) else "oui"


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
            # La reprise de question passe en premier ; l'appariement
            # oui/non reste le repli.
            reprise = extraire_reprise(champ.nom, texte)
            return reprise if reprise is not None else extraire_binaire(texte)
        return extraire_choix(texte, champ.options)
    if champ.type == "texte":
        return texte.strip() or None
    return None


# --------------------------------------------------------------------------
# Secours par modèle de langage — à brancher par le membre 2.
# Ne doit être appelé que si extraire() a renvoyé None, et uniquement
# pour renvoyer une valeur du domaine du champ. Jamais pour décider.
# --------------------------------------------------------------------------

_TRANCHES = [(5, "moins de 5 ans"), (10, "5 a 9 ans"), (15, "10 a 14 ans"),
             (60, "15 a 60 ans"), (200, "plus de 60 ans")]
_MOTS_AGE = {"un":1,"deux":2,"trois":3,"quatre":4,"cinq":5,"six":6,"sept":7,
             "huit":8,"neuf":9,"dix":10,"vingt":20,"trente":30,"quarante":40,
             "cinquante":50,"soixante":60,
             "benn":1,"naar":2,"nett":3,"nent":4,"juroom":5,
             # Wolof : le lexique doit suffire seul, age_tranche étant un
             # champ critique désormais privé de secours par modèle.
             "juroom benn":6, "juroom naar":7, "juroom nett":8,
             "juroom nent":9,
             "fanweer":30}
#            fukk / fukki (10) ne figurent PAS ici : ils portent un
#            multiplicateur et sont traités par _dizaines(), plus bas.

# Les formes longues d'abord : « juroom benn » doit l'emporter sur « juroom ».
_MOTS_AGE_TRIES = sorted(_MOTS_AGE.items(), key=lambda kv: -len(kv[0]))

# Le wolof multiplie les dizaines par juxtaposition : « ñaari fukk » = 2 x 10.
# Ce qui précède « fukk » n'est donc jamais décoratif.
#
# « yu naanu » : forme réellement produite par le modèle de transcription
# pour « ñaari », observée sur « yu ñaanu fukki at ak juróom » (25 ans).
# Ajoutée parce qu'elle est identifiée avec certitude — pas parce qu'elle
# ressemble à quelque chose.
_MULTIPLICATEURS = {
    "benn": 1,
    "naar": 2, "naari": 2, "yu naanu": 2,
    "nett": 3, "netti": 3,
    "nent": 4, "nenti": 4,
    "juroom": 5, "juroomi": 5,
}

# Mots qui peuvent précéder « fukk » sans être un multiplicateur : articles,
# possessifs, particules verbales, unités de temps. Cette liste est fermée
# À DESSEIN — tout ce qui n'y figure pas rend le composé indéterminé.
_AVANT_FUKK_NEUTRE = {
    "", "at", "an", "ans", "ak", "am", "na", "naa", "la", "laa", "ngi",
    "sama", "dafa", "dafay", "def", "yi", "bi", "ci", "ma", "maa", "mu",
    "bu", "de", "ay", "man", "moom", "yu",
}

# Un composé numérique que l'on ne sait pas lire en entier.
# Il ne vaut pas « rien » : il vaut « ne réponds pas ».
_INDETERMINE = object()

_FUKK = ("fukk", "fukki")


def _dizaines(mots: list):
    """Valeur du groupe « [multiplicateur] fukk », s'il y en a un.

    None si le segment ne contient pas de dizaine.
    _INDETERMINE si un mot inconnu précède « fukk » : c'est peut-être un
    multiplicateur mal transcrit, et le sauter donnerait 10 au lieu de 20 —
    un âge plausible, faux, et silencieux. age_tranche étant un champ
    critique, on préfère faire relancer la question.
    """
    for i, mot in enumerate(mots):
        if mot not in _FUKK:
            continue
        precedent = mots[i - 1] if i >= 1 else ""
        couple = " ".join(mots[i - 2:i]) if i >= 2 else ""

        # Les formes en deux mots d'abord : « yu naanu » avant « naanu ».
        if couple in _MULTIPLICATEURS:
            return 10 * _MULTIPLICATEURS[couple]
        if precedent in _MULTIPLICATEURS:
            return 10 * _MULTIPLICATEURS[precedent]
        if precedent in _AVANT_FUKK_NEUTRE:
            return 10
        return _INDETERMINE
    return None


def _age_en_lettres(t: str) -> int | None:
    """Âge écrit en toutes lettres, formes additives ET multiplicatives.

    Le wolof additionne avec « ak » et multiplie par juxtaposition :

        fukki at                  10
        fukki at ak juroom        10 + 5
        ñaari fukki at ak juroom  2 x 10 + 5

    Une unité de temps (at, an, ans) doit figurer quelque part : sans elle,
    un nombre isolé dans la phrase serait pris pour un âge.

    Retourne None dès qu'un composé n'est pas lu ENTIÈREMENT. Un total
    partiel serait la pire des sorties : 15 au lieu de 25 se range dans une
    tranche, franchit tous les garde-fous et ne se voit nulle part.
    """
    if not re.search(r"\b(ans?|at)\b", t):
        return None

    total = None
    for segment in re.split(r"\bak\b", t):
        mots = segment.split()

        dizaine = _dizaines(mots)
        if dizaine is _INDETERMINE:
            return None
        if dizaine is not None:
            total = dizaine if total is None else total + dizaine
            continue

        for mot, valeur in _MOTS_AGE_TRIES:
            if re.search(rf"\b{mot}\b", segment):
                total = valeur if total is None else total + valeur
                break
    return total


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
        n = _age_en_lettres(t)
    if n is None:
        return None
    for seuil, label in _TRANCHES:
        if n < seuil:
            return label
    return "plus de 60 ans"

# Modèle, paramètres et gestion des erreurs : voir llm.py, partagé avec recit.py.

# Valeurs renvoyées par le modèle mais refusées par le garde-fou.
# Diagnostic uniquement : rien dans le triage ne lit cette liste.
REJETS_LLM: list = []
_MAX_REJETS = 50

# Le mot « JSON » doit rester présent dans ce texte : avec
# response_format={"type": "json_object"}, l'API rejette la requête (HTTP 400)
# si aucun message ne le mentionne. Le retirer casse tout le secours LLM,
# silencieusement — l'erreur est avalée et la fonction renvoie None.
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
- Chaque question porte sur UN symptôme précis. Si le patient parle d'un AUTRE
  symptôme, il n'a pas répondu à la question posée : réponds null. Parler du
  ventre ne dit rien de la fièvre.
  Ne raisonne jamais « il n'en a pas parlé, donc il ne l'a pas ».
- Ne confonds pas TON incertitude avec celle du patient. Si le patient déclare
  explicitement qu'il ne sait pas ("xamuma", "je ne sais pas", "je ne suis pas
  sûr") et que "je ne sais pas" figure dans les options, choisis cette option :
  c'est une réponse, pas une absence de réponse.

Exemples.

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


def _corrobore(champ, texte: str, valeur) -> bool:
    """Le texte du patient soutient-il vraiment cette valeur ?

    Deux garanties déterministes, qui ne dépendent pas du prompt — la
    formulation de l'instruction s'est montrée trop instable pour porter
    seule une propriété de sécurité :

      - un "non" n'est accepté que si un marqueur de négation figure dans la
        réponse. Sinon le modèle a déduit une négation d'un silence, ce qui
        neutralise une règle d'alerte ;
      - une réponse réduite à « waaw » ou « déedéet » ne peut pas désigner
        une option dans une liste non binaire : dire oui ne dit pas si l'on
        est un homme ou une femme.
    """
    if valeur is None:
        return True

    binaire = set(champ.options) <= {"oui", "non", "je ne sais pas"}

    if binaire:
        return valeur != "non" or _detecte("non", texte)

    mots = str(texte).split()
    if len(mots) == 1 and (_detecte("oui", texte) or _detecte("non", texte)):
        return False
    return True


def extraire_par_llm(champ, texte: str, langue: str = "fr") -> str | None:
    """Secours lexical : range une réponse libre dans champ.options.

    Retourne None à la moindre incertitude — clé absente, réseau, timeout,
    JSON invalide, ou valeur hors domaine. Ne lève jamais d'exception :
    l'orchestrateur doit pouvoir relancer sa question normalement.
    """
    # Les signes d'alerte ne passent jamais par le modèle. Les réponses
    # attendues sont binaires et couvertes par le lexique ; un "non" inventé
    # y coûte une orientation. Garantie structurelle, pas dépendante du prompt.
    if champ.nom in CHAMPS_CRITIQUES:
        return None

    if not texte or not str(texte).strip() or not champ.options:
        return None

    question = (champ.question_wo if langue == "wo" else champ.question_fr) or champ.question_fr
    demande = (
        f"Question : {question}\n"
        f"Options : {json.dumps(champ.options, ensure_ascii=False)}\n"
        f"Patient : \"{str(texte).strip()}\"\n"
        "Réponse :"
    )

    try:
        valeur = llm.demander_json(_INSTRUCTION, demande).get("valeur")
    except llm.EchecLLM:
        # Clé absente, panne réseau, quota, timeout, JSON malformé :
        # on relance la question plutôt que de deviner.
        return None

    # Garde-fou : la sortie du modèle n'est jamais crue sur parole.
    if not _corrobore(champ, texte, valeur):
        if len(REJETS_LLM) < _MAX_REJETS:
            REJETS_LLM.append({"champ": champ.nom, "brut": texte,
                               "refuse": valeur, "motif": "non corroboré"})
        return None
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
