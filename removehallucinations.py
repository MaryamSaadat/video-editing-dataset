#!/usr/bin/env python3
"""
Interactive anomaly reviewer & editor for video effect rows.

Requirements:
  pip install pandas opencv-python

Usage:
  python review_anomalies.py \
    --original videos.csv \
    --anomalies video_anomalies.csv \
    --videos_dir /path/to/videos \
    --out updated_videos.csv \
    --log edits_log.jsonl \
    [--inplace]
"""

import argparse
import glob
import json
import os
import sys
import time
from datetime import datetime
from typing import List, Optional, Dict, Any

import pandas as pd

# --- Try OpenCV for inline playback; if not present, we fallback to printing paths ---
try:
    import cv2
    HAS_CV2 = True
except Exception:
    HAS_CV2 = False

# ---- Import your constants / enums / model ----
# Create constants.py with the exact content you shared.
try:
    from constants import (
        camera_angles,
        overall_type,
        text_type,
        transitions,
        category,
        playback_speed,
        broll_type,
        animated_graphics_type,
        VideoEditAnalysis,
    )
except Exception as e:
    print("ERROR: Could not import from constants.py. Make sure it’s next to this script.")
    print(e)
    sys.exit(1)

# -----------------------------------------
# Config / helpers
# -----------------------------------------

POSSIBLE_ID_COLS = ["video_id", "id", "videoId", "videoID", "video_key", "videoKey"]
VIDEO_EXTS = ["*.mp4", "*.mov", "*.mkv", "*.avi", "*.webm", "*.m4v"]

# Map boolean → dependent fields to auto-clear if set False
DEPENDENTS: Dict[str, List[str]] = {
    "shot_or_scene_changes_present": ["shot_or_scene_change_count", "average_interval_shot_or_scene_changes_seconds"],
    "b_roll_footage_present": ["b_roll_visuals", "b_roll_count"],
    "animated_graphics_present": ["types_of_animated_graphics", "animated_graphics_count"],
    "on_screen_text_present": ["type_of_on_screen_text"],
    "transitions_present": ["types_of_transitions", "transitions_count"],
    "voiceover_present": ["voiceover_type"],
    "background_music_present": [],  # no dependents
    "sound_effects_present": ["sound_effects_type", "sound_effects_count"],
}

# Fields that are lists of enums/strings
LIST_ENUM_FIELDS = {
    "b_roll_visuals": broll_type,
    "types_of_animated_graphics": animated_graphics_type,
    "type_of_on_screen_text": text_type,
    "types_of_transitions": transitions,
}

# Boolean fields
BOOL_FIELDS = [
    "shot_or_scene_changes_present",
    "b_roll_footage_present",
    "animated_graphics_present",
    "on_screen_text_present",
    "transitions_present",
    "voiceover_present",
    "background_music_present",
    "sound_effects_present",
]

# Numeric fields
INT_FIELDS = [
    "shot_or_scene_change_count",
    "b_roll_count",
    "animated_graphics_count",
    "transitions_count",
    "sound_effects_count",
]
FLOAT_FIELDS = [
    "average_interval_shot_or_scene_changes_seconds",
]

# String fields (plain)
STRING_FIELDS = [
    "sound_effects_type",
]

# ---- Skip re-prompting these in the generic loops (already handled above) ----
DEPENDENT_INT_FIELDS = {
    "shot_or_scene_change_count",
    "b_roll_count",
    "animated_graphics_count",
    "transitions_count",
    "sound_effects_count",
}
DEPENDENT_STRING_FIELDS = {
    "sound_effects_type",
}

def to_csv_list(val) -> str:
    """
    Serialize list-like values to 'A, B, C' (no brackets).
    - If empty or null -> '' (blank cell)
    - Accepts actual lists, JSON-ish strings, or existing comma-separated strings.
    """
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return ""
    if isinstance(val, list):
        items = [str(x).strip() for x in val if str(x).strip()]
        return ", ".join(items) if items else ""

    s = str(val).strip()
    if not s or s == "[]":
        return ""
    # If it looks like JSON list, parse then join
    if s.startswith("[") and s.endswith("]"):
        try:
            arr = json.loads(s)
            if isinstance(arr, list):
                items = [str(x).strip() for x in arr if str(x).strip()]
                return ", ".join(items) if items else ""
        except Exception:
            pass
    # Already plain text; keep it
    return s


def detect_id_col(df: pd.DataFrame) -> Optional[str]:
    for c in POSSIBLE_ID_COLS:
        if c in df.columns:
            return c
    return None

def coerce_bool(x):
    if isinstance(x, bool):
        return x
    s = str(x).strip().lower()
    return s in {"true", "1", "yes", "y", "t"}

