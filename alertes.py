"""
Signes d'alerte : règles déterministes, évaluées à chaque tour.

Ces règles ne passent JAMAIS par un modèle de langage. Elles court-circuitent
tout le raisonnement et basculent en orientation dès qu'une condition est vraie.

C'est le filet de sécurité du système, et la partie que le jury testera.
À faire relire par un professionnel de santé avant la soutenance.
"""

from dataclasses import dataclass
from typing import Callable

URGENT = "urgent"          # orientation immédiate
ORIENTE = "oriente"        # orientation, sans caractère d'urgence


@dataclass
class Alerte:
    code: str
    libelle: str
    niveau: str
    condition: Callable[[dict], bool]


def _oui(d: dict, champ: str) -> bool:
    return d.get(champ) == "oui"


REGLES = [
    Alerte("age_nourrisson", "Enfant de moins de 5 ans", ORIENTE,
           lambda d: d.get("age_tranche") == "moins de 5 ans"),

    Alerte("grossesse", "Grossesse déclarée", ORIENTE,
           lambda d: _oui(d, "grossesse")),

    Alerte("dyspnee", "Difficulté respiratoire", URGENT,
           lambda d: _oui(d, "dyspnee")),

    Alerte("douleur_thoracique", "Douleur thoracique", URGENT,
           lambda d: _oui(d, "douleur_thoracique")),

    Alerte("conscience", "Altération de la conscience", URGENT,
           lambda d: _oui(d, "conscience_alteree")),

    Alerte("saignement", "Saignement actif", URGENT,
           lambda d: _oui(d, "saignement")),

    Alerte("raideur_nuque", "Raideur de nuque avec fièvre — suspicion méningée", URGENT,
           lambda d: _oui(d, "raideur_nuque") and _oui(d, "fievre")),

    Alerte("deshydratation", "Signes de déshydratation", URGENT,
           lambda d: _oui(d, "deshydratation")),

    Alerte("fievre_prolongee", "Fièvre évoluant depuis plus de 3 jours", ORIENTE,
           lambda d: _oui(d, "fievre") and _entier(d, "duree_jours") > 3),

    Alerte("diarrhee_severe", "Diarrhée profuse (plus de 6 selles par jour)", ORIENTE,
           lambda d: _entier(d, "selles_par_jour") > 6),

    Alerte("vomissements_persistants", "Vomissements avec fièvre", ORIENTE,
           lambda d: _oui(d, "vomissements") and _oui(d, "fievre")),

    Alerte("terrain", "Antécédent de diabète ou d'hypertension", ORIENTE,
           lambda d: _oui(d, "antecedents")),

    Alerte("echec_traitement", "Absence d'amélioration après automédication", ORIENTE,
           lambda d: _oui(d, "echec_automedication")),

    Alerte("duree_longue", "Symptômes évoluant depuis plus de 7 jours", ORIENTE,
           lambda d: _entier(d, "duree_jours") > 7),

    Alerte("tdr_systematique",
           "Fièvre : test de diagnostic rapide du paludisme requis (PNLP)", ORIENTE,
           lambda d: _oui(d, "fievre")),

    Alerte("toux_plus_3_semaines",
           "Toux depuis plus de 3 semaines — dépistage tuberculose (PNT)", ORIENTE,
           lambda d: d.get("motif_principal") == "respiratoire"
                     and _entier(d, "duree_jours") > 21),
]


def _entier(d: dict, champ: str) -> int:
    valeur = d.get(champ)
    try:
        return int(valeur)
    except (TypeError, ValueError):
        return -1


def evaluer(dossier: dict) -> list:
    """Retourne la liste des alertes déclenchées, les urgentes en premier."""
    declenchees = []
    for regle in REGLES:
        try:
            if regle.condition(dossier):
                declenchees.append(regle)
        except Exception:
            # Une règle ne doit jamais interrompre l'entretien.
            continue
    declenchees.sort(key=lambda a: 0 if a.niveau == URGENT else 1)
    return declenchees


def niveau_global(alertes: list) -> str | None:
    if not alertes:
        return None
    return URGENT if any(a.niveau == URGENT for a in alertes) else ORIENTE
