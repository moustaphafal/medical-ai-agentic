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
import llm
import recit

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
    """Exécute extraire_par_llm en simulant ce que renvoie l'API.

    Force llm.ACTIF : ces tests valident la chaîne de validation, pas la
    disponibilité du service. Ils doivent rester significatifs même quand
    le secours est coupé en production.
    """
    vrai_urlopen = urllib.request.urlopen
    vraie_cle = os.environ.get("GROQ_API_KEY")
    vrai_actif = llm.ACTIF
    llm.ACTIF = True
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
        llm.ACTIF = vrai_actif
        if vraie_cle is None:
            os.environ.pop("GROQ_API_KEY", None)
        else:
            os.environ["GROQ_API_KEY"] = vraie_cle


# --------------------------------------------------------------------------
# Tests de sûreté — bloquants
# --------------------------------------------------------------------------

def test_sans_cle():
    """Sans GROQ_API_KEY : None, sans exception et sans appel réseau.

    Force le fournisseur distant : l'invariant porte sur les services à
    clé. Sans ce cadrage, le test appellerait un modèle local — donc ne
    testerait plus rien — le jour où le fournisseur par défaut change.
    """
    vraie_cle = os.environ.pop("GROQ_API_KEY", None)
    vrai_fournisseur = llm.FOURNISSEUR
    llm.FOURNISSEUR = "groq"
    try:
        r = extraction.extraire_par_llm(CHAMPS["sexe"], "jigéen laa")
        return r is None, f"attendu None, obtenu {r!r}"
    except Exception as e:
        return False, f"exception levée : {e!r}"
    finally:
        llm.FOURNISSEUR = vrai_fournisseur
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


def test_champs_critiques_hors_llm():
    """Aucun signe d'alerte ne doit atteindre le modèle.

    Garantie structurelle : elle tient même avec une clé valide et une API
    disponible, donc sans dépendre de la qualité du prompt.
    """
    vraie_cle = os.environ.get("GROQ_API_KEY")
    os.environ["GROQ_API_KEY"] = "cle-de-test"

    appels = []
    vrai_urlopen = urllib.request.urlopen

    def espion(*a, **k):
        appels.append(1)
        return _FausseReponse('{"valeur": "non"}')

    urllib.request.urlopen = espion
    try:
        fuites = []
        for nom in sorted(domaine.CHAMPS_CRITIQUES):
            champ = CHAMPS.get(nom)
            if champ is None:
                continue
            valeur = extraction.extraire_par_llm(champ, "sama yaram tang na")
            if valeur is not None or appels:
                fuites.append(nom)
            appels.clear()
    finally:
        urllib.request.urlopen = vrai_urlopen
        if vraie_cle is None:
            os.environ.pop("GROQ_API_KEY", None)
        else:
            os.environ["GROQ_API_KEY"] = vraie_cle

    return not fuites, f"champs critiques passes au LLM : {fuites}"


def test_champ_non_critique_passe():
    """Contre-épreuve : le blocage ne doit pas assécher les autres champs."""
    r = _avec_reponse_simulee('{"valeur": "oui"}', CHAMPS["vomissements"])
    return r == "oui", f"attendu 'oui', obtenu {r!r}"


def test_interrupteur_coupe_tout():
    """llm.ACTIF = False doit empêcher tout appel, sans exception."""
    vrai_actif, vraie_cle = llm.ACTIF, os.environ.get("GROQ_API_KEY")
    vrai_urlopen = urllib.request.urlopen
    appels = []

    llm.ACTIF = False
    os.environ["GROQ_API_KEY"] = "cle-de-test"
    urllib.request.urlopen = lambda *a, **k: appels.append(1)
    try:
        valeur = extraction.extraire_par_llm(CHAMPS["vomissements"], "damay waccu")
        recolte = recit.extraire_recit("sama bopp dafay metti naari fan yi",
                                       domaine.CHAMPS, {})
    finally:
        urllib.request.urlopen = vrai_urlopen
        llm.ACTIF = vrai_actif
        if vraie_cle is None:
            os.environ.pop("GROQ_API_KEY", None)
        else:
            os.environ["GROQ_API_KEY"] = vraie_cle

    ok = valeur is None and recolte == {} and not appels
    return ok, (f"valeur={valeur!r} recit={recolte!r} appels={len(appels)}")


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
    ("Champs critiques                  -> jamais au LLM", test_champs_critiques_hors_llm),
    ("Champ non critique                -> LLM actif", test_champ_non_critique_passe),
    ("Interrupteur llm.ACTIF=False      -> aucun appel", test_interrupteur_coupe_tout),
]


# --------------------------------------------------------------------------
# Tests de qualité wolof — informatifs
# --------------------------------------------------------------------------

# Seuls des champs NON critiques : les signes d'alerte ne passent plus par
# le modèle (voir test_champs_critiques_hors_llm), donc les y tester
# reviendrait à mesurer le blocage plutôt que la qualité du modèle.
CAS_WOLOF = [
    ("sexe",         "jigéen laa",          "femme"),
    ("fievre",       "sama yaram tàng na",  "oui"),
    ("fievre",       "xamuma",              "je ne sais pas"),
    ("vomissements", "damay waccu",         "oui"),
]

