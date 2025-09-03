
---

## Step 1 — Download & Filter Videos

Run the downloadvideos.py file. This script downloads TikTok videos from a list of IDs, saves **raw metadata** in `raw_csv/`, saves **filtered metadata** in `filtered/`, and moves only the valid MP4s (English + under 120 seconds) into `kept_<GENRE>_videos/`.

### Requirements

* A `.env` file with the genre you want to process:

  ```env
  VIDEO_CATEGORY=drama
  ```
* A text file containing TikTok video IDs, one per line:

  ```
  video_data/<GENRE>.txt
  ```

### Outputs

* Raw CSV → `raw_csv/<GENRE>.csv`
* Filtered CSV → `filtered/<GENRE>_filtered.csv`
* Kept MP4s → `kept_<GENRE>_videos/`

---

Here’s an updated **Step 2** script that:

* Reads **`VIDEO_CATEGORY`** and **`GEMINI_API_KEY`** from your `.env`
* Uses the same folders as Step 1: `filtered/<GENRE>_filtered.csv` and `kept_<GENRE>_videos/`
* **Skips Gemini** if the video ID isn’t in the CSV or already has a `video_summary`
* Saves after each update

---

## Step 2 — Analyze Kept Videos with Gemini

Run the get_effect_counts.py file. This script analyzes each MP4 in `kept_<GENRE>_videos/` (from Step 1), asks Gemini for editing/structure details, and writes results back into `filtered/<GENRE>_filtered.csv`. It skips videos not listed in the CSV and ones already analyzed (non-empty `video_summary`).

### Requirements
* `.env` file:

  ```env
  VIDEO_CATEGORY=drama
  GEMINI_API_KEY=your_api_key_here
  ```
### Inputs

* Kept videos: `kept_<GENRE>_videos/*.mp4`
* Filtered CSV: `filtered/<GENRE>_filtered.csv` (must include a `video_id` column)

### Output

* The same filtered CSV is updated in place with Gemini results (e.g., `video_summary`, counts, etc.).


## Step 3 — Filter out “no-effect” videos (and clean files)

This script prunes your dataset to **only keep videos that show at least one editing effect**.
It updates the filtered CSV **in place** and optionally **deletes** MP4s in the kept-videos folder that no longer match.

### What it does

* **Backs up** your `filtered/<GENRE>_filtered.csv` (timestamped copy).
* Keeps rows where **any** of these columns is truthy:

  * `transitions_present`, `b_roll_footage_present`, `animated_graphics_present`, `on_screen_text_present`
* Writes the **filtered CSV back to the same path**.
* If the kept-videos folder exists, **removes video files** whose filenames contain a `video_id` that was filtered out.

> It treats missing effect columns as `False`, and normalizes common truthy values (`true`, `1`, `yes`, etc.).

### Requirements

* Environment variable `VIDEO_CATEGORY` (same as earlier steps), e.g.:

### Expected inputs & paths

* **CSV**: `filtered/<GENRE>_filtered.csv`
* **Videos folder (optional)**: `kept_<GENRE>_videos/`
  (Files are recognized by extension: `.mp4`, `.mov`, `.m4v`, `.avi`, `.mkv`, `.webm`.)

### Outputs

* **Updated CSV** in place at `filtered/<GENRE>_filtered.csv`
* **Backup CSV** next to it, named like:
  `<GENRE>_filtered.backup-YYYYMMDD-HHMMSS.csv`
* **Deleted files report** for videos whose `video_id` had no effects


## Step 4 — Find & Export Anomalies

This script scans your **filtered dataset** and flags rows that look suspicious or inconsistent, then writes only those rows to an **anomalies CSV**.

### What it checks (rules)

* **Sound conflict:** `background_music_present` **and** `sound_effects_present` are both true.
* **Overuse counts (>5):** any of `b_roll_count`, `animated_graphics_count`, `transitions_count`, `sound_effects_count`.
* **Text conflict:** `type_of_on_screen_text` contains both **Transcript/Text on Screen** and **Specific Keywords**.

