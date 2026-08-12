"""
Service de transcription — MEMBRE 2.

Deux modèles chargés une seule fois au démarrage :
  - français : faster-whisper small, quantifié int8 (CPU)
  - wolof    : bilalfaye/wav2vec2-large-mms-1b-wolof (CPU)

MODE_SIMULE permet à toute l'équipe de travailler sur l'API avant que les
modèles ne soient téléchargés. À passer à False une fois les modèles en place.
"""

import os
import subprocess
import tempfile
from pathlib import Path

MODE_SIMULE = os.environ.get("STT_SIMULE", "1") == "1"

_whisper = None
_mms_modele = None
_mms_proc = None
_wolof_pipe = None


# --------------------------------------------------------------------------
# Conversion audio — le navigateur envoie du webm/opus, les modèles
# n'acceptent que du WAV 16 kHz mono.
# --------------------------------------------------------------------------

def convertir_en_wav(chemin_entree: str) -> str:
    sortie = tempfile.mktemp(suffix=".wav")
    subprocess.run(
        ["ffmpeg", "-y", "-i", chemin_entree,
         "-ar", "16000", "-ac", "1", "-c:a", "pcm_s16le", sortie],
        check=True, capture_output=True,
    )
    return sortie


def charger_audio(chemin: str):
    import soundfile as sf
    import numpy as np
    wav, sr = sf.read(chemin, dtype="float32")
    if wav.ndim > 1:
        wav = wav.mean(axis=1)
    if sr != 16000:
        import librosa
        wav = librosa.resample(wav, orig_sr=sr, target_sr=16000)
    return wav


# --------------------------------------------------------------------------
# Chargement des modèles — appelé une fois au démarrage de l'API.
# Ne jamais charger un modèle dans le corps d'une requête : le temps de
# chargement (plusieurs secondes) s'ajouterait à chaque tour.
# --------------------------------------------------------------------------

def charger_modeles():
    """Ne charge plus rien au démarrage : chaque modèle est chargé
    à sa première utilisation. Évite de saturer la mémoire."""
    if MODE_SIMULE:
        print("[STT] mode simulé — aucun modèle chargé")
    else:
        print("[STT] chargement paresseux activé")


def _get_whisper():
    global _whisper
    if _whisper is None:
        from faster_whisper import WhisperModel
        print("[STT] chargement du modèle français…")
        _whisper = WhisperModel("small", device="cpu", compute_type="int8")
        print("[STT] français prêt")
    return _whisper

def _get_wolof():
    global _wolof_pipe
    if _wolof_pipe is None:
        from transformers import pipeline
        print("[STT] chargement du modèle wolof…")
        _wolof_pipe = pipeline(
            "automatic-speech-recognition",
            model="M9and2M/whisper-small-wolof",
            device=-1,
        )
        print("[STT] wolof prêt")
    return _wolof_pipe

def _get_mms():
    global _mms_modele, _mms_proc
    if _mms_modele is None:
        from transformers import AutoProcessor, Wav2Vec2ForCTC
        print("[STT] chargement du modèle wolof…")
        mid = "speechbrain/asr-wav2vec2-dvoice-wolof"
        _mms_proc = AutoProcessor.from_pretrained(mid)
        _mms_modele = Wav2Vec2ForCTC.from_pretrained(mid).to("cpu").eval()
        print("[STT] wolof prêt")
    return _mms_modele, _mms_proc


# --------------------------------------------------------------------------
# Transcription
# --------------------------------------------------------------------------

def _transcrire_fr(chemin_wav: str) -> str:
    modele = _get_whisper()
    segments, _ = modele.transcribe(chemin_wav, language="fr", beam_size=1)
    return " ".join(s.text for s in segments).strip()


""" def _transcrire_wo(chemin_wav: str) -> str:
    import torch
    modele, proc = _get_mms()
    wav = charger_audio(chemin_wav)
    x = proc(wav, sampling_rate=16000, return_tensors="pt")
    with torch.no_grad():
        logits = modele(**x).logits
    return proc.decode(logits.argmax(-1)[0]).strip() """

def _transcrire_wo(chemin_wav: str) -> str:
    return _get_wolof()(chemin_wav, chunk_length_s=30)["text"].strip()


def transcrire(chemin_audio: str, langue: str = "fr") -> str:
    """Point d'entrée unique. Accepte n'importe quel format audio."""
    if MODE_SIMULE:
        return "[simulé] " + Path(chemin_audio).stem

    chemin_wav = chemin_audio
    if not chemin_audio.lower().endswith(".wav"):
        chemin_wav = convertir_en_wav(chemin_audio)

    try:
        return _transcrire_wo(chemin_wav) if langue == "wo" else _transcrire_fr(chemin_wav)
    finally:
        if chemin_wav != chemin_audio:
            Path(chemin_wav).unlink(missing_ok=True)
