# This file just includes downloads the videos from the txt file filters only english videos based on descriptions and length and saves them to raw csv

import os
import shutil
import pandas as pd
import pyktok as pyk
from langdetect import detect
from dotenv import load_dotenv
load_dotenv()

# --------------------------
# CONFIG
# --------------------------

MAX_DURATION = 120
MINIMUM_VIEWS = 100000 #The video should have atleast 100,000 to consider viral
LANGUAGE = "en"

GENRE = os.environ.get("VIDEO_CATEGORY").strip()
VIDEO_DATA_DIR = "video_data"
VIDEO_IDS_FILE = os.path.join(VIDEO_DATA_DIR, f"{GENRE}.txt")

RAW_CSV_DIR = "raw_csv"
FILTERED_DIR = "filtered"
KEEP_DIR = f"kept_{GENRE}_videos"

RAW_CSV_PATH = os.path.join(RAW_CSV_DIR, f"{GENRE}.csv")
FILTERED_CSV_PATH = os.path.join(FILTERED_DIR, f"{GENRE}_filtered.csv")

# Ensure dirs exist
os.makedirs(VIDEO_DATA_DIR, exist_ok=True)
os.makedirs(RAW_CSV_DIR, exist_ok=True)
os.makedirs(FILTERED_DIR, exist_ok=True)
os.makedirs(KEEP_DIR, exist_ok=True)
# --------------------------
# Step 0: Load video IDs
# --------------------------
if not os.path.isfile(VIDEO_IDS_FILE):
    raise FileNotFoundError(f"Could not find IDs file at: {VIDEO_IDS_FILE}")

with open(VIDEO_IDS_FILE, "r", encoding="utf-8") as f:
    seen = set()
    video_ids = []
    for line in f:
        vid = line.strip()
        if vid and vid not in seen:
            seen.add(vid)
            video_ids.append(vid)

if not video_ids:
    raise ValueError(f"No video IDs found in {VIDEO_IDS_FILE}")

# --------------------------
# Step 1: Download videos & metadata (one by one with try/except)
# --------------------------
successful_ids = []
for vid in video_ids:
    url = f"https://www.tiktok.com/@tiktok/video/{vid}"
    try:
        pyk.save_tiktok_multi_urls(
            [url],
            True,   # download videos too
            RAW_CSV_PATH,
            1
        )
        successful_ids.append(vid)
        print(f"Downloaded {vid}")
    except Exception as e:
        print(f"❌ Failed to download {vid}: {e}")

print(f"Processed {len(successful_ids)} successful downloads. Data saved to {RAW_CSV_PATH}.")

# --------------------------
# Step 2: Filter CSV & keep videos
# --------------------------
if not os.path.exists(RAW_CSV_PATH):
    print("No CSV generated. Exiting.")
    raise SystemExit(0)

df = pd.read_csv(RAW_CSV_PATH)

def is_english(text):
    try:
        return detect(str(text)) == LANGUAGE
    except Exception:
        return False

df_filtered = df[
    df["video_description"].apply(is_english)
    & (df["video_duration"] <= MAX_DURATION)
    & (df["video_playcount"] >= MINIMUM_VIEWS)
]
if df_filtered.empty:
    print("No matching videos found after filter.")
    raise SystemExit(0)

df_filtered.to_csv(FILTERED_CSV_PATH, index=False)
os.makedirs(KEEP_DIR, exist_ok=True)

video_ids_to_keep = set(str(vid) for vid in df_filtered["video_id"].astype(str))
kept_count = 0
deleted_count = 0

for fname in os.listdir("."):
    if fname.endswith(".mp4"):
        vid = fname.split("_")[-1].replace(".mp4", "")
        if vid in video_ids_to_keep:
            shutil.move(fname, os.path.join(KEEP_DIR, fname))
            kept_count += 1
        else:
            os.remove(fname)
            deleted_count += 1

print(f"Moved {kept_count} videos to '{KEEP_DIR}', deleted {deleted_count} others.")
print(f"Filtered metadata saved to {FILTERED_CSV_PATH}.")
