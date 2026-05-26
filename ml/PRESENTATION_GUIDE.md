# Guide de presentation - Partie ML (MSPR)

Ce guide te donne une trame simple, claire et defendable pour presenter
la partie Machine Learning en soutenance.

## 1) Besoin metier

Electio-Analytics veut anticiper les tendances electorales en Pays de la Loire:

- Predire la participation.
- Comprendre la dynamique politique dominante.

Message a dire:

> Notre role data science est de transformer les donnees ETL en aide a la decision.

## 2) Lien direct avec la problematique

Problematique du projet:

- Predire `taux_participation_reel` (regression supervisee).
- Predire `famille_dominante` (classification supervisee).

Ce que vous avez fait:

- Validation complete sur la regression.
- Classification preparee en piste d'amelioration (limitee par le volume actuel).

## 3) Donnees utilisees

Source de travail:

- `outputs/warehouse/dm_dataset_ml.csv`

Rappels importants:

- Granularite regionale.
- 6 observations (2012/2017/2022 x presidentielle/legislative).
- Variables socio-economiques, deltas, variables electorales agregees.

## 4) Methodologie ML

Etapes:

1. Selection de la cible: `taux_participation_reel`
2. Selection des variables explicatives numeriques
3. Imputation mediane des valeurs manquantes
4. Validation `Leave-One-Out` (adaptee petit dataset)
5. Comparaison de 3 modeles:
   - LinearRegression
   - Ridge
   - RandomForestRegressor

## 5) Metriques de comparaison

- RMSE: erreur moyenne en points de participation (plus bas = mieux)
- MAE: erreur absolue moyenne (plus bas = mieux)
- R2: part de variance expliquee (plus haut = mieux)

## 6) Justification du modele retenu

Logique attendue:

- Choix du modele avec meilleur RMSE.
- Verification de la coherence metier.
- Mention explicite des limites de robustesse statistique.

Phrase type:

> Nous retenons ce modele car il minimise l'erreur predictive tout en restant
> coherent avec les mecanismes socio-electoraux observes.

## 7) Limites et transparence (important pour la note)

- Jeu de donnees tres petit -> resultat POC, non industrialisable tel quel.
- Deux valeurs manquantes pour `famille_dominante`.
- Necessite d'enrichir l'echantillon pour renforcer la generalisation.

## 8) Plan d'amelioration propose

- Passer au grain departemental pour augmenter le nombre de lignes.
- Completer la cible de classification.
- Ajouter une validation temporelle plus stricte.
- Re-entrainer et comparer a nouveau les 3 modeles.

## 9) Livrables a montrer pendant la demo

- Notebook modele 1: `ml/01_modele_linear_regression.ipynb`
- Notebook modele 2: `ml/02_modele_ridge.ipynb`
- Notebook modele 3: `ml/03_modele_random_forest.ipynb`
- Notebook comparaison: `ml/04_comparaison_des_3_modeles.ipynb`
- Tableau final: `outputs/datamarts/ml_model_comparison.csv`

## 10) Conclusion a l'oral (30 secondes)

> La demarche ML est complete et alignee avec la problematique: preparation,
> modelisation, evaluation, choix argumente. Les resultats sont coherents pour un POC.
> La prochaine etape est l'enrichissement du datamart pour consolider la prediction 2027.
