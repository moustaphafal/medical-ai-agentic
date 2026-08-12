# Fiche de validation clinique

Document à faire remplir et signer par un professionnel de santé avant la
démonstration. Une version scannée ou photographiée suffit.

Durée de l'entretien : 30 à 45 minutes.

---

## 1. Identité du relecteur

| Champ | Valeur |
|---|---|
| Nom et prénom | |
| Qualité | (médecin, interne, infirmier d'État, sage-femme, pharmacien) |
| Structure d'exercice | |
| Date de la relecture | |

---

## 2. Périmètre relu

Cocher ce qui a effectivement été examiné.

- [ ] Les 14 règles de signes d'alerte (`donnees/alertes_sources.json`)
- [ ] Les entrées du formulaire thérapeutique (`donnees/formulaire.json`)
- [ ] Les références de protocole par motif (`donnees/protocoles.json`)
- [ ] Le libellé des messages d'orientation rendus au patient
- [ ] Le positionnement du produit (outil d'orientation, non de diagnostic)

---

## 3. Avis sur les signes d'alerte

| Question | Réponse |
|---|---|
| Manque-t-il un signe d'alerte important ? | |
| Une règle vous semble-t-elle excessive ou inutile ? | |
| Le niveau (urgent / orientation) est-il correctement attribué ? | |

Commentaires libres :

---

## 4. Avis sur le formulaire thérapeutique

| Code | Posologie correcte ? | Contre-indications complètes ? | Observation |
|---|---|---|---|
| | | | |
| | | | |
| | | | |

---

## 5. Conclusion

- [ ] Validé sans réserve
- [ ] Validé après les corrections notées ci-dessus
- [ ] Non validé — motifs :

**Mention à recopier par le relecteur :**

> J'ai relu les règles d'alerte et les recommandations thérapeutiques de ce
> prototype. Je comprends qu'il s'agit d'un outil d'orientation de premier
> niveau et non d'un dispositif de diagnostic autonome.

Signature :

---

## 6. Report dans le code

Après signature, pour chaque entrée relue, renseigner dans les fichiers JSON :

```json
"validation": {
  "statut": "valide",
  "par": "Nom du relecteur",
  "qualite": "Interne en médecine générale",
  "date": "2026-08-13",
  "commentaire": ""
}
```

Puis vérifier :

```bash
python donnees/charger.py
```

Le nombre d'entrées servables doit être supérieur à zéro.
