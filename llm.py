"""
Accès unique au fournisseur de modèle de langage.

extraction.py et recit.py passent tous les deux par ici : le modèle, ses
paramètres et le traitement des erreurs sont définis une seule fois.

DEUX FOURNISSEURS
« groq » appelle l'API distante, « ollama » un modèle qui tourne sur la
machine. Ollama expose un endpoint compatible OpenAI
(/v1/chat/completions) : même corps de requête, même forme de réponse, à
trois différences près — pas d'en-tête d'autorisation, pas d'effort de
raisonnement, et un délai plus large car l'inférence est sur processeur.
C'est ce qui permet de garder UNE seule fonction d'appel.

Le fournisseur se choisit par la variable d'environnement LLM_FOURNISSEUR,
sinon par FOURNISSEUR ci-dessous.

POURQUOI CES PARAMÈTRES
gpt-oss-20b est un modèle à raisonnement : il consomme des tokens de
réflexion avant d'écrire sa réponse. Avec max_tokens=40, il épuisait son
budget avant d'émettre le JSON et l'API renvoyait HTTP 400 — donc None,
indiscernable d'un refus légitime. D'où une enveloppe large et un effort
de raisonnement bas.

DISTINGUER L'ÉCHEC DU REFUS
demander_json lève EchecLLM quand l'appel n'aboutit pas, au lieu de
renvoyer None. Sans cette distinction, un 400 ou un 429 se lit exactement
comme « le modèle a répondu null » — et une panne passe pour un succès.
"""

import json
import os
import re
import urllib.error
import urllib.request

import config  # noqa: F401  — charge .env dans os.environ dès l'import

MAX_TOKENS = 400
AGENT = "medical-ai-agentic/1.0 (+https://github.com/moustaphafal/medical-ai-agentic)"

# Un fournisseur décrit TOUT ce qui change d'un service à l'autre. Ajouter
# un candidat, c'est ajouter une entrée ici — pas un « if » dans l'appel.
#
#   cle_env       nom de la variable d'environnement, None si aucune clé
#   raisonnement  effort de raisonnement à envoyer, None si le modèle n'en a pas
#   json_natif    le service accepte response_format={"type":"json_object"}
#   timeout       secondes ; l'inférence locale sur processeur est lente,
#                 et le PREMIER appel paie en plus le chargement du modèle
#                 en mémoire (13 s mesurées pour un 8B)
FOURNISSEURS = {
    "groq": {
        "url": "https://api.groq.com/openai/v1/chat/completions",
        "modele": "openai/gpt-oss-20b",
        "cle_env": "GROQ_API_KEY",
        "raisonnement": "low",
        "json_natif": True,
        "timeout": 12,
    },
    "ollama": {
        "url": "http://localhost:11434/v1/chat/completions",
        "modele": "llama3.2:3b",
        "cle_env": None,
        "raisonnement": None,
        "json_natif": True,
        "timeout": 30,
    },
}

FOURNISSEUR = os.environ.get("LLM_FOURNISSEUR", "groq")

# SECOURS DÉSACTIVÉ — décision du 2026-08-17, reconduite le 2026-08-19.
#
# llama-3.1-8b-instant a été retiré du catalogue Groq (HTTP 404). Quatre
# remplaçants distants ont été évalués ; aucun ne respecte la règle du
# silence, qui est notre critère éliminatoire :
#
#   qwen/qwen3.6-27b      HTTP 400 persistants, a renvoyé le gabarit littéral
#   openai/gpt-oss-120b   invente « je ne sais pas » sur un silence
#   allam-2-7b            répond « non » à tout
#   openai/gpt-oss-20b    3 valeurs inventées sur 7, avec la vraie instruction
#                         et 0 échec HTTP : « sama bopp dafa metti » (mal à la
#                         tête) a produit fievre="oui", alors que ce cas exact
#                         figure comme contre-exemple dans le prompt.
#
# Deux modèles LOCAUX ont ensuite été évalués via Ollama (2026-08-19), le
# disque n'étant plus une contrainte. Même batterie, même instruction :
#
#   llama3.2:3b   1 invention / 7, reproduite sur 2 passages : « je tousse
#                 depuis trois jours » a produit vomissements="oui". Le
#                 modèle déduit un vomissement d'une toux.
#   llama3.1:8b   1 invention / 7, reproduite sur 2 passages : « sama bopp
#                 dafa metti » (mal à la tête) a produit fievre="oui" —
#                 le contre-exemple qui figure LITTÉRALEMENT dans le prompt,
#                 exactement la faute de gpt-oss-20b.
#
# Passer de 3 à 8 milliards de paramètres déplace la faute, ne la supprime
# pas. La règle du silence ne s'obtient pas en grossissant le modèle.
#
# PIÈGE DE MESURE, vécu le 2026-08-19 : au tout premier appel, le modèle
# doit être chargé en mémoire (13 s pour le 8B). Cet appel a dépassé le
# délai, la batterie l'a compté « API indisponible » — et a affiché
# « 0 invention sur 6 », donc un faux succès. Toujours exiger 7
# observations valides, jamais 6. C'est précisément pour ça que
# _appel_observe distingue l'échec d'appel du refus du modèle.
#
# Une valeur inventée sur un silence est le faux négatif que ce projet a
# passé plusieurs itérations à éliminer. Mieux vaut aucun secours qu'un
# secours qui invente : sans lui, l'agent relance sa question, et tout le
# triage déterministe — lexique, règles d'alerte, formulaire — est intact.
#
# Pour réactiver quand un modèle convenable sera disponible : choisir le
# FOURNISSEUR ci-dessus, remettre ACTIF = True, puis relancer test_llm.py et
# test_recit.py. La règle du silence doit afficher zéro valeur inventée
# sur SEPT observations valides, deux passages de suite.
#
# Latences mesurées en local (processeur, batterie complète, modèle chaud) :
# 4,6 s par appel pour le 3B, 7,2 s pour le 8B. À comparer au budget de
# 12 s par tour dont ~7 s de transcription : même sans le défaut ci-dessus,
# le 8B ne tiendrait pas dans l'enveloppe.
ACTIF = False

