from typing import Any, Dict, List

import pandas as pd


def extract_excel_markdown(file_path: str) -> Dict[str, Any]:
    df = pd.read_excel(file_path).fillna("")
    return {
        "text_content": df.to_markdown(index=False),
        "detected_columns": [str(c).strip() for c in list(df.columns) if str(c).strip()],
        "rows_count": len(df),
    }


def extract_csv_markdown(file_path: str) -> Dict[str, Any]:
    try:
        df = pd.read_csv(file_path)
    except Exception:
        try:
            df = pd.read_csv(file_path, sep=";")
        except Exception:
            df = pd.read_csv(file_path, sep=None, engine="python", encoding="latin-1")
    df = df.fillna("")
    return {
        "text_content": df.to_markdown(index=False),
        "detected_columns": [str(c).strip() for c in list(df.columns) if str(c).strip()],
        "rows_count": len(df),
    }

