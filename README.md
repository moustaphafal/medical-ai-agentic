# medical-ai-agentic

Agent vocal de triage médical de premier niveau, bilingue **français / wolof**,
conçu pour le contexte sénégalais.

L'utilisateur décrit son problème à la voix ou au clavier. L'agent conduit une
anamnèse structurée, détecte les signes d'alerte, puis conclut soit par une
**orientation** vers une structure de soins, soit par une **automédication
encadrée** issue d'un formulaire thérapeutique fermé.

> **Avertissement.** Ce projet est un prototype de hackathon. Il n'a reçu
> aucune validation clinique et ne doit pas être utilisé pour une prise en
> charge réelle. Voir [Statut des données cliniques](#statut-des-données-cliniques).

---

## Principe de conception

La propriété centrale du système : **le modèle de langage ne décide jamais**.

- L'extraction comprend la parole libre de l'utilisateur et remplit un dossier.
- Une **machine à états déterministe** (`orchestrateur.py`) pilote l'entretien.
- Des **règles codées en dur** (`alertes.py`) court-circuitent le raisonnement
  dès qu'un signe d'alerte est vrai.
- Le traitement éventuel est **sélectionné** dans une liste fermée
  (`donnees/formulaire.json`), jamais rédigé librement.
- Toute entrée non validée cliniquement est **refusée** par le chargeur de
  données. Le code interdit lui-même de recommander ce qui n'a pas été relu.

Chaque consultation produit une **trace de décision** consultable : dossier
collecté, règles déclenchées, conclusion, journal des événements.

---

## Prérequis

| Élément | Version | Remarque |
|---|---|---|
| Python | **3.11** | Les versions figées de `torch` et `ctranslate2` ciblent cp311 |
| ffmpeg | récent | Indispensable **uniquement** pour l'entrée vocale |
| Espace disque | ~2 Go | Modèles de reconnaissance et de synthèse vocale |
| GPU | inutile | Tout tourne sur CPU |

L'installation de ffmpeg :

```bash
winget install Gyan.FFmpeg          # Windows
brew install ffmpeg                 # macOS
sudo apt install ffmpeg             # Debian / Ubuntu
```

Vérifiez qu'il est bien dans le `PATH` avec `ffmpeg -version`.

---

## Installation

```bash
git clone https://github.com/moustaphafal/medical-ai-agentic.git
cd medical-ai-agentic
```

> **Le dépôt contient encore un dossier `.venv/` hérité d'un ancien commit.**
> Ne l'utilisez pas : il est incomplet et lié à une machine Windows.
> Créez votre propre environnement, sous un autre nom si besoin.

**Windows (PowerShell)**

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

**macOS / Linux**

```bash
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

### Configuration — fichier `.env`

Copiez le modèle fourni et remplissez-le :

```bash
cp .env.example .env          # macOS / Linux
copy .env.example .env        # Windows
```

`.env` est ignoré par git : vos clés n'y seront jamais commitées. Le fichier
est chargé automatiquement par `config.py`, sans dépendance externe. Une
variable déjà définie dans votre shell l'emporte toujours sur le fichier.

| Variable | Rôle | Obligatoire |
|---|---|---|
| `GROQ_API_KEY` | Secours d'extraction pour les réponses en wolof | non |
| `HF_TOKEN` | Téléchargement d'un modèle Hugging Face à accès restreint | non |
| `STT_SIMULE` | `1` simulé, `0` modèles réels | non, défaut `1` |
| `TTS_SIMULE` | `1` simulé, `0` modèles réels | non, défaut `1` |

Vérifier ce qui est effectivement chargé, sans afficher les secrets :

```bash
python config.py
```

**Sans `GROQ_API_KEY`, l'agent fonctionne normalement** : le secours par modèle
de langage est simplement désactivé, et l'agent relance sa question quand il ne
comprend pas.

### Pourquoi les versions sont figées

`requirements.txt` épingle `torch==2.5.1`, `ctranslate2==4.4.0`,
`faster-whisper==1.0.3` et `av==12.3.0`. Ce n'est pas décoratif : les builds
récents de PyTorch échouent au chargement de leurs DLL sur certains CPU Intel
(constaté sur un i7-10510U, Comet Lake) avec un `OSError [WinError 1114]`.
**Ne mettez pas ces paquets à jour sans tester** — voir [Dépannage](#dépannage).

---

## Lancer le projet

Trois points d'entrée, du plus léger au plus complet.

### 1. Console — aucun modèle requis

Le plus rapide pour comprendre le parcours. Toute la logique de triage se teste
au clavier, sans reconnaissance vocale.

```bash
python demo.py            # entretien en français
python demo.py wo         # entretien en wolof
python demo.py test       # jeu de cas de test (attendu : 7/7)
```

### 2. API HTTP

```bash
python -m uvicorn api:app --port 8000
```

Utilisez bien `python -m uvicorn` plutôt que `uvicorn` seul : si un autre
environnement virtuel est présent dans votre `PATH`, la commande nue peut
lancer le mauvais interpréteur.

- Documentation interactive : <http://localhost:8000/docs>
- État du service : <http://localhost:8000/sante>

### 3. Interface web

L'API sert elle-même l'interface de démonstration :

**<http://localhost:8000/app>**

Ouvrez-la depuis `localhost`, **pas** en double-cliquant sur
`web/index.html` : l'accès au microphone exige un contexte sécurisé, ce qu'un
fichier ouvert en `file://` n'est pas.

---

## Mode simulé et modèles réels

Par défaut, la reconnaissance et la synthèse vocales sont **simulées**. L'API
démarre instantanément, ne télécharge rien, et toute la logique de triage reste
testable. C'est le mode adapté au développement et aux tests.

```
[STT] mode simulé — aucun modèle chargé
[TTS] mode simulé — aucun modèle chargé
```

Pour activer les vrais modèles, passez `STT_SIMULE=0` et `TTS_SIMULE=0` dans
votre `.env`, ou positionnez-les dans le shell avant le lancement :

```powershell
$env:STT_SIMULE = "0"; $env:TTS_SIMULE = "0"    # Windows PowerShell
```

```bash
export STT_SIMULE=0 TTS_SIMULE=0                # macOS / Linux
```

Les modèles sont alors téléchargés **à leur première utilisation**, pas au
démarrage — le premier tour de parole est donc lent, les suivants non.

| Usage | Modèle | Où |
|---|---|---|
| Transcription française | `faster-whisper small`, quantifié int8 | serveur, CPU |
| Transcription wolof | `speechbrain/asr-wav2vec2-dvoice-wolof` | serveur, CPU |
| Voix française | API `speechSynthesis` du navigateur | navigateur |
| Voix wolof | `facebook/mms-tts-wol` (~150 Mo) | serveur, CPU |

Le français n'est jamais synthétisé côté serveur : le navigateur le fait
gratuitement, sans latence, et avec une voix disponible partout.

**Optionnel** — pré-générer les questions en wolof retire 1 à 2 s par tour :

```bash
python -c "from services.tts import pregenerer; pregenerer()"
```

---

## Points d'entrée de l'API

| Méthode | Route | Rôle |
|---|---|---|
| `GET` | `/sante` | État du service, modes simulés, sessions actives |
| `POST` | `/session` | Ouvre une session (`langue` : `fr` ou `wo`) |
| `POST` | `/session/{id}/texte` | Répond au clavier |
| `POST` | `/session/{id}/audio` | Répond à la voix (fichier audio) |
| `GET` | `/session/{id}/trace` | Trace de décision complète |
| `DELETE` | `/session/{id}` | Ferme la session |

Les sessions vivent **en mémoire** : redémarrer le serveur les efface toutes.

---

## Statut des données cliniques

Le dossier `donnees/` sépare volontairement ce qui est **sourcé** de ce qui ne
l'est pas.

| Fichier | Contenu | Statut |
|---|---|---|
| `alertes_sources.json` | 31 règles d'alerte documentées | 16 codées dans `alertes.py`, 15 documentées seulement |
| `formulaire.json` | 9 médicaments | **Toutes en brouillon** |
| `protocoles.json` | Références de protocole par motif | Vide, à remplir |

**Les posologies du formulaire ont été produites par une IA générative, pas par
une source médicale.** Elles sont toutes marquées `statut: "brouillon"` et le
chargeur refuse de les servir tant qu'un professionnel de santé ne les a pas
relues. Conséquence directe et voulue : **toutes les consultations basculent
aujourd'hui en orientation**, aucune automédication n'est jamais proposée.

Contrôler l'état des données à tout moment :

```bash
python donnees/charger.py
```

Sortie attendue en l'état : `0 prête`, `9 non validées`, `0 servable`.

Les signes d'alerte, eux, s'appuient sur des sources vérifiables — dont deux
sources nationales sénégalaises officielles : le **PNT** (toux de plus de trois
semaines, dépistage tuberculose) et le **PNLP/MSAS** (TDR systématique devant
toute fièvre, signes de paludisme grave).

---

## Structure du projet

```
orchestrateur.py     machine à états — décide de tout
domaine.py           motifs, champs, questions fr/wo
alertes.py           16 règles déterministes de signe d'alerte
extraction.py        compréhension des réponses en parole libre
formulaire.py        sélection du traitement dans la liste fermée
api.py               API HTTP + service de l'interface web
config.py            chargement du .env, sans dépendance
demo.py              console interactive et jeu de tests
test_llm.py          garde-fous et qualité du secours par modèle
services/stt.py      transcription fr/wo
services/tts.py      synthèse vocale wolof
web/index.html       interface de démonstration
donnees/             contenu clinique sourcé + contrôleur de complétude
```

---

## Vérifier une installation

```bash
python demo.py test          # cas de triage de bout en bout
python donnees/charger.py    # rapport de complétude des données
python test_llm.py           # garde-fous du secours par modèle de langage
python config.py             # variables chargées depuis .env
```

`test_llm.py` sépare deux choses : des tests de **sûreté** bloquants, qui
tournent sans clé ni réseau et vérifient qu'aucune valeur hors domaine ne peut
passer, et des tests de **qualité** wolof, purement informatifs, qui n'échouent
jamais la suite — la sortie d'un modèle n'est pas une garantie.

Ces vérifications fonctionnent même sans ffmpeg ni modèles vocaux, qui ne
concernent que la voix.

---

## Dépannage

**`OSError: [WinError 1114] ... c10.dll`**
PyTorch n'arrive pas à charger ses DLL. Vérifiez que vous êtes bien sur les
versions épinglées de `requirements.txt` ; les builds récents échouent sur
certains CPU Intel. Installez la variante CPU explicitement :

```bash
python -m pip install torch==2.5.1 --index-url https://download.pytorch.org/whl/cpu
```

Si l'erreur persiste, installez les redistribuables Visual C++
(`winget install Microsoft.VCRedist.2015+.x64`) puis redémarrez la machine.

**`ModuleNotFoundError` alors que le paquet est installé**
La commande utilise probablement un autre environnement virtuel présent dans le
`PATH`. Lancez tout via l'interpréteur du projet : `python -m uvicorn …`,
`python -m pip …`.

**`UnicodeEncodeError: 'charmap' codec can't encode character`**
Console Windows en cp1252. Préfixez la commande :

```powershell
$env:PYTHONIOENCODING = "utf-8"
```

**La transcription échoue avec une erreur ffmpeg**
Le navigateur envoie du webm/opus, que les modèles n'acceptent pas ; ffmpeg
convertit en WAV 16 kHz mono. Vérifiez `ffmpeg -version`.

**Le microphone ne s'active pas**
L'interface doit être servie depuis `http://localhost:8000/app`, pas ouverte en
`file://`.

**Le serveur ne répond pas depuis l'interface**
Vérifiez qu'uvicorn tourne bien sur le port 8000 : <http://localhost:8000/sante>.

---

## Limites connues

- Aucune validation clinique. Les posologies ne sont pas utilisables en l'état.
- Les protocoles par motif (`protocoles.json`) ne sont pas encore renseignés.
- 15 signes d'alerte sont documentés mais pas encore codés : ils sont sans
  effet sur le triage.
- Les sessions sont en mémoire, sans persistance ni authentification.
- CORS est ouvert à toutes les origines — à restreindre hors hackathon.
