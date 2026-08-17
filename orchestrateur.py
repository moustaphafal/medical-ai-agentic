"""
Orchestrateur : machine à états déterministe.

Principe fondamental : le modèle de langage extrait et raisonne, mais c'est
CETTE classe qui décide. Aucune transition d'état, aucune conclusion et aucune
recommandation ne dépendent d'une sortie de modèle non contrainte.

Utilisation :
    session = Session(langue="fr")
    print(session.demarrer().texte)
    while not session.terminee:
        reponse = input("> ")
        print(session.repondre(reponse).texte)
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
import uuid

import alertes
import domaine
import extraction
import formulaire
import recit

# États
ACCUEIL = "accueil"
ANAMNESE = "anamnese"
CONFIRMATION = "confirmation"
RESTITUTION = "restitution"
TERMINE = "termine"

MAX_REPRISES = 2          # relances avant de passer au champ suivant
MAX_TOURS = 25            # garde-fou contre les boucles infinies

# Valeur explicite pour un champ que l'agent n'a pas réussi à comprendre.
# Ne JAMAIS utiliser None : un None est lu comme "non" par les règles d'alerte,
# ce qui reviendrait à conclure au bénin sur une information manquante.
INCONNU = "inconnu"

# Champs dont l'absence de réponse interdit toute conclusion bénigne.
# Si l'un d'eux reste inconnu, l'entretien bascule en orientation.
CHAMPS_CRITIQUES = {
    "age_tranche",
    "grossesse",
    "dyspnee",
    "conscience_alteree",
    "saignement",
    "douleur_thoracique",
    "deshydratation",
    "raideur_nuque",
}


@dataclass
class Tour:
    """Ce que l'agent renvoie à l'interface à chaque tour."""
    texte: str
    etat: str
    champ: str | None = None
    options: list = field(default_factory=list)
    conclusion: dict | None = None


class Session:
    def __init__(self, langue: str = "fr", localite: str | None = None):
        self.id = str(uuid.uuid4())[:8]
        self.langue = langue
        self.debut = datetime.now(timezone.utc)
        self.dossier: dict = {}
        self.etat = ACCUEIL
        self.champ_courant = None
        self.reprises = 0
        self.tours = 0
        self.recit_traite = False
        self.trace: list = []
        self.conclusion: dict | None = None
        if localite:
            self.dossier["localite"] = localite

    # ---------------------------------------------------------------- API

    @property
    def terminee(self) -> bool:
        return self.etat == TERMINE

    def demarrer(self) -> Tour:
        self._journaliser("session_ouverte", {"langue": self.langue})
        accueil = (
            "Bonjour. Je suis un assistant d'orientation, je ne remplace pas un médecin. "
            "Je vais vous poser quelques questions."
            if self.langue == "fr" else
            "Salaam aleekum. Man dama lay jàppale ngir gis fu nga wara dem. "
            "Duma doktoor. Dinaa la laaj ay laaj."
        )
        self.etat = ANAMNESE
        suite = self._question_suivante()
        return Tour(f"{accueil} {suite.texte}", self.etat, suite.champ, suite.options)

    def repondre(self, texte: str) -> Tour:
        self.tours += 1
        if self.tours > MAX_TOURS:
            return self._conclure_orientation(
                [], motif="Entretien trop long, orientation par précaution")

        if self.etat == ANAMNESE:
            return self._traiter_anamnese(texte)
        if self.etat == CONFIRMATION:
            return self._traiter_confirmation(texte)
        return Tour("Entretien terminé.", TERMINE, conclusion=self.conclusion)

    # ------------------------------------------------------------ anamnèse

    def _traiter_anamnese(self, texte: str) -> Tour:
        champ = self.champ_courant
        if champ is None:
            return self._question_suivante()

        valeur = extraction.extraire(champ, texte, self.langue)
        if valeur is None:
            valeur = extraction.extraire_par_llm(champ, texte, self.langue)

        if valeur is None:
            self.reprises += 1
            self._journaliser("non_compris", {"champ": champ.nom, "brut": texte})
            if self.reprises <= MAX_REPRISES:
                return Tour(self._reformuler(champ), ANAMNESE,
                            champ.nom, champ.options)

            # Échec définitif sur ce champ. On le marque explicitement inconnu.
            self.dossier[champ.nom] = INCONNU
            self.reprises = 0
            self._journaliser("champ_inconnu", {"champ": champ.nom})

            # Sur un champ critique, l'ignorer reviendrait à supposer une
            # réponse négative. On oriente par précaution.
            if champ.nom in CHAMPS_CRITIQUES:
                return self._conclure_orientation(
                    [],
                    motif=f"Information manquante sur un signe d'alerte ({champ.nom})",
                )
            return self._question_suivante()

        self.dossier[champ.nom] = valeur
        self.reprises = 0
        self._journaliser("champ_rempli", {"champ": champ.nom, "valeur": valeur})

        # Premier tour : le patient décrit spontanément plusieurs choses.
        # Un seul appel remplit alors plusieurs champs, et l'entretien
        # passe d'environ 11 questions à 6 ou 7.
        # Seuls des champs positifs sont déduits : un signe d'alerte non
        # mentionné n'est jamais interprété comme absent.
        if not self.recit_traite:
            self.recit_traite = True
            deduits = recit.extraire_recit(texte, domaine.CHAMPS, self.dossier)
            for nom, val in deduits.items():
                self.dossier[nom] = val
                self._journaliser("champ_deduit",
                                  {"champ": nom, "valeur": val, "source": "recit"})
        
        # Les alertes urgentes court-circuitent immédiatement l'entretien.
        urgentes = [a for a in alertes.evaluer(self.dossier)
                    if a.niveau == alertes.URGENT]
        if urgentes:
            return self._conclure_orientation(urgentes)
        
        return self._question_suivante()

    def _question_suivante(self) -> Tour:
        champ = domaine.prochain_champ(self.dossier)
        if champ is None:
            return self._passer_en_confirmation()
        self.champ_courant = champ
        self.reprises = 0
        question = champ.question_fr if self.langue == "fr" else champ.question_wo
        return Tour(question, ANAMNESE, champ.nom, champ.options)

    def _reformuler(self, champ) -> str:
        base = champ.question_fr if self.langue == "fr" else champ.question_wo
        prefixe = ("Je n'ai pas bien compris. " if self.langue == "fr"
                   else "Dégg naa ko bu baax. ")
        if champ.options:
            listes = " ou ".join(champ.options[:3])
            return f"{prefixe}{base} ({listes})"
        return f"{prefixe}{base}"

    # -------------------------------------------------------- confirmation

    def _passer_en_confirmation(self) -> Tour:
        self.etat = CONFIRMATION
        resume = self._resumer()
        question = ("Ai-je bien compris ? Répondez oui ou non."
                    if self.langue == "fr" else "Ndax dëgg la ? Waaw walla déedéet.")
        return Tour(f"{resume} {question}", CONFIRMATION, "confirmation",
                    ["oui", "non"])

    def _traiter_confirmation(self, texte: str) -> Tour:
        reponse = extraction.extraire_binaire(texte)
        if reponse == "non":
            # L'utilisateur corrige : on repart des symptômes, terrain conservé.
            self._journaliser("confirmation_refusee", {})
            for nom in list(self.dossier):
                if nom not in ("age_tranche", "sexe", "grossesse", "localite"):
                    del self.dossier[nom]
            self.etat = ANAMNESE
            return self._question_suivante()
        if reponse is None:
            return Tour(self._resumer() + " Répondez oui ou non.",
                        CONFIRMATION, "confirmation", ["oui", "non"])
        self._journaliser("confirmation_acceptee", {})
        return self._trier()

    def _resumer(self) -> str:
        d = self.dossier
        motif = domaine.MOTIFS.get(d.get("motif_principal"), "problème non précisé")
        bouts = [motif.lower()]
        if d.get("duree_jours") is not None:
            bouts.append(f"depuis {d['duree_jours']} jour(s)")
        if d.get("fievre") == "oui":
            bouts.append("avec fièvre")
        if d.get("vomissements") == "oui":
            bouts.append("avec vomissements")
        return "Vous me dites : " + ", ".join(bouts) + "."

    # -------------------------------------------------------------- triage

    def _trier(self) -> Tour:
        declenchees = alertes.evaluer(self.dossier)
        if declenchees:
            return self._conclure_orientation(declenchees)
        return self._conclure_benin()

    def _conclure_orientation(self, declenchees, motif: str | None = None) -> Tour:
        niveau = alertes.niveau_global(declenchees) or alertes.ORIENTE
        libelles = [a.libelle for a in declenchees] or [motif or "Précaution"]
        urgent = niveau == alertes.URGENT

        if self.langue == "fr":
            texte = (
                "Vous devez consulter un professionnel de santé sans attendre. "
                if urgent else
                "Je vous conseille de vous rendre au poste de santé le plus proche. "
            ) + "Je ne peux pas vous proposer de traitement dans cette situation."
        else:
            texte = (
                "War nga dem doktoor léegi léegi. "
                if urgent else
                "War nga dem poste de santé bi la gën a jege. "
            ) + "Manuma la jox garab ci mbir mii."

        self.conclusion = {
            "decision": "orientation",
            "niveau": niveau,
            "alertes": libelles,
            "recommandation": None,
        }
        self._journaliser("orientation", {"niveau": niveau, "alertes": libelles})
        self.etat = TERMINE
        return Tour(texte, TERMINE, conclusion=self.conclusion)

    def _conclure_benin(self) -> Tour:
        # Dernier verrou : aucune conclusion bénigne si une information
        # critique manque. Le système doit échouer du côté prudent.
        manquants = [
            nom for nom in CHAMPS_CRITIQUES
            if self.dossier.get(nom) == INCONNU
        ]
        if manquants:
            return self._conclure_orientation(
                [],
                motif="Informations manquantes : " + ", ".join(manquants),
            )

        motif = self.dossier.get("motif_principal")
        age = self.dossier.get("age_tranche")
        options = formulaire.candidats(motif, age)

        if not options:
            return self._conclure_orientation(
                [], motif="Aucune recommandation disponible pour ce profil")

        # Sélection dans la liste close, jamais une génération libre.
        entree = options[0]
        reco = formulaire.rendre(entree, age)

        if self.langue == "fr":
            texte = (
                f"Votre situation semble bénigne. Vous pouvez prendre "
                f"{reco['principe_actif']} : {reco['posologie']}. "
                f"Pendant {reco['duree_max_jours']} jours au maximum. "
                f"Si cela ne s'améliore pas, consultez un professionnel de santé."
            )
        else:
            texte = (
                f"Sa mbir dafa yomb. Mën nga jël {reco['principe_actif']}. "
                f"{reco['posologie']}. Bu baaxul, dem doktoor."
            )

        self.conclusion = {
            "decision": "automedication_encadree",
            "niveau": "benin",
            "alertes": [],
            "recommandation": reco,
        }
        self._journaliser("recommandation", {"code": reco["code"]})
        self.etat = TERMINE
        return Tour(texte, TERMINE, conclusion=self.conclusion)

    # --------------------------------------------------------------- trace

    def _journaliser(self, evenement: str, details: dict):
        self.trace.append({
            "horodatage": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "evenement": evenement,
            **details,
        })

    def journal(self) -> dict:
        """Ligne à écrire en base — sans donnée nominative."""
        return {
            "session": self.id,
            "debut": self.debut.isoformat(timespec="seconds"),
            "langue": self.langue,
            "localite": self.dossier.get("localite"),
            "motif": self.dossier.get("motif_principal"),
            "age_tranche": self.dossier.get("age_tranche"),
            "decision": (self.conclusion or {}).get("decision"),
            "niveau": (self.conclusion or {}).get("niveau"),
            "alertes": (self.conclusion or {}).get("alertes", []),
            "nb_tours": self.tours,
        }

    def trace_lisible(self) -> str:
        """Affichage de la trace de décision — argument de soutenance."""
        lignes = ["--- Trace de décision ---"]
        for nom, val in self.dossier.items():
            lignes.append(f"  {nom:24} = {val}")
        declenchees = alertes.evaluer(self.dossier)
        lignes.append("  règles déclenchées      : " +
                      (", ".join(a.code for a in declenchees) or "aucune"))
        if self.conclusion:
            lignes.append(f"  décision                : {self.conclusion['decision']}")
        return "\n".join(lignes)