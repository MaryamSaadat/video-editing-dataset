import os
import time
import json
import pandas as pd
from google import genai
from dotenv import load_dotenv
from constants import VideoEditAnalysis
import os

# --------------------------
# Setup
# --------------------------
load_dotenv()  # loads .env

GENRE = os.environ.get("VIDEO_CATEGORY").strip()
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
if not GEMINI_API_KEY:
    raise RuntimeError("GEMINI_API_KEY is not set in environment/.env")

FILTERED_CSV_PATH = os.path.join("filtered", f"{GENRE}_filtered.csv")
KEEP_DIR = f"kept_{GENRE}_videos"

client = genai.Client(api_key=GEMINI_API_KEY)


# --------------------------
# Gemini call
# --------------------------
def gemini_analysis(video_path: str) -> str:
    myfile = client.files.upload(file=video_path)

    # Wait for processing
    while True:
        current_file = client.files.get(name=myfile.name)
        if current_file.state != "PROCESSING":
            break
        print("Waiting for video to be processed...")
        time.sleep(5)

    print("Video processed, sending to Gemini...")

    prompt = ("You are a professional video analyzer for blind and low vision users. Carefully analyze the uploaded video and provide a detailed breakdown of all video editing effects and techniques used. "
              "Answer the following questions about the video:"
              "Provide a short summary of video content. Do not include any information about the video effects, the summary should only be focused on the content of the video"
              "What is the category of the video?"
              "What is the overall type of the video?"
              "Is the video shot from a single camera angle or multiple angles?"
              "Are there shot changes (hard cuts) or scene changes in the video? Small changes in motions or actions should not categorise as shot or scene changes."
              "What is the average interval in seconds between shot or scene changes?"
              "Provide count of shot and scene changes."
              "Does the video include B-roll footage?  The B-roll footage refers to stock footage or any image/video differing from the main A-roll."
              "If B-roll is present, is it a video or an image B-roll?"
              "Provide count of B-roll footage?"
              "Are there any animated graphics used? The animated graphics refers to any stickers, memes or GIFs in the video. Animated graphics does not include text overlays."
              "If so, what types of animated graphics are present?"
              "Provide count of animated graphics used?"
              "Does the video include on-screen text?"
              "What type of on-screen text appears?"
              "Are there transitions between clips?"
              "Provide count of the number of transitions."
              "If yes, what types of transitions are used?"
              "Does the video contain a voiceover or transcript?"
              "If yes, is the voiceover narrating or independent of the visuals?"
              "What is the playback speed of the video?"
              "Is there background music added as editing effect in the video"
              "Are there any sound effects added as editing effect in the video?"
              "If sounds effects are present what type of sound effects are they?"
              "Provide count of the number of sound effects present."
              "After completing your analysis, review the video again. Verify each answer against the video content. If any part of your analysis does not match the observed edits, update your responses. Repeat this process until all answers are accurate and fully aligned with the video."
              "Provide all timestamps as whole numbers in seconds, based on the actual video timeline, not on any on-screen timers or visual countdowns that may appear in the video."
              "Return your response in JSON format")

    response = client.models.generate_content(
        model="gemini-2.5-pro",
        contents=[myfile, prompt],
        config={
            "response_mime_type": "application/json",
            "response_schema": VideoEditAnalysis,
        },
    )
    print("===============================================")
    print(response.text)
    print("===============================================")
    return response.text


# --------------------------
# Main analysis loop
# --------------------------
def analyze_and_save(output_dir: str, result_csv: str) -> None:
    print("Analyzing videos with Gemini...")

    if not os.path.exists(result_csv):
        raise FileNotFoundError(f"Filtered CSV not found: {result_csv}")
    if not os.path.isdir(output_dir):
        raise FileNotFoundError(f"Kept videos folder not found: {output_dir}")

    df = pd.read_csv(result_csv)
    if "video_id" not in df.columns:
        raise ValueError("Filtered CSV must contain a 'video_id' column.")

    # Normalize for membership checks
    df["video_id"] = df["video_id"].astype(str)
    ids_in_csv = set(df["video_id"].values)

    for filename in os.listdir(output_dir):
        if not filename.lower().endswith(".mp4"):
            continue

        video_id = filename.split("_")[-1].replace(".mp4", "")
        file_path = os.path.join(output_dir, filename)

        # Skip if not in CSV
        if video_id not in ids_in_csv:
            print(f"Skipping {video_id}: not in CSV.")
            continue

        # Skip if already analyzed (non-empty video_summary)
        already_done = False
        if "video_summary" in df.columns:
            existing = df.loc[df["video_id"] == video_id, "video_summary"].values[0]
            if pd.notna(existing) and str(existing).strip() != "":
                already_done = True

        if already_done:
            print(f"Skipping {video_id}: already analyzed.")
            continue

        print(f"Analyzing {video_id}...")
        try:
            raw_json = gemini_analysis(file_path)
            gemini_data = json.loads(raw_json)
        except Exception as e:
            print(f"Failed to analyze or parse for {video_id}: {e}")
            continue

        # Convert lists to CSV-friendly strings (optional)
        for k, v in list(gemini_data.items()):
            if isinstance(v, list):
                gemini_data[k] = ", ".join(map(str, v))

        # Upsert columns and update row
        for k, v in gemini_data.items():
            if k not in df.columns:
                df[k] = pd.NA
            df.loc[df["video_id"] == video_id, k] = v

        print(f"Updated analysis for video ID: {video_id}")
        df.to_csv(result_csv, index=False)
        print(f"Saved CSV after updating {video_id}")

        time.sleep(10)  # Optional rate-limit cushion

    print(f"Final CSV saved to {result_csv}")


# --------------------------
# Entrypoint
# --------------------------
if __name__ == "__main__":
    analyze_and_save(KEEP_DIR, FILTERED_CSV_PATH)

