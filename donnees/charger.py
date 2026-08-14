"""
Chargement et contrôle des données cliniques.

Ce module refuse de servir une entrée incomplète ou non validée.
C'est une propriété de sécurité, et un argument de soutenance :
le code lui-même interdit de recommander ce qui n'a pas été relu.

Vérification en ligne de commande :
    python donnees/charger.py
"""

import json
from pathlib import Path

RACINE = Path(__file__).parent

# Passer à False uniquement pour une démonstration explicitement annoncée
# comme non validée cliniquement.
MODE_STRICT = True

CHAMPS_SOURCE = ["titre", "editeur", "annee", "url", "consulte_le"]
TRANCHES = ["moins de 5 ans", "5 a 15 ans", "15 a 60 ans", "plus de 60 ans"]


class DonneeInvalide(Exception):
    pass


def _charger(nom: str) -> dict:
    chemin = RACINE / nom
    if not chemin.exists():
        raise DonneeInvalide(f"Fichier manquant : {nom}")
    return json.loads(chemin.read_text(encoding="utf-8"))


def _source_complete(source: dict) -> list:
    return [c for c in CHAMPS_SOURCE if not source.get(c)]


def _validee(entree: dict) -> bool:
    """Aligné sur formulaire.py : seul le statut décide.

    Le champ 'par' reste volontairement vide tant qu'aucun professionnel de
    santé n'a relu les fiches ; l'exiger ici faisait diverger ce rapport de
    ce que le système sert réellement.
    """
    return entree.get("validation", {}).get("statut") == "valide"


# --------------------------------------------------------------------------

def controler() -> dict:
    """Retourne un rapport de complétude. N'interrompt jamais l'exécution."""
    rapport = {"pretes": [], "incompletes": [], "non_validees": []}

    formulaire = _charger("formulaire.json")
    for e in formulaire["entrees"]:
        code = e.get("code", "?")
        manques = []

        if not e.get("principe_actif"):
            manques.append("principe_actif")
        if not e.get("indication"):
            manques.append("indication")
        if not any(e.get("posologie", {}).get(t) for t in TRANCHES):
            manques.append("posologie (aucune tranche renseignée)")
        manques += [f"source.{c}" for c in _source_complete(e.get("source", {}))]

        if manques:
            rapport["incompletes"].append({"code": code, "manque": manques})
        elif not _validee(e):
            rapport["non_validees"].append(code)
        else:
            rapport["pretes"].append(code)

    return rapport


def entrees_servables() -> list:
    """Entrées que le système accepte de recommander."""
    formulaire = _charger("formulaire.json")
    entrees = formulaire["entrees"]
    if not MODE_STRICT:
        return entrees
    return [e for e in entrees if _validee(e) and not _source_complete(e.get("source", {}))]


def protocole(motif: str) -> dict | None:
    p = _charger("protocoles.json")["protocoles"].get(motif)
    if not p or not p.get("titre"):
        return None
    return p


# --------------------------------------------------------------------------

if __name__ == "__main__":
    r = controler()
    print(f"Prêtes à servir      : {len(r['pretes'])}  {r['pretes']}")
    print(f"Validées manquantes  : {len(r['non_validees'])}  {r['non_validees']}")
    print(f"Incomplètes          : {len(r['incompletes'])}")
    for e in r["incompletes"]:
        print(f"   {e['code']} : {', '.join(e['manque'])}")

    print("\nProtocoles renseignés :")
    for m in ["fievre_palu", "diarrhee", "respiratoire", "abdominal", "cephalee"]:
        print(f"   {m:14} : {'oui' if protocole(m) else 'NON'}")

    servables = entrees_servables()
    print(f"\nMODE_STRICT={MODE_STRICT} → {len(servables)} entrée(s) servable(s)")
    if not servables:
        print("   Toutes les consultations basculeront en orientation.")
        print("   C'est le comportement correct tant que rien n'est validé.")
