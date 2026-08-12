"""
API HTTP — MEMBRE 2.

Enveloppe l'orchestrateur pour que le membre 3 puisse construire l'interface
sans jamais lire la machine à états.

Lancement :
    uvicorn api:app --reload --port 8000

Documentation interactive : http://localhost:8000/docs
"""

import base64
import tempfile
from pathlib import Path

from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from orchestrateur import Session
from services import stt, tts

app = FastAPI(title="Agent vocal de triage")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],          # hackathon : à restreindre en production
    allow_methods=["*"],
    allow_headers=["*"],
)

SESSIONS: dict[str, Session] = {}


@app.on_event("startup")
def demarrage():
    stt.charger_modeles()
    tts.charger_modeles()


# Interface de démonstration servie par l'API elle-même.
# Indispensable : getUserMedia (micro) exige un contexte sécurisé, ce que
# file:// n'est pas. Servie depuis localhost, le micro fonctionne.
_web = Path(__file__).parent / "web"
if _web.is_dir():
    from fastapi.staticfiles import StaticFiles
    app.mount("/app", StaticFiles(directory=str(_web), html=True), name="web")


# --------------------------------------------------------------------------
# Modèles d'échange
# --------------------------------------------------------------------------

class CreationSession(BaseModel):
    langue: str = "fr"
    localite: str | None = None


class ReponseTexte(BaseModel):
    texte: str


def _serialiser(session: Session, tour) -> dict:
    """Format unique renvoyé au front, quel que soit le point d'entrée."""
    audio = None
    if session.langue == "wo" and tour.texte:
        données = tts.depuis_cache(tour.texte) or tts.synthetiser_wolof(tour.texte)
        if données:
            audio = base64.b64encode(données).decode()

    return {
        "session_id": session.id,
        "texte": tour.texte,
        "etat": tour.etat,
        "champ": tour.champ,
        "options": tour.options,
        "terminee": session.terminee,
        "conclusion": tour.conclusion,
        "audio_wav_b64": audio,     # null en français : le navigateur synthétise
    }


def _recuperer(session_id: str) -> Session:
    session = SESSIONS.get(session_id)
    if session is None:
        raise HTTPException(404, "Session inconnue ou expirée")
    return session


# --------------------------------------------------------------------------
# Points d'entrée
# --------------------------------------------------------------------------

@app.get("/sante")
def sante():
    return {
        "statut": "ok",
        "stt_simule": stt.MODE_SIMULE,
        "tts_simule": tts.MODE_SIMULE,
        "sessions_actives": len(SESSIONS),
    }


@app.post("/session")
def creer_session(corps: CreationSession):
    if corps.langue not in ("fr", "wo"):
        raise HTTPException(400, "Langue non prise en charge")
    session = Session(langue=corps.langue, localite=corps.localite)
    SESSIONS[session.id] = session
    return _serialiser(session, session.demarrer())


@app.post("/session/{session_id}/texte")
def repondre_texte(session_id: str, corps: ReponseTexte):
    """Réponse tapée au clavier — utile pour les tests et comme repli."""
    session = _recuperer(session_id)
    if session.terminee:
        raise HTTPException(409, "Session déjà terminée")
    return _serialiser(session, session.repondre(corps.texte))


@app.post("/session/{session_id}/audio")
async def repondre_audio(session_id: str, fichier: UploadFile = File(...)):
    """Réponse vocale : transcription puis passage à l'orchestrateur."""
    session = _recuperer(session_id)
    if session.terminee:
        raise HTTPException(409, "Session déjà terminée")

    suffixe = Path(fichier.filename or "audio.webm").suffix or ".webm"
    chemin = tempfile.mktemp(suffix=suffixe)
    with open(chemin, "wb") as f:
        f.write(await fichier.read())

    try:
        transcription = stt.transcrire(chemin, langue=session.langue)
    except Exception as e:
        raise HTTPException(500, f"Échec de la transcription : {e}")
    finally:
        Path(chemin).unlink(missing_ok=True)

    reponse = _serialiser(session, session.repondre(transcription))
    reponse["transcription"] = transcription     # affichée pour la démonstration
    return reponse


@app.get("/session/{session_id}/trace")
def trace(session_id: str):
    """Trace de décision — c'est l'écran qui impressionne le jury."""
    session = _recuperer(session_id)
    import alertes
    return {
        "dossier": session.dossier,
        "regles_declenchees": [
            {"code": a.code, "libelle": a.libelle, "niveau": a.niveau}
            for a in alertes.evaluer(session.dossier)
        ],
        "conclusion": session.conclusion,
        "journal": session.journal(),
        "evenements": session.trace,
    }


@app.delete("/session/{session_id}")
def fermer(session_id: str):
    SESSIONS.pop(session_id, None)
    return {"ferme": True}
