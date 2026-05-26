from __future__ import annotations

import csv
import json
import math
import sqlite3
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from statistics import mean


ROOT_DIR = Path(__file__).resolve().parents[1]
RAW_DIR = ROOT_DIR / "data" / "raw_batches"
OUT_DIR = ROOT_DIR / "outputs"
STG_RAW_DIR = OUT_DIR / "staging" / "raw"
STG_STD_DIR = OUT_DIR / "staging" / "std"
STG_REJECT_DIR = OUT_DIR / "staging" / "reject"
TR_DIR = OUT_DIR / "transformations"
WH_DIR = OUT_DIR / "warehouse"
OPS_DIR = OUT_DIR / "ops"
DB_PATH = ROOT_DIR / "database" / "electio_dwh.db"

PDL_DEPARTMENTS = {"44", "49", "53", "72", "85"}
REGION_CODE = "52"
REGION_NAME = "Pays de la Loire"
ELECTIONS_TO_KEEP = {
    "2012_pres_t1",
    "2012_legi_t1",
    "2017_pres_t1",
    "2017_legi_t1",
    "2022_pres_t1",
    "2022_legi_t1",
}

GENERAL_NUMERIC_COLS = [
    "inscrits",
    "abstentions",
    "votants",
    "blancs",
    "nuls",
    "exprimes",
    "ratio_abstentions_inscrits",
    "ratio_votants_inscrits",
    "ratio_blancs_inscrits",
    "ratio_blancs_votants",
    "ratio_nuls_inscrits",
    "ratio_nuls_votants",
    "ratio_exprimes_inscrits",
    "ratio_exprimes_votants",
]

SOCIO_COLS = [
    "CODGEO",
    "P22_POP",
    "P16_POP",
    "P22_MEN",
    "MED_SL23",
    "PR_MD60_23",
    "P22_CHOM1564",
    "P22_ACT1564",
    "P22_EMPLT",
    "ETTOT24",
]

EMPLOI_COLS = [
    "CODGEO",
    "P10_POP1564",
    "P10_CHOM1564",
    "P15_POP1564",
    "P15_CHOM1564",
    "P21_POP1564",
    "P21_CHOM1564",
]

SECURITY_INDICATORS = {
    "Coups et blessures volontaires",
    "Vols avec armes",
    "Vols violents sans arme",
    "Cambriolages de logement",
    "Destructions et degradations volontaires",
    "Vols de vehicules",
}

FAMILY_MAP = {
    "EXG": "gauche_radicale",
    "FI": "gauche_radicale",
    "FG": "gauche_radicale",
    "COM": "gauche_radicale",
    "SOC": "gauche",
    "UG": "gauche",
    "DVG": "gauche",
    "RDG": "gauche",
    "VEC": "ecologie",
    "ECO": "ecologie",
    "ENS": "centre",
    "MDM": "centre",
    "UC": "centre",
    "UDI": "centre",
    "LR": "droite",
    "UMP": "droite",
    "DVD": "droite",
    "UXD": "droite",
    "FN": "extreme_droite",
    "RN": "extreme_droite",
    "EXD": "extreme_droite",
    "REC": "extreme_droite",
    "DIV": "divers",
    "REG": "divers",
}

ML_FAMILY_COLS = [
    "pct_autre",
    "pct_centre",
    "pct_divers",
    "pct_droite",
    "pct_ecologie",
    "pct_extreme_droite",
    "pct_gauche",
    "pct_gauche_radicale",
]


def ensure_directories() -> None:
    for path in [
        STG_RAW_DIR,
        STG_STD_DIR,
        STG_REJECT_DIR,
        TR_DIR,
        WH_DIR,
        OPS_DIR,
        DB_PATH.parent,
    ]:
        path.mkdir(parents=True, exist_ok=True)


def now_iso() -> str:
    return datetime.now().replace(microsecond=0).isoformat()


def normalize_code(value: object, width: int = 5) -> str:
    text = "" if value is None else str(value).strip()
    if not text or text.upper() in {"NA", "NAN"}:
        return ""
    if text.endswith(".0"):
        text = text[:-2]
    return text.zfill(width)


def parse_float(value: object) -> float | None:
    """Convertit les formats francais/INSEE en nombre Python exploitable."""
    if value is None:
        return None
    text = str(value).strip().replace("\u202f", "").replace(" ", "")
    if text == "" or text.upper() in {"NA", "NAN", "ND", "NDIFF"}:
        return None
    text = text.replace(",", ".")
    try:
        return float(text)
    except ValueError:
        return None


