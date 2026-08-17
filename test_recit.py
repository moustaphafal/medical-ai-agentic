"""
Tests du récit libre.

Deux catégories :
  - SÛRETÉ  : doivent passer sans clé d'API. Bloquants.
  - RÉELS   : nécessitent GROQ_API_KEY. Informatifs, non bloquants
              (le modèle n'est pas déterministe même à température 0).

    python test_recit.py
"""

import os
import sys

import domaine
import recit
from orchestrateur import CHAMPS_CRITIQUES


def sûreté():
    """Invariants qui ne doivent jamais être violés."""
    echecs = []

    # 1. Aucun signe d'alerte ne doit être déductible d'un récit.
    fuite = set(recit.CHAMPS_DEDUCTIBLES) & CHAMPS_CRITIQUES
    fuite.discard("age_tranche")      # exception assumée, voir plus bas
    if fuite:
        echecs.append(f"REGRESSION : champs critiques déductibles -> {fuite}")

    # 2. Sans clé, la fonction renvoie {} sans exception.
    sauve = os.environ.pop("GROQ_API_KEY", None)
    try:
        r = recit.extraire_recit("j'ai mal a la tete depuis deux jours",
                                 domaine.CHAMPS, {})
        if r != {}:
            echecs.append(f"sans cle : attendu {{}}, obtenu {r}")
    except Exception as e:
        echecs.append(f"sans cle : exception {type(e).__name__}")
    finally:
        if sauve:
            os.environ["GROQ_API_KEY"] = sauve

    # 3. Un énoncé trop court n'appelle pas le modèle.
    if recit.extraire_recit("waaw", domaine.CHAMPS, {}) != {}:
        echecs.append("enonce court : devrait renvoyer {}")

    # 4. Un champ déjà rempli n'est jamais écrasé.
    dossier = {"motif_principal": "cephalee", "duree_jours": 5}
    r = recit.extraire_recit(
        "j'ai mal au ventre depuis dix jours et j'ai de la fievre",
        domaine.CHAMPS, dossier)
    if "motif_principal" in r or "duree_jours" in r:
        echecs.append(f"champ existant ecrase : {r}")

    # 5. « je ne sais pas » ne peut pas être déduit d'un récit.
    #    Le prompt l'interdit, le code doit le garantir : on simule ici une
    #    sortie de modèle qui l'enfreint, sans réseau ni clé.
    avant = len(recit.REJETS_IGNORANCE)
    r = recit.valider(
        {"fievre": "je ne sais pas", "vomissements": "je ne sais pas"},
        domaine.CHAMPS, {})
    if r != {}:
        echecs.append(f"REGRESSION : « je ne sais pas » deduit accepte -> {r}")
    if len(recit.REJETS_IGNORANCE) != avant + 2:
        echecs.append("les rejets « je ne sais pas » ne sont pas comptabilises")

    # 6. Contre-épreuve : sans elle, un valider() qui rejetterait tout
    #    passerait le test precedent.
    r = recit.valider({"fievre": "oui", "duree_jours": 2}, domaine.CHAMPS, {})
    if r != {"fievre": "oui", "duree_jours": 2}:
        echecs.append(f"valeurs licites rejetees a tort : {r}")

    # 7. Une valeur hors domaine reste refusee.
    r = recit.valider({"fievre": "peut-etre", "motif_principal": "grippe"},
                      domaine.CHAMPS, {})
    if r != {}:
        echecs.append(f"valeur hors domaine acceptee : {r}")

    return echecs


CAS_REELS = [
    ("sama bopp dafay metti ñaari fan yi yépp sama yaram dafa tang te damay waccu",
     {"motif_principal": "cephalee", "duree_jours": 2,
      "fievre": "oui", "vomissements": "oui"}),
    # Transcription reelle relevee en test terrain : donnait auparavant
    # fievre et vomissements a « je ne sais pas », ce qui neutralisait
    # la regle tdr_systematique dans alertes.py.
    ("sama bopp dafay meti dëppi ñaari fan sama yaram dufa tangg te damay wacc",
     {"motif_principal": "cephalee", "duree_jours": 2,
      "fievre": "oui", "vomissements": "oui"}),
    ("j'ai mal au ventre depuis hier",
     {"motif_principal": "abdominal", "duree_jours": 1}),
    ("dama am tàngaay, ayubés la",
     {"motif_principal": "fievre_palu", "duree_jours": 7, "fievre": "oui"}),
    ("bonjour je ne me sens pas tres bien aujourd'hui",
     {}),
]

# Le silence n'est pas une négation : ces récits ne doivent produire
# AUCUNE valeur négative sur un symptôme non mentionné.
CAS_SILENCE = [
    "j'ai mal a la tete depuis deux jours",
    "sama biir dafay metti",
    "je tousse beaucoup depuis une semaine",
]


def reels():
    if not os.environ.get("GROQ_API_KEY"):
        print("\n[reels] GROQ_API_KEY absente — tests reels ignores")
        return

    depart = len(recit.REJETS_IGNORANCE)

    print("\n--- extraction reelle (informatif) ---")
    for texte, attendu in CAS_REELS:
        obtenu = recit.extraire_recit(texte, domaine.CHAMPS, {})
        ok = all(obtenu.get(k) == v for k, v in attendu.items())
        print(f"{'ok  ' if ok else 'diff'} {texte[:52]:54}")
        if not ok:
            print(f"     attendu {attendu}")
            print(f"     obtenu  {obtenu}")

    print("\n--- silence non interprete comme negation ---")
    for texte in CAS_SILENCE:
        obtenu = recit.extraire_recit(texte, domaine.CHAMPS, {})
        negatifs = {k: v for k, v in obtenu.items() if v == "non"}
        marque = "ok  " if not negatifs else "REGRESSION"
        print(f"{marque} {texte[:46]:48} negatifs={negatifs or 'aucun'}")

    # Un « je ne sais pas » deduit ne doit jamais ressortir. Le garde-fou
    # code l'empeche ; ce compteur dit si le prompt seul aurait suffi.
    print("\n--- « je ne sais pas » deduit ---")
    tous = CAS_REELS + [(t, {}) for t in CAS_SILENCE]
    for texte, _ in tous:
        obtenu = recit.extraire_recit(texte, domaine.CHAMPS, {})
        ignorances = {k: v for k, v in obtenu.items() if v == "je ne sais pas"}
        marque = "ok  " if not ignorances else "REGRESSION"
        print(f"{marque} {texte[:46]:48} {ignorances or 'aucun'}")

    rejetes = recit.REJETS_IGNORANCE[depart:]
    print(f"\nGarde-fou code : {len(rejetes)} « je ne sais pas » refuse(s) "
          f"pendant ces tests {rejetes or ''}")
    if not rejetes:
        print("   Le prompt a suffi sur cette serie — le filtre reste le "
              "garant en cas de derive du modele.")


if __name__ == "__main__":
    echecs = sûreté()
    for e in echecs:
        print("ECHEC :", e)
    print(f"\nSurete : {'OK' if not echecs else str(len(echecs)) + ' echec(s)'}")
    reels()
    sys.exit(1 if echecs else 0)
