"""
Formulaire thérapeutique fermé.

Le modèle de langage ne rédige JAMAIS un médicament ni une posologie :
il sélectionne une entrée dans cette liste. Toute recommandation renvoyée
par le système doit provenir d'ici, sans exception.

À faire relire par un professionnel de santé avant la soutenance.
Les posologies ci-dessous sont indicatives et doivent être vérifiées.
"""

from dataclasses import dataclass, field


@dataclass
class Entree:
    code: str
    principe_actif: str
    indication: str
    motifs: set
    posologie: dict                  # tranche d'âge -> texte
    contre_indications: list = field(default_factory=list)
    duree_max_jours: int = 3
    conseils: list = field(default_factory=list)


FORMULAIRE = [
    Entree(
        code="PARA",
        principe_actif="Paracétamol",
        indication="Douleur légère à modérée, fièvre",
        motifs={"cephalee", "fievre_palu", "respiratoire", "abdominal"},
        posologie={
            "5 a 15 ans": "15 mg/kg toutes les 6 heures, sans dépasser 4 prises par jour",
            "15 a 60 ans": "1 g toutes les 6 heures, sans dépasser 3 g par jour",
            "plus de 60 ans": "500 mg à 1 g toutes les 8 heures, sans dépasser 2 g par jour",
        },
        contre_indications=["Maladie du foie connue", "Allergie au paracétamol"],
        duree_max_jours=3,
        conseils=["Boire abondamment", "Ne pas associer à un autre médicament contenant du paracétamol"],
    ),
    Entree(
        code="SRO",
        principe_actif="Sels de réhydratation orale",
        indication="Diarrhée sans signe de déshydratation sévère",
        motifs={"diarrhee"},
        posologie={
            "5 a 15 ans": "Un sachet dilué dans 1 litre d'eau propre, à boire par petites gorgées après chaque selle",
            "15 a 60 ans": "Un sachet dilué dans 1 litre d'eau propre, 2 litres par jour minimum",
            "plus de 60 ans": "Un sachet dilué dans 1 litre d'eau propre, surveiller étroitement",
        },
        contre_indications=["Vomissements incoercibles"],
        duree_max_jours=2,
        conseils=["Poursuivre l'alimentation", "Consulter si aucune amélioration en 48 heures"],
    ),
    Entree(
        code="REPOS_HYDR",
        principe_actif="Mesures non médicamenteuses",
        indication="Symptômes bénins ne justifiant pas de traitement",
        motifs={"cephalee", "respiratoire", "fievre_palu", "abdominal", "diarrhee"},
        posologie={
            "5 a 15 ans": "Repos, hydratation régulière",
            "15 a 60 ans": "Repos, hydratation régulière",
            "plus de 60 ans": "Repos, hydratation régulière, surveillance rapprochée",
        },
        duree_max_jours=2,
        conseils=["Consulter sans délai si les symptômes s'aggravent"],
    ),
]

PAR_CODE = {e.code: e for e in FORMULAIRE}


def candidats(motif: str, age_tranche: str) -> list:
    """Entrées éligibles pour un motif et une tranche d'âge donnés."""
    return [
        e for e in FORMULAIRE
        if motif in e.motifs and age_tranche in e.posologie
    ]


def rendre(entree: Entree, age_tranche: str) -> dict:
    return {
        "code": entree.code,
        "principe_actif": entree.principe_actif,
        "posologie": entree.posologie.get(age_tranche, "Posologie non définie — orienter"),
        "duree_max_jours": entree.duree_max_jours,
        "contre_indications": entree.contre_indications,
        "conseils": entree.conseils,
    }
