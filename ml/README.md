# Dossier ML - MSPR Electio-Analytics

Ce dossier est dedie a la partie Machine Learning du projet MSPR.
Il est construit pour repondre a la problematique du cadrage:

> Predire le taux de participation et identifier la famille politique dominante
> pour 2027, a partir des donnees 2012, 2017, 2022 en Pays de la Loire.

## Objectif de ce dossier

- Expliquer clairement le besoin metier et la logique ML.
- Tester plusieurs modeles (3 modeles de regression) sur la cible participation.
- Comparer les modeles avec des metriques explicites.
- Justifier un choix de modele final pour la soutenance.
- Documenter les limites actuelles des donnees pour rester rigoureux.

## Contenu du dossier

### Notebooks (un par modele)

| Notebook | Modele | Export resultats |
|---|---|---|
| `01_modele_linear_regression.ipynb` | Linear Regression | `outputs/datamarts/ml_linear_regression_results.csv` |
| `02_modele_ridge.ipynb` | Ridge | `outputs/datamarts/ml_ridge_results.csv` |
| `03_modele_random_forest.ipynb` | Random Forest | `outputs/datamarts/ml_random_forest_results.csv` |
| `04_comparaison_des_3_modeles.ipynb` | Comparaison finale | `outputs/datamarts/ml_model_comparison.csv` |

Chaque notebook contient :
- documentation markdown (besoin, definition du modele, lien problematique)
- code commente etape par etape
- tableau **fold par fold** (reel vs predit par election)
- graphique reel vs predit
- export CSV + PNG

### Scripts et guides

- `run_ml_models.py` : lance les 3 modeles en une commande (option rapide).
- `PRESENTATION_GUIDE.md` : structure prete pour presenter la partie ML a l'oral.

## Lien avec la problematique

La problematique definie deux cibles:

1. `taux_participation_reel` (regression)
2. `famille_dominante` (classification)

Dans l'etat actuel du datamart, le travail le plus solide est la regression sur
`taux_participation_reel`.

Pourquoi:

- Le nouvel ETL publie un dataset au grain `commune x election`.
- Le fichier `outputs/warehouse/dm_dataset_ml.csv` contient maintenant 8039 lignes.
- `famille_dominante` peut etre utilisee en analyse descriptive, mais la partie ML
  fournie reste centree sur la regression de la participation.

## Modeles compares (regression)

Le script compare ces 3 modeles:

1. `LinearRegression` : baseline simple et interpretable.
2. `Ridge` : regression lineaire regularisee (meilleure stabilite).
3. `RandomForestRegressor` : modele non lineaire (capture des interactions).

Validation utilisee:

- `LeaveOneOut` cross-validation (adaptee aux petits datasets).

Metriques:

- `RMSE` (plus bas = mieux)
- `MAE` (plus bas = mieux)
- `R2` (plus haut = mieux)

## Donnees utilisees

Le script lit:

- `outputs/warehouse/dm_dataset_ml.csv`

Fichiers produits:

- `outputs/datamarts/ml_model_comparison.csv`
- `outputs/datamarts/ml_best_model_summary.txt`

## Comment executer

Depuis la racine du projet:

```bash
pip install -r requirements.txt
python ml/run_ml_models.py
```

## Comment choisir le modele final

1. Regarder le tableau `ml_model_comparison.csv`.
2. Prioriser le plus faible `RMSE`.
3. Verifier que le resultat est coherent metier.
4. Expliquer pourquoi ce modele est retenu pour 2027.

## Limites importantes a presenter

- Les millesimes socio-economiques ne correspondent pas toujours exactement aux
  annees electorales.
- Les donnees securite sont rapprochees par annee disponible la plus proche.
- Certaines variables explicatives peuvent etre manquantes selon les communes.
- Les resultats restent a interpreter avec prudence, mais la base est maintenant
  beaucoup plus exploitable que l'ancienne aggregation regionale.

## Conclusion attendue pour la soutenance

Ce dossier montre une demarche ML complete et rigoureuse:

- besoin metier -> formulation cible -> modelisation -> evaluation -> justification.

Il est donc coherent avec la problematique MSPR, tout en explicitant les limites.
