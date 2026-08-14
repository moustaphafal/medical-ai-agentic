"""
Tests du secours par modèle de langage (Groq).

    python test_llm.py

Deux blocs distincts :

  - Les tests de SÛRETÉ sont bloquants. Ils vérifient que la fonction ne
    remonte jamais d'exception et ne laisse jamais passer une valeur hors
    domaine. Ils tournent sans réseau ni clé d'API.

  - Les tests de QUALITÉ wolof sont purement informatifs. Ils appellent le
    vrai modèle et ne font jamais échouer la suite : la qualité de sortie
    d'un modèle de 8 milliards de paramètres n'est pas une garantie.
"""

import json
import os
import sys
import time
import urllib.error
import urllib.request

import domaine
import extraction

CHAMPS = {c.nom: c for c in domaine.CHAMPS}


# --------------------------------------------------------------------------
# Simulation de la réponse HTTP de Groq
# --------------------------------------------------------------------------

class _FausseReponse:
    def __init__(self, contenu: str):
        self._charge = json.dumps(
            {"choices": [{"message": {"content": contenu}}]}).encode("utf-8")

    def read(self):
        return self._charge

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False


def _avec_reponse_simulee(contenu, champ, texte="peu importe"):
    """Exécute extraire_par_llm en simulant ce que renvoie l'API."""
    vrai_urlopen = urllib.request.urlopen
    vraie_cle = os.environ.get("GROQ_API_KEY")
    os.environ["GROQ_API_KEY"] = "cle-de-test"

    def faux_urlopen(*_a, **_k):
        if isinstance(contenu, Exception):
            raise contenu
        return _FausseReponse(contenu)

    urllib.request.urlopen = faux_urlopen
    try:
        return extraction.extraire_par_llm(champ, texte)
    finally:
        urllib.request.urlopen = vrai_urlopen
        if vraie_cle is None:
            os.environ.pop("GROQ_API_KEY", None)
        else:
            os.environ["GROQ_API_KEY"] = vraie_cle


# --------------------------------------------------------------------------
# Tests de sûreté — bloquants
# --------------------------------------------------------------------------

def test_sans_cle():
    """Sans GROQ_API_KEY : None, sans exception et sans appel réseau."""
    vraie_cle = os.environ.pop("GROQ_API_KEY", None)
    try:
        r = extraction.extraire_par_llm(CHAMPS["sexe"], "jigéen laa")
        return r is None, f"attendu None, obtenu {r!r}"
    except Exception as e:
        return False, f"exception levée : {e!r}"
    finally:
        if vraie_cle is not None:
            os.environ["GROQ_API_KEY"] = vraie_cle


def test_valeur_hors_domaine():
    """Le garde-fou refuse une option que le modèle a inventée."""
    r = _avec_reponse_simulee('{"valeur": "quinze ans"}', CHAMPS["age_tranche"])
    return r is None, f"attendu None, obtenu {r!r}"


def test_valeur_nulle():
    r = _avec_reponse_simulee('{"valeur": null}', CHAMPS["fievre"])
    return r is None, f"attendu None, obtenu {r!r}"


def test_json_invalide():
    r = _avec_reponse_simulee("ceci n'est pas du JSON", CHAMPS["fievre"])
    return r is None, f"attendu None, obtenu {r!r}"


def test_erreur_reseau():
    r = _avec_reponse_simulee(
        urllib.error.URLError("réseau injoignable"), CHAMPS["fievre"])
    return r is None, f"attendu None, obtenu {r!r}"


def test_timeout():
    r = _avec_reponse_simulee(TimeoutError("delai depasse"), CHAMPS["fievre"])
    return r is None, f"attendu None, obtenu {r!r}"


def test_valeur_valide_passe():
    """Contre-épreuve : sans elle, une fonction qui renvoie toujours None
    passerait tous les tests ci-dessus."""
    r = _avec_reponse_simulee('{"valeur": "femme"}', CHAMPS["sexe"])
    return r == "femme", f"attendu 'femme', obtenu {r!r}"


SURETE = [
    ("Sans GROQ_API_KEY                 -> None", test_sans_cle),
    ("Valeur hors domaine               -> None", test_valeur_hors_domaine),
    ("Valeur null                       -> None", test_valeur_nulle),
    ("JSON invalide                     -> None", test_json_invalide),
    ("Erreur reseau                     -> None", test_erreur_reseau),
    ("Timeout                           -> None", test_timeout),
    ("Valeur valide                     -> acceptee", test_valeur_valide_passe),
]


