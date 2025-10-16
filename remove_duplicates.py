import pandas as pd

# Load CSV
df = pd.read_csv("filtered/sports_filtered.csv")

# Drop duplicate video_id rows (keep first occurrence)
df_no_duplicates = df.drop_duplicates(subset='video_id', keep='first')

# Save to new file (or overwrite original if desired)
df_no_duplicates.to_csv("sports_filtered.csv", index=False)

print(f"Removed duplicates. Original rows: {len(df)}, After deduplication: {len(df_no_duplicates)}")
