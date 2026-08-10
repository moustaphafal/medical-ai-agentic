"""
Schéma des champs collectés par l'agent et définition des motifs cliniques.

C'est le contrat central du système : l'orchestrateur, l'extraction et le triage
s'appuient tous sur ce fichier. Toute évolution du questionnaire se fait ici,
et nulle part ailleurs.
"""

from dataclasses import dataclass, field
from typing import Callable, Optional

# --------------------------------------------------------------------------
# Motifs cliniques couverts par la version 1
# --------------------------------------------------------------------------

MOTIFS = {
    "fievre_palu": "Syndrome fébrile / suspicion de paludisme",
    "diarrhee": "Diarrhée aiguë",
    "respiratoire": "Toux et infection respiratoire",
    "abdominal": "Douleur abdominale",
    "cephalee": "Céphalée",
}

TOUS = set(MOTIFS)


# --------------------------------------------------------------------------
# Définition d'un champ
# --------------------------------------------------------------------------

@dataclass
class Champ:
    nom: str
    question_fr: str
    question_wo: str
    type: str                       # "choix" | "entier" | "booleen" | "multiple"
    options: list = field(default_factory=list)
    pertinent_pour: set = field(default_factory=lambda: set(TOUS))
    requis_si: Optional[Callable] = None   # dossier -> bool
    ordre: int = 100

    def est_requis(self, dossier: dict) -> bool:
        # Un champ spécifique à certains motifs n'est requis que si le motif
        # est identifié et figure dans sa liste. Les champs universels
        # (pertinent_pour == TOUS) restent requis même si le motif a échoué,
        # sans quoi l'entretien se bloquerait entièrement.
        if self.pertinent_pour != TOUS:
            if dossier.get("motif_principal") not in self.pertinent_pour:
                return False
        if self.requis_si is not None:
            return bool(self.requis_si(dossier))
        return True


OUI_NON = ["oui", "non", "je ne sais pas"]


# --------------------------------------------------------------------------
# Le questionnaire
#
# ordre 0-9    : identification du motif
# ordre 10-19  : terrain (âge, sexe, grossesse) — conditionne les alertes
# ordre 20-29  : caractérisation générale
# ordre 30+    : questions spécifiques au motif
# --------------------------------------------------------------------------

