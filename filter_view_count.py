#!/usr/bin/env python3
import os
import re
import pandas as pd
from dotenv import load_dotenv

load_dotenv()

# --------------------------
# CONFIG
# --------------------------
GENRE = os.environ.get("VIDEO_CATEGORY", "").strip()
if not GENRE:
    raise ValueError("Missing VIDEO_CATEGORY in .env")

# you only need to run this for videos that were not filtered using the updated download videos
FILTERED_DIR = "filtered"
KEEP_DIR = f"kept_{GENRE}_videos"
FILTERED_CSV_PATH = os.path.join(FILTERED_DIR, f"{GENRE}_filtered.csv")

MINIMUM_VIEWS = 100000

os.makedirs(FILTERED_DIR, exist_ok=True)
os.makedirs(KEEP_DIR, exist_ok=True)

# --------------------------
# Helpers
# --------------------------
ID_COL, VIEWS_COL = "video_id", "video_playcount"

def extract_video_id(fname: str) -> str | None:
    """
    Infer the TikTok video ID from filenames like:
      anything_<id>.mp4, anything-<id>.mp4, or <id>.mp4
    """
    if not fname.lower().endswith(".mp4"):
        return None
    base = os.path.basename(fname)
    for sep in ("_", "-"):
        if sep in base:
            cand = base.rsplit(sep, 1)[-1].removesuffix(".mp4")
            if cand.isdigit():
                return cand
    m = re.search(r"(\d+)(?=\.mp4$)", base)
    return m.group(1) if m else None

# --------------------------
# Prune by view count
# --------------------------
if not os.path.isfile(FILTERED_CSV_PATH):
    raise FileNotFoundError(f"Filtered CSV not found: {FILTERED_CSV_PATH}")

df = pd.read_csv(FILTERED_CSV_PATH)
if ID_COL not in df.columns or VIEWS_COL not in df.columns:
    raise ValueError(f"CSV must contain '{ID_COL}' and '{VIEWS_COL}'")

# Normalize
df[ID_COL] = df[ID_COL].astype(str)
df[VIEWS_COL] = pd.to_numeric(df[VIEWS_COL], errors="coerce")

# Determine which to drop
low_mask = df[VIEWS_COL] < MINIMUM_VIEWS
low_ids = set(df.loc[low_mask, ID_COL].astype(str))

print(f"[{GENRE}] Loaded {len(df)} rows from {FILTERED_CSV_PATH}")
print(f"Minimum views: {MINIMUM_VIEWS:,}")
print(f"Below-threshold rows: {low_mask.sum()}")

# Delete files from kept_{GENRE}_videos
deleted = 0
for entry in os.listdir(KEEP_DIR):
    if not entry.lower().endswith(".mp4"):
        continue
    vid = extract_video_id(entry)
    if vid and vid in low_ids:
        try:
            os.remove(os.path.join(KEEP_DIR, entry))
            deleted += 1
        except Exception as e:
            print(f"Could not delete {entry}: {e}")

print(f"Deleted {deleted} video file(s) from {KEEP_DIR}")

# Overwrite filtered CSV with kept rows
kept_df = df.loc[~low_mask].copy()
kept_df.to_csv(FILTERED_CSV_PATH, index=False)
print(f"Wrote pruned CSV with {len(kept_df)} rows to {FILTERED_CSV_PATH}")