def fmt(value: object) -> str:
    """Ecrit des CSV propres: vide pour les valeurs absentes, arrondi lisible."""
    if value is None:
        return ""
    if isinstance(value, float):
        if math.isnan(value):
            return ""
        return f"{value:.6f}".rstrip("0").rstrip(".")
    return str(value)


def read_rows(path: Path, delimiter: str = ";"):
    with path.open(newline="", encoding="utf-8", errors="replace") as handle:
        yield from csv.DictReader(handle, delimiter=delimiter)


def write_rows(path: Path, rows: list[dict], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: fmt(row.get(field)) for field in fieldnames})


def append_control(rows: list[dict]) -> None:
    path = OPS_DIR / "ops_batch_control.csv"
    fieldnames = [
        "run_ts",
        "phase",
        "dataset",
        "rows_in",
        "rows_out",
        "rows_rejected",
        "commentaire",
    ]
    existing = []
    if path.exists():
        with path.open(newline="", encoding="utf-8") as handle:
            existing = list(csv.DictReader(handle))
    write_rows(path, existing + rows, fieldnames)


def election_meta(id_election: str) -> tuple[int | None, str]:
    parts = (id_election or "").split("_")
    if len(parts) < 2:
        return None, ""
    try:
        year = int(parts[0])
    except ValueError:
        year = None
    election_type = parts[1]
    return year, election_type


def normalize_family(nuance: str) -> str:
    key = (nuance or "").strip().upper()
    return FAMILY_MAP.get(key, "autre")


