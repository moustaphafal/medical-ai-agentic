"""
Démonstration console et jeu de tests.

    python demo.py            # entretien interactif en français
    python demo.py wo         # entretien interactif en wolof
    python demo.py test       # exécute les cas de test

Aucun modèle de langage ni reconnaissance vocale n'est requis :
la logique de triage se teste entièrement au clavier.
"""

import sys
from orchestrateur import Session


def interactif(langue="fr"):
    s = Session(langue=langue, localite="Dakar")
    tour = s.demarrer()
    print(f"\nAGENT : {tour.texte}")
    if tour.options:
        print(f"        ({' / '.join(tour.options)})")

    while not s.terminee:
        try:
            reponse = input("VOUS  : ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if reponse.lower() in ("quit", "q"):
            break
        tour = s.repondre(reponse)
        print(f"\nAGENT : {tour.texte}")
        if tour.options and not s.terminee:
            print(f"        ({' / '.join(tour.options)})")

    print("\n" + s.trace_lisible())
    print("\nJournal :", s.journal())


# --------------------------------------------------------------------------
# Cas de test — à compléter jusqu'à 15 (5 bénins, 5 alertes, 5 ambigus)
# --------------------------------------------------------------------------

CAS = [
    {
        "nom": "Céphalée simple chez l'adulte — attendu : bénin",
        "reponses": ["j'ai mal a la tete", "15 a 60 ans", "homme", "2", "non",
                     "non", "non", "non", "non", "non", "oui"],
        "attendu": "automedication_encadree",
    },
    {
        "nom": "Fièvre prolongée — attendu : orientation",
        "reponses": ["j'ai de la fievre", "15 a 60 ans", "homme", "5", "oui",
                     "non", "non", "non", "non", "non", "non", "oui"],
        "attendu": "orientation",
    },
    {
        "nom": "Difficulté respiratoire — attendu : orientation urgente",
        "reponses": ["je tousse beaucoup", "15 a 60 ans", "homme", "2", "non", "oui"],
        "attendu": "orientation",
    },
    {
        "nom": "Enfant de moins de 5 ans — attendu : orientation",
        "reponses": ["mon enfant a la diarrhee", "moins de 5 ans", "homme", "1",
                     "non", "non", "non", "non", "non", "3", "non", "oui"],
        "attendu": "orientation",
    },
    {
        "nom": "Réponse en wolof — mal à la tête",
        "langue": "wo",
        "reponses": ["sama bob da fey metti", "15 a 60 ans", "homme", "naar",
                     "deedeet", "deedeet", "deedeet", "deedeet", "deedeet",
                     "deedeet", "waaw"],
        "attendu": "automedication_encadree",
    },
    {
        "nom": "Réponses incompréhensibles sur signe d'alerte — attendu : orientation",
        "reponses": ["j'ai mal a la tete", "15 a 60 ans", "homme", "2", "non",
                     "xxxx", "yyyy", "zzzz"],
        "attendu": "orientation",
    },
    {
        "nom": "Bruit sur la question dyspnée — attendu : orientation",
        "reponses": ["je tousse", "15 a 60 ans", "homme", "2", "non",
                     "?????", "?????", "?????"],
        "attendu": "orientation",
    },
]


def tester():
    reussis = 0
    for cas in CAS:
        s = Session(langue=cas.get("langue", "fr"))
        s.demarrer()
        for r in cas["reponses"]:
            if s.terminee:
                break
            s.repondre(r)

        obtenu = (s.conclusion or {}).get("decision")
        ok = obtenu == cas["attendu"]
        reussis += ok
        print(f"{'PASS' if ok else 'FAIL'}  {cas['nom']}")
        if not ok:
            print(f"      attendu={cas['attendu']}  obtenu={obtenu}")
            print(f"      dossier={s.dossier}")

    print(f"\n{reussis}/{len(CAS)} cas réussis")
    return reussis == len(CAS)


if __name__ == "__main__":
    arg = sys.argv[1] if len(sys.argv) > 1 else "fr"
    if arg == "test":
        sys.exit(0 if tester() else 1)
    interactif("wo" if arg == "wo" else "fr")