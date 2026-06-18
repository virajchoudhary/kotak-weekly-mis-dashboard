from __future__ import annotations

import re

import pandas as pd

from .validators import MISValidationError


def normalized_text(value: object) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip()).casefold()


def fintech_token(value: object) -> str:
    return re.sub(r"[^A-Z0-9]", "", str(value or "").upper())


def is_fintech_row(row: pd.Series) -> bool:
    return fintech_token(row.get("category")) == "FINTECH" or fintech_token(
        row.get("sub_category")
    ) == "FINTECH"


def apply_mapping_rules(
    frame: pd.DataFrame, rules: list[dict], scheme_master: list[dict]
) -> pd.DataFrame:
    mapped = frame.copy()
    for rule in rules:
        source_field = rule["source_field"]
        if source_field not in mapped.columns:
            continue
        mask = mapped[source_field].map(normalized_text) == normalized_text(rule["source_value"])
        if not mask.any():
            continue
        for target in ("category", "sub_category", "sch_group", "asset_class"):
            if rule.get(target) is not None:
                mapped.loc[mask, target] = rule[target]

    canonical = {normalized_text(row["asset_class"]): row for row in scheme_master}
    unknown = sorted(
        {
            str(value)
            for value in mapped["asset_class"].dropna().unique()
            if normalized_text(value) not in canonical
        }
    )
    if unknown:
        raise MISValidationError(
            "One or more scheme types are not present in the scheme master.",
            [
                {
                    "field": "Scheme Type",
                    "value": value,
                    "message": "Add a scheme_master or mapping_rules entry",
                }
                for value in unknown
            ],
        )

    for index, value in mapped["asset_class"].items():
        master = canonical[normalized_text(value)]
        mapped.at[index, "asset_class"] = master["asset_class"]
        mapped.at[index, "sch_group"] = master["sch_group"]
    return mapped

