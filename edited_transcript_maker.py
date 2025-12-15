import os
import time
import json
import pandas as pd
from pathlib import Path
from dotenv import load_dotenv
from typing import Optional
from google import genai

# from backups.editsvals.constants import transitions

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
NEW_JSON_COL = "edited_script"  # new column to store Gemini JSON

# Gemini client
client = genai.Client(api_key=GEMINI_API_KEY)

# --------------------------
# Env + config
# --------------------------


def extract_video_id(filename: str) -> str:
    return filename.split("_")[-1].replace(".mp4", "")

def get_segment_for_video(df: pd.DataFrame, video_id: str) -> Optional[str]:
    mask = df["video_id"].astype(str) == str(video_id)
    if mask.any():
        seg = df.loc[mask, "segments"].values[0]
        return None if (pd.isna(seg) or seg is None) else str(seg)
    return None

def build_effect_instruction(row: dict) -> str:
    effects = []

    b_roll_count = int(row.get("b_roll_count", 0))
    if b_roll_count > 0:
        effects.append(f"- Insert exactly {b_roll_count} B-roll spans using [BROLL] to mark start and [/BROLL] to mark the end. You are not required to provide information about the type of B-roll between the spans.")

    animated_count = int(row.get("animated_graphics_count", 0))
    if animated_count > 0:
        effects.append(f"- Insert exactly {animated_count} animated graphics spans using [ANIMATED] to mark start and [/ANIMATED] to mark the end. You are not required to provide information about the type of animated graphic between the spans.")

    transition_count = int(row.get("transition_count", 0))
    if transition_count > 0:
        effects.append(f"- Insert exactly {transition_count } [TRANSITION] markers at start of the script where the transition is present.")

    sound_count = int(row.get("sound_effects_count", 0))
    if sound_count > 0:
        effects.append(f"- Insert exactly {sound_count} [SOUND_EFFECT] ... [/SOUND_EFFECT] spans for sound effects where they are present. You are not required to provide information about the type of sound effect between the spans.")

    if str(row.get("background_music_present", "")).strip().upper() == "TRUE":
        effects.append("- Background music is present. Insert [BACKGROUND_MUSIC] at the start of the first script.")

    tos_present = str(row.get("on_screen_text_present", "")).strip().upper() == "TRUE"
    tos_types = row.get("type_of_on_screen_text", [])
    if tos_present:
        if isinstance(tos_types, str):
            try:
                tos_types = json.loads(tos_types.replace("'", '"'))
            except:
                tos_types = [tos_types]
        effects.append("- Insert [TOS] to marks start and [/TOS] to mark end for meaningful on-screen text overlays (not account handles). You are not required to provide information about the content of the text on screen between the spans.")

    if not effects:
        return "There are no editing effects to place."

    return (
        "Please place the following editing effects:\n\n"
        + "\n".join(effects)
        + "\n\nOnly place the effects listed above. Do not add any other effects."
    )

def gemini_analysis(video_path: str, segment_text: Optional[str], row: dict) -> dict:
    myfile = client.files.upload(file=video_path)

    while True:
        current_file = client.files.get(name=myfile.name)
        if current_file.state != "PROCESSING":
            break
        print("Waiting for video to be processed...")
        time.sleep(5)

    print(f"[Gemini] Video processed → {os.path.basename(video_path)}; analyzing...")

    segment_block = segment_text or "(no segment text provided)"
    effect_instructions = build_effect_instruction(row)

    prompt = (
        "You are a professional video effect placer.\n"
        "You will be provided with a visual description and a script of a video.\n"
        "Your task is to place the video effects that exists in the video in appropriate places within the script.\n"
        "The script can either be the transcript or a dense caption containing actions and objects.\n"
        "Do not invent effects. Only place markers for effects that are explicitly listed.\n\n"
        f"{effect_instructions}\n\n"
        "Keep the original script and visual descriptions unmodified. Only insert markers as needed.\n"
        "Only insert the effects in the script, do not insert the markers in the visual description\n"
        "The effects should only be placed in one script and should not be inserted in multiple scripts.\n"
        ""
        f"[SEGMENT]\n{segment_block}\n[/SEGMENT]"
    )

    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=[myfile, prompt],
        config={"response_mime_type": "application/json"},
    )
    print("++++++++++++++++++++++++++++++++++++++++++++++++++++++++++")
    print(prompt)
    print("==========================================================")
    print(response.text)
    print("==========================================================")

    raw = response.text if hasattr(response, "text") else response
    if isinstance(raw, str):
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            print("[Gemini] Could not parse JSON; storing raw text.")
            return {"raw": raw}
    elif isinstance(raw, dict):
        return raw
    else:
        return {"raw": str(raw)}

def analyze_and_save_with_segments(keep_dir: str, csv_path: str) -> None:
    if not os.path.exists(csv_path):
        raise FileNotFoundError(f"CSV not found: {csv_path}")

    df = pd.read_csv(csv_path)

    if "video_id" not in df.columns:
        raise ValueError("CSV must contain a 'video_id' column.")
    if "segments" not in df.columns:
        raise ValueError("CSV must contain a 'segments' column.")
    if NEW_JSON_COL not in df.columns:
        df[NEW_JSON_COL] = pd.NA

    for idx, row in df.iterrows():
        video_id = str(row["video_id"]).strip()

        # Skip already processed rows
        if not pd.isna(row.get(NEW_JSON_COL, None)):
            print(f"Skipping video_id={video_id}: already analyzed.")
            continue

        # Find matching video file: "@tiktok_video_<id>.mp4"
        matched_file = None
        for fname in os.listdir(keep_dir):
            if fname.endswith(f"{video_id}.mp4"):
                matched_file = fname
                break

        if matched_file is None:
            print(f"⚠ No video found for video_id={video_id}. Skipping.")
            continue

        video_path = os.path.join(keep_dir, matched_file)
        segment_text = row["segments"]

        print(f"\n=== Processing video_id={video_id} -> {matched_file} ===")

        try:
            result_json = gemini_analysis(video_path, segment_text, row.to_dict())
        except Exception as e:
            print(f"[Gemini] Error analyzing video_id={video_id}: {e}")
            continue

        # Save result into CSV row
        df.at[idx, NEW_JSON_COL] = json.dumps(
            result_json, ensure_ascii=False, separators=(",", ":")
        )

        df.to_csv(csv_path, index=False)  # Save after each processed video
        time.sleep(1)

    print(f"\nDone. Updated CSV saved to {csv_path}")


if __name__ == "__main__":
    analyze_and_save_with_segments(KEEP_DIR, FILTERED_CSV)