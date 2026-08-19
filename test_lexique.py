"""
Non-régression du lexique sur des transcriptions RÉELLES.

    python test_lexique.py

Tous les énoncés de ce fichier sortent du modèle de transcription, pas
d'une orthographe normée : « samag bopp », « noyibu jafe », « waccub »,
« dëdëd ». C'est ce que le triage reçoit vraiment.

Trois blocs, tous bloquants :

  RECONNAISSANCE   ce qui doit être compris malgré la transcription
  NOMBRES          les composés wolof (« ñaari fukki at ak juroom » = 25)
  FAUX POSITIFS    ce qui ne doit SURTOUT PAS être compris — « tànk »
                   (jambe) ne doit jamais déclencher « tàngaay » (fièvre)

Le troisième bloc est le garde-fou du premier : assouplir la normalisation
phonétique fait gagner des reconnaissances et perdre de la discrimination.
Sans ces cas, un assouplissement trop large passerait pour un progrès.
"""

import sys

import extraction
from extraction import contient, extraire_age, extraire_binaire, extraire_motif


# Options réelles du champ age_tranche (domaine.py).
TRANCHES = ["moins de 5 ans", "5 a 9 ans", "10 a 14 ans",
            "15 a 60 ans", "plus de 60 ans"]


def _nombre(texte: str):
    """Nombre lu par le lexique des âges, avant rangement en tranche."""
    return extraction._age_en_lettres(extraction._simplifier(texte))


# --------------------------------------------------------------------------
# Reconnaissance
# --------------------------------------------------------------------------

RECONNAISSANCE = [
    ("motif cephalee",
     lambda: extraire_motif("samag bopp dafay metti"), "cephalee"),
    ("motif abdominal",
     lambda: extraire_motif("sama biir dafay metti"), "abdominal"),
    ("motif respiratoire",
     lambda: extraire_motif("damay sëqat bu baax"), "respiratoire"),
    ("dyspnee = oui",
     lambda: extraction.extraire_reprise("dyspnee", "noyibu jafe laa ame"),
     "oui"),
    ("binaire non (dëdëd)",
     lambda: extraire_binaire("dëdëd"), "non"),
]

# Le récit complet du banc d'essai, avec « waccub » tel que transcrit.
RECIT = ("sama bopp dafay metti ñaari fan yi yépp sama yaram dafa tang "
         "te damay waccub")

RECONNAISSANCE += [
    ("recit complet -> motif cephalee",
     lambda: extraire_motif(RECIT), "cephalee"),
    ("recit complet -> fievre detectable",
     lambda: extraction._detecte("fievre", RECIT), True),
    ("recit complet -> vomir detectable",
     lambda: extraction._detecte("vomir", RECIT), True),
]


# --------------------------------------------------------------------------
# Nombres composés
# --------------------------------------------------------------------------
#
# Le wolof compose par addition avec « ak » et par multiplication par
# juxtaposition : fukki = 10, ñaari fukki = 2 x 10.
#
# On vérifie le NOMBRE autant que la tranche : 15 et 25 tombent tous deux
# dans « 15 a 60 ans ». Un test qui ne regarderait que la tranche laisserait
# passer un multiplicateur perdu.

NOMBRES = [
    ("fukki at                 -> 10", lambda: _nombre("fukki at"), 10),
    ("fukki at ak juroom       -> 15",
     lambda: _nombre("fukki at ak juroom"), 15),
    ("ñaari fukki at ak juroom -> 25",
     lambda: _nombre("ñaari fukki at ak juroom"), 25),
]

TRANCHE = [
    ("fukki at                 -> 10 a 14 ans",
     lambda: extraire_age("fukki at", TRANCHES), "10 a 14 ans"),
    ("fukki at ak juroom       -> 15 a 60 ans",
     lambda: extraire_age("fukki at ak juroom", TRANCHES), "15 a 60 ans"),
    ("ñaari fukki at ak juroom -> 15 a 60 ans",
     lambda: extraire_age("ñaari fukki at ak juroom", TRANCHES),
     "15 a 60 ans"),
]


def composes_non_resolus():
    """Un composé numérique non résolu doit donner None, jamais 15.

    « yu ñaanu fukki at ak juróom » est « ñaari fukki at ak juróom » (25 ans)
    mal transcrit. Le préfixe n'est pas du bruit : c'est le multiplicateur.
    L'ignorer pour ne garder que « fukki » rendrait 15 — un âge plausible et
    faux, donc une tranche potentiellement fausse sur un champ critique.

    Deux issues sont acceptables, et deux seulement :
      - 25, si la forme transcrite est au lexique ;
      - None, pour que l'agent repose la question.
    """
    echecs = []
    for texte in ("yu ñaanu fukki at ak juróom",
                  "xxxx fukki at ak juroom"):
        n = _nombre(texte)
        if n not in (25, None):
            echecs.append(f"{texte!r} -> {n!r} (attendu 25 ou None, "
                          "jamais une valeur partielle)")
    return echecs


# --------------------------------------------------------------------------
# Faux positifs — le garde-fou de l'assouplissement phonétique
# --------------------------------------------------------------------------

FAUX_POSITIFS = [
    ('tank  dans "dama am tangaay"  (jambe vs fievre)',
     lambda: contient("tank", "dama am tangaay"), False),
    ('bopp  dans "sama biir dafa daw"',
     lambda: contient("bopp", "sama biir dafa daw"), False),
    ('biir  dans "samag bopp dafay metti"',
     lambda: contient("biir", "samag bopp dafay metti"), False),
]


# --------------------------------------------------------------------------

def _bloc(titre, cas):
    print(f"\n{titre}")
    print("-" * 66)
    echecs = []
    for libelle, appel, attendu in cas:
        try:
            obtenu = appel()
        except Exception as e:                       # ne doit jamais arriver
            echecs.append(f"{libelle} : exception {e!r}")
            print(f"  FAIL  {libelle}")
            print(f"          exception {e!r}")
            continue
        if obtenu == attendu:
            print(f"  PASS  {libelle}")
        else:
            echecs.append(f"{libelle} : attendu {attendu!r}, obtenu {obtenu!r}")
            print(f"  FAIL  {libelle}")
            print(f"          attendu {attendu!r}, obtenu {obtenu!r}")
    return echecs


def main():
    echecs = []
    echecs += _bloc("Reconnaissance sur transcriptions reelles", RECONNAISSANCE)
    echecs += _bloc("Nombres wolof composes (valeur)", NOMBRES)
    echecs += _bloc("Nombres wolof composes (tranche)", TRANCHE)

    print("\nComposes non resolus -> None, jamais une valeur partielle")
    print("-" * 66)
    non_resolus = composes_non_resolus()
    echecs += non_resolus
    for detail in non_resolus:
        print(f"  FAIL  {detail}")
    if not non_resolus:
        print("  PASS  aucun multiplicateur perdu")

    echecs += _bloc("Faux positifs (doivent rester False)", FAUX_POSITIFS)

    total = (len(RECONNAISSANCE) + len(NOMBRES) + len(TRANCHE)
             + len(FAUX_POSITIFS) + 1)
    print("\n" + "=" * 66)
    print(f"  {total - len(echecs)}/{total} cas reussis")
    if echecs:
        print("\nECHECS :")
        for e in echecs:
            print(f"   {e}")
    return 1 if echecs else 0


if __name__ == "__main__":
    sys.exit(main())
