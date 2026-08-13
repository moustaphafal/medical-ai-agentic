"""
Formulaire thérapeutique fermé.

Le modèle de langage ne rédige JAMAIS un médicament ni une posologie :
il sélectionne une entrée de cette liste. Toute recommandation renvoyée
par le système doit provenir d'ici, sans exception.

Le contenu clinique vit dans donnees/formulaire.json, avec sa source et son
statut de validation. Ce module ne fait que filtrer et mettre en forme :
aucune posologie n'est écrite ici.

Deux notions distinctes, à ne pas confondre :
  - validation.statut  : fiabilité de la SOURCE (relecture documentaire)
  - automedication     : le médicament peut-il être proposé à un patient
                         par un agent de triage ?
Une fiche peut être parfaitement sourcée et valide tout en étant hors
automédication — un injectable, ou un antibiotique sur prescription.
"""

import json
from pathlib import Path

# Passer à False uniquement pour une démonstration explicitement annoncée
# comme non validée cliniquement.
MODE_STRICT = True

CHEMIN = Path(__file__).parent / "donnees" / "formulaire.json"

TRANCHES = ["moins de 5 ans", "5 a 15 ans", "15 a 60 ans", "plus de 60 ans"]

# Une case de posologie peut être renseignée sans être servable : elle renvoie
# à une autre forme, à une autre tranche d'âge, ou à un avis médical. Lire ces
# textes à voix haute à un patient reviendrait à lui donner un non-sens.
PREFIXES_NON_SERVABLES = (
    "non adapte", "non adapté",
    "non recommande", "non recommandé",
    "passer a", "passer à",
    "usage principalement",
)


def _charger() -> list:
    donnees = json.loads(CHEMIN.read_text(encoding="utf-8"))
    return donnees["entrees"]


FORMULAIRE = _charger()
PAR_CODE = {e["code"]: e for e in FORMULAIRE}


# --------------------------------------------------------------------------

def posologie_servable(entree: dict, age_tranche: str) -> str | None:
    """Posologie utilisable pour cette tranche, ou None.

    None signifie « rien à proposer ici » : case vide, ou texte qui renvoie
    ailleurs plutôt que de donner une dose.
    """
    texte = ((entree.get("posologie") or {}).get(age_tranche) or "").strip()
    if not texte:
        return None
    if texte.lower().startswith(PREFIXES_NON_SERVABLES):
        return None
    return texte


def candidats(motif: str, age_tranche: str) -> list:
    """Entrées que le système accepte de recommander pour ce profil.

    Quatre filtres successifs : motif couvert, posologie servable pour la
    tranche, médicament relevant de l'automédication, source validée.
    """
    retenues = []
    for entree in FORMULAIRE:
        if motif not in entree.get("motifs", []):
            continue
        if posologie_servable(entree, age_tranche) is None:
            continue
        if entree.get("automedication", True) is not True:
            continue
        if MODE_STRICT and entree.get("validation", {}).get("statut") != "valide":
            continue
        retenues.append(entree)
    return retenues


def rendre(entree: dict, age_tranche: str) -> dict:
    """Met en forme une entrée pour l'interface et la trace de décision.

    La source est incluse : une recommandation doit toujours pouvoir être
    rattachée au document dont elle provient.
    """
    source = entree.get("source") or {}
    return {
        "code": entree["code"],
        "principe_actif": entree.get("principe_actif", ""),
        "forme": entree.get("forme", ""),
        "posologie": posologie_servable(entree, age_tranche)
                     or "Posologie non définie — orienter",
        "duree_max_jours": entree.get("duree_max_jours"),
        "contre_indications": entree.get("contre_indications", []),
        "conseils": entree.get("conseils", []),
        "orienter_si": entree.get("orienter_si", []),
        "source": {
            "titre": source.get("titre", ""),
            "editeur": source.get("editeur", ""),
            "annee": source.get("annee"),
        },
    }
