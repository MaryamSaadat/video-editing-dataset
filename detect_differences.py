# once you have ran the effects_transcript creator, you run this to find any mismatches

#!/usr/bin/env python3
import pandas as pd
import json
import ast
import re


FILTERED_CSV = "education_filtered.csv"  #<------- Add csv name here
# ---------------------------
# Tag definitions and expected columns
#  - Use LITERAL strings (not regex) for tags
#  - Count ONLY start tags for count-style effects
# ---------------------------

EFFECTS = {
    "b_roll": {
        "start_tag": "[BROLL]",
        "end_tag": "[/BROLL]",
        "pred_count_col": "b_roll_count",
    },
    "animated": {
        "start_tag": "[ANIMATED]",
        "end_tag": "[/ANIMATED]",
        "pred_count_col": "animated_graphics_count",
    },
    "tos": {
        "start_tag": "[TOS]",
        "end_tag": "[/TOS]",
        "pred_bool_col": "on_screen_text_present",
    },
    "transition": {
        "tag": "[TRANSITION]",
        "pred_bool_col": "transitions_present",
    },
    "sound_effect": {
        "start_tag": "[SOUND_EFFECT]",
        "end_tag": "[/SOUND_EFFECT]",
        "pred_bool_col": "sound_effects_present",
    },
    "background_music": {
        "start_tag": "[BACKGROUND_MUSIC]",
        "end_tag": "[/BACKGROUND_MUSIC]",
        "pred_bool_col": "background_music_present",
    },
}

# ---------------------------
# Helpers: literal tag counting & presence
# ---------------------------

def count_start_tags(text: str, start_tag: str) -> int:
    """
    Count literal occurrences of the start tag (ignores end tags entirely).
    Uses re.escape to avoid regex semantics.
    """
    if not isinstance(text, str) or not text:
        return 0
    return len(re.findall(re.escape(start_tag), text))

def tag_present_literal(text: str, tag: str) -> bool:
    """
    True if the literal tag appears at least once in text.
    """
    if not isinstance(text, str) or not text:
        return False
    return bool(re.search(re.escape(tag), text))

def truthy(val) -> bool:
    """
    Normalize booleans coming as TRUE/FALSE strings, 1/0, etc.
    """
    if isinstance(val, bool):
        return val
    if val is None:
        return False
    s = str(val).strip().lower()
    return s in {"true", "1", "yes", "y"}

# ---------------------------
# Robust segment text extraction
#  - Accepts JSON string for either:
#    (a) a list of segments: [{transcript, visualDescription, ...}, ...]
#    (b) an object with key "segments": {"segments": [ ... ]}
#  - Falls back to ast.literal_eval for non-JSON string-likes
# ---------------------------

def extract_full_text(segments_str: str) -> str:
    """
    Combines transcript + visualDescription into one searchable string.
    Returns "" if parsing fails.
    """
    if not isinstance(segments_str, str) or not segments_str.strip():
        return ""

    # Normalize some quote irregularities early
    raw = segments_str.strip()

    parsed = None
    # Try JSON first (with a gentle quote fix)
    try:
        fixed = raw.replace("'", '"')
        parsed = json.loads(fixed)
    except Exception:
        # Try literal_eval next
        try:
            parsed = ast.literal_eval(raw)
        except Exception:
            return ""

    # If it's a dict with "segments", use that list
    if isinstance(parsed, dict) and "segments" in parsed:
        parsed = parsed.get("segments", [])

    # If it's not a list at this point, bail
    if not isinstance(parsed, list):
        return ""

    # Build the combined text
    parts = []
    for seg in parsed:
        if isinstance(seg, dict):
            t = seg.get("transcript", "")
            v = seg.get("visualDescription", "")
            if t:
                parts.append(str(t))
            if v:
                parts.append(str(v))
    return " ".join(parts).strip()

# ---------------------------
# Mismatch checker
# ---------------------------

def check_effect_mismatches(df: pd.DataFrame) -> list:
    mismatches = []

    for idx, row in df.iterrows():
        vid = row.get("video_id", f"row_{idx}")
        text = extract_full_text(row.get("edited script", ""))

        # DEBUG (optional): Uncomment to verify extraction and counts
        # print(f"[DEBUG] {vid} text length={len(text)}")
        # print(f"[DEBUG] {vid} [S_ANIMATED] count={count_start_tags(text, EFFECTS['animated']['start_tag'])}")

        row_mismatches = {"video_id": vid}

        for eff_key, eff in EFFECTS.items():
            # Count-based predictions: compare predicted count vs start tag occurrences
            if "pred_count_col" in eff:
                predicted_raw = row.get(eff["pred_count_col"], 0)
                predicted = int(predicted_raw) if pd.notna(predicted_raw) and str(predicted_raw).strip() != "" else 0
                placed = count_start_tags(text, eff["start_tag"])
                if placed != predicted:
                    row_mismatches[eff_key] = (predicted, placed)

            # Boolean predictions: compare predicted bool vs presence of tag(s)
            elif "pred_bool_col" in eff:
                predicted = truthy(row.get(eff["pred_bool_col"], False))

                # Single-tag style (e.g., [TRANSITION])
                if "tag" in eff:
                    placed_bool = tag_present_literal(text, eff["tag"])
                else:
                    # Start/end style → presence determined solely by start tag
                    placed_bool = count_start_tags(text, eff["start_tag"]) > 0

                if placed_bool != predicted:
                    row_mismatches[eff_key] = (predicted, placed_bool)

        if len(row_mismatches) > 1:  # any mismatches beyond the video_id field
            mismatches.append(row_mismatches)

    return mismatches

# ---------------------------
# Run
# ---------------------------

if __name__ == "__main__":
    df = pd.read_csv(FILTERED_CSV)
    results = check_effect_mismatches(df)

    for r in results:
        print(r)
