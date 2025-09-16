import os
import time
import pyktok as pyk
import pandas as pd
from google import genai
from langdetect import detect
import json
import shutil
from constants import VideoEditAnalysis

client = genai.Client(api_key="AIzaSyCdjgIZZfUelDEukQELEFIk59FTMznfEgM")


def gemini_analysis(video_path, max_attempts=3, initial_delay=5):
    """
    Calls Gemini with simple retries. Retries the whole flow (upload + generate)
    up to `max_attempts` times if an exception occurs, with exponential backoff.
    Returns the response text on success, or None if all attempts fail.
    """
    attempt = 1
    delay = initial_delay

    while attempt <= max_attempts:
        try:
            video_file_name = video_path

            myfile = client.files.upload(file=video_file_name)

            # Wait for processing
            while True:
                current_file = client.files.get(name=myfile.name)
                if current_file.state != "PROCESSING":
                    break
                print("Waiting for video to be processed...")
                time.sleep(5)

            print("Video processed, sending to Gemini...")

            response = client.models.generate_content(
                model="gemini-2.5-flash",
                contents=[
                    myfile,
                    (
                        "You are a professional video analyzer for blind and low vision users. Carefully analyze the uploaded video and provide a detailed breakdown of all video editing effects and techniques used. "
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
                        "Return your response in JSON format"
                    ),
                ],
                config={
                    "response_mime_type": "application/json",
                    "response_schema": VideoEditAnalysis,
                },
            )

            print("===============================================")
            print(response.text)
            print("===============================================")
            return response.text

        except Exception as e:
            if attempt < max_attempts:
                print(f"[Gemini error] Attempt {attempt}/{max_attempts} failed: {e}")
                print(f"Retrying in {delay} seconds...")
                time.sleep(delay)
                delay = min(delay * 2, 60)  # cap backoff
                attempt += 1
            else:
                print(f"[Gemini error] All {max_attempts} attempts failed: {e}")
                return None


def analyze_and_save(output_dir, result_csv):
    print("Analyzing videos with Gemini...")

    # Load existing CSV
    df = pd.read_csv(result_csv)
    df["video_id"] = df["video_id"].astype(str)
    
    # All mp4s present
    files = [f for f in os.listdir(output_dir) if f.endswith(".mp4")]

    # Helper to extract ID from filename
    vid_from = lambda f: f.split("_")[-1].replace(".mp4", "")

    # Which ones still need analysis (present in CSV + missing/empty video_summary)
    to_analyze = []
    for f in files:
        vid = vid_from(f)
        if vid in set(df["video_id"]):
            if "video_summary" not in df.columns:
                to_analyze.append(vid)
            else:
                val = df.loc[df["video_id"] == vid, "video_summary"].values[0] \
                    if (df["video_id"] == vid).any() else None
                if (val is None) or (pd.isna(val)) or (str(val).strip() == ""):
                    to_analyze.append(vid)

    total_to_analyze = len(to_analyze)
    print(f"To analyze now: {total_to_analyze} video(s) "
        f"| mp4s in folder: {len(files)} | CSV rows: {len(df)}")

    done = 0  # progress counter

    for filename in files:
        if not filename.endswith(".mp4"):
            continue

        # Extract video ID from filename
        video_id = filename.split("_")[-1].replace(".mp4", "")
        
        if video_id not in to_analyze:
            continue
        
        done += 1

        # Skip if already analyzed
        # if "video_summary" in df.columns and \
        #    video_id in df["video_id"].astype(str).values and \
        #    not pd.isna(df.loc[df["video_id"].astype(str) == video_id, "video_summary"].values[0]):
        #     print(f"Skipping {video_id}: already analyzed.")
        #     continue
        
        print(f"[{done}/{total_to_analyze}] Analyzing {video_id}...")
        # print(f"Analyzing {video_id}...")

        # Run Gemini analysis (returns raw JSON string)
        file_path = os.path.join(output_dir, filename)
        raw_json = gemini_analysis(file_path)

        try:
            gemini_data = json.loads(raw_json)
        except Exception as e:
            print(f"Failed to parse Gemini output for {video_id}: {e}")
            continue

        # Convert lists to strings for CSV
        for key, value in gemini_data.items():
            if isinstance(value, list):
                gemini_data[key] = ", ".join(map(str, value))

        # Update matching row
        if video_id in df["video_id"].astype(str).values:
            for key, value in gemini_data.items():
                df.loc[df["video_id"].astype(str) == video_id, key] = value
            print(f"Updated analysis for video ID: {video_id}")

            # SAVE after each update
            df.to_csv(result_csv, index=False)
            print(f"Saved CSV after updating {video_id}")
        else:
            print(f"Video ID {video_id} not found in CSV. Skipping.")

        time.sleep(1)  # Optional delay for rate limits

    print(f"Final CSV saved to {result_csv}")


# Main
if __name__ == "__main__":
    type_of_videos = "outfit" # <--------  Change based on the genre you are analysing
    folder = "kept_" + type_of_videos + "_videos"
    filtered_csv_name = type_of_videos +  "_filtered.csv"

    analyze_and_save(folder, filtered_csv_name)
