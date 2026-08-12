"""
Service de synthèse vocale — MEMBRE 2.

Décision d'architecture : le français est synthétisé PAR LE NAVIGATEUR
(API speechSynthesis, côté membre 3). Zéro dépendance serveur, latence nulle,
voix française disponible partout.

Ce module ne traite donc que le wolof, pour lequel aucune voix navigateur
n'existe : facebook/mms-tts-wol, environ 150 Mo.
"""

import io
import os

MODE_SIMULE = os.environ.get("TTS_SIMULE", "1") == "1"

_modele = None
_tokenizer = None


def charger_modeles():
    global _modele, _tokenizer
    if MODE_SIMULE:
        print("[TTS] mode simulé — aucun modèle chargé")
        return
    from transformers import VitsModel, AutoTokenizer
    print("[TTS] chargement de la voix wolof…")
    _tokenizer = AutoTokenizer.from_pretrained("facebook/mms-tts-wol")
    _modele = VitsModel.from_pretrained("facebook/mms-tts-wol").eval()
    print("[TTS] prêt")


def synthetiser_wolof(texte: str) -> bytes:
    """Retourne un WAV en mémoire. Lève une exception si le modèle est absent."""
    if MODE_SIMULE or _modele is None:
        return b""

    import torch
    import numpy as np
    import soundfile as sf

    entree = _tokenizer(texte, return_tensors="pt")
    with torch.no_grad():
        sortie = _modele(**entree).waveform

    audio = sortie.squeeze().cpu().numpy().astype(np.float32)
    tampon = io.BytesIO()
    sf.write(tampon, audio, _modele.config.sampling_rate, format="WAV")
    return tampon.getvalue()


# --------------------------------------------------------------------------
# Questions pré-enregistrées — optimisation recommandée.
#
# Les questions d'anamnèse sont peu nombreuses et toujours identiques.
# Les synthétiser une fois et les servir depuis le disque retire 1 à 2 s
# par tour, sur les tours les plus fréquents.
#
#   python -c "from services.tts import pregenerer; pregenerer()"
# --------------------------------------------------------------------------

DOSSIER_CACHE = "audio_cache"


def pregenerer():
    import hashlib
    import domaine

    os.makedirs(DOSSIER_CACHE, exist_ok=True)
    for champ in domaine.CHAMPS:
        texte = champ.question_wo
        if not texte:
            continue
        cle = hashlib.md5(texte.encode()).hexdigest()[:12]
        chemin = os.path.join(DOSSIER_CACHE, f"{cle}.wav")
        if os.path.exists(chemin):
            continue
        données = synthetiser_wolof(texte)
        if données:
            with open(chemin, "wb") as f:
                f.write(données)
            print("généré :", champ.nom)


def depuis_cache(texte: str) -> bytes | None:
    import hashlib
    cle = hashlib.md5(texte.encode()).hexdigest()[:12]
    chemin = os.path.join(DOSSIER_CACHE, f"{cle}.wav")
    if os.path.exists(chemin):
        with open(chemin, "rb") as f:
            return f.read()
    return None