# --------------------------------------------------------------------------
# Tests de qualité wolof — informatifs
# --------------------------------------------------------------------------

CAS_WOLOF = [
    ("age_tranche", "fukki at",                 "10 a 14 ans"),
    ("age_tranche", "ñaar fukk ak juroom at",   "15 a 60 ans"),
    ("sexe",        "jigéen laa",               "femme"),
    ("fievre",      "sama yaram tàng na",       "oui"),
    ("fievre",      "xamuma",                   "je ne sais pas"),
]

# Le patient ne répond PAS à la question posée. Attendu : None, jamais "non".
# Ces cas gardent la règle la plus importante du prompt : une absence
# d'information n'est jamais une réponse négative. À relancer après toute
# modification de _INSTRUCTION.
CAS_SILENCE = [
    ("fievre",     "sama bopp dafa metti"),          # parle de sa tête
    ("fievre",     "naka nga def"),                  # salutation, hors sujet
    ("dyspnee",    "sama biir dafa metti"),          # parle du ventre
    ("sexe",       "waaw"),                          # « oui » ne dit pas le sexe
]

BUDGET_LATENCE = 2.0        # secondes ; au-delà, on le signale


def qualite_wolof():
    print("\nQualite wolof (informatif — n'echoue jamais la suite)")
    print("-" * 66)

    latences, corrects = [], 0
    for nom_champ, texte, attendu in CAS_WOLOF:
        champ = CHAMPS[nom_champ]
        debut = time.perf_counter()
        try:
            obtenu = extraction.extraire_par_llm(champ, texte, langue="wo")
        except Exception as e:                      # ne doit jamais arriver
            print(f"  ERREUR INATTENDUE  {nom_champ} <- {texte!r} : {e!r}")
            continue
        duree = time.perf_counter() - debut
        latences.append(duree)

        ok = obtenu == attendu
        corrects += ok
        marque = "ok  " if ok else "  X "
        print(f"  {marque} {nom_champ:12} <- {texte!r}")
        print(f"       attendu {attendu!r} | obtenu {obtenu!r} | {duree:.2f}s")

    if latences:
        moyenne = sum(latences) / len(latences)
        print("-" * 66)
        print(f"  {corrects}/{len(CAS_WOLOF)} corrects | "
              f"latence moyenne {moyenne:.2f}s "
              f"(min {min(latences):.2f}s, max {max(latences):.2f}s)")
        if moyenne > BUDGET_LATENCE:
            print(f"  ATTENTION : la latence moyenne depasse {BUDGET_LATENCE}s.")
            print("  Budget total 12s par tour, dont ~7s de transcription.")

    print("\n  Regle du silence — une non-reponse ne doit jamais donner 'non' :")
    for nom_champ, texte in CAS_SILENCE:
        try:
            obtenu = extraction.extraire_par_llm(CHAMPS[nom_champ], texte,
                                                 langue="wo")
        except Exception as e:
            print(f"    ERREUR INATTENDUE {nom_champ} <- {texte!r} : {e!r}")
            continue
        alerte = "  <-- REGRESSION" if obtenu == "non" else ""
        print(f"    {nom_champ:12} {texte!r:40} -> {obtenu!r}{alerte}")

    if extraction.REJETS_LLM:
        print("\n  Valeurs refusees par le garde-fou :")
        for r in extraction.REJETS_LLM:
            print(f"    {r['champ']:12} {r['brut']!r} -> {r['refuse']!r}")
    else:
        print("\n  Aucune valeur refusee par le garde-fou.")


# --------------------------------------------------------------------------

def main():
    print("Surete (bloquant)")
    print("-" * 66)
    echecs = 0
    for libelle, fonction in SURETE:
        ok, detail = fonction()
        echecs += not ok
        print(f"  {'PASS' if ok else 'FAIL'}  {libelle}")
        if not ok:
            print(f"        {detail}")
    print("-" * 66)
    print(f"  {len(SURETE) - echecs}/{len(SURETE)} tests de surete reussis")

    if os.environ.get("GROQ_API_KEY"):
        qualite_wolof()
    else:
        print("\nGROQ_API_KEY absente : tests de qualite wolof ignores.")
        print("Le secours par modele est desactive, l'agent relance ses questions.")

    return 1 if echecs else 0


if __name__ == "__main__":
    sys.exit(main())