def phase_01_collecte() -> dict:
    """Filtre les donnees sources sur le perimetre projet sans les agreger."""
    ensure_directories()
    started = now_iso()
    control_rows = []

    specs = [
        (
            "general",
            RAW_DIR / "general_results.csv",
            STG_RAW_DIR / "stg_raw_general.csv",
            ";",
            lambda r: r.get("id_election") in ELECTIONS_TO_KEEP
            and str(r.get("code_departement", "")).zfill(2) in PDL_DEPARTMENTS,
        ),
        (
            "candidats",
            RAW_DIR / "candidats_results.csv",
            STG_RAW_DIR / "stg_raw_candidats.csv",
            ";",
            lambda r: r.get("id_election") in ELECTIONS_TO_KEEP
            and str(r.get("code_departement", "")).zfill(2) in PDL_DEPARTMENTS,
        ),
        (
            "socioeco",
            RAW_DIR / "base_cc_comparateur.csv",
            STG_RAW_DIR / "stg_raw_socioeco.csv",
            ";",
            lambda r: normalize_code(r.get("CODGEO"))[:2] in PDL_DEPARTMENTS,
        ),
        (
            "emploi",
            RAW_DIR / "emploi_pop_active.CSV",
            STG_RAW_DIR / "stg_raw_emploi.csv",
            ";",
            lambda r: normalize_code(r.get("CODGEO"))[:2] in PDL_DEPARTMENTS,
        ),
        (
            "securite",
            RAW_DIR / "crimes_delits_communes.csv",
            STG_RAW_DIR / "stg_raw_securite.csv",
            ";",
            lambda r: normalize_code(r.get("CODGEO_2025"))[:2] in PDL_DEPARTMENTS
            and str(r.get("annee", "")).isdigit()
            and 2012 <= int(r.get("annee")) <= 2024,
        ),
    ]

    summary = {}
    for dataset, source, target, delimiter, keep_row in specs:
        rows_in = rows_out = 0
        fieldnames = None
        with source.open(newline="", encoding="utf-8", errors="replace") as src:
            reader = csv.DictReader(src, delimiter=delimiter)
            fieldnames = reader.fieldnames or []
            with target.open("w", newline="", encoding="utf-8") as dst:
                writer = csv.DictWriter(dst, fieldnames=fieldnames)
                writer.writeheader()
                for row in reader:
                    rows_in += 1
                    if keep_row(row):
                        writer.writerow(row)
                        rows_out += 1
        rejected = rows_in - rows_out
        summary[dataset] = {
            "source": str(source.relative_to(ROOT_DIR)),
            "target": str(target.relative_to(ROOT_DIR)),
            "rows_in": rows_in,
            "rows_out": rows_out,
            "rows_rejected": rejected,
        }
        control_rows.append(
            {
                "run_ts": started,
                "phase": "01_collecte",
                "dataset": dataset,
                "rows_in": rows_in,
                "rows_out": rows_out,
                "rows_rejected": rejected,
                "commentaire": "Filtrage Pays de la Loire et elections 2012/2017/2022 T1.",
            }
        )

    append_control(control_rows)
    (STG_RAW_DIR / "_phase_01_summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    return summary


def phase_02_staging_qualite() -> dict:
    """Standardise les types, codes et libelles avant toute jointure."""
    ensure_directories()
    started = now_iso()
    control_rows = []
    summary = {}

    # Resultats generaux: un enregistrement par bureau de vote.
    general_rows, general_rejects = [], []
    for row in read_rows(STG_RAW_DIR / "stg_raw_general.csv", delimiter=","):
        commune = normalize_code(row.get("code_commune"))
        dept = str(row.get("code_departement", "")).zfill(2)
        year, election_type = election_meta(row.get("id_election", ""))
        if not commune or dept not in PDL_DEPARTMENTS or year is None:
            general_rejects.append(row)
            continue
        clean = {key: row.get(key, "") for key in row.keys()}
        clean["code_commune"] = commune
        clean["code_departement"] = dept
        clean["code_bv"] = normalize_code(row.get("code_bv"), width=4)
        clean["annee"] = year
        clean["type_election"] = election_type
        clean["region"] = REGION_NAME
        clean["code_region"] = REGION_CODE
        for col in GENERAL_NUMERIC_COLS:
            clean[col] = parse_float(row.get(col))
        general_rows.append(clean)
    write_rows(
        STG_STD_DIR / "stg_std_general.csv",
        general_rows,
        list(general_rows[0].keys()) if general_rows else [],
    )
    write_rows(
        STG_REJECT_DIR / "stg_reject_general.csv",
        general_rejects,
        list(general_rejects[0].keys()) if general_rejects else ["raison"],
    )
    summary["general"] = [len(general_rows), len(general_rejects)]

    # Resultats candidats: conservation des voix et creation d'une famille politique.
    candidat_rows, candidat_rejects = [], []
    for row in read_rows(STG_RAW_DIR / "stg_raw_candidats.csv", delimiter=","):
        commune = normalize_code(row.get("code_commune"))
        dept = str(row.get("code_departement", "")).zfill(2)
        year, election_type = election_meta(row.get("id_election", ""))
        voix = parse_float(row.get("voix"))
        if not commune or dept not in PDL_DEPARTMENTS or year is None or voix is None:
            candidat_rejects.append(row)
            continue
        clean = {key: row.get(key, "") for key in row.keys()}
        clean["code_commune"] = commune
        clean["code_departement"] = dept
        clean["code_bv"] = normalize_code(row.get("code_bv"), width=4)
        clean["annee"] = year
        clean["type_election"] = election_type
        clean["voix"] = voix
        clean["ratio_voix_inscrits"] = parse_float(row.get("ratio_voix_inscrits"))
        clean["ratio_voix_exprimes"] = parse_float(row.get("ratio_voix_exprimes"))
        clean["famille_politique"] = normalize_family(row.get("nuance"))
        candidat_rows.append(clean)
    write_rows(
        STG_STD_DIR / "stg_std_candidats.csv",
        candidat_rows,
        list(candidat_rows[0].keys()) if candidat_rows else [],
    )
    write_rows(
        STG_REJECT_DIR / "stg_reject_candidats.csv",
        candidat_rejects,
        list(candidat_rejects[0].keys()) if candidat_rejects else ["raison"],
    )
    summary["candidats"] = [len(candidat_rows), len(candidat_rejects)]

    socio_rows, socio_rejects = [], []
    for row in read_rows(STG_RAW_DIR / "stg_raw_socioeco.csv", delimiter=","):
        commune = normalize_code(row.get("CODGEO"))
        if commune[:2] not in PDL_DEPARTMENTS:
            socio_rejects.append(row)
            continue
        clean = {"CODGEO": commune, "code_departement": commune[:2]}
        for col in SOCIO_COLS:
            if col != "CODGEO":
                clean[col] = parse_float(row.get(col))
        socio_rows.append(clean)
    write_rows(STG_STD_DIR / "stg_std_socioeco.csv", socio_rows, ["CODGEO", "code_departement"] + SOCIO_COLS[1:])
    write_rows(STG_REJECT_DIR / "stg_reject_socioeco.csv", socio_rejects, list(socio_rejects[0].keys()) if socio_rejects else ["raison"])
    summary["socioeco"] = [len(socio_rows), len(socio_rejects)]

    emploi_rows, emploi_rejects = [], []
    for row in read_rows(STG_RAW_DIR / "stg_raw_emploi.csv", delimiter=","):
        commune = normalize_code(row.get("CODGEO"))
        if commune[:2] not in PDL_DEPARTMENTS:
            emploi_rejects.append(row)
            continue
        clean = {"CODGEO": commune, "code_departement": commune[:2]}
        for col in EMPLOI_COLS:
            if col != "CODGEO":
                clean[col] = parse_float(row.get(col))
        for year, pop_col, chom_col in [
            (2012, "P10_POP1564", "P10_CHOM1564"),
            (2017, "P15_POP1564", "P15_CHOM1564"),
            (2022, "P21_POP1564", "P21_CHOM1564"),
        ]:
            pop = clean.get(pop_col)
            chom = clean.get(chom_col)
            clean[f"taux_chomage_{year}"] = (chom / pop * 100) if pop else None
        emploi_rows.append(clean)
    emploi_fields = ["CODGEO", "code_departement"] + EMPLOI_COLS[1:] + [
        "taux_chomage_2012",
        "taux_chomage_2017",
        "taux_chomage_2022",
    ]
    write_rows(STG_STD_DIR / "stg_std_emploi.csv", emploi_rows, emploi_fields)
    write_rows(STG_REJECT_DIR / "stg_reject_emploi.csv", emploi_rejects, list(emploi_rejects[0].keys()) if emploi_rejects else ["raison"])
    summary["emploi"] = [len(emploi_rows), len(emploi_rejects)]

    security_rows, security_rejects = [], []
    for row in read_rows(STG_RAW_DIR / "stg_raw_securite.csv", delimiter=","):
        commune = normalize_code(row.get("CODGEO_2025"))
        year = parse_float(row.get("annee"))
        if commune[:2] not in PDL_DEPARTMENTS or year is None:
            security_rejects.append(row)
            continue
        clean = {key: row.get(key, "") for key in row.keys()}
        clean["CODGEO_2025"] = commune
        clean["code_departement"] = commune[:2]
        clean["annee"] = int(year)
        clean["nombre"] = parse_float(row.get("nombre"))
        clean["taux_pour_mille"] = parse_float(row.get("taux_pour_mille"))
        clean["insee_pop"] = parse_float(row.get("insee_pop"))
        security_rows.append(clean)
    security_fields = list(security_rows[0].keys()) if security_rows else []
    write_rows(STG_STD_DIR / "stg_std_securite.csv", security_rows, security_fields)
    write_rows(STG_REJECT_DIR / "stg_reject_securite.csv", security_rejects, list(security_rejects[0].keys()) if security_rejects else ["raison"])
    summary["securite"] = [len(security_rows), len(security_rejects)]

    for dataset, (rows_out, rows_rejected) in summary.items():
        control_rows.append(
            {
                "run_ts": started,
                "phase": "02_staging_qualite",
                "dataset": dataset,
                "rows_in": rows_out + rows_rejected,
                "rows_out": rows_out,
                "rows_rejected": rows_rejected,
                "commentaire": "Normalisation des codes, types numeriques et rejets qualite.",
            }
        )
    append_control(control_rows)
    (STG_STD_DIR / "_phase_02_summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    return summary


def phase_03_transformations() -> dict:
    """Construit le datamart ML au grain commune-election."""
    ensure_directories()
    started = now_iso()

    # 1) Agregation des bureaux de vote vers commune-election.
    elections = {}
    for row in read_rows(STG_STD_DIR / "stg_std_general.csv", delimiter=","):
        key = (row["id_election"], row["code_commune"])
        item = elections.setdefault(
            key,
            {
                "id_election": row["id_election"],
                "annee": int(row["annee"]),
                "type_election": row["type_election"],
                "code_commune": row["code_commune"],
                "libelle_commune": row.get("libelle_commune", ""),
                "code_departement": row["code_departement"],
                "region": REGION_NAME,
                "code_region": REGION_CODE,
                "total_inscrits": 0.0,
                "total_votants": 0.0,
                "total_abstentions": 0.0,
                "total_blancs": 0.0,
                "total_nuls": 0.0,
                "total_exprimes": 0.0,
                "nb_bureaux": 0,
            },
        )
        for source, target in [
            ("inscrits", "total_inscrits"),
            ("votants", "total_votants"),
            ("abstentions", "total_abstentions"),
            ("blancs", "total_blancs"),
            ("nuls", "total_nuls"),
            ("exprimes", "total_exprimes"),
        ]:
            item[target] += parse_float(row.get(source)) or 0.0
        item["nb_bureaux"] += 1

    election_rows = []
    for item in elections.values():
        inscrits = item["total_inscrits"]
        votants = item["total_votants"]
        abstentions = item["total_abstentions"]
        item["taux_participation_reel"] = (votants / inscrits * 100) if inscrits else None
        item["taux_abstention_reel"] = (abstentions / inscrits * 100) if inscrits else None
        election_rows.append(item)

    # 2) Agregation des voix par famille politique au meme grain.
    voices = defaultdict(Counter)
    for row in read_rows(STG_STD_DIR / "stg_std_candidats.csv", delimiter=","):
        key = (row["id_election"], row["code_commune"])
        voices[key][row["famille_politique"]] += parse_float(row.get("voix")) or 0.0

    for row in election_rows:
        key = (row["id_election"], row["code_commune"])
        family_counts = voices.get(key, Counter())
        total_voices = sum(family_counts.values())
        dominant, dominant_votes = ("non_disponible", 0.0)
        if family_counts:
            dominant, dominant_votes = family_counts.most_common(1)[0]
        row["famille_dominante"] = dominant
        row["pct_voix_famille_dominante"] = (dominant_votes / total_voices * 100) if total_voices else None
        for col in ML_FAMILY_COLS:
            family = col.replace("pct_", "")
            row[col] = (family_counts.get(family, 0.0) / total_voices * 100) if total_voices else 0.0

    socio = {
        row["CODGEO"]: row
        for row in read_rows(STG_STD_DIR / "stg_std_socioeco.csv", delimiter=",")
    }
    emploi = {
        row["CODGEO"]: row
        for row in read_rows(STG_STD_DIR / "stg_std_emploi.csv", delimiter=",")
    }

    # 3) Securite: les donnees commencent souvent en 2016, on prend l'annee la plus proche.
    security_by_commune_year = defaultdict(lambda: {"nombre": 0.0, "taux": []})
    for row in read_rows(STG_STD_DIR / "stg_std_securite.csv", delimiter=","):
        indicator = row.get("indicateur", "")
        if SECURITY_INDICATORS and indicator not in SECURITY_INDICATORS:
            continue
        key = (row["CODGEO_2025"], int(row["annee"]))
        security_by_commune_year[key]["nombre"] += parse_float(row.get("nombre")) or 0.0
        taux = parse_float(row.get("taux_pour_mille"))
        if taux is not None:
            security_by_commune_year[key]["taux"].append(taux)

    available_security_years = defaultdict(list)
    for commune, year in security_by_commune_year:
        available_security_years[commune].append(year)

    def nearest_security(commune: str, election_year: int) -> tuple[float | None, float | None, int | None]:
        years = available_security_years.get(commune, [])
        if not years:
            return None, None, None
        chosen = min(years, key=lambda year: (abs(year - election_year), year))
        values = security_by_commune_year[(commune, chosen)]
        avg_taux = mean(values["taux"]) if values["taux"] else None
        return values["nombre"], avg_taux, chosen

    dataset_ml = []
    for row in sorted(election_rows, key=lambda r: (r["annee"], r["type_election"], r["code_commune"])):
        commune = row["code_commune"]
        year = int(row["annee"])
        merged = dict(row)

        socio_row = socio.get(commune, {})
        emploi_row = emploi.get(commune, {})
        for col in SOCIO_COLS[1:]:
            merged[col.lower()] = parse_float(socio_row.get(col))

        # Les millesimes INSEE sont rapproches des annees electorales disponibles.
        if year <= 2012:
            pop_col, chom_col, taux_col = "P10_POP1564", "P10_CHOM1564", "taux_chomage_2012"
        elif year <= 2017:
            pop_col, chom_col, taux_col = "P15_POP1564", "P15_CHOM1564", "taux_chomage_2017"
        else:
            pop_col, chom_col, taux_col = "P21_POP1564", "P21_CHOM1564", "taux_chomage_2022"
        merged["pop_15_64"] = parse_float(emploi_row.get(pop_col))
        merged["chomeurs_15_64"] = parse_float(emploi_row.get(chom_col))
        merged["taux_chomage"] = parse_float(emploi_row.get(taux_col))

        nb_delits, taux_delits, sec_year = nearest_security(commune, year)
        merged["nb_faits_securite"] = nb_delits
        merged["taux_faits_securite_pour_mille"] = taux_delits
        merged["annee_securite_reference"] = sec_year

        # Variables derivees utiles pour la prediction et l'analyse visuelle.
        pop = merged.get("p22_pop")
        menages = merged.get("p22_men")
        entreprises = merged.get("ettot24")
        merged["inscrits_par_habitant"] = (merged["total_inscrits"] / pop) if pop else None
        merged["entreprises_par_1000_hab"] = (entreprises / pop * 1000) if pop and entreprises is not None else None
        merged["taille_moyenne_menage"] = (pop / menages) if pop and menages else None
        dataset_ml.append(merged)

    fields = [
        "id_election",
        "annee",
        "type_election",
        "code_commune",
        "libelle_commune",
        "code_departement",
        "region",
        "code_region",
        "total_inscrits",
        "total_votants",
        "total_abstentions",
        "total_blancs",
        "total_nuls",
        "total_exprimes",
        "nb_bureaux",
        "taux_participation_reel",
        "taux_abstention_reel",
        "famille_dominante",
        "pct_voix_famille_dominante",
    ] + ML_FAMILY_COLS + [
        "p22_pop",
        "p16_pop",
        "p22_men",
        "med_sl23",
        "pr_md60_23",
        "p22_chom1564",
        "p22_act1564",
        "p22_emplt",
        "ettot24",
        "pop_15_64",
        "chomeurs_15_64",
        "taux_chomage",
        "nb_faits_securite",
        "taux_faits_securite_pour_mille",
        "annee_securite_reference",
        "inscrits_par_habitant",
        "entreprises_par_1000_hab",
        "taille_moyenne_menage",
    ]
    write_rows(TR_DIR / "tr_elections_commune.csv", election_rows, fields[:19] + ML_FAMILY_COLS)
    write_rows(TR_DIR / "tr_dataset_ml.csv", dataset_ml, fields)

    indicator_rows = []
    for row in dataset_ml:
        indicator_rows.append(
            {
                "id_election": row["id_election"],
                "annee": row["annee"],
                "code_commune": row["code_commune"],
                "population_totale": row.get("p22_pop"),
                "revenu_median": row.get("med_sl23"),
                "taux_pauvrete": row.get("pr_md60_23"),
                "taux_chomage": row.get("taux_chomage"),
                "nb_entreprises": row.get("ettot24"),
                "taux_faits_securite_pour_mille": row.get("taux_faits_securite_pour_mille"),
            }
        )
    write_rows(
        TR_DIR / "tr_indicateurs_commune.csv",
        indicator_rows,
        [
            "id_election",
            "annee",
            "code_commune",
            "population_totale",
            "revenu_median",
            "taux_pauvrete",
            "taux_chomage",
            "nb_entreprises",
            "taux_faits_securite_pour_mille",
        ],
    )

    correlations = compute_correlations(dataset_ml)
    write_rows(
        TR_DIR / "tr_correlations.csv",
        correlations,
        ["indicateur", "correlation_participation", "force", "sens", "nb_observations"],
    )

    summary = {
        "grain": "commune-election",
        "rows_dataset_ml": len(dataset_ml),
        "rows_elections_commune": len(election_rows),
        "rows_correlations": len(correlations),
        "target": "taux_participation_reel",
    }
    append_control(
        [
            {
                "run_ts": started,
                "phase": "03_transformations",
                "dataset": "dataset_ml",
                "rows_in": len(general_rows := list(read_rows(STG_STD_DIR / "stg_std_general.csv", delimiter=","))),
                "rows_out": len(dataset_ml),
                "rows_rejected": 0,
                "commentaire": "Agregation au grain commune-election pour eviter le datamart regional trop petit.",
            }
        ]
    )
    (TR_DIR / "_phase_03_summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    return summary


def pearson(rows: list[dict], x_col: str, y_col: str) -> tuple[float | None, int]:
    pairs = []
    for row in rows:
        x = parse_float(row.get(x_col))
        y = parse_float(row.get(y_col))
        if x is not None and y is not None:
            pairs.append((x, y))
    if len(pairs) < 3:
        return None, len(pairs)
    xs, ys = zip(*pairs)
    mx, my = mean(xs), mean(ys)
    num = sum((x - mx) * (y - my) for x, y in pairs)
    den_x = math.sqrt(sum((x - mx) ** 2 for x in xs))
    den_y = math.sqrt(sum((y - my) ** 2 for y in ys))
    if den_x == 0 or den_y == 0:
        return None, len(pairs)
    return num / (den_x * den_y), len(pairs)


def compute_correlations(rows: list[dict]) -> list[dict]:
    indicators = [
        "p22_pop",
        "med_sl23",
        "pr_md60_23",
        "taux_chomage",
        "ettot24",
        "taux_faits_securite_pour_mille",
        "inscrits_par_habitant",
        "entreprises_par_1000_hab",
    ]
    result = []
    for indicator in indicators:
        corr, n = pearson(rows, indicator, "taux_participation_reel")
        abs_corr = abs(corr) if corr is not None else 0
        if abs_corr >= 0.5:
            force = "forte"
        elif abs_corr >= 0.25:
            force = "moyenne"
        else:
            force = "faible"
        result.append(
            {
                "indicateur": indicator,
                "correlation_participation": corr,
                "force": force,
                "sens": "positive" if (corr or 0) >= 0 else "negative",
                "nb_observations": n,
            }
        )
    return result


def phase_04_data_warehouse() -> dict:
    """Publie les dimensions, faits, datamarts CSV et la base SQLite finale."""
    ensure_directories()
    started = now_iso()
    dataset = list(read_rows(TR_DIR / "tr_dataset_ml.csv", delimiter=","))

    communes = {}
    for row in dataset:
        communes[row["code_commune"]] = {
            "commune_sk": len(communes) + 1 if row["code_commune"] not in communes else communes[row["code_commune"]]["commune_sk"],
            "code_commune": row["code_commune"],
            "libelle_commune": row["libelle_commune"],
            "code_departement": row["code_departement"],
            "region": REGION_NAME,
            "code_region": REGION_CODE,
        }
    dim_commune = sorted(communes.values(), key=lambda r: r["code_commune"])
    for i, row in enumerate(dim_commune, start=1):
        row["commune_sk"] = i
    commune_sk = {row["code_commune"]: row["commune_sk"] for row in dim_commune}

    dim_date = []
    for i, (year, typ) in enumerate(sorted({(r["annee"], r["type_election"]) for r in dataset}), start=1):
        label = "Presidentielle" if typ == "pres" else "Legislatives"
        dim_date.append(
            {
                "date_sk": i,
                "annee": year,
                "type_election": typ,
                "libelle": f"{label} {year} - 1er tour",
                "est_prediction": 0,
            }
        )
    dim_date.append(
        {
            "date_sk": len(dim_date) + 1,
            "annee": 2027,
            "type_election": "pres",
            "libelle": "Presidentielle 2027 - scenario de prediction",
            "est_prediction": 1,
        }
    )
    date_sk = {(row["annee"], row["type_election"]): row["date_sk"] for row in dim_date}

    indicator_defs = [
        ("population_totale", "Population totale", "habitants"),
        ("revenu_median", "Revenu median", "euros"),
        ("taux_pauvrete", "Taux de pauvrete", "%"),
        ("taux_chomage", "Taux de chomage", "%"),
        ("nb_entreprises", "Nombre d'entreprises", "nombre"),
        ("taux_faits_securite_pour_mille", "Faits de securite pour mille habitants", "pour mille"),
    ]
    dim_indicateur = [
        {
            "indicateur_sk": i,
            "code_indicateur": code,
            "libelle": label,
            "unite": unit,
            "source": "INSEE / MIOM / SSMSI",
            "description": "Indicateur prepare au grain commune-election pour analyse et ML.",
        }
        for i, (code, label, unit) in enumerate(indicator_defs, start=1)
    ]
    indicator_sk = {row["code_indicateur"]: row["indicateur_sk"] for row in dim_indicateur}

    fact_election = []
    fact_indicateur = []
    for idx, row in enumerate(dataset, start=1):
        fact_election.append(
            {
                "election_sk": idx,
                "date_sk": date_sk[(row["annee"], row["type_election"])],
                "commune_sk": commune_sk[row["code_commune"]],
                "id_election": row["id_election"],
                "total_inscrits": row["total_inscrits"],
                "total_votants": row["total_votants"],
                "total_abstentions": row["total_abstentions"],
                "total_exprimes": row["total_exprimes"],
                "nb_bureaux": row["nb_bureaux"],
                "taux_participation_reel": row["taux_participation_reel"],
                "taux_abstention_reel": row["taux_abstention_reel"],
                "famille_dominante": row["famille_dominante"],
                "pct_voix_famille_dominante": row["pct_voix_famille_dominante"],
            }
        )
        for code, _label, _unit in indicator_defs:
            value = row.get(
                {
                    "population_totale": "p22_pop",
                    "revenu_median": "med_sl23",
                    "taux_pauvrete": "pr_md60_23",
                    "taux_chomage": "taux_chomage",
                    "nb_entreprises": "ettot24",
                    "taux_faits_securite_pour_mille": "taux_faits_securite_pour_mille",
                }[code]
            )
            fact_indicateur.append(
                {
                    "indicateur_fact_sk": len(fact_indicateur) + 1,
                    "date_sk": date_sk[(row["annee"], row["type_election"])],
                    "commune_sk": commune_sk[row["code_commune"]],
                    "indicateur_sk": indicator_sk[code],
                    "code_indicateur": code,
                    "valeur": value,
                }
            )

    write_rows(WH_DIR / "dim_commune.csv", dim_commune, ["commune_sk", "code_commune", "libelle_commune", "code_departement", "region", "code_region"])
    write_rows(WH_DIR / "dim_date.csv", dim_date, ["date_sk", "annee", "type_election", "libelle", "est_prediction"])
    write_rows(WH_DIR / "dim_indicateur.csv", dim_indicateur, ["indicateur_sk", "code_indicateur", "libelle", "unite", "source", "description"])
    write_rows(WH_DIR / "fact_election.csv", fact_election, list(fact_election[0].keys()))
    write_rows(WH_DIR / "fact_indicateur.csv", fact_indicateur, list(fact_indicateur[0].keys()))
    write_rows(WH_DIR / "dm_dataset_ml.csv", dataset, list(dataset[0].keys()))
    write_rows(WH_DIR / "dm_correlations.csv", list(read_rows(TR_DIR / "tr_correlations.csv", delimiter=",")), ["indicateur", "correlation_participation", "force", "sens", "nb_observations"])

    write_sqlite(
        {
            "dim_commune": dim_commune,
            "dim_date": dim_date,
            "dim_indicateur": dim_indicateur,
            "fact_election": fact_election,
            "fact_indicateur": fact_indicateur,
            "dm_dataset_ml": dataset,
        }
    )

    summary = {
        "grain_final": "commune-election",
        "rows_dm_dataset_ml": len(dataset),
        "rows_fact_election": len(fact_election),
        "rows_fact_indicateur": len(fact_indicateur),
        "rows_dim_commune": len(dim_commune),
        "sqlite": str(DB_PATH.relative_to(ROOT_DIR)),
    }
    append_control(
        [
            {
                "run_ts": started,
                "phase": "04_data_warehouse",
                "dataset": "warehouse",
                "rows_in": len(dataset),
                "rows_out": len(fact_election),
                "rows_rejected": 0,
                "commentaire": "Publication des dimensions, faits, datamarts ML et SQLite.",
            }
        ]
    )
    (WH_DIR / "_phase_04_summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    return summary


def write_sqlite(tables: dict[str, list[dict]]) -> None:
    if DB_PATH.exists():
        DB_PATH.unlink()
    with sqlite3.connect(DB_PATH) as conn:
        for table_name, rows in tables.items():
            if not rows:
                continue
            columns = list(rows[0].keys())
            col_defs = ", ".join(f'"{col}" TEXT' for col in columns)
            conn.execute(f'DROP TABLE IF EXISTS "{table_name}"')
            conn.execute(f'CREATE TABLE "{table_name}" ({col_defs})')
            placeholders = ", ".join(["?"] * len(columns))
            conn.executemany(
                f'INSERT INTO "{table_name}" VALUES ({placeholders})',
                [[fmt(row.get(col)) for col in columns] for row in rows],
            )
        conn.commit()