# Le patient ne répond PAS à la question posée. Attendu : None, jamais "non".
# Ces cas gardent la règle la plus importante du prompt : une absence
# d'information n'est jamais une réponse négative. À relancer après toute
# modification de _INSTRUCTION.
#
# Tous portent sur des SIGNES D'ALERTE : un "non" inventé y neutralise une
# règle de alertes.py et fait perdre une orientation. Un None est toujours
# acceptable, une valeur inventée ne l'est jamais.
# Champs NON critiques uniquement. Les signes d'alerte sont désormais
# protégés par construction et non plus par le prompt : les inclure ici
# validerait le blocage, pas la règle du silence.
CAS_SILENCE = [
    ("fievre",               "sama bopp dafa metti"),   # parle de sa tête
    ("fievre",               "naka nga def"),           # salutation, hors sujet
    ("fievre",               "j'ai mal au ventre"),
    ("vomissements",         "je tousse depuis trois jours"),
    ("antecedents",          "sama bopp dafay metti"),
    ("echec_automedication", "dama am tangaay"),
    ("sexe",                 "waaw"),                   # « oui » ne dit pas le sexe
]

# Le plafond Groq mesuré est de 6000 tokens/min pour ~940 tokens par appel,
# soit environ 6 appels par minute. Au-delà, l'API renvoie 429 — et un 429
# se lit comme un None, donc comme un succès. Sans cette pause, la batterie
# de silence s'auto-valide à tort.
#
# Un fournisseur local n'a pas de plafond de débit : la pause y ajouterait
# 70 secondes pour rien. On la réserve donc aux services qui demandent une
# clé d'API, ce qui est exactement le critère « service distant facturé ».
def _pause_debit() -> float:
    try:
        return 10.0 if llm.fournisseur()["cle_env"] else 0.0
    except llm.EchecLLM:
        return 10.0


PAUSE_DEBIT = _pause_debit()

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

    if extraction.REJETS_LLM:
        print("\n  Valeurs refusees par le garde-fou :")
        for r in extraction.REJETS_LLM:
            print(f"    {r['champ']:12} {r['brut']!r} -> {r['refuse']!r}")
    else:
        print("\n  Aucune valeur refusee par le garde-fou.")


# --------------------------------------------------------------------------

def _appel_observe(nom_champ, texte):
    """(valeur, disponible). disponible=False si l'API a refusé l'appel.

    Sans cette distinction, un 429 renvoie None et se lit comme un succès :
    la batterie de silence se validerait elle-même en cas de quota épuisé.
    """
    vrai = urllib.request.urlopen
    incident = {}

    def espion(*a, **k):
        try:
            return vrai(*a, **k)
        except urllib.error.HTTPError as e:
            incident["x"] = f"HTTP {e.code}"
            raise
        except Exception as e:
            incident["x"] = type(e).__name__
            raise

    urllib.request.urlopen = espion
    try:
        valeur = extraction.extraire_par_llm(CHAMPS[nom_champ], texte,
                                             langue="wo")
    finally:
        urllib.request.urlopen = vrai
    return valeur, "x" not in incident


def regle_du_silence():
    """Bloquant sur une valeur inventée, tolérant sur une API indisponible.

    Un faux « non » sur un signe d'alerte est un défaut de sécurité.
    Un quota épuisé n'est pas un défaut du code : on le signale sans échouer.
    """
    print("\nRegle du silence — le patient repond a cote (bloquant)")
    print("-" * 66)
    print(f"  {len(CAS_SILENCE)} cas, 1 appel / {PAUSE_DEBIT:.0f}s "
          "pour rester sous le plafond de debit")

    violations, indisponibles = [], 0
    for nom_champ, texte in CAS_SILENCE:
        valeur, disponible = _appel_observe(nom_champ, texte)
        time.sleep(PAUSE_DEBIT)

        if not disponible:
            indisponibles += 1
            print(f"    {nom_champ:19} {texte[:30]:32} API indisponible")
            continue

        if valeur is None:
            print(f"    {nom_champ:19} {texte[:30]:32} None")
        else:
            violations.append(f"{nom_champ} <- {texte!r} a produit {valeur!r}")
            print(f"    {nom_champ:19} {texte[:30]:32} {valeur!r}"
                  "  <-- REGRESSION")

    observees = len(CAS_SILENCE) - indisponibles
    print(f"\n  {len(violations)} valeur(s) inventee(s) sur {observees} "
          f"observation(s) valide(s)")
    if indisponibles:
        print(f"  {indisponibles} appel(s) non aboutis — non comptes, "
              "ni comme succes ni comme echec")
    return violations


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

    if not llm.ACTIF:
        print(f"\nSecours par modele DESACTIVE (llm.ACTIF = False, "
              f"modele {llm.MODELE!r}).")
        print("Aucun candidat ne respecte la regle du silence — voir llm.py.")
        print("L'agent relance ses questions ; le triage deterministe est intact.")
    elif llm.disponible():
        qualite_wolof()
        violations = regle_du_silence()
        if violations:
            echecs += len(violations)
            print("\nECHEC — une non-reponse a produit une valeur :")
            for v in violations:
                print(f"   {v}")
    else:
        print(f"\nFournisseur {llm.FOURNISSEUR!r} indisponible : "
              "tests de qualite wolof ignores.")
        print("Le secours par modele est desactive, l'agent relance ses questions.")

    return 1 if echecs else 0


if __name__ == "__main__":
    sys.exit(main())
