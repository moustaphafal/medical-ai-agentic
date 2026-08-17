"""
Accès unique au fournisseur de modèle de langage.

extraction.py et recit.py passent tous les deux par ici : le modèle, ses
paramètres et le traitement des erreurs sont définis une seule fois.

POURQUOI CES PARAMÈTRES
gpt-oss-20b est un modèle à raisonnement : il consomme des tokens de
réflexion avant d'écrire sa réponse. Avec max_tokens=40, il épuisait son
budget avant d'émettre le JSON et l'API renvoyait HTTP 400 — donc None,
indiscernable d'un refus légitime. D'où une enveloppe large et un effort
de raisonnement bas.

Ce modèle remplace llama-3.1-8b-instant, retiré du catalogue Groq
(HTTP 404, model_not_found).

DISTINGUER L'ÉCHEC DU REFUS
demander_json lève EchecLLM quand l'appel n'aboutit pas, au lieu de
renvoyer None. Sans cette distinction, un 400 ou un 429 se lit exactement
comme « le modèle a répondu null » — et une panne passe pour un succès.
"""

import json
import os
import urllib.error
import urllib.request

import config  # noqa: F401  — charge .env dans os.environ dès l'import

URL = "https://api.groq.com/openai/v1/chat/completions"
MODELE = "openai/gpt-oss-20b"
EFFORT_RAISONNEMENT = "low"
MAX_TOKENS = 400
TIMEOUT = 12
AGENT = "medical-ai-agentic/1.0 (+https://github.com/moustaphafal/medical-ai-agentic)"

# SECOURS DÉSACTIVÉ — décision du 2026-08-17.
#
# llama-3.1-8b-instant a été retiré du catalogue Groq (HTTP 404). Quatre
# remplaçants ont été évalués ; aucun ne respecte la règle du silence, qui
# est notre critère éliminatoire :
#
#   qwen/qwen3.6-27b      HTTP 400 persistants, a renvoyé le gabarit littéral
#   openai/gpt-oss-120b   invente « je ne sais pas » sur un silence
#   allam-2-7b            répond « non » à tout
#   openai/gpt-oss-20b    3 valeurs inventées sur 7, avec la vraie instruction
#                         et 0 échec HTTP : « sama bopp dafa metti » (mal à la
#                         tête) a produit fievre="oui", alors que ce cas exact
#                         figure comme contre-exemple dans le prompt.
#
# Une valeur inventée sur un silence est le faux négatif que ce projet a
# passé plusieurs itérations à éliminer. Mieux vaut aucun secours qu'un
# secours qui invente : sans lui, l'agent relance sa question, et tout le
# triage déterministe — lexique, règles d'alerte, formulaire — est intact.
#
# Pour réactiver quand un modèle convenable sera disponible : renseigner
# MODELE ci-dessus, remettre ACTIF = True, puis relancer test_llm.py et
# test_recit.py. La règle du silence doit afficher zéro valeur inventée.
ACTIF = False


class EchecLLM(Exception):
    """Appel non abouti. Porte le code HTTP quand il y en a un."""

    def __init__(self, detail: str, code: int | None = None):
        super().__init__(detail)
        self.detail = detail
        self.code = code


def disponible() -> bool:
    return bool(ACTIF and MODELE and os.environ.get("GROQ_API_KEY"))


def demander_json(instruction: str, demande: str,
                  max_tokens: int = MAX_TOKENS) -> dict:
    """Retourne l'objet JSON produit par le modèle, ou lève EchecLLM."""
    if not ACTIF or not MODELE:
        raise EchecLLM("secours desactive")

    cle = os.environ.get("GROQ_API_KEY")
    if not cle:
        raise EchecLLM("cle absente")

    corps = json.dumps({
        "model": MODELE,
        "temperature": 0,
        "max_tokens": max_tokens,
        "reasoning_effort": EFFORT_RAISONNEMENT,
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": instruction},
            {"role": "user", "content": demande},
        ],
    }).encode("utf-8")

    requete = urllib.request.Request(
        URL, data=corps, method="POST",
        headers={"Content-Type": "application/json",
                 "Authorization": f"Bearer {cle}",
                 "User-Agent": AGENT},
    )

    try:
        with urllib.request.urlopen(requete, timeout=TIMEOUT) as reponse:
            charge = json.loads(reponse.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        raise EchecLLM(f"HTTP {e.code}", e.code) from e
    except Exception as e:
        raise EchecLLM(type(e).__name__) from e

    try:
        contenu = charge["choices"][0]["message"]["content"]
        objet = json.loads(contenu)
    except Exception as e:
        raise EchecLLM(f"reponse illisible ({type(e).__name__})") from e

    if not isinstance(objet, dict):
        raise EchecLLM("reponse non-objet")
    return objet
