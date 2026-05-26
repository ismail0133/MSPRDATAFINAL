# Documentation ETL - Projet Electio Analytics

## Problématique

Le projet cherche à préparer une base fiable pour analyser la participation électorale en Pays de la Loire et alimenter des modèles de Machine Learning capables d'estimer le taux de participation pour de futures élections.

La difficulté principale venait de l'ancien ETL : la base finale était agrégée trop tôt au niveau `region x election`. Avec une seule région et quelques élections, le datamart final tombait à quelques lignes, ce qui rendait les modèles ML peu exploitables.

Le nouvel ETL corrige ce point en conservant le grain `commune x election`.

## Grain final retenu

Le grain officiel du datamart ML est :

```text
1 ligne = 1 commune + 1 election
```

Ce choix est logique pour le projet car :

- les résultats électoraux sont disponibles par bureau puis commune ;
- les variables socio-économiques, emploi et sécurité sont disponibles par commune ;
- le Machine Learning a besoin d'un nombre suffisant d'observations ;
- les visualisations peuvent comparer les territoires communaux et départementaux ;
- l'agrégation régionale reste possible après coup, sans détruire l'information détaillée.

## Chaîne ETL

### 01 - Collecte

Notebook : `notebooks/01_collecte.ipynb`

Rôle :

- lire les fichiers bruts nationaux ;
- filtrer le périmètre Pays de la Loire ;
- conserver les élections 2012, 2017 et 2022 au premier tour ;
- écrire un staging raw régional.

Sorties principales :

- `outputs/staging/raw/stg_raw_general.csv`
- `outputs/staging/raw/stg_raw_candidats.csv`
- `outputs/staging/raw/stg_raw_socioeco.csv`
- `outputs/staging/raw/stg_raw_emploi.csv`
- `outputs/staging/raw/stg_raw_securite.csv`

### 02 - Staging qualité

Notebook : `notebooks/02_staging_qualite.ipynb`

Rôle :

- standardiser les codes communes ;
- convertir les nombres au format exploitable ;
- créer les colonnes `annee`, `type_election`, `region`, `code_region` ;
- mapper les nuances politiques vers des familles politiques ;
- produire des fichiers de rejet.

Sorties principales :

- `outputs/staging/std/stg_std_general.csv`
- `outputs/staging/std/stg_std_candidats.csv`
- `outputs/staging/std/stg_std_socioeco.csv`
- `outputs/staging/std/stg_std_emploi.csv`
- `outputs/staging/std/stg_std_securite.csv`

### 03 - Transformations

Notebook : `notebooks/03_transformations.ipynb`

Rôle :

- agréger les bureaux de vote au niveau commune-élection ;
- calculer le taux de participation réel ;
- agréger les voix par famille politique ;
- identifier la famille politique dominante ;
- joindre les indicateurs socio-économiques, emploi et sécurité ;
- créer les variables utiles au ML.

Sorties principales :

- `outputs/transformations/tr_elections_commune.csv`
- `outputs/transformations/tr_indicateurs_commune.csv`
- `outputs/transformations/tr_dataset_ml.csv`
- `outputs/transformations/tr_correlations.csv`

### 04 - Data warehouse

Notebook : `notebooks/04_data_warehouse.ipynb`

Rôle :

- publier les dimensions ;
- publier les tables de faits ;
- créer le datamart ML officiel ;
- créer la base SQLite finale.

Sorties principales :

- `outputs/warehouse/dim_commune.csv`
- `outputs/warehouse/dim_date.csv`
- `outputs/warehouse/dim_indicateur.csv`
- `outputs/warehouse/fact_election.csv`
- `outputs/warehouse/fact_indicateur.csv`
- `outputs/warehouse/dm_dataset_ml.csv`
- `database/electio_dwh.db`

## Résultat obtenu

Le datamart final `outputs/warehouse/dm_dataset_ml.csv` contient maintenant des milliers de lignes au grain `commune x election`, au lieu d'une base régionale trop petite.

Lors de la dernière exécution :

- `dm_dataset_ml.csv` : 8039 lignes ;
- `fact_election.csv` : 8039 lignes ;
- `fact_indicateur.csv` : 48234 lignes ;
- `dim_commune.csv` : 1502 communes.

## Compatibilité Machine Learning

Le fichier ML officiel reste :

```text
outputs/warehouse/dm_dataset_ml.csv
```

Il contient la cible :

```text
taux_participation_reel
```

Et des variables explicatives :

- volumes électoraux ;
- pourcentages par famille politique ;
- population ;
- revenu médian ;
- pauvreté ;
- chômage ;
- sécurité ;
- entreprises ;
- variables dérivées par habitant.

Cette structure est compatible avec les notebooks et scripts ML du dossier `ml/`.

## Limites et choix techniques

- Les millésimes INSEE ne correspondent pas toujours exactement aux années électorales. Le pipeline rapproche donc les millésimes disponibles : 2010 pour 2012, 2015 pour 2017, 2021/2022 pour 2022.
- Les données sécurité commencent souvent après 2012. L'ETL choisit l'année de sécurité la plus proche disponible pour chaque commune.
- La base finale garde les lignes même si certaines variables explicatives sont manquantes. Les modèles ML peuvent ensuite imputer ces valeurs.
- Les agrégations régionales sont volontairement repoussées après la création du datamart détaillé.

## Ordre d'exécution

Exécuter les notebooks dans cet ordre :

1. `notebooks/01_collecte.ipynb`
2. `notebooks/02_staging_qualite.ipynb`
3. `notebooks/03_transformations.ipynb`
4. `notebooks/04_data_warehouse.ipynb`

Le module commun `notebooks/etl_pipeline.py` contient le code reproductible et commenté utilisé par les quatre notebooks.