> The script accepts booleans like `true/1/yes/y/t` and parses list-like columns that may be stored as Python/JSON lists or comma-separated strings.

---

### Inputs & Outputs

* **Input CSV:** `filtered/<GENRE>_filtered.csv`
  (`GENRE` comes from the environment variable `VIDEO_CATEGORY`, default `drama`.)
* **Output CSV:** `anomalies/<GENRE>_anomalies.csv` (folder is created if missing)

---

### Requirements

* Set genre in `.env` (recommended):

  ```env
  VIDEO_CATEGORY=drama
  ```

---

### Customize thresholds & logic

* Change the “overuse” threshold inside the script (default `> 5`).
* Add/remove rules in `find_anomalies_row()` as needed.

---


## Review & Fix Anomalies — Interactive Editor

This script lets you **review** rows flagged as anomalous and **edit** their metadata interactively while watching the corresponding video. It merges your **original CSV** with an **anomalies CSV**, opens each affected video, and walks you through quick prompts to correct fields. Changes are saved after each row; a JSONL log tracks edits.

---

### Requirements
* A `constants.py` next to this script, exporting:

  * Enum-like objects: `camera_angles`, `overall_type`, `text_type`, `transitions`, `category`, `playback_speed`, `broll_type`, `animated_graphics_type`
  * A Pydantic model: `VideoEditAnalysis` (used for optional validation)

---

### Inputs

* `--original` — your **main CSV** with video metadata (must contain a video ID column such as `video_id`, `id`, `videoId`, etc.).
* `--anomalies` — CSV with at least a video ID column and (optionally) `anomalies_joined`.
* `--videos_dir` — folder containing your MP4/MOV/etc. The script matches files by `<video_id>` or `*<video_id>*`.

### Outputs

* Updated CSV: either `--out updated_videos.csv` (default) **or** `--inplace` to write back to `--original`.
* Edit log: `--log edits_log.jsonl` (append-only JSON lines).

---

### Usage


To update the original CSV in place:

```bash
python removehallucinations.py \
  --original filtered/drama_filtered.csv \
  --anomalies anomalies/drama_anomalies.csv \
  --videos_dir kept_drama_videos \
  --log logs/drama_edits.jsonl \
  --inplace
```

---

### Interactive controls

* When a video opens, the script waits:

  * Press **Enter** → start editing prompts for that row
  * Press **c** → **skip** this row (no changes)
  * Press **q** → **quit** the whole review early
* For each field:

  * **Enter** keeps the current value
  * Provide a value to update it (e.g., `y/n` for booleans, integers for counts)
  * For enum lists (e.g., `types_of_transitions`), enter **comma-separated enum NAMES** (shown in the prompt)

---


## Step 5 - Segment Script Extraction

This script analyzes each kept video and produces **segments** (timestamped visual descriptions + transcript snippets) tailored for BLV editors. It updates your filtered CSV **in place**.

### What it does

* Loads videos from: `kept_<GENRE>_videos/`
* Reads/writes CSV: `filtered/<GENRE>_filtered.csv`
* For each MP4 whose `video_id` is in the CSV and whose `segments` is empty:

  * Uploads the file to Gemini
  * Requests structured segments
  * Saves results back into the CSV (keeps `segments` as JSON in a single cell)

### Requirements

  ```env
  VIDEO_CATEGORY=drama
  GEMINI_API_KEY=your_gemini_api_key_here
  ```
### Inputs

* `kept_<GENRE>_videos/*.mp4` (from your earlier step)
* `filtered/<GENRE>_filtered.csv` (must include `video_id`; `segments` is created if missing)

### Outputs

* Updated `filtered/<GENRE>_filtered.csv` with a `segments` column containing JSON like:

  ```json
  {
    "segments": [
      {"timestamp": 0, "visualDescription": "…", "transcript": "…"},
      {"timestamp": 12, "visualDescription": "…", "transcript": "…"}
    ]
  }
  ```