from enum import Enum
from pydantic import BaseModel
from typing import List, Union


class camera_angles(Enum):
    SINGLEANGLE= 'Single Static Angle'
    MULTIPLEANGLE='Multiple Static Angle'
    DYNAMIC='Dynamic Camera Movement'


class overall_type(Enum):
    MONTAGE='Montage'
    MOVIECLIP='Movie'
    POV='POV'
    TALKINGHEAD='Talking Head'
    VLOG='Vlog'
    TEXTOVERLAY='Text Overlay'
    INTERVIEW='Interview'
    ANIMATED='Animated'
    HOWTO='How-to'
    TRENDINGAUDIO='Trending Audio'


class text_type(Enum):
    CTA="Call to Action"
    TRANSCRIPT= "Transcript"
    HOOK="Hook"
    SPECIFICKEYWORDS="Specific Keywords"


class transitions(Enum):
    FADE_TRANSITION = "Fade Transition"
    SLIDE_TRANSITION = "Slide Transition"
    WIPE_TRANSITION = "Wipe Transition"
    FLIP_TRANSITION = "Flip Transition"
    CLOCKWIPE_TRANSITION = "Clockwipe Transition"
    IRIS_TRANSITION = "Iris Transition"
    ZOOM_TRANSITION = "Zoom Transition"

class category(Enum):
    SINGING= "Singing & Dancing"
    COMEDY= "Comedy"
    SPORTS= "Sports"
    ANIMEANDCOMICS= "Anime & Comics"
    RELATIONSHIP= "Relationship"
    SHOWS= "Shows"
    LIPSYNC= "Lipsync"
    DAILYLIFE= "Daily Life"
    BEAUTYCARE= "Beauty Care"
    GAMES= "Games"
    SOCIETY= "Society"
    OUTFIT= "Outfit"
    CARS= "Cars"
    FOOD= "Food"
    ANIMALS= "Animals"
    FAMILY= "Family"
    DRAMA= "Drama"
    FITNESSANDHEALTH= "Fitness & Health"
    EDUCATION= "Education"
    TECHNOLOGY= "Technology"


class playback_speed(Enum):
    INCREASED= "Increased"
    NORMAL= "Normal"
    SLOWED= "Slowed"

class broll_type(Enum):
    VIDEO= "video"
    IMAGE= "image"

class animated_graphics_type(Enum):
    GIF= "GIF"
    STICKER= "STICKER"
    CLIP= "CLIP"
    MEME= "MEME"
    EMOJI= "EMOJI"

class VideoEditAnalysis(BaseModel):
    video_summary: str
    category: category
    overall_type: overall_type
    camera_angles: camera_angles
    shot_or_scene_changes_present: bool
    average_interval_shot_or_scene_changes_seconds: float
    shot_or_scene_change_count: int
    b_roll_footage_present: bool
    b_roll_visuals: List[broll_type]
    b_roll_count: int
    animated_graphics_present: bool
    types_of_animated_graphics: List[animated_graphics_type]
    animated_graphics_count: int
    on_screen_text_present: bool
    type_of_on_screen_text: list[text_type]
    transitions_present: bool
    types_of_transitions: list[transitions]
    transitions_count: int
    voiceover_present: bool
    voiceover_type: str
    playback_speed: playback_speed
    background_music_present: bool
    sound_effects_present: bool
    sound_effects_type: str
    sound_effects_count: int