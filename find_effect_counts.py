#!/usr/bin/env python3
import os
import sys
import shutil
from datetime import datetime
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv

load_dotenv()

# -------- Config & paths --------
GENRE = os.getenv("VIDEO_CATEGORY")
if not GENRE:
    print("ERROR: VIDEO_CATEGORY is not set (in env or .env).")
    sys.exit(1)
GENRE = GENRE.strip()

CSV_PATH = Path("filtered") / f"{GENRE}_filtered.csv"
VIDEO_DIR = Path(f"kept_{GENRE}_videos")  # <-- no stray space!
BACKUP_DIR = Path("backups") / GENRE
BACKUP_DIR.mkdir(parents=True, exist_ok=True)

EFFECT_COLS = [
    "transitions_present",
    "b_roll_footage_present",
    "animated_graphics_present",
    "on_screen_text_present",
]

VIDEO_EXTS = {".mp4", ".mov", ".m4v", ".avi", ".mkv", ".webm"}

def to_bool(x):
    if isinstance(x, bool):
        return x
    if pd.isna(x):
        return False
    return str(x).strip().lower() in {"true", "1", "yes", "y", "t"}

def main():
    if not CSV_PATH.exists():
        print(f"ERROR: CSV not found at {CSV_PATH.resolve()}")
        sys.exit(1)

    # ---- 1) Backup CSV to backups/<GENRE>/ ----
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup_path = BACKUP_DIR / f"{CSV_PATH.stem}.backup-{ts}{CSV_PATH.suffix}"
    shutil.copyfile(CSV_PATH, backup_path)
    print(f"Backed up CSV -> {backup_path}")

    # ---- 2) Load & filter rows ----
    df = pd.read_csv(CSV_PATH)

    # Ensure effect columns exist; default to False if missing
    for col in EFFECT_COLS:
        if col not in df.columns:
            df[col] = False

    if "video_id" not in df.columns:
        print("ERROR: 'video_id' column is required in the CSV.")
        sys.exit(1)

    # Normalize boolean-ish columns
    for col in EFFECT_COLS:
        df[col] = df[col].apply(to_bool)

    # Keep rows where at least one effect is present
    mask_any_effect = df[EFFECT_COLS].any(axis=1)
    kept_df = df[mask_any_effect].copy()
    removed_df = df[~mask_any_effect].copy()

    kept_ids = set(kept_df["video_id"].astype(str))
    removed_ids = set(removed_df["video_id"].astype(str))

    # Write filtered CSV in place
    kept_df.to_csv(CSV_PATH, index=False)
    print(f"Filtered CSV saved: kept {len(kept_df)} rows, removed {len(removed_df)} rows.")

    # ---- 3) Delete unmatched video files from folder ----
    if not VIDEO_DIR.exists():
        print(f"NOTE: Video directory not found at {VIDEO_DIR.resolve()} — skipping file deletions.")
        return

    deleted_files = 0
    kept_files = 0

    for p in VIDEO_DIR.rglob("*"):
        if p.is_file() and p.suffix.lower() in VIDEO_EXTS:
            name_no_ext = p.stem
            # delete if filename contains any removed video_id
            if any(vid and vid in name_no_ext for vid in removed_ids):
                try:
                    p.unlink()
                    deleted_files += 1
                except Exception as e:
                    print(f"Could not delete {p}: {e}")
            else:
                kept_files += 1

    print(f"Video cleanup complete: deleted {deleted_files} files, kept {kept_files} files.")
    print("Done.")

if __name__ == "__main__":
    main()
