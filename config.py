"""
Chargement des variables d'environnement depuis un fichier .env.

Sans dépendance externe : le projet a déjà des contraintes de versions
natives (voir README), on n'ajoute pas python-dotenv pour vingt lignes.

À importer AVANT toute lecture de os.environ. Le chargement est déclenché
à l'import du module.

L'environnement réel prime toujours sur le fichier : une variable déjà
définie dans le shell n'est jamais écrasée.
"""

import os
from pathlib import Path

CHEMIN = Path(__file__).parent / ".env"


def charger(chemin: Path = CHEMIN) -> list:
    """Charge le .env dans os.environ. Retourne les clés effectivement posées.

    Format accepté, une paire par ligne :
        CLE=valeur
        export CLE=valeur
        CLE="valeur entre guillemets"
    Les lignes vides, celles commençant par # et les valeurs vides sont
    ignorées. Pas de commentaire en fin de ligne : le # y serait pris
    pour un caractère de la valeur.
    """
    posees = []
    if not chemin.exists():
        return posees

    for ligne in chemin.read_text(encoding="utf-8").splitlines():
        ligne = ligne.strip()
        if not ligne or ligne.startswith("#") or "=" not in ligne:
            continue
        if ligne.startswith("export "):
            ligne = ligne[len("export "):]

        cle, _, valeur = ligne.partition("=")
        cle = cle.strip()
        valeur = valeur.strip()
        if len(valeur) >= 2 and valeur[0] == valeur[-1] and valeur[0] in "\"'":
            valeur = valeur[1:-1]

        if cle and valeur and cle not in os.environ:
            os.environ[cle] = valeur
            posees.append(cle)

    return posees


CHARGEES = charger()


if __name__ == "__main__":
    # python config.py — verifier ce qui est charge, sans afficher les secrets.
    if not CHEMIN.exists():
        print(f"Aucun fichier .env trouve ({CHEMIN}).")
    elif CHARGEES:
        print(f"Chargees depuis {CHEMIN.name} :")
        for c in CHARGEES:
            valeur = os.environ[c]
            apercu = "***" if "KEY" in c or "TOKEN" in c else valeur
            print(f"  {c} = {apercu}")
    else:
        print(f"{CHEMIN.name} lu, aucune variable posee "
              "(fichier vide, ou variables deja definies dans le shell).")
