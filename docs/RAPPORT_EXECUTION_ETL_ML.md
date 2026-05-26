# Rapport d'execution ETL + Machine Learning

Date d'execution : 2026-05-26

## Statut general

La chaine complete a ete executee avec succes :

- ETL phase 01 : collecte des donnees brutes
- ETL phase 02 : staging qualite et standardisation
- ETL phase 03 : transformations metier
- ETL phase 04 : data warehouse
- Machine Learning : comparaison des 3 modeles

## Resultat ETL

Le datamart final n'est plus reduit a quelques lignes.

Le nouveau grain retenu est :

```text
1 ligne = 1 commune + 1 election
```

Volumes obtenus :

| Fichier | Nombre de lignes |
|---|---:|
| `outputs/warehouse/dm_dataset_ml.csv` | 8039 |
| `outputs/warehouse/fact_election.csv` | 8039 |
| `outputs/warehouse/fact_indicateur.csv` | 48234 |
| `outputs/warehouse/dim_commune.csv` | 1502 |

## Fichiers principaux generes

### Staging

- `outputs/staging/raw/stg_raw_general.csv`
- `outputs/staging/raw/stg_raw_candidats.csv`
- `outputs/staging/raw/stg_raw_socioeco.csv`
- `outputs/staging/raw/stg_raw_emploi.csv`
- `outputs/staging/raw/stg_raw_securite.csv`
- `outputs/staging/std/stg_std_general.csv`
- `outputs/staging/std/stg_std_candidats.csv`
- `outputs/staging/std/stg_std_socioeco.csv`
- `outputs/staging/std/stg_std_emploi.csv`
- `outputs/staging/std/stg_std_securite.csv`

### Transformations

- `outputs/transformations/tr_elections_commune.csv`
- `outputs/transformations/tr_indicateurs_commune.csv`
- `outputs/transformations/tr_dataset_ml.csv`
- `outputs/transformations/tr_correlations.csv`

### Data warehouse

- `outputs/warehouse/dim_commune.csv`
- `outputs/warehouse/dim_date.csv`
- `outputs/warehouse/dim_indicateur.csv`
- `outputs/warehouse/fact_election.csv`
- `outputs/warehouse/fact_indicateur.csv`
- `outputs/warehouse/dm_dataset_ml.csv`
- `outputs/warehouse/dm_correlations.csv`
- `database/electio_dwh.db`

## Resultat Machine Learning

Dataset utilise :

```text
outputs/warehouse/dm_dataset_ml.csv
```

Volume :

- Observations utilisees : 8039
- Variables numeriques : 38
- Validation croisee : KFold(5)

Comparaison des modeles :

| Modele | RMSE | MAE | R2 |
|---|---:|---:|---:|
| RandomForest | 3.695029 | 2.804608 | 0.941992 |
| Ridge | 4.347998 | 3.196866 | 0.919711 |
| LinearRegression | 4.348848 | 3.198863 | 0.919680 |

Modele retenu :

```text
RandomForest
```

Fichiers ML generes :

- `outputs/datamarts/ml_model_comparison.csv`
- `outputs/datamarts/ml_best_model_summary.txt`

## Conclusion

La base finale est maintenant coherente avec la problematique du projet.

Elle est exploitable pour :

- l'analyse electorale ;
- la visualisation territoriale ;
- la comparaison des communes ;
- les modeles de Machine Learning ;
- la prediction du taux de participation.

L'ancien probleme venait d'une aggregation trop forte au niveau region-election.
Le nouvel ETL conserve le niveau commune-election, ce qui permet d'obtenir 8039 observations exploitables.