CHAMPS = [
    Champ(
        nom="motif_principal",
        question_fr="Quel est votre problème principal aujourd'hui ?",
        question_wo="Lan moo la jot ? Bopp, biir, tàngaay, sëqët, walla biir bu daw ?",
        type="choix",
        options=list(MOTIFS),
        ordre=0,
    ),

    # ---- terrain ----
    Champ(
        nom="age_tranche",
        question_fr="Quel âge a le patient ?",
        question_wo="Ñaata at la am ?",
        type="choix",
        options=["moins de 5 ans", "5 a 15 ans", "15 a 60 ans", "plus de 60 ans"],
        ordre=10,
    ),
    Champ(
        nom="sexe",
        question_fr="Le patient est-il un homme ou une femme ?",
        question_wo="Góor la walla jigéen ?",
        type="choix",
        options=["homme", "femme"],
        ordre=11,
    ),
    Champ(
        nom="grossesse",
        question_fr="Êtes-vous enceinte ?",
        question_wo="Yow ëmb nga ?",
        type="choix",
        options=OUI_NON,
        requis_si=lambda d: d.get("sexe") == "femme"
        and d.get("age_tranche") in ("15 a 60 ans",),
        ordre=12,
    ),

    # ---- caractérisation générale ----
    Champ(
        nom="duree_jours",
        question_fr="Depuis combien de jours avez-vous ces symptômes ?",
        question_wo="Ñaata fan la ?",
        type="entier",
        ordre=20,
    ),
    Champ(
        nom="fievre",
        question_fr="Avez-vous de la fièvre ou le corps chaud ?",
        question_wo="Am nga tàngaay ? Sa yaram tàng na ?",
        type="choix",
        options=OUI_NON,
        pertinent_pour={"fievre_palu", "diarrhee", "respiratoire", "abdominal", "cephalee"},
        ordre=21,
    ),

    # ---- signes d'alerte transversaux ----
    Champ(
        nom="dyspnee",
        question_fr="Avez-vous du mal à respirer ?",
        question_wo="Noyyi dafa la jafe ?",
        type="choix",
        options=OUI_NON,
        pertinent_pour={"fievre_palu", "respiratoire", "abdominal"},
        ordre=22,
    ),
    Champ(
        nom="conscience_alteree",
        question_fr="Le patient est-il confus, très somnolent ou a-t-il perdu connaissance ?",
        question_wo="Xel mi dafa jaxasoo ? Dafa nelaw bu baree ?",
        type="choix",
        options=OUI_NON,
        pertinent_pour={"fievre_palu", "cephalee", "abdominal"},
        ordre=23,
    ),
    Champ(
        nom="saignement",
        question_fr="Y a-t-il un saignement quelque part ?",
        question_wo="Am na deret ?",
        type="choix",
        options=OUI_NON,
        pertinent_pour={"diarrhee", "abdominal", "respiratoire"},
        ordre=24,
    ),
    Champ(
        nom="vomissements",
        question_fr="Vomissez-vous ?",
        question_wo="Dangay waccu ?",
        type="choix",
        options=OUI_NON,
        pertinent_pour={"fievre_palu", "diarrhee", "abdominal", "cephalee"},
        ordre=25,
    ),
    Champ(
        nom="antecedents",
        question_fr="Avez-vous du diabète ou de l'hypertension ?",
        question_wo="Am nga diabet walla tension ?",
        type="choix",
        options=OUI_NON,
        ordre=26,
    ),
    Champ(
        nom="echec_automedication",
        question_fr="Avez-vous déjà pris un médicament sans amélioration ?",
        question_wo="Jël nga garab te baaxul ?",
        type="choix",
        options=OUI_NON,
        ordre=27,
    ),

    # ---- spécifiques : diarrhée ----
    Champ(
        nom="selles_par_jour",
        question_fr="Combien de fois allez-vous à la selle par jour ?",
        question_wo="Ñaata yoon nga dem wanag ci bés bu nekk ?",
        type="entier",
        pertinent_pour={"diarrhee"},
        ordre=30,
    ),
    Champ(
        nom="deshydratation",
        question_fr="Avez-vous très soif, la bouche sèche, ou urinez-vous peu ?",
        question_wo="Mar nga bu baree ? Sa gémmiñ dafa wow ?",
        type="choix",
        options=OUI_NON,
        pertinent_pour={"diarrhee"},
        ordre=31,
    ),

    # ---- spécifiques : respiratoire ----
    Champ(
        nom="douleur_thoracique",
        question_fr="Avez-vous mal à la poitrine ?",
        question_wo="Sa dënn dafa metti ?",
        type="choix",
        options=OUI_NON,
        pertinent_pour={"respiratoire", "abdominal"},
        ordre=32,
    ),

    # ---- spécifiques : céphalée ----
    Champ(
        nom="raideur_nuque",
        question_fr="Avez-vous du mal à baisser la tête vers la poitrine ?",
        question_wo="Sa baat dafa dëgër ? Mën nga suuxal sa bopp ?",
        type="choix",
        options=OUI_NON,
        pertinent_pour={"cephalee", "fievre_palu"},
        ordre=33,
    ),

    # ---- localisation (facultatif, pour la donnée) ----
    Champ(
        nom="localite",
        question_fr="Dans quelle localité vous trouvez-vous ?",
        question_wo="Fan nga nekk ?",
        type="texte",
        requis_si=lambda d: False,     # jamais demandé : rempli par l'interface
        ordre=99,
    ),
]

CHAMPS_PAR_NOM = {c.nom: c for c in CHAMPS}


def prochain_champ(dossier: dict):
    """Retourne le premier champ requis non encore rempli, ou None."""
    for champ in sorted(CHAMPS, key=lambda c: c.ordre):
        if champ.nom in dossier:
            continue
        if champ.est_requis(dossier):
            return champ
    return None


def champs_manquants(dossier: dict) -> list:
    return [c.nom for c in CHAMPS if c.nom not in dossier and c.est_requis(dossier)]
