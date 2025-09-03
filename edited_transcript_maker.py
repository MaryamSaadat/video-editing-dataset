import os
import time
import json
from pathlib import Path
from typing import Optional

import pandas as pd
from dotenv import load_dotenv
from google import genai

# --------------------------
# ENV & CONFIG
# --------------------------
load_dotenv()

GENRE = os.getenv("VIDEO_CATEGORY", "education").strip()
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
if not GEMINI_API_KEY:
    raise RuntimeError("GEMINI_API_KEY not set. Put it in .env or export it.")

FILTERED_CSV = Path("filtered") / f"{GENRE}_filtered.csv"
KEEP_DIR = Path(f"kept_{GENRE}_videos")
NEW_JSON_COL = "edited_script"

client = genai.Client(api_key=GEMINI_API_KEY)

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

    transition_count = int(row.get("transitions_count", 0))
    if transition_count > 0:
        effects.append(f"- Insert exactly {transition_count} Transition spans using [TRANSITION] to mark a transition. Transition are always present at the start of a segment. You are not required to provide information about the type of transition.")

    if str(row.get("sound_effects_present", "")).strip().upper() == "TRUE":
        sound_effects_count = int(row.get("sound_effects_count", 0))
        effects.append(f"- Insert exactly {sound_effects_count} sound effect span using [SOUND_EFFECT] to mark the start of a sound effect. You are not required to provide information about the type of sound effect between the spans.")

    if str(row.get("background_music_present", "")).strip().upper() == "TRUE":
        effects.append("- Background music is present. Insert [BACKGROUND_MUSIC] at the start and [/BACKGROUND_MUSIC] at the end of the full video.")

    tos_present = str(row.get("on_screen_text_present", "")).strip().upper() == "TRUE"
    tos_types = row.get("type_of_on_screen_text", [])
    if tos_present:
        if isinstance(tos_types, str):
            try:
                tos_types = json.loads(tos_types.replace("'", '"'))
            except:
                tos_types = [tos_types]
        if "Transcript" in tos_types:
            effects.append("- The on-screen text is a transcript. Use a single [TOS] at the beginning and [/TOS] at the end of the full video.")
        else:
            effects.append("- Insert [TOS] ... [/TOS] spans only for meaningful on-screen text overlays (not account handles).")

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
        "You are a professional video effect analyser.\n"
        "You will be provided with a visual description and transcript of a video.\n"
        "Your task is to place the video effects that exists in the video in approriate places within the transcript and visual descriptions.\n"
        "Do not invent effects. Only place markers for effects that are explicitly listed.\n\n"
        f"{effect_instructions}\n\n"
        "Keep the original transcript and visual descriptions unmodified. Only insert markers as needed.\n"
        "If a transcript does not exist for a segment, insert markers into the visual description.\n"
        "Do not change the format of the segments, the effects should only be placed in the provided transcript or visual descriptions.\n\n"
        
        f"<SEGMENT>\n{segment_block}\n</SEGMENT>"
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

    for filename in os.listdir(keep_dir):
        if not filename.lower().endswith(".mp4"):
            continue

        video_id = extract_video_id(filename)

        if NEW_JSON_COL in df.columns and \
           video_id in df["video_id"].astype(str).values and \
           not pd.isna(df.loc[df["video_id"].astype(str) == video_id, NEW_JSON_COL].values[0]):
            print(f"Skipping {video_id}: already analyzed.")
            continue

        file_path = os.path.join(keep_dir, filename)
        print(f"\n=== Processing {filename} (video_id={video_id}) ===")

        row_mask = df["video_id"].astype(str) == str(video_id)
        segment_text = get_segment_for_video(df, video_id)
        row_data = df.loc[row_mask].iloc[0].to_dict() if row_mask.any() else {}

        try:
            result_json = gemini_analysis(file_path, segment_text, row_data)
        except Exception as e:
            print(f"[Gemini] Error analyzing {filename}: {e}")
            result_json = {"error": str(e)}

        compact = json.dumps(result_json, ensure_ascii=False, separators=(",", ":"))
        if row_mask.any():
            df.loc[row_mask, NEW_JSON_COL] = compact
        else:
            new_row = {"video_id": str(video_id), "segments": segment_text or "", NEW_JSON_COL: compact}
            df = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)

        df.to_csv(csv_path, index=False)
        time.sleep(1)

    print(f"\nDone. Updated CSV saved to {csv_path}")

if __name__ == "__main__":
    analyze_and_save_with_segments(KEEP_DIR, FILTERED_CSV)
