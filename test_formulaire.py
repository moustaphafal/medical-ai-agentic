"""
Couverture du formulaire thérapeutique et garde-fous.

    python test_formulaire.py

Parcourt les 5 motifs x 4 tranches d'âge et affiche ce que candidats()
retourne. Trois propriétés sont vérifiées de façon bloquante :

  1. Aucune entrée hors automédication n'est jamais proposée.
     METRO (antibiotique sur prescription) et PARA-INJ (perfusion IV)
     ne doivent apparaître dans aucune des 20 combinaisons.
  2. Aucune posologie servie n'est vide ni ne renvoie ailleurs
     ("Non adapté", "Non recommandé", "Passer à", "Usage principalement").
  3. En MODE_STRICT, aucune entrée en statut brouillon n'est servie.
"""

import sys

import domaine
import formulaire

MOTIFS = list(domaine.MOTIFS)
TRANCHES = formulaire.TRANCHES

# Doivent rester invisibles quel que soit le profil.
INTERDITS = ["METRO", "PARA-INJ"]


def couverture():
    """Tableau motif x tranche. Retourne les anomalies détectées."""
    anomalies = []
    lignes = []

    for motif in MOTIFS:
        for tranche in TRANCHES:
            trouves = formulaire.candidats(motif, tranche)
            codes = [e["code"] for e in trouves]

            for e in trouves:
                code = e["code"]

                if code in INTERDITS:
                    anomalies.append(
                        f"{motif}/{tranche} : {code} propose alors qu'il est "
                        "hors automedication")

                if e.get("automedication", True) is not True:
                    anomalies.append(
                        f"{motif}/{tranche} : {code} a automedication=false")

                posologie = formulaire.posologie_servable(e, tranche)
                if not posologie:
                    anomalies.append(
                        f"{motif}/{tranche} : {code} sans posologie servable")
                elif posologie.lower().startswith(
                        formulaire.PREFIXES_NON_SERVABLES):
                    anomalies.append(
                        f"{motif}/{tranche} : {code} posologie non servable "
                        f"« {posologie[:50]} »")

                statut = e.get("validation", {}).get("statut")
                if formulaire.MODE_STRICT and statut != "valide":
                    anomalies.append(
                        f"{motif}/{tranche} : {code} en statut {statut!r}")

            lignes.append((motif, tranche, codes))

    return lignes, anomalies


def afficher(lignes):
    print("Couverture — candidats(motif, tranche)")
    print("=" * 74)
    motif_courant = None
    for motif, tranche, codes in lignes:
        if motif != motif_courant:
            print(f"\n{motif}")
            motif_courant = motif
        etat = ", ".join(codes) if codes else "— aucun, bascule en orientation"
        print(f"   {tranche:16} {etat}")


def inventaire():
    """Entrées du JSON qu'aucune combinaison ne peut atteindre, et pourquoi."""
    atteignables = set()
    for motif in MOTIFS:
        for tranche in TRANCHES:
            for e in formulaire.candidats(motif, tranche):
                atteignables.add(e["code"])

    print("\n" + "=" * 74)
    print("Entrees jamais atteignables")
    print("=" * 74)
    for e in formulaire.FORMULAIRE:
        code = e["code"]
        if code in atteignables:
            continue
        raisons = []
        if e.get("automedication", True) is not True:
            raisons.append("hors automedication")
        statut = e.get("validation", {}).get("statut")
        if statut != "valide":
            raisons.append(f"statut {statut}")
        if not any(formulaire.posologie_servable(e, t) for t in TRANCHES):
            raisons.append("aucune posologie servable")
        if not e.get("motifs"):
            raisons.append("aucun motif")
        print(f"   {code:12} {', '.join(raisons) or 'raison indeterminee'}")

    servies = sorted(atteignables)
    print(f"\n   Atteignables : {len(servies)}/{len(formulaire.FORMULAIRE)} "
          f"{servies}")


def main():
    print(f"MODE_STRICT = {formulaire.MODE_STRICT}   "
          f"entrees chargees : {len(formulaire.FORMULAIRE)}\n")

    lignes, anomalies = couverture()
    afficher(lignes)
    inventaire()

    print("\n" + "=" * 74)
    if anomalies:
        print(f"ECHEC — {len(anomalies)} anomalie(s)")
        for a in anomalies:
            print(f"   {a}")
        return 1

    print("OK — aucune anomalie")
    print(f"   {', '.join(INTERDITS)} absents des {len(lignes)} combinaisons")
    print("   aucune posologie vide ou renvoyant a une autre forme")
    print("   aucune entree en brouillon servie")
    return 0


if __name__ == "__main__":
    sys.exit(main())
