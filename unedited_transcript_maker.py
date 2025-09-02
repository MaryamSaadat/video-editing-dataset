import os
import time
import json
import pandas as pd
from pathlib import Path
from typing import List
from pydantic import BaseModel
from dotenv import load_dotenv
from google import genai

# --------------------------
# Env + config
# --------------------------
load_dotenv()

GENRE = os.getenv("VIDEO_CATEGORY", "drama").strip()
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
if not GEMINI_API_KEY:
    raise RuntimeError("GEMINI_API_KEY not set. Add it to your .env or export it in your shell.")

FILTERED_CSV = Path("filtered") / f"{GENRE}_filtered.csv"
KEEP_DIR = Path(f"kept_{GENRE}_videos")

# Gemini client
client = genai.Client(api_key=GEMINI_API_KEY)

# --------------------------
# Gemini analysis
# --------------------------
def gemini_analysis(video_path):
    myfile = client.files.upload(file=video_path)

    # Wait for processing
    while True:
        current_file = client.files.get(name=myfile.name)
        if current_file.state != "PROCESSING":
            break
        print("Waiting for video to be processed...")
        time.sleep(5)

    print("Video processed, sending to Gemini...")

    prompt = (
        "You are a professional video analyser for blind and low vision editors."
        "Your task is to create an audio video script that provides the following:"
        "Different segments, each segments is a distinct shot or scene change. Small changes in motions or actions should not categorise as different segments."
        "If there are no shot or scene changes, or if the time interval between shot or scene is large, you can also create segments based on the transcript if available."
        "The segments should not be too long or too short."
        "For each segment, provide the start timestamp."
        "For each segment, provide a visual description that allows a blind person with enough information to gauge what is going on in this segment. Ensure that the visual description is not too verbose to prevent information overload."
        "Do not include information about video editing effects such as text overlays or on screen text, animated graphics, b-rolls, sounds effects, background music in the generated visual description or transcript."
        "If the segment contains transcript, provide the transcript of that segment, do not provide transcript from music. The transcript should only include spoken audio in the video."
    )

    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=[myfile, prompt],
        config={
            "response_mime_type": "application/json",
            "response_schema": VideoAnalysis,
        },
    )
    print(response.text)
    return response.text


def analyze_and_save(output_dir, result_csv):
    print("Analyzing videos with Gemini...")
    df = pd.read_csv(result_csv)

    for filename in os.listdir(output_dir):
        if not filename.endswith(".mp4"):
            continue

        video_id = filename.split("_")[-1].replace(".mp4", "")

        # Skip if video ID not in CSV
        if video_id not in df["video_id"].astype(str).values:
            print(f"Skipping {video_id}: not in CSV.")
            continue

        # Skip if already analyzed
        if "segments" in df.columns and \
           video_id in df["video_id"].astype(str).values and \
           not pd.isna(df.loc[df["video_id"].astype(str) == video_id, "segments"].values[0]):
            print(f"Skipping {video_id}: already analyzed.")
            continue


        print(f"Analyzing {video_id}...")
        file_path = os.path.join(output_dir, filename)
        raw_json = gemini_analysis(file_path)

        try:
            gemini_data = json.loads(raw_json)
        except Exception as e:
            print(f"Failed to parse Gemini output for {video_id}: {e}")
            continue

        # Convert lists to strings
        for key, value in gemini_data.items():
            if isinstance(value, list):
                gemini_data[key] = ", ".join(map(str, value))

        # Update row in CSV
        if video_id in df["video_id"].astype(str).values:
            for key, value in gemini_data.items():
                df.loc[df["video_id"].astype(str) == video_id, key] = value
            print(f"Updated analysis for video ID: {video_id}")
            df.to_csv(result_csv, index=False)
            print(f"Saved CSV after updating {video_id}")
        else:
            print(f"Video ID {video_id} not found in CSV. Skipping.")

        time.sleep(10)  # optional delay

    print(f"Final CSV saved to {result_csv}")


# --------------------------
# Step 4: Run Gemini analysis on kept videos
# --------------------------
analyze_and_save(KEEP_DIR, FILTERED_CSV)