def safe_parse_list(s) -> List[str]:
    """Accepts JSON-like lists or comma-separated strings; returns list of strings (stripped)."""
    if isinstance(s, list):
        return [str(x).strip() for x in s if str(x).strip()]
    if pd.isna(s):
        return []
    text = str(s).strip()
    if not text:
        return []
    # Try JSON-ish
    if text.startswith("[") and text.endswith("]"):
        try:
            arr = json.loads(text)
            if isinstance(arr, list):
                return [str(x).strip() for x in arr if str(x).strip()]
        except Exception:
            pass
    # Fallback: comma-separated
    return [t.strip() for t in text.split(",") if t.strip()]

def find_video(video_id: str, videos_dir: str) -> Optional[str]:
    # Try exact filename with any extension
    for pattern in VIDEO_EXTS:
        hits = glob.glob(os.path.join(videos_dir, f"{video_id}{pattern[1:]}"))
        if hits:
            return hits[0]
    # Try glob *video_id*.* to be lenient
    for pattern in VIDEO_EXTS:
        hits = glob.glob(os.path.join(videos_dir, f"*{video_id}*{pattern[1:]}"))
        if hits:
            return hits[0]
    return None

import subprocess
import platform
import tempfile

def play_video(video_path: str) -> str:
    """
    Launches the video in an external player instead of using OpenCV.
    Returns: 'skip' | 'quit' | 'edit'
    """
    print(f"\nOpening video externally: {video_path}")

    try:
        if platform.system() == "Darwin":  # macOS
            subprocess.Popen(["open", video_path])
    except Exception as e:
        print("Error opening video:", e)

    print("While the video is open, you can watch and scrub freely.")
    resp = input("Press 'c' to skip this row, 'q' to quit, or Enter to proceed to editing prompts: ").strip().lower()
    if resp == 'c':
        return 'skip'
    if resp == 'q':
        return 'quit'
    return 'edit'

def prompt_bool(label: str, current) -> Optional[bool]:
    s = input(f"{label} [current={current}] (y/n, Enter=keep): ").strip().lower()
    if s == "":
        return None
    if s in {"y", "yes"}:
        return True
    if s in {"n", "no"}:
        return False
    print("  (not understood, keeping current)")
    return None

def prompt_int(label: str, current) -> Optional[int]:
    s = input(f"{label} [current={current}] (int, Enter=keep): ").strip()
    if s == "":
        return None
    try:
        return int(s)
    except Exception:
        print("  (invalid int, keeping current)")
        return None

def prompt_float(label: str, current) -> Optional[float]:
    s = input(f"{label} [current={current}] (float, Enter=keep): ").strip()
    if s == "":
        return None
    try:
        return float(s)
    except Exception:
        print("  (invalid float, keeping current)")
        return None

def prompt_str(label: str, current) -> Optional[str]:
    s = input(f"{label} [current={current}] (Enter=keep): ").strip()
    if s == "":
        return None
    return s

def enum_name_list(E) -> str:
    names = [e.name for e in E]
    return ", ".join(names)

def prompt_enum(label: str, E, current) -> Optional[str]:
    s = input(f"{label} [current={current}] (choose by NAME; {enum_name_list(E)}; Enter=keep): ").strip()
    if s == "":
        return None
    try:
        _ = E[s]  # validate
        return s
    except Exception:
        print("  (invalid name, keeping current)")
        return None

def prompt_enum_list(label: str, E, current_list: List[str]) -> Optional[List[str]]:
    s = input(f"{label} [current={current_list}] (comma-separated NAMES; {enum_name_list(E)}; Enter=keep): ").strip()
    if s == "":
        return None
    parts = [p.strip() for p in s.split(",") if p.strip()]
    valid = []
    for p in parts:
        if p in E.__members__:
            valid.append(p)
        else:
            print(f"  (ignored invalid: {p})")
    return valid

def apply_auto_clear(row: dict, field: str, value: bool) -> None:
    """If boolean set to False, auto-clear its dependent fields."""
    if not value and field in DEPENDENTS:
        for dep in DEPENDENTS[field]:
            if dep in INT_FIELDS:
                row[dep] = 0
            elif dep in FLOAT_FIELDS:
                row[dep] = 0.0
            elif dep in LIST_ENUM_FIELDS:
                row[dep] = []
            else:
                row[dep] = ""

def row_to_display_dict(row: pd.Series) -> Dict[str, Any]:
    # Convert lists from strings, leave primitives as-is
    d = dict(row)
    for lf in LIST_ENUM_FIELDS.keys():
        d[lf] = safe_parse_list(d.get(lf, []))
    return d

