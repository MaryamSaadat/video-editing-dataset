# This file takes in a file and outputs video ids which have hallucination
# It outputs where transcript and specific keywords are together, that often means that it is usually the transcript and not specific keywords
# It outputs where there is sounds effects and music together as often times there is not music

#!/usr/bin/env python3
import os
import ast
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv

load_dotenv()

# ==== CONFIG (env-driven) ====
GENRE = os.getenv("VIDEO_CATEGORY").strip()
INPUT_CSV = Path("filtered") / f"{GENRE}_filtered.csv"
ANOMALIES_DIR = Path("anomalies")
OUTPUT_CSV = ANOMALIES_DIR / f"{GENRE}_anomalies.csv"

ANOMALIES_DIR.mkdir(parents=True, exist_ok=True)

def to_bool(x):
    if isinstance(x, bool):
        return x
    if pd.isna(x):
        return False
    s = str(x).strip().lower()
    return s in {"true", "1", "yes", "y", "t"}

def to_int(x, default=0):
    try:
        if pd.isna(x):
            return default
        return int(float(x))
    except Exception:
        return default

def parse_list_like(x):
    """
    Accepts lists, JSON/Python-like lists in strings, or comma-separated strings.
    Returns a list of stripped strings.
    """
    if isinstance(x, list):
        return [str(it).strip() for it in x if str(it).strip()]
    if pd.isna(x):
        return []
    s = str(x).strip()
    try:
        val = ast.literal_eval(s)
        if isinstance(val, list):
            return [str(it).strip() for it in val if str(it).strip()]
    except Exception:
        pass
    return [t.strip() for t in s.split(",") if t.strip()]

def find_anomalies_row(row) -> dict:
    anomalies = []

    # Normalize fields
    bgm = to_bool(row.get("background_music_present", False))
    sfx_present = to_bool(row.get("sound_effects_present", False))
    b_roll_count = to_int(row.get("b_roll_count", 0))
    anim_count = to_int(row.get("animated_graphics_count", 0))
    trans_count = to_int(row.get("transitions_count", 0))
    sfx_count = to_int(row.get("sound_effects_count", 0))

    text_types_raw = parse_list_like(row.get("type_of_on_screen_text", []))
    text_types_lower = {t.lower() for t in text_types_raw}

    # Rule 1: sound anomaly — both present
    rule1 = bgm and sfx_present
    if rule1:
        anomalies.append("Both sound effects and background music are present")

    # Rule 2: overuse anomaly — any count > 5
    overuse_fields = []
    if b_roll_count > 5:
        overuse_fields.append(f"b_roll_count={b_roll_count}")
    if anim_count > 5:
        overuse_fields.append(f"animated_graphics_count={anim_count}")
    if trans_count > 5:
        overuse_fields.append(f"transitions_count={trans_count}")
    if sfx_count > 5:
        overuse_fields.append(f"sound_effects_count={sfx_count}")
    rule2 = len(overuse_fields) > 0
    if rule2:
        anomalies.append("High edit counts (>5): " + ", ".join(overuse_fields))

    # Rule 3: text conflict — transcript/text-on-screen AND specific keywords together
    has_transcript_or_text = any(
        t in {"transcript", "text on screen", "text-on-screen"} for t in text_types_lower
    )
    has_specific_keywords = any(
        ("specific" in t and "keyword" in t) or t == "specific keywords"
        for t in text_types_lower
    )
    rule3 = has_transcript_or_text and has_specific_keywords
    if rule3:
        anomalies.append("Both Transcript/Text-on-screen and Specific Keywords are present")

    return {
        "rule_sound_and_bgm": rule1,
        "rule_overuse_counts": rule2,
        "rule_text_conflict": rule3,
        "has_anomaly": (rule1 or rule2 or rule3),
        "anomalies_joined": "; ".join(anomalies),
    }

def main():
    if not INPUT_CSV.exists():
        raise FileNotFoundError(f"Input CSV not found: {INPUT_CSV.resolve()}")

    df = pd.read_csv(INPUT_CSV)
    id_col = "video_id" if "video_id" in df.columns else None

    results = df.apply(find_anomalies_row, axis=1, result_type="expand")

    # Assemble output
    if id_col:
        out = pd.DataFrame({
            "video_id": df[id_col].astype(str),
            **{col: results[col] for col in results.columns}
        })
    else:
        out = pd.DataFrame({
            "video_row_index": df.index.astype(int),
            **{col: results[col] for col in results.columns}
        })

    # Keep only rows with anomalies
    out_with_anomalies = out[out["has_anomaly"] == True].copy()
    out_with_anomalies.to_csv(OUTPUT_CSV, index=False)

    print(f"Saved anomalies: {OUTPUT_CSV}")
    print(f"Total rows: {len(df)} | With anomalies: {len(out_with_anomalies)}")
    if not out_with_anomalies.empty:
        print(out_with_anomalies.head(10).to_string(index=False))

if __name__ == "__main__":
    main()