# Premier objet JSON du texte, accolades équilibrées sur un seul niveau.
# Filet pour les services qui n'ont pas de mode JSON natif et encadrent
# leur réponse de texte libre. Ne rattrape volontairement pas un JSON
# tronqué : un objet incomplet doit rester un échec, pas une demi-valeur.
_MOTIF_JSON = re.compile(r"\{[^{}]*\}", re.S)


class EchecLLM(Exception):
    """Appel non abouti. Porte le code HTTP quand il y en a un."""

    def __init__(self, detail: str, code: int | None = None):
        super().__init__(detail)
        self.detail = detail
        self.code = code


def fournisseur() -> dict:
    """Configuration active. Lève EchecLLM si le nom est inconnu."""
    conf = FOURNISSEURS.get(FOURNISSEUR)
    if conf is None:
        raise EchecLLM(f"fournisseur inconnu : {FOURNISSEUR!r}")
    return conf


def _cle() -> str | None:
    """Clé d'API du fournisseur actif, None s'il n'en demande pas."""
    nom = fournisseur()["cle_env"]
    return os.environ.get(nom) if nom else None


# Compatibilité : plusieurs modules et tests lisent llm.MODELE / llm.URL.
MODELE = FOURNISSEURS[FOURNISSEUR]["modele"]
URL = FOURNISSEURS[FOURNISSEUR]["url"]


def disponible() -> bool:
    conf = FOURNISSEURS.get(FOURNISSEUR)
    if not ACTIF or conf is None or not conf["modele"]:
        return False
    return bool(os.environ.get(conf["cle_env"])) if conf["cle_env"] else True


def _lire_json(contenu: str) -> dict:
    """Objet JSON contenu dans la réponse du modèle, ou EchecLLM."""
    try:
        objet = json.loads(contenu)
    except Exception:
        trouve = _MOTIF_JSON.search(contenu or "")
        if trouve is None:
            raise EchecLLM("reponse illisible (aucun objet JSON)")
        try:
            objet = json.loads(trouve.group(0))
        except Exception as e:
            raise EchecLLM(f"reponse illisible ({type(e).__name__})") from e

    if not isinstance(objet, dict):
        raise EchecLLM("reponse non-objet")
    return objet


def demander_json(instruction: str, demande: str,
                  max_tokens: int = MAX_TOKENS) -> dict:
    """Retourne l'objet JSON produit par le modèle, ou lève EchecLLM."""
    if not ACTIF:
        raise EchecLLM("secours desactive")

    conf = fournisseur()
    if not conf["modele"]:
        raise EchecLLM("modele non renseigne")

    cle = _cle()
    if conf["cle_env"] and not cle:
        raise EchecLLM("cle absente")

    charge_utile = {
        "model": conf["modele"],
        "temperature": 0,
        "max_tokens": max_tokens,
        "messages": [
            {"role": "system", "content": instruction},
            {"role": "user", "content": demande},
        ],
    }
    if conf["raisonnement"]:
        charge_utile["reasoning_effort"] = conf["raisonnement"]
    if conf["json_natif"]:
        charge_utile["response_format"] = {"type": "json_object"}

    entetes = {"Content-Type": "application/json", "User-Agent": AGENT}
    if cle:
        entetes["Authorization"] = f"Bearer {cle}"

    requete = urllib.request.Request(
        conf["url"], data=json.dumps(charge_utile).encode("utf-8"),
        method="POST", headers=entetes,
    )

    try:
        with urllib.request.urlopen(requete, timeout=conf["timeout"]) as reponse:
            charge = json.loads(reponse.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        raise EchecLLM(f"HTTP {e.code}", e.code) from e
    except Exception as e:
        raise EchecLLM(type(e).__name__) from e

    try:
        contenu = charge["choices"][0]["message"]["content"]
    except Exception as e:
        raise EchecLLM(f"reponse illisible ({type(e).__name__})") from e

    return _lire_json(contenu)