def validate_optional(row: dict) -> Optional[str]:
    """
    Optional: Try to validate with Pydantic model (best-effort casting).
    Returns None if ok, else an error string. We won’t block on errors—just report.
    """
    try:
        payload = dict(row)
        # Cast enums by VALUE (not name)
        for k, E in LIST_ENUM_FIELDS.items():
            vals = payload.get(k, [])
            if isinstance(vals, list):
                new_vals = []
                for v in vals:
                    if v in E.__members__:
                        new_vals.append(E[v].value)
                    else:
                        new_vals.append(str(v))
                payload[k] = new_vals

        VideoEditAnalysis(**payload)  # may raise
        return None
    except Exception as e:
        return str(e)

def atomic_write_csv(df: pd.DataFrame, out_path: str) -> None:
    """Write CSV atomically to reduce risk of corruption on crash."""
    dir_ = os.path.dirname(os.path.abspath(out_path)) or "."
    base = os.path.basename(out_path)
    tmp_path = os.path.join(dir_, f".{base}.tmp")
    df.to_csv(tmp_path, index=False)
    os.replace(tmp_path, out_path)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--original", required=True, help="Path to original CSV")
    ap.add_argument("--anomalies", required=True, help="Path to anomaly CSV")
    ap.add_argument("--videos_dir", required=True, help="Folder containing videos")
    ap.add_argument("--out", default="updated_videos.csv", help="Output CSV path (ignored if --inplace)")
    ap.add_argument("--log", default="edits_log.jsonl", help="Change log JSONL path")
    ap.add_argument("--inplace", action="store_true", help="Write updates back into --original")
    args = ap.parse_args()

    # Decide output path
    out_path = args.original if args.inplace else args.out

    df = pd.read_csv(args.original)
    adf = pd.read_csv(args.anomalies)

    vid_col_main = detect_id_col(df)
    vid_col_anom = detect_id_col(adf)
    if not vid_col_main or not vid_col_anom:
        print("ERROR: Could not detect a video id column in one of the CSVs.")
        print("Looked for:", POSSIBLE_ID_COLS)
        sys.exit(1)

    # Ensure missing columns exist with sane defaults (to avoid KeyErrors)
    for col in set(BOOL_FIELDS + INT_FIELDS + FLOAT_FIELDS
                   + list(LIST_ENUM_FIELDS.keys()) + STRING_FIELDS):
        if col not in df.columns:
            if col in BOOL_FIELDS:
                df[col] = False
            elif col in INT_FIELDS:
                df[col] = 0
            elif col in FLOAT_FIELDS:
                df[col] = 0.0
            elif col in LIST_ENUM_FIELDS:
                df[col] = [[] for _ in range(len(df))]
            else:
                df[col] = ""

    print(f"Loaded {len(adf)} anomalies. Starting review...")
    changes = []

    for i, anom in adf.iterrows():
        vid = str(anom[vid_col_anom]).strip()
        if not vid:
            continue

        matches = df[df[vid_col_main].astype(str).str.strip() == vid]
        if matches.empty:
            print(f"\n[{i+1}/{len(adf)}] Video ID in anomalies not found in original: {vid}")
            continue

        idx = matches.index[0]
        current = row_to_display_dict(matches.iloc[0])

        print("\n" + "="*80)
        print(f"[{i + 1}/{len(adf)}] Reviewing Video ID: {vid}")

        # Harden anomalies_joined read
        anomaly_reason = str(anom.get("anomalies_joined", "") or "").strip()
        if anomaly_reason:
            print(f"[Anomaly] {anomaly_reason}")

        video_path = find_video(vid, args.videos_dir)
        if video_path:
            print(f"Opening video: {video_path}")
            action = play_video(video_path)
            if action == 'skip':
                print("Skipped row.")
                continue
            if action == 'quit':
                print("Quitting review.")
                break
        else:
            print("(No video file found for this ID.)")

        # Interactive editing prompts
        print("\n--- Edit values (Enter = keep current) ---")

        updated = dict(current)  # start from current
        row_changes = {}

        # 1) Booleans first, because they affect dependents
        for bf in BOOL_FIELDS:
            newb = prompt_bool(bf, updated.get(bf))
            if newb is not None and newb != updated.get(bf):
                row_changes[bf] = {"old": updated.get(bf), "new": newb}
                updated[bf] = newb
                apply_auto_clear(updated, bf, newb)

        # 2) Dependent numeric/string prompts (only if their parent is True)
        # Shot/scene changes
        if updated.get("shot_or_scene_changes_present"):
            val = prompt_int("shot_or_scene_change_count", updated.get("shot_or_scene_change_count"))
            if val is not None:
                row_changes["shot_or_scene_change_count"] = {"old": updated.get("shot_or_scene_change_count"), "new": val}
                updated["shot_or_scene_change_count"] = val

            val = prompt_float("average_interval_shot_or_scene_changes_seconds",
                               updated.get("average_interval_shot_or_scene_changes_seconds"))
            if val is not None:
                row_changes["average_interval_shot_or_scene_changes_seconds"] = {
                    "old": updated.get("average_interval_shot_or_scene_changes_seconds"), "new": val
                }
                updated["average_interval_shot_or_scene_changes_seconds"] = val

        # B-roll
        if updated.get("b_roll_footage_present"):
            val = prompt_int("b_roll_count", updated.get("b_roll_count"))
            if val is not None:
                row_changes["b_roll_count"] = {"old": updated.get("b_roll_count"), "new": val}
                updated["b_roll_count"] = val
            val = prompt_enum_list("b_roll_visuals", broll_type, updated.get("b_roll_visuals", []))
            if val is not None:
                row_changes["b_roll_visuals"] = {"old": updated.get("b_roll_visuals"), "new": val}
                updated["b_roll_visuals"] = val

        # Animated graphics
        if updated.get("animated_graphics_present"):
            val = prompt_int("animated_graphics_count", updated.get("animated_graphics_count"))
            if val is not None:
                row_changes["animated_graphics_count"] = {"old": updated.get("animated_graphics_count"), "new": val}
                updated["animated_graphics_count"] = val
            val = prompt_enum_list("types_of_animated_graphics", animated_graphics_type,
                                   updated.get("types_of_animated_graphics", []))
            if val is not None:
                row_changes["types_of_animated_graphics"] = {
                    "old": updated.get("types_of_animated_graphics"), "new": val
                }
                updated["types_of_animated_graphics"] = val

        # On-screen text
        if updated.get("on_screen_text_present"):
            val = prompt_enum_list("type_of_on_screen_text", text_type, updated.get("type_of_on_screen_text", []))
            if val is not None:
                row_changes["type_of_on_screen_text"] = {"old": updated.get("type_of_on_screen_text"), "new": val}
                updated["type_of_on_screen_text"] = val

        # Transitions
        if updated.get("transitions_present"):
            val = prompt_int("transitions_count", updated.get("transitions_count"))
            if val is not None:
                row_changes["transitions_count"] = {"old": updated.get("transitions_count"), "new": val}
                updated["transitions_count"] = val
            val = prompt_enum_list("types_of_transitions", transitions, updated.get("types_of_transitions", []))
            if val is not None:
                row_changes["types_of_transitions"] = {"old": updated.get("types_of_transitions"), "new": val}
                updated["types_of_transitions"] = val

        # Sound effects
        if updated.get("sound_effects_present"):
            val = prompt_int("sound_effects_count", updated.get("sound_effects_count"))
            if val is not None:
                row_changes["sound_effects_count"] = {"old": updated.get("sound_effects_count"), "new": val}
                updated["sound_effects_count"] = val
            val = prompt_str("sound_effects_type", updated.get("sound_effects_type", ""))
            if val is not None:
                row_changes["sound_effects_type"] = {"old": updated.get("sound_effects_type"), "new": val}
                updated["sound_effects_type"] = val

        # Strings (generic) — skip ones already handled above
        for f in STRING_FIELDS:
            if f in DEPENDENT_STRING_FIELDS:
                continue
            cur = updated.get(f, "")
            newv = prompt_str(f, cur)
            if newv is not None:
                row_changes[f] = {"old": cur, "new": newv}
                updated[f] = newv

        # Numeric (generic) — skip ones already handled above
        for f in INT_FIELDS:
            if f in DEPENDENT_INT_FIELDS:
                continue
            cur = updated.get(f, 0)
            newv = prompt_int(f, cur)
            if newv is not None:
                row_changes[f] = {"old": cur, "new": newv}
                updated[f] = newv

        for f in FLOAT_FIELDS:
            cur = updated.get(f, 0.0)
            newv = prompt_float(f, cur)
            if newv is not None:
                row_changes[f] = {"old": cur, "new": newv}
                updated[f] = newv

        # Optional validation (won’t block saving)
        err = validate_optional(updated)
        if err:
            print(f"[Validation warning] {err}")

        # Persist updates back to DataFrame
        # Convert list fields to JSON strings for the CSV
        # Convert list fields to CSV-friendly comma-separated strings
        for lf in LIST_ENUM_FIELDS.keys():
            updated[lf] = to_csv_list(updated.get(lf, ""))

        for k, v in updated.items():
            if k in df.columns:
                df.at[idx, k] = v

        if row_changes:
            changes.append({"video_id": vid, "changes": row_changes})
        print("Row updated.")

        # ---- Save after each row (atomic), to chosen output path ----
        atomic_write_csv(df, out_path)
        print(f"Saved CSV → {out_path}\n")

    # Append change log at the end
    if changes:
        with open(args.log, "a", encoding="utf-8") as f:
            for c in changes:
                f.write(json.dumps(c) + "\n")
        print(f"Appended change log → {args.log}")
    else:
        print("No edits were made; no change log entries created.")

if __name__ == "__main__":
    main()
