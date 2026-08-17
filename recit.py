"""
Extraction multi-champs à partir d'un récit libre.

Au premier tour, le patient décrit spontanément tout ce qui ne va pas.
Un seul appel au modèle de langage remplit alors plusieurs champs, au lieu
de poser une question par champ.

Mesure de référence (banc d'essai Kaggle) : l'énoncé
    « sama bopp dafay metti ñaari fan yi yépp sama yaram dafa tang
      te damay waccu »
est transcrit avec 0 % d'erreur sur mots-clés. Le récit libre est donc
exploitable en wolof comme en français.

RÈGLE DE SÉCURITÉ CENTRALE
Seuls des champs POSITIFS peuvent être déduits d'un récit. Un symptôme non
mentionné n'est PAS un symptôme absent : le patient n'y a simplement pas
pensé. Les champs de CHAMPS_DEDUCTIBLES excluent donc tous les signes
d'alerte, qui restent posés explicitement, un par un.
"""

import json

import config  # noqa: F401  — charge .env dans os.environ dès l'import
import llm

# Champs qu'un récit peut renseigner. Volontairement restreint.
# N'ajoutez JAMAIS ici un champ figurant dans orchestrateur.CHAMPS_CRITIQUES.
CHAMPS_DEDUCTIBLES = [
    "motif_principal",
    "duree_jours",
    "fievre",
    "vomissements",
    "sexe",
    "age_tranche",
]

# Modèle et paramètres : voir llm.py, partagé avec extraction.py.
# Sortie multi-champs et instruction plus longue qu'en extraction : on laisse
# davantage de place après les tokens de raisonnement.
MAX_TOKENS = 600

# Champs pour lesquels le modèle a proposé « je ne sais pas » et que le code
# a refusés. Diagnostic uniquement : mesure ce que le prompt seul ne suffit
# pas à empêcher. Rien dans le triage ne lit cette liste.
REJETS_IGNORANCE: list = []
_MAX_REJETS = 100

_INSTRUCTION = """Tu extrais des informations médicales d'un récit de patient au Sénégal.
Le patient parle wolof, français, ou mélange les deux.

On te donne le récit et la liste des champs à remplir avec leurs valeurs autorisées.
Tu renvoies UNIQUEMENT un objet JSON associant un champ à une valeur.

RÈGLES ABSOLUES
1. Une valeur doit être copiée CARACTÈRE POUR CARACTÈRE depuis les valeurs autorisées.
2. N'inclus un champ QUE si le patient l'exprime explicitement.
3. Le silence n'est jamais une négation. Si le patient ne parle pas de fièvre,
   n'écris PAS "fievre": "non" — omets simplement le champ.
4. Si TU es incertain sur un champ, OMETS-LE. N'écris jamais
   "je ne sais pas" pour exprimer ton propre doute.
5. duree_jours est un entier : nombre de jours. Une semaine vaut 7, un mois 30.
6. N'invente rien. Mieux vaut un objet vide qu'une valeur devinée.
7. La valeur "je ne sais pas" est réservée au cas où le PATIENT déclare
   explicitement ignorer quelque chose ("xamuma", "je ne sais pas").
   Elle ne doit jamais traduire ton incertitude d'extracteur.

EXEMPLES

Récit : "sama bopp dafay metti ñaari fan yi yépp sama yaram dafa tang te damay waccu"
{"motif_principal": "cephalee", "duree_jours": 2, "fievre": "oui", "vomissements": "oui"}

Récit : "sama bopp dafay meti dëppi ñaari fan sama yaram dufa tangg te damay wacc"
{"motif_principal": "cephalee", "duree_jours": 2, "fievre": "oui", "vomissements": "oui"}

Récit : "j'ai mal au ventre depuis hier"
{"motif_principal": "abdominal", "duree_jours": 1}

Récit : "dama am tàngaay, ayubés la, jigéen laa, fanweer at"
{"motif_principal": "fievre_palu", "duree_jours": 7, "fievre": "oui", "sexe": "femme", "age_tranche": "15 a 60 ans"}

Récit : "bonjour, je ne me sens pas bien"
{}
"""


def _domaine(champs) -> dict:
    """Valeurs autorisées pour chaque champ déductible."""
    dom = {}
    for champ in champs:
        if champ.nom not in CHAMPS_DEDUCTIBLES:
            continue
        dom[champ.nom] = champ.options if champ.options else "entier"
    return dom


def valider(brut: dict, champs, dossier: dict) -> dict:
    """Filtre ce que le modèle propose. Le prompt guide, ce code garantit.

    Isolée de extraire_recit pour être testable sans réseau ni clé d'API :
    le modèle n'étant pas déterministe même à température 0, les invariants
    doivent tenir ici, pas dans l'instruction système.
    """
    par_nom = {c.nom: c for c in champs}
    retenus = {}

    for nom, valeur in brut.items():
        if nom not in CHAMPS_DEDUCTIBLES or nom in dossier:
            continue
        champ = par_nom.get(nom)
        if champ is None:
            continue

        # "je ne sais pas" ne peut pas être DÉDUIT d'un récit : c'est une
        # réponse que seul le patient peut donner explicitement, à une
        # question posée. Déduite, elle bloque le champ à tort et neutralise
        # les règles d'alerte.
        if valeur == "je ne sais pas":
            if len(REJETS_IGNORANCE) < _MAX_REJETS:
                REJETS_IGNORANCE.append(nom)
            continue

        if champ.type == "entier":
            try:
                n = int(valeur)
            except (TypeError, ValueError):
                continue
            if 0 <= n <= 365:
                retenus[nom] = n
        elif valeur in champ.options:
            retenus[nom] = valeur

    return retenus


def extraire_recit(texte: str, champs, dossier: dict) -> dict:
    """Retourne les champs déduits du récit. Dictionnaire vide si échec.

    Ne remplit jamais un champ déjà présent dans le dossier.
    Toute valeur hors du domaine du champ est rejetée.
    """
    if not texte or len(texte.split()) < 4:
        return {}

    domaine = {n: v for n, v in _domaine(champs).items() if n not in dossier}
    if not domaine:
        return {}

    contenu = (f"Champs à remplir : {json.dumps(domaine, ensure_ascii=False)}\n"
               f'Récit : "{texte}"')

    try:
        brut = llm.demander_json(_INSTRUCTION, contenu, max_tokens=MAX_TOKENS)
    except llm.EchecLLM:
        return {}          # panne réseau : l'entretien continue normalement

    return valider(brut, champs, dossier)
