import pandas as pd
import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

GENRE = os.getenv("VIDEO_CATEGORY").strip()
INPUT_CSV = Path("filtered") / f"{GENRE}_filtered.csv"
OUTPUT_CSV = Path("filtered")  / f"{GENRE}_filtered.csv"
# Load CSV
df = pd.read_csv(INPUT_CSV)


# Drop duplicate video_id rows (keep first occurrence)
df_no_duplicates = df.drop_duplicates(subset='video_id', keep='first')


df_no_duplicates.to_csv(OUTPUT_CSV, index=False)

print(f"Removed duplicates. Original rows: {len(df)}, After deduplication: {len(df_no_duplicates)}")
