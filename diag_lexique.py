"""Où l'appariement échoue-t-il ? Sur des transcriptions réelles."""
import domaine, extraction
from extraction import contient, phonetiser

# Collez ici vos transcriptions RÉELLES, telles que l'interface les affiche
CAS = [
    "samag bopp dafay metti",
    "sama bopp dafay metti ñaari fan yi yépp sama yaram dafa tang te damay waccub",
    "dëdëd",
    "fukki at ak juroom",
    "yu ñaanu fukki at ak juróom",
    "sama biir dafay metti",
    "noyibu jafe laa ame",
    "damay sëqat bu baax",
]

print("=== mots-clés détectés par transcription ===")
for txt in CAS:
    trouves = [cle for cle, formes in extraction.LEXIQUE.items()
               if any(contient(f, txt) for f in formes)]
    print(f"\n{txt}")
    print(f"  phonétisé : {phonetiser(txt)}")
    print(f"  détectés  : {trouves or 'AUCUN'}")
    print(f"  motif     : {extraction.extraire_motif(txt)}")

print("\n\n=== simulation d'un entretien complet ===")
from orchestrateur import Session
s = Session(langue="wo")
t = s.demarrer()
print("AGENT :", t.texte[:70])
for rep in CAS[:5]:
    if s.terminee:
        break
    t = s.repondre(rep)
    print(f"\nPATIENT : {rep[:50]}")
    print(f"AGENT   : {t.texte[:70]}")
    print(f"  champ={t.champ}  dossier={s.dossier}")