from __future__ import annotations

from pathlib import Path
import warnings

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestRegressor
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LinearRegression, Ridge
from sklearn.model_selection import KFold, LeaveOneOut, cross_validate
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler


ROOT_DIR = Path(__file__).resolve().parents[1]
INPUT_PATH = ROOT_DIR / "outputs" / "warehouse" / "dm_dataset_ml.csv"
OUTPUT_DIR = ROOT_DIR / "outputs" / "datamarts"
OUTPUT_COMPARISON = OUTPUT_DIR / "ml_model_comparison.csv"
OUTPUT_SUMMARY = OUTPUT_DIR / "ml_best_model_summary.txt"

TARGET = "taux_participation_reel"
EXCLUDED_COLS = {
    "id_election",
    "load_ts",
    "famille_dominante",
    "taux_abstention_reel",
}


def build_pipelines() -> dict[str, Pipeline]:
    scaled_prep = Pipeline(
        steps=[
            ("imputer", SimpleImputer(strategy="median")),
            ("scaler", StandardScaler()),
        ]
    )
    tree_prep = Pipeline(steps=[("imputer", SimpleImputer(strategy="median"))])

    return {
        "LinearRegression": Pipeline(
            steps=[("prep", scaled_prep), ("model", LinearRegression())]
        ),
        "Ridge": Pipeline(steps=[("prep", scaled_prep), ("model", Ridge(alpha=1.0))]),
        "RandomForest": Pipeline(
            steps=[
                ("prep", tree_prep),
                (
                    "model",
                    RandomForestRegressor(
                        n_estimators=300,
                        max_depth=4,
                        random_state=42,
                    ),
                ),
            ]
        ),
    }


def load_dataset(path: Path) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(f"Dataset introuvable: {path}")
    return pd.read_csv(path)


def prepare_xy(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.Series]:
    if TARGET not in df.columns:
        raise ValueError(f"Colonne cible absente: {TARGET}")

    work = df.copy()
    work = work.dropna(subset=[TARGET])

    drop_cols = [col for col in EXCLUDED_COLS if col in work.columns]
    work = work.drop(columns=drop_cols)

    x = work.drop(columns=[TARGET])
    y = work[TARGET]

    # POC robuste: on garde uniquement les variables numeriques.
    x = x.select_dtypes(include=[np.number]).copy()

    if x.empty:
        raise ValueError("Aucune variable numerique disponible pour le ML.")

    return x, y


def evaluate_models(x: pd.DataFrame, y: pd.Series) -> pd.DataFrame:
    n_rows = len(x)
    if n_rows < 4:
        warnings.warn(
            "Le dataset contient tres peu de lignes. Les resultats sont indicatifs.",
            RuntimeWarning,
        )

    if n_rows >= 30:
        cv = KFold(n_splits=5, shuffle=True, random_state=42)
        cv_label = "KFold(5)"
        scoring = {
            "rmse": "neg_root_mean_squared_error",
            "mae": "neg_mean_absolute_error",
            "r2": "r2",
        }
    else:
        cv = LeaveOneOut()
        cv_label = "LeaveOneOut"
        scoring = {
            "rmse": "neg_root_mean_squared_error",
            "mae": "neg_mean_absolute_error",
        }

    rows: list[dict[str, float | str]] = []
    for model_name, pipeline in build_pipelines().items():
        # n_jobs=1 avoids multiprocessing limitations on some locked environments.
        scores = cross_validate(pipeline, x, y, cv=cv, scoring=scoring, n_jobs=1)
        r2 = float(scores["test_r2"].mean()) if "test_r2" in scores else np.nan
        rows.append(
            {
                "model": model_name,
                "RMSE": float(-scores["test_rmse"].mean()),
                "MAE": float(-scores["test_mae"].mean()),
                "R2": r2,
                "n_obs": n_rows,
                "cv": cv_label,
            }
        )

    return pd.DataFrame(rows).sort_values(by="RMSE", ascending=True).reset_index(
        drop=True
    )


def write_summary(results: pd.DataFrame) -> None:
    best = results.iloc[0]
    lines = [
        "=== Resume choix modele (MSPR) ===",
        f"Modele retenu (RMSE min): {best['model']}",
        f"RMSE: {best['RMSE']:.4f}",
        f"MAE: {best['MAE']:.4f}",
        f"R2: {best['R2']:.4f}" if pd.notna(best["R2"]) else "R2: non interpretable en Leave-One-Out",
        "",
        "Justification:",
        "- Selection basee sur la performance predictive (RMSE).",
        "- Validation croisee adaptee au volume du datamart.",
        "- Interpretation a croiser avec les limites metier et la qualite des millesimes.",
    ]
    OUTPUT_SUMMARY.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    print("=== ML MSPR - comparaison 3 modeles ===")
    print(f"Lecture dataset: {INPUT_PATH}")

    df = load_dataset(INPUT_PATH)
    x, y = prepare_xy(df)

    print(f"Observations utilisables: {len(x)}")
    print(f"Variables numeriques: {x.shape[1]}")

    results = evaluate_models(x, y)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    results.to_csv(OUTPUT_COMPARISON, index=False, encoding="utf-8")
    write_summary(results)

    print("\nResultats comparaison:")
    print(results.to_string(index=False))
    print(f"\nFichier cree: {OUTPUT_COMPARISON}")
    print(f"Fichier cree: {OUTPUT_SUMMARY}")


if __name__ == "__main__":
    main()
