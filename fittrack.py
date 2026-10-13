from __future__ import annotations

import hashlib
import json
import os
import re
import secrets
import sqlite3
import subprocess
import sys
import tkinter as tk
import webbrowser
from tkinter import ttk, messagebox
from datetime import datetime, timedelta
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent
DB_PATH = APP_DIR / "fittrack.db"
VIDEO_CONFIG_PATH = APP_DIR / "exercise_videos.json"
VIDEO_DIR = APP_DIR / "videos"

# ---------------------------------------------------------------- theme (white + blue)
BG = "#f4f7fb"          # main workspace
SIDEBAR = "#ffffff"
PANEL = "#ffffff"
PANEL_2 = "#eef3fa"     # inputs / secondary surfaces
BORDER = "#d5deea"
TEXT = "#14213d"        # dark navy
MUTED = "#5f6f86"
BLUE = "#2563eb"        # primary
BLUE_DARK = "#1d4ed8"
BLUE_LIGHT = "#dbeafe"  # selected cards / active nav
HERO = "#e8f1ff"
HERO_BORDER = "#c7dbfb"
RED = "#d64545"
OK = "#16a34a"
GREEN = BLUE            # legacy alias so older helper calls keep working
GREEN_DARK = BLUE_LIGHT

MAX_ROUTINE_EXERCISES = 20
ROUTINE_FOCUSES = ["Full body", "Strength", "Build muscle", "Cardio", "Mobility", "Improve endurance"]
GOALS = ["Build strength", "Build muscle", "Improve endurance", "Get moving", "Stay consistent"]
LEVELS = ["Beginner", "Intermediate", "Advanced"]
GENDERS = ["Prefer not to say", "Male", "Female"]
HEIGHT_RANGE = (100.0, 250.0)   # cm
WEIGHT_RANGE = (25.0, 300.0)    # kg

EXERCISE_SEED = [
    ("Barbell Squat", "Quads · Glutes", "Intermediate", "Barbell", "3", "8–10", "Brace your core; keep heels grounded and knees tracking over toes.", ["Stand with feet about shoulder-width apart and brace your core.", "Send your hips back and bend your knees with heels grounded.", "Lower only as far as you can while keeping a neutral spine.", "Drive through your whole foot to stand tall."]),
    ("Push-up", "Chest · Triceps", "Beginner", "Bodyweight", "3", "8–12", "Keep a straight line from head to heels and lower with control.", ["Place hands slightly wider than shoulders.", "Extend legs and brace your abs in a straight plank.", "Lower your chest with elbows at a comfortable angle.", "Push the floor away and return to the start."]),
    ("Dumbbell Row", "Back · Biceps", "Beginner", "Dumbbells", "3", "10–12", "Pull your elbow toward your hip without twisting your torso.", ["Hinge at the hips with a flat back and soft knees.", "Let the dumbbell hang under your shoulder.", "Pull your elbow back, squeezing the shoulder blade.", "Lower slowly and repeat on the other side."]),
    ("Romanian Deadlift", "Hamstrings · Glutes", "Intermediate", "Dumbbells / Barbell", "3", "8–10", "Push hips back; keep weights close and stop at a comfortable hamstring stretch.", ["Stand tall with weights in front of your thighs.", "Soften your knees and push hips backward.", "Lower weights close to your legs with a neutral spine.", "Drive hips forward to stand without leaning back."]),
    ("Plank", "Core", "Beginner", "Bodyweight", "3", "30–45 sec", "Squeeze glutes and abs; do not let your lower back sag.", ["Place forearms under your shoulders.", "Step feet back to make a straight line with your body.", "Brace abs and squeeze glutes while breathing steadily.", "Hold with hips level, then lower with control."]),
    ("Dumbbell Shoulder Press", "Shoulders · Triceps", "Intermediate", "Dumbbells", "3", "8–12", "Use a comfortable range and avoid arching your lower back.", ["Hold dumbbells at shoulder height with wrists stacked.", "Brace your core and keep ribs down.", "Press weights overhead with control.", "Lower slowly to shoulder height."]),
    ("Walking Lunge", "Quads · Glutes", "Beginner", "Bodyweight / Dumbbells", "3", "10 each side", "Step carefully and keep your front knee tracking over your toes.", ["Stand tall with feet hip-width apart.", "Step forward and bend both knees under control.", "Keep your torso upright and front foot flat.", "Push through the front foot and step forward again."]),
    ("Jumping Jack", "Full body · Cardio", "Beginner", "Bodyweight", "3", "30 sec", "Land softly; use a step-out version for lower impact.", ["Stand tall with arms at your sides.", "Jump feet apart as arms rise overhead.", "Land softly with knees relaxed.", "Return to the start and repeat steadily."]),
]

# Exercises suggested for each focus / goal.
EXERCISE_FOCUS_MAP = {
    "Full body": ["Barbell Squat", "Push-up", "Dumbbell Row", "Romanian Deadlift", "Plank", "Dumbbell Shoulder Press", "Walking Lunge", "Jumping Jack"],
    "Strength": ["Barbell Squat", "Romanian Deadlift", "Dumbbell Row", "Dumbbell Shoulder Press", "Push-up"],
    "Build strength": ["Barbell Squat", "Romanian Deadlift", "Dumbbell Row", "Dumbbell Shoulder Press", "Push-up"],
    "Build muscle": ["Barbell Squat", "Romanian Deadlift", "Dumbbell Row", "Dumbbell Shoulder Press", "Push-up"],
    "Cardio": ["Jumping Jack", "Walking Lunge"],
    "Improve endurance": ["Jumping Jack", "Walking Lunge", "Plank", "Push-up"],
    "Mobility": ["Walking Lunge", "Plank", "Romanian Deadlift"],
    "Get moving": ["Jumping Jack", "Walking Lunge", "Push-up", "Plank"],
    "Stay consistent": ["Push-up", "Walking Lunge", "Plank", "Jumping Jack"],
}

# ======================================================================
# Validation helpers (pure functions - no Tk, easy to test)
# ======================================================================
EMAIL_RE = re.compile(
    r"^(?!\.)(?!.*\.\.)[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]{1,64}(?<!\.)@"
    r"(?:[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?\.)+[A-Za-z]{2,24}$"
)


def normalize_email(email: str) -> str:
    return (email or "").strip().lower()


def validate_email(email: str) -> str | None:
    """Return an error message, or None when the address looks valid."""
    email = normalize_email(email)
    if not email:
        return "Enter your email address."
    if len(email) > 254 or not EMAIL_RE.match(email):
        return "Enter a valid email address, like name@example.com."
    return None


def password_checks(password: str, confirm: str = "") -> list[tuple[str, bool]]:
    checks = [
        ("At least 8 characters", len(password) >= 8),
        ("Contains a letter", any(c.isalpha() for c in password)),
        ("Contains a number", any(c.isdigit() for c in password)),
        ("Contains a special character", any(not c.isalnum() and not c.isspace() for c in password)),
        ("No spaces", not any(c.isspace() for c in password)),
    ]
    if confirm != "":
        checks.append(("Passwords match", password == confirm))
    return checks


def parse_measure(text, low: float, high: float, label: str, unit: str):
    """Parse an optional positive number within bounds. Blank -> None."""
    text = (str(text) if text is not None else "").strip()
    if not text:
        return None
    try:
        value = float(text)
    except ValueError:
        raise ValueError(f"{label} must be a number in {unit}.")
    if value != value or value in (float("inf"), float("-inf")):
        raise ValueError(f"{label} must be a number in {unit}.")
    if value <= 0:
        raise ValueError(f"{label} must be a positive number in {unit}.")
    if not (low <= value <= high):
        raise ValueError(f"{label} should be between {low:g} and {high:g} {unit}.")
    return round(value, 1)


# ======================================================================
# Smart recommendation engine (pure functions)
# ======================================================================
GOAL_GROUP = {
    "Full body": "general", "Strength": "strength", "Build strength": "strength",
    "Build muscle": "muscle", "Cardio": "cardio", "Mobility": "mobility",
    "Improve endurance": "endurance", "Get moving": "easy", "Stay consistent": "easy",
}
LEVEL_INDEX = {"Beginner": 0, "Intermediate": 1, "Advanced": 2}

# kind of movement for each library exercise (drives which rep ranges make sense)
EXERCISE_META = {
    "Barbell Squat": {"kind": "compound"},
    "Romanian Deadlift": {"kind": "compound"},
    "Dumbbell Row": {"kind": "accessory", "per_side": True},
    "Dumbbell Shoulder Press": {"kind": "accessory"},
    "Push-up": {"kind": "bodyweight"},
    "Walking Lunge": {"kind": "bodyweight", "per_side": True},
    "Plank": {"kind": "hold"},
    "Jumping Jack": {"kind": "cardio"},
}

# PRESC[kind][group] = (sets for [Beginner, Intermediate, Advanced], (lo, hi) per level, unit)
_hold_strength = ([2, 3, 3], [(15, 25), (25, 40), (40, 60)], "sec")
_cardio_strength = ([2, 2, 3], [(20, 30), (30, 40), (30, 45)], "sec")
PRESC = {
    "compound": {
        "strength": ([3, 4, 5], [(5, 8), (3, 6), (3, 5)], "reps"),
        "muscle": ([2, 3, 4], [(8, 10), (6, 12), (6, 12)], "reps"),
        "endurance": ([2, 2, 3], [(10, 12), (12, 15), (12, 20)], "reps"),
        "general": ([2, 3, 3], [(8, 10), (8, 10), (6, 10)], "reps"),
        "cardio": ([2, 2, 3], [(10, 12), (12, 15), (12, 15)], "reps"),
        "mobility": ([2, 2, 2], [(6, 8), (6, 8), (8, 10)], "reps"),
        "easy": ([2, 2, 3], [(8, 10), (8, 10), (8, 10)], "reps"),
    },
    "accessory": {
        "strength": ([3, 3, 4], [(6, 8), (5, 8), (5, 8)], "reps"),
        "muscle": ([2, 3, 4], [(8, 12), (8, 12), (8, 12)], "reps"),
        "endurance": ([2, 2, 3], [(12, 15), (12, 15), (12, 20)], "reps"),
        "general": ([2, 3, 3], [(10, 12), (8, 12), (8, 12)], "reps"),
        "cardio": ([2, 2, 3], [(12, 15), (12, 15), (15, 20)], "reps"),
        "mobility": ([2, 2, 2], [(8, 10), (8, 10), (10, 12)], "reps"),
        "easy": ([2, 2, 3], [(10, 12), (10, 12), (10, 12)], "reps"),
    },
    "bodyweight": {
        "strength": ([3, 3, 4], [(5, 8), (6, 10), (8, 12)], "reps"),
        "muscle": ([2, 3, 4], [(8, 12), (8, 15), (10, 15)], "reps"),
        "endurance": ([2, 3, 3], [(10, 12), (12, 20), (15, 20)], "reps"),
        "general": ([2, 3, 3], [(8, 10), (10, 12), (10, 15)], "reps"),
        "cardio": ([2, 3, 3], [(10, 15), (15, 20), (20, 30)], "reps"),
        "mobility": ([2, 2, 2], [(6, 8), (8, 10), (8, 10)], "reps"),
        "easy": ([2, 2, 3], [(8, 10), (8, 12), (10, 12)], "reps"),
    },
    "hold": {
        "strength": _hold_strength, "muscle": _hold_strength,
        "endurance": ([2, 3, 3], [(20, 30), (30, 45), (45, 60)], "sec"),
        "general": ([2, 3, 3], [(20, 30), (30, 45), (30, 45)], "sec"),
        "cardio": ([2, 3, 3], [(20, 30), (30, 45), (30, 45)], "sec"),
        "mobility": ([2, 2, 2], [(10, 15), (15, 20), (20, 30)], "sec"),
        "easy": ([2, 2, 3], [(15, 20), (20, 30), (30, 45)], "sec"),
    },
    "cardio": {
        "strength": _cardio_strength, "muscle": _cardio_strength,
        "endurance": ([2, 3, 3], [(30, 40), (40, 60), (45, 60)], "sec"),
        "general": ([2, 3, 3], [(20, 30), (30, 45), (30, 45)], "sec"),
        "cardio": ([3, 3, 4], [(30, 40), (40, 60), (45, 60)], "sec"),
        "mobility": ([1, 2, 2], [(15, 20), (20, 30), (20, 30)], "sec"),
        "easy": ([2, 2, 3], [(20, 30), (30, 40), (30, 45)], "sec"),
    },
}

# Starting-weight guidance per exercise and level: (low, high) kg, or None for "learn the movement first".
WEIGHT_GUIDE = {
    "Dumbbell Row": ([(4, 8), (8, 14), (12, 20)], "per hand"),
    "Dumbbell Shoulder Press": ([(2, 5), (5, 10), (8, 16)], "per hand"),
    "Romanian Deadlift": ([(4, 8), (10, 16), (16, 24)], "per hand (dumbbells)"),
    "Walking Lunge": ([None, (2, 6), (6, 12)], "per hand"),
    "Barbell Squat": ([None, (30, 50), (50, 80)], "total bar load"),
}
BEGINNER_FIRST = {
    "Barbell Squat": "Bodyweight squats or an empty bar (about 20 kg) while you learn the pattern",
    "Walking Lunge": "Bodyweight only until the movement feels steady",
}
LEVEL_NOTES = {
    "Push-up": "Beginners: use an incline or knee push-up if full push-ups break form.",
    "Plank": "Stop the hold when your hips sag; several shorter holds are fine.",
    "Barbell Squat": "Beginners: master bodyweight form before adding load.",
    "Romanian Deadlift": "Keep the weight light until the hip hinge feels natural.",
}
GROUP_REASON = {
    "strength": "lower-rep, controlled work to build strength",
    "muscle": "moderate reps to build muscle",
    "endurance": "higher reps with manageable resistance to build endurance",
    "cardio": "keeps your heart rate up for cardio conditioning",
    "mobility": "slow, controlled reps to improve movement quality",
    "general": "covers a balanced full-body session",
    "easy": "approachable and easy to repeat, which helps you stay consistent",
}
WEIGHT_DISCLAIMER = ("Weight suggestions are general starting estimates, not medical advice or guaranteed "
                     "safe limits. Start light, put form first, and adjust anything that does not feel right.")


def _level_idx(level: str) -> int:
    return LEVEL_INDEX.get(level, 0)  # unknown/missing -> conservative beginner


AGE_RANGE = (13, 100)  # years
REST = {  # (standard, beginner)
    "strength": ("2–3 minutes", "90 seconds–2 minutes"),
    "muscle": ("60–90 seconds", "60–90 seconds"),
    "endurance": ("30–45 seconds", "30–45 seconds"),
    "cardio": ("20–30 seconds", "30–45 seconds"),
    "mobility": ("no fixed rest - breathe and move slowly", "no fixed rest - breathe and move slowly"),
    "general": ("60–90 seconds", "60–90 seconds"),
    "easy": ("45–60 seconds", "60 seconds"),
}
BEGINNER_FALLBACK = ["Push-up", "Walking Lunge", "Plank", "Dumbbell Row", "Jumping Jack"]


def age_band(age) -> str:
    if age is None: return "adult"
    if age < 18: return "teen"
    if age >= 65: return "senior"
    if age >= 50: return "mature"
    return "adult"


def bmi_of(height_cm, weight_kg):
    if not height_cm or not weight_kg: return None
    return weight_kg / ((height_cm / 100.0) ** 2)


def profile_args(p) -> dict:
    """Keyword args for recommend() from a profile row (or None)."""
    if p is None: return {}
    return {"age": p["age"], "height_cm": p["height_cm"], "weight_kg": p["body_weight"]}


def validate_body(age, height, weight):
    """Required age/height/weight. Returns (values, errors); errors are friendly sentences."""
    errors, vals = [], {}
    t = str(age if age is not None else "").strip()
    if not t:
        errors.append("Enter your age in years.")
    else:
        try:
            f = float(t)
            if f != f or f != int(f): raise ValueError
            a = int(f)
        except (ValueError, OverflowError):
            errors.append("Age must be a whole number of years, like 28.")
        else:
            if not AGE_RANGE[0] <= a <= AGE_RANGE[1]:
                errors.append(f"Age should be between {AGE_RANGE[0]} and {AGE_RANGE[1]} years.")
            else:
                vals["age"] = a
    for key, text, rng, label, unit in (("height_cm", height, HEIGHT_RANGE, "Height", "centimeters (cm)"),
                                        ("body_weight", weight, WEIGHT_RANGE, "Weight", "kilograms (kg)")):
        if not str(text if text is not None else "").strip():
            errors.append(f"Enter your {label.lower()} in {unit}.")
            continue
        try:
            vals[key] = parse_measure(text, *rng, label, unit)
        except ValueError as err:
            errors.append(str(err))
    return vals, errors


def select_exercises(rows, focus: str, level: str, age=None):
    """Real library exercises for a focus, filtered for beginners / very young users."""
    by_name = {r["name"]: r for r in rows}
    chosen = [by_name[n] for n in EXERCISE_FOCUS_MAP.get(focus, EXERCISE_FOCUS_MAP["Full body"]) if n in by_name]
    if _level_idx(level) == 0 or (age is not None and age < 16):
        easy = [r for r in chosen if r["level"] == "Beginner"]
        for n in BEGINNER_FALLBACK:
            if len(easy) >= 3: break
            if n in by_name and by_name[n] not in easy and by_name[n]["level"] == "Beginner":
                easy.append(by_name[n])
        chosen = easy
    return chosen


def _progression(kind, unit, li):
    if unit == "sec":
        return "Add about 5 seconds to each hold once every set feels steady for two sessions in a row."
    if kind in ("compound", "accessory"):
        if li == 0:
            return ("Keep the same light load for the first 2–3 weeks while technique settles. When every set feels controlled, "
                    "add 1–2 reps per set first, then the smallest weight step (about 1–2 kg).")
        return ("When you reach the top of the rep range on every set with good form for two sessions in a row, add the smallest "
                "weight step (about 1–2 kg) and drop back to the low end of the range.")
    return "Add 1–2 reps per set each week. At the top of the range, make it harder (slower tempo, less assistance) instead of rushing."


def recommend(ex, focus: str, level: str, age=None, height_cm=None, weight_kg=None) -> dict:
    """Programming suggestion for one exercise, tailored to level, age and (lightly) height/weight.

    Height and weight never set a lifting load; they only trigger joint-friendly notes (via BMI)."""
    name = ex["name"]
    meta = EXERCISE_META.get(name, {"kind": "bodyweight"})
    group = GOAL_GROUP.get(focus, "general")
    li = _level_idx(level)
    band = age_band(age)
    bmi = bmi_of(height_cm, weight_kg)
    sets_list, ranges, unit = PRESC[meta["kind"]][group]
    sets, (lo, hi) = sets_list[li], ranges[li]
    loaded = meta["kind"] in ("compound", "accessory")
    personal = []
    if band == "teen":
        if loaded: lo, hi = max(lo, 8), max(hi, 12)
        personal.append("Under 18: light loads, 8–12 controlled reps and technique first; train with supervision when you can.")
    elif band == "senior":
        sets = min(sets, 3 if li else 2)
        if loaded: lo, hi = max(lo, 8), max(hi, 12)
        personal.append("Age 65+: moderate volume, smooth 8–12 rep sets and longer rests; warm up for 5–10 minutes.")
    elif band == "mature":
        sets = min(sets, 3)
        if loaded: lo, hi = max(lo, 6), max(hi, 10)
        personal.append("Age 50+: slightly lower volume, a thorough warm-up and a comfortable range of motion.")
    suffix = " each side" if meta.get("per_side") else ""
    reps_text = f"{lo}–{hi} {'sec' if unit == 'sec' else 'reps'}{suffix}"
    wi = li
    if band == "senior": wi = 0
    elif band == "mature": wi = max(0, li - 1)
    weight_text, weight_range = None, None
    guide = WEIGHT_GUIDE.get(name)
    if guide:
        table, unit_txt = guide
        entry = table[wi]
        if band == "teen":
            weight_text = "Bodyweight or very light resistance (a light dumbbell) - technique first"
        elif group == "mobility":
            weight_text = "Very light or bodyweight - focus on range of motion and control"
        elif entry is None:
            weight_text = BEGINNER_FIRST.get(name, "Start with bodyweight or the lightest option")
        else:
            wlo, whi = entry
            if group in ("endurance", "easy", "cardio"):
                whi = wlo + max(1, (whi - wlo) // 2)  # lighter end of the range for higher-rep work
            weight_range = (wlo, whi)
            weight_text = f"{wlo}–{whi} kg {unit_txt} (adjust to what keeps your form clean)"
    if bmi is not None and bmi >= 30:
        if name == "Jumping Jack":
            personal.append("Low-impact option: step side to side instead of jumping.")
        elif name == "Push-up" and li == 0:
            personal.append("Incline push-ups (hands on a sturdy bench or counter) are a joint-friendly way to start.")
    elif name == "Jumping Jack" and band == "senior":
        personal.append("Low-impact option: step side to side instead of jumping.")
    rest = REST[group][1 if li == 0 else 0]
    if band in ("mature", "senior"): rest += " (take longer if you need it)"
    muscles = ex["muscles"].replace(" · ", ", ")
    reason = f"Works {muscles.lower()}; {GROUP_REASON[group]}. Matched to your {level.lower() if level in LEVELS else 'beginner'} level"
    reason += " and age." if band != "adult" else "."
    try: steps = [x for x in ex["steps"].splitlines() if x.strip()]
    except (KeyError, IndexError): steps = []
    return {
        "name": name, "sets": sets, "lo": lo, "hi": hi, "unit": unit, "reps_text": reps_text,
        "weight_text": weight_text, "weight_range": weight_range, "reason": reason,
        "note": LEVEL_NOTES.get(name) if li == 0 else None,
        "rest": rest, "personal": personal, "steps": steps,
        "progression": _progression(meta["kind"], unit, li),
    }


def set_feedback(rec: dict, weight: float, reps: int) -> str:
    """Soft guidance after a completed set. Never auto-increases load."""
    unit = "seconds" if rec["unit"] == "sec" else "reps"
    if reps <= 0:
        return "Enter what you completed."
    if reps < rec["lo"]:
        msg = f"Under the {rec['lo']}–{rec['hi']} {unit} target. If form slipped, lower the load or {unit} next set."
    elif reps > rec["hi"]:
        msg = (f"Above the {rec['lo']}–{rec['hi']} {unit} target. If form stayed solid, consider a small "
               "increase in a future session - not necessarily today.")
    else:
        msg = "In your target range. If it felt comfortable with steady form, consider progressing gradually next session."
    wr = rec.get("weight_range")
    if wr and weight > wr[1]:
        msg += " This is above a typical starting range, so keep reps controlled."
    return msg


def load_video_config(names=None) -> dict:
    """Read (and create if missing) exercise_videos.json: {exercise name: path or URL}."""
    cfg = {}
    try:
        if VIDEO_CONFIG_PATH.exists():
            data = json.loads(VIDEO_CONFIG_PATH.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                cfg = {str(k): str(v or "") for k, v in data.items()}
    except (OSError, ValueError):
        cfg = {}
    changed = not VIDEO_CONFIG_PATH.exists()
    for n in (names or [r[0] for r in EXERCISE_SEED]):
        if n not in cfg:
            cfg[n] = ""
            changed = True
    if changed:
        try:
            VIDEO_DIR.mkdir(exist_ok=True)
            VIDEO_CONFIG_PATH.write_text(json.dumps(cfg, indent=2, ensure_ascii=False), encoding="utf-8")
        except OSError:
            pass
    return cfg


def resolve_video(name: str):
    """Return (kind, value): ('none',''), ('url', url), ('file', path) or ('missing', path)."""
    value = load_video_config().get(name, "").strip()
    if not value:
        return ("none", "")
    if re.match(r"^https?://", value, re.I):
        return ("url", value)
    p = Path(value)
    if not p.is_absolute():
        p = APP_DIR / p
    return ("file", str(p)) if p.exists() else ("missing", str(p))


# ======================================================================
# Database
# ======================================================================
class FitTrackDB:
    def __init__(self, path: Path = DB_PATH):
        self.conn = sqlite3.connect(path)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON")
        self._setup()

    def _setup(self):
        self.conn.executescript("""
        CREATE TABLE IF NOT EXISTS users (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          email TEXT UNIQUE NOT NULL,
          display_name TEXT NOT NULL,
          salt TEXT NOT NULL,
          password_hash TEXT NOT NULL,
          created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS profiles (
          user_id INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
          fitness_goal TEXT NOT NULL DEFAULT 'Build strength',
          experience_level TEXT NOT NULL DEFAULT 'Beginner',
          weekly_target INTEGER NOT NULL DEFAULT 4,
          body_weight REAL
        );
        CREATE TABLE IF NOT EXISTS exercises (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          name TEXT UNIQUE NOT NULL,
          muscles TEXT NOT NULL,
          level TEXT NOT NULL,
          equipment TEXT NOT NULL,
          recommended_sets TEXT NOT NULL,
          recommended_reps TEXT NOT NULL,
          cue TEXT NOT NULL,
          steps TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS routines (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
          name TEXT NOT NULL,
          focus TEXT NOT NULL,
          created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS routine_exercises (
          routine_id INTEGER NOT NULL REFERENCES routines(id) ON DELETE CASCADE,
          exercise_id INTEGER NOT NULL REFERENCES exercises(id),
          position INTEGER NOT NULL DEFAULT 0,
          PRIMARY KEY (routine_id, exercise_id)
        );
        CREATE TABLE IF NOT EXISTS workouts (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
          routine_name TEXT NOT NULL,
          started_at TEXT NOT NULL,
          duration_minutes INTEGER NOT NULL DEFAULT 1,
          volume_kg REAL NOT NULL DEFAULT 0,
          sets_completed INTEGER NOT NULL DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS workout_sets (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          workout_id INTEGER NOT NULL REFERENCES workouts(id) ON DELETE CASCADE,
          exercise_id INTEGER NOT NULL REFERENCES exercises(id),
          set_number INTEGER NOT NULL,
          weight_kg REAL NOT NULL DEFAULT 0,
          reps INTEGER NOT NULL DEFAULT 0,
          done INTEGER NOT NULL DEFAULT 1
        );
        CREATE INDEX IF NOT EXISTS idx_routines_user ON routines(user_id);
        CREATE INDEX IF NOT EXISTS idx_workouts_user ON workouts(user_id);
        """)
        self._migrate()
        for row in EXERCISE_SEED:
            self.conn.execute(
                "INSERT OR IGNORE INTO exercises(name,muscles,level,equipment,recommended_sets,recommended_reps,cue,steps) VALUES(?,?,?,?,?,?,?,?)",
                (*row[:7], "\n".join(row[7]))
            )
        self.conn.commit()

    def _migrate(self):
        """Additive, non-destructive schema upgrade (existing rows are untouched)."""
        cols = {r["name"] for r in self.conn.execute("PRAGMA table_info(profiles)").fetchall()}
        if "height_cm" not in cols:
            self.conn.execute("ALTER TABLE profiles ADD COLUMN height_cm REAL")
        if "gender" not in cols:
            self.conn.execute("ALTER TABLE profiles ADD COLUMN gender TEXT")
        if "age" not in cols:
            self.conn.execute("ALTER TABLE profiles ADD COLUMN age INTEGER")
        # make sure every existing user has a profile row
        self.conn.execute("INSERT OR IGNORE INTO profiles(user_id) SELECT id FROM users")

    @staticmethod
    def _hash_password(password: str, salt_hex: str | None = None):
        salt = bytes.fromhex(salt_hex) if salt_hex else secrets.token_bytes(16)
        hashed = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 210_000)
        return salt.hex(), hashed.hex()

    def email_exists(self, email: str) -> bool:
        return self.conn.execute("SELECT 1 FROM users WHERE email=?", (normalize_email(email),)).fetchone() is not None

    def create_user(self, email: str, display_name: str, password: str):
        email = normalize_email(email)
        if self.email_exists(email):
            return None
        salt, digest = self._hash_password(password)
        try:
            cur = self.conn.execute(
                "INSERT INTO users(email,display_name,salt,password_hash,created_at) VALUES(?,?,?,?,?)",
                (email, display_name.strip(), salt, digest, datetime.now().isoformat(timespec="seconds"))
            )
            user_id = cur.lastrowid
            self.conn.execute("INSERT INTO profiles(user_id) VALUES(?)", (user_id,))
            self._create_starter_routines(user_id)
            self.conn.commit()
            return user_id
        except sqlite3.IntegrityError:
            self.conn.rollback()
            return None

    def verify_user(self, email: str, password: str):
        row = self.conn.execute("SELECT * FROM users WHERE email=?", (normalize_email(email),)).fetchone()
        if not row:
            return None
        _, digest = self._hash_password(password, row["salt"])
        return dict(row) if secrets.compare_digest(digest, row["password_hash"]) else None

    def _create_starter_routines(self, user_id: int):
        starters = [
            ("Full Body Foundation", "Full body", ["Push-up", "Dumbbell Row", "Barbell Squat", "Plank"]),
            ("Strength & Power", "Strength", ["Barbell Squat", "Romanian Deadlift", "Dumbbell Shoulder Press"]),
            ("Quick Cardio Reset", "Cardio", ["Jumping Jack", "Walking Lunge", "Plank"]),
        ]
        for name, focus, names in starters:
            cur = self.conn.execute("INSERT INTO routines(user_id,name,focus,created_at) VALUES(?,?,?,?)", (user_id, name, focus, datetime.now().date().isoformat()))
            rid = cur.lastrowid
            for pos, ex_name in enumerate(names):
                row = self.conn.execute("SELECT id FROM exercises WHERE name=?", (ex_name,)).fetchone()
                if row:
                    self.conn.execute("INSERT OR IGNORE INTO routine_exercises(routine_id,exercise_id,position) VALUES(?,?,?)", (rid, row["id"], pos))

    def profile(self, user_id: int):
        q = "SELECT u.display_name,p.* FROM users u JOIN profiles p ON p.user_id=u.id WHERE u.id=?"
        row = self.conn.execute(q, (user_id,)).fetchone()
        if row is None:  # defensive: user without a profile row
            self.conn.execute("INSERT OR IGNORE INTO profiles(user_id) VALUES(?)", (user_id,))
            self.conn.commit()
            row = self.conn.execute(q, (user_id,)).fetchone()
        return row

    def profile_complete(self, user_id: int) -> bool:
        p = self.profile(user_id)
        return p["age"] is not None and p["height_cm"] is not None and p["body_weight"] is not None

    @staticmethod
    def _check_goal_level(goal, level):
        if goal not in GOALS:
            raise ValueError("Choose a fitness goal from the list.")
        if level not in LEVELS:
            raise ValueError("Choose an experience level from the list.")

    def save_body(self, user_id: int, age, height, weight, goal: str, level: str):
        """Required profile-setup save (age, height, weight, goal, level). Validates before writing."""
        self._check_goal_level(goal, level)
        vals, errors = validate_body(age, height, weight)
        if errors:
            raise ValueError("\n".join(errors))
        self.conn.execute(
            "UPDATE profiles SET age=?,height_cm=?,body_weight=?,fitness_goal=?,experience_level=? WHERE user_id=?",
            (vals["age"], vals["height_cm"], vals["body_weight"], goal, level, user_id))
        self.conn.commit()

    def save_profile(self, user_id: int, name: str, goal: str, level: str, target: int,
                     weight: str, height: str = "", gender: str = "", age: str = ""):
        self._check_goal_level(goal, level)
        try:
            target = int(target)
        except (TypeError, ValueError):
            raise ValueError("Weekly workout target must be a whole number.")
        if not 1 <= target <= 7:
            raise ValueError("Weekly workout target must be between 1 and 7.")
        if gender and gender not in GENDERS:
            raise ValueError("Choose a gender option from the list.")
        vals, errors = validate_body(age, height, weight)
        if errors:
            raise ValueError("\n".join(errors))
        self.conn.execute("UPDATE users SET display_name=? WHERE id=?", ((name or "").strip() or "Athlete", user_id))
        self.conn.execute(
            "UPDATE profiles SET fitness_goal=?,experience_level=?,weekly_target=?,body_weight=?,height_cm=?,gender=?,age=? WHERE user_id=?",
            (goal, level, target, vals["body_weight"], vals["height_cm"], gender or None, vals["age"], user_id))
        self.conn.commit()

    def exercises(self, query: str = ""):
        # The library stays at the original eight exercises. Two names may remain in an
        # older database; they are hidden (not deleted) so history stays intact.
        excluded = ("Cat-Cow Stretch", "Hip Flexor Stretch")
        if query and query.strip():
            term = f"%{query.strip()}%"
            return self.conn.execute(
                "SELECT * FROM exercises "
                "WHERE (name LIKE ? OR muscles LIKE ? OR equipment LIKE ? OR level LIKE ?) "
                "AND name NOT IN (?, ?) ORDER BY name",
                (term, term, term, term, *excluded),
            ).fetchall()
        return self.conn.execute(
            "SELECT * FROM exercises WHERE name NOT IN (?, ?) ORDER BY name",
            excluded,
        ).fetchall()

    def create_routine(self, user_id: int, name: str, focus: str, exercise_ids: list[int]):
        name = (name or "").strip()
        if not name:
            raise ValueError("Enter a routine name.")
        if len(name) > 80:
            raise ValueError("Routine name must be 80 characters or fewer.")
        if focus not in ROUTINE_FOCUSES:
            raise ValueError("Choose a valid training focus.")
        ids = list(exercise_ids)
        if not ids:
            raise ValueError("Select at least one exercise.")
        if len(set(ids)) != len(ids):
            raise ValueError("A routine cannot contain the same exercise twice.")
        if len(ids) > MAX_ROUTINE_EXERCISES:
            raise ValueError(f"A routine can have at most {MAX_ROUTINE_EXERCISES} exercises (you selected {len(ids)}).")
        marks = ",".join("?" * len(ids))
        found = self.conn.execute(f"SELECT COUNT(*) FROM exercises WHERE id IN ({marks})", ids).fetchone()[0]
        if found != len(ids):
            raise ValueError("One or more selected exercises no longer exist.")
        try:
            cur = self.conn.execute("INSERT INTO routines(user_id,name,focus,created_at) VALUES(?,?,?,?)", (user_id, name, focus, datetime.now().date().isoformat()))
            rid = cur.lastrowid
            for pos, exid in enumerate(ids):
                self.conn.execute("INSERT INTO routine_exercises(routine_id,exercise_id,position) VALUES(?,?,?)", (rid, exid, pos))
            self.conn.commit()
        except sqlite3.Error:
            self.conn.rollback()
            raise
        return rid

    def routines(self, user_id: int):
        rows = self.conn.execute("SELECT * FROM routines WHERE user_id=? ORDER BY id DESC", (user_id,)).fetchall()
        result = []
        for r in rows:
            names = self.conn.execute("SELECT e.name FROM routine_exercises re JOIN exercises e ON e.id=re.exercise_id WHERE re.routine_id=? ORDER BY re.position", (r["id"],)).fetchall()
            result.append({**dict(r), "exercise_names": [x["name"] for x in names]})
        return result

    def routine(self, user_id: int, routine_id: int):
        row = self.conn.execute("SELECT * FROM routines WHERE id=? AND user_id=?", (routine_id, user_id)).fetchone()
        if not row:
            return None
        exercises = self.conn.execute("SELECT e.* FROM routine_exercises re JOIN exercises e ON e.id=re.exercise_id WHERE re.routine_id=? ORDER BY re.position", (routine_id,)).fetchall()
        return {**dict(row), "exercises": exercises}

    def delete_routine(self, user_id: int, routine_id: int):
        self.conn.execute("DELETE FROM routines WHERE id=? AND user_id=?", (routine_id, user_id))
        self.conn.commit()

    def save_workout(self, user_id: int, routine_name: str, started_at: datetime, sets: list[dict]):
        finished = datetime.now()
        duration = max(1, int((finished - started_at).total_seconds() // 60))
        completed = [s for s in sets if s["done"]]
        volume = sum(s["weight"] * s["reps"] for s in completed)
        cur = self.conn.execute("INSERT INTO workouts(user_id,routine_name,started_at,duration_minutes,volume_kg,sets_completed) VALUES(?,?,?,?,?,?)", (user_id, routine_name, finished.isoformat(timespec="seconds"), duration, volume, len(completed)))
        workout_id = cur.lastrowid
        for s in completed:
            self.conn.execute("INSERT INTO workout_sets(workout_id,exercise_id,set_number,weight_kg,reps,done) VALUES(?,?,?,?,?,1)", (workout_id, s["exercise_id"], s["set_number"], s["weight"], s["reps"]))
        self.conn.commit()
        return workout_id

    def workouts(self, user_id: int, search: str = ""):
        if search:
            term = f"%{search.strip()}%"
            return self.conn.execute("SELECT * FROM workouts WHERE user_id=? AND routine_name LIKE ? ORDER BY started_at DESC LIMIT 250", (user_id, term)).fetchall()
        return self.conn.execute("SELECT * FROM workouts WHERE user_id=? ORDER BY started_at DESC LIMIT 250", (user_id,)).fetchall()

    def delete_workout(self, user_id: int, workout_id: int):
        self.conn.execute("DELETE FROM workouts WHERE user_id=? AND id=?", (user_id, workout_id))
        self.conn.commit()

    def stats(self, user_id: int):
        base = self.conn.execute("SELECT COUNT(*) workouts, COALESCE(SUM(duration_minutes),0) minutes, COALESCE(SUM(volume_kg),0) volume, COALESCE(SUM(sets_completed),0) sets FROM workouts WHERE user_id=?", (user_id,)).fetchone()
        since = (datetime.now() - timedelta(days=7)).isoformat()
        week = self.conn.execute("SELECT COUNT(*) FROM workouts WHERE user_id=? AND started_at>=?", (user_id, since)).fetchone()[0]
        prs = self.conn.execute("SELECT e.name,e.muscles,MAX(ws.weight_kg) best FROM workout_sets ws JOIN workouts w ON w.id=ws.workout_id JOIN exercises e ON e.id=ws.exercise_id WHERE w.user_id=? AND ws.done=1 GROUP BY e.id HAVING best>0 ORDER BY best DESC", (user_id,)).fetchall()
        return {**dict(base), "week": week, "prs": prs}

    def close(self):
        self.conn.close()


# ======================================================================
# Scrollable container shared by every long page / dialog
# ======================================================================
class ScrollFrame(tk.Frame):
    """Canvas + inner frame + visible scrollbar. Mouse-wheel handled by FitTrackApp._on_wheel."""

    def __init__(self, parent, bg=BG, center=False):
        super().__init__(parent, bg=bg)
        self.center = center
        self.canvas = tk.Canvas(self, bg=bg, highlightthickness=0, borderwidth=0, yscrollincrement=20)
        self.scrollbar = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.inner = tk.Frame(self.canvas, bg=bg)
        self._win = self.canvas.create_window((0, 0), window=self.inner, anchor="nw")
        self.canvas.configure(yscrollcommand=self.scrollbar.set)
        self.canvas._ft_canvas = self.canvas
        self._ft_canvas = self.canvas
        self.inner.bind("<Configure>", lambda _e: self._fit())
        self.canvas.bind("<Configure>", lambda _e: self._fit())
        self.canvas.pack(side="left", fill="both", expand=True)
        self.scrollbar.pack(side="right", fill="y")

    def _fit(self):
        w, h = self.canvas.winfo_width(), self.canvas.winfo_height()
        req = self.inner.winfo_reqheight()
        height = max(h, req) if self.center else req
        self.canvas.itemconfigure(self._win, width=max(1, w), height=height)
        self.canvas.configure(scrollregion=(0, 0, max(1, w), max(height, 1)))

    def to_top(self):
        self.canvas.yview_moveto(0)

# ======================================================================
# Application
# ======================================================================
class FitTrackApp(tk.Tk):
    def __init__(self, db_path: Path | None = None):
        super().__init__()
        self.title("FitTrack — Workout Management System")
        self.geometry("1220x800")
        self.minsize(920, 650)
        self.configure(bg=BG)
        self.db = FitTrackDB(db_path or DB_PATH)
        self.user = None
        self.active_routine = None
        self.workout_started = None
        self.tracking_rows = []
        self.page = None
        self.nav_buttons = {}
        self._style_ttk()
        # One global wheel handler: scrolls whichever ScrollFrame is under the pointer.
        self.bind_all("<MouseWheel>", self._on_wheel)
        self.bind_all("<Button-4>", self._on_wheel)
        self.bind_all("<Button-5>", self._on_wheel)
        self.show_auth()
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    # ------------------------------------------------------------ styling / widgets
    def _style_ttk(self):
        style = ttk.Style(self)
        try: style.theme_use("clam")
        except tk.TclError: pass
        style.configure("Treeview", background=PANEL, foreground=TEXT, fieldbackground=PANEL, rowheight=30, borderwidth=0)
        style.configure("Treeview.Heading", background=BLUE_LIGHT, foreground=BLUE_DARK, relief="flat", font=("Segoe UI", 9, "bold"))
        style.map("Treeview", background=[("selected", BLUE_LIGHT)], foreground=[("selected", TEXT)])
        style.configure("TCombobox", fieldbackground=PANEL_2, background=PANEL_2, foreground=TEXT, arrowcolor=BLUE, bordercolor=BORDER)
        style.map("TCombobox", fieldbackground=[("readonly", PANEL_2)], foreground=[("readonly", TEXT)])
        style.configure("Vertical.TScrollbar", background=BORDER, troughcolor=PANEL_2, arrowcolor=MUTED, bordercolor=PANEL_2)
        self.option_add("*TCombobox*Listbox.background", PANEL)
        self.option_add("*TCombobox*Listbox.foreground", TEXT)
        self.option_add("*TCombobox*Listbox.selectBackground", BLUE_LIGHT)
        self.option_add("*TCombobox*Listbox.selectForeground", TEXT)

    def button(self, parent, text, command, primary=False, **kwargs):
        return tk.Button(parent, text=text, command=command, bg=BLUE if primary else PANEL_2, fg="#ffffff" if primary else TEXT,
                         activebackground=BLUE_DARK if primary else BLUE_LIGHT, activeforeground="#ffffff" if primary else TEXT,
                         disabledforeground="#9fb4d9" if primary else MUTED,
                         relief="flat", bd=0, cursor="hand2", font=("Segoe UI", 10, "bold"), padx=14, pady=10, **kwargs)

    def label(self, parent, text, size=10, color=TEXT, bold=False, **kwargs):
        return tk.Label(parent, text=text, bg=kwargs.pop("bg", parent.cget("bg") if hasattr(parent, "cget") else BG), fg=color,
                        font=("Segoe UI", size, "bold" if bold else "normal"), **kwargs)

    def entry(self, parent, textvariable=None, width=None, show=None, no_space=False):
        e = tk.Entry(parent, textvariable=textvariable, width=width, show=show, bg=PANEL_2, fg=TEXT, insertbackground=BLUE,
                     relief="flat", bd=0, highlightthickness=1, highlightbackground=BORDER, highlightcolor=BLUE,
                     font=("Segoe UI", 11))
        if no_space:
            # Block the space bar and strip whitespace from pasted text.
            e.bind("<space>", lambda _e: "break")
            e.bind("<<Paste>>", lambda ev: self._paste_no_space(ev.widget))
            e.bind("<Control-v>", lambda ev: self._paste_no_space(ev.widget))
            e.bind("<Control-V>", lambda ev: self._paste_no_space(ev.widget))
        return e

    def _paste_no_space(self, widget):
        """Paste clipboard text with all whitespace removed."""
        try:
            text = "".join(self.clipboard_get().split())
        except tk.TclError:
            return "break"
        try:
            if widget.selection_present():
                widget.delete("sel.first", "sel.last")
        except tk.TclError:
            pass
        widget.insert("insert", text)
        return "break"

    def field(self, parent, caption, variable=None, show=None, width=32, no_space=False):
        wrap = tk.Frame(parent, bg=parent.cget("bg"))
        self.label(wrap, caption, 9, MUTED, True).pack(anchor="w", pady=(0, 6))
        ent = self.entry(wrap, variable, width, show, no_space=no_space)
        ent.pack(fill="x", ipady=10)
        return wrap, ent

    def combo(self, parent, variable, values):
        cb = ttk.Combobox(parent, textvariable=variable, values=values, state="readonly")
        cb.bind("<MouseWheel>", lambda _e: "break")  # wheel must not change a dropdown by accident
        return cb

    def card(self, parent, **kwargs):
        return tk.Frame(parent, bg=PANEL, padx=18, pady=17, highlightbackground=BORDER, highlightthickness=1, **kwargs)

    def metric_card(self, parent, title, value, note):
        f = self.card(parent)
        self.label(f, title.upper(), 8, MUTED, True).pack(anchor="w")
        self.label(f, str(value), 25, BLUE, True).pack(anchor="w", pady=(12, 2))
        self.label(f, note, 8, MUTED).pack(anchor="w")
        return f

    def _on_wheel(self, event):
        """Scroll the ScrollFrame under the pointer (Windows, macOS, Linux); ignore dropdowns/tables."""
        try:
            w = self.winfo_containing(event.x_root, event.y_root)
        except (KeyError, tk.TclError):
            return None
        canvas = None
        while w is not None:
            if isinstance(w, (ttk.Combobox, ttk.Treeview, tk.Listbox, tk.Text)):
                return None
            canvas = getattr(w, "_ft_canvas", None)
            if canvas is not None:
                break
            w = getattr(w, "master", None)
        if canvas is None or not canvas.winfo_exists():
            return None
        bbox = canvas.bbox("all")
        if bbox is None or (bbox[3] - bbox[1]) <= canvas.winfo_height():
            return None  # nothing to scroll
        num = getattr(event, "num", None)
        if num == 4: direction = -1
        elif num == 5: direction = 1
        else:
            delta = getattr(event, "delta", 0)
            if not delta: return "break"
            direction = -1 if delta > 0 else 1
        canvas.yview_scroll(direction * 3, "units")
        return "break"

    # ------------------------------------------------------------ auth
    def show_auth(self):
        self.auth_signup = False
        self.nav_buttons = {}
        for child in self.winfo_children(): child.destroy()
        root = tk.Frame(self, bg=BG)
        root.pack(fill="both", expand=True)
        LEFT, ROW = BLUE_DARK, "#2f63e6"
        left = tk.Frame(root, bg=LEFT, width=510, padx=45, pady=40)
        left.pack(side="left", fill="both", expand=True)
        left.pack_propagate(False)
        mark = tk.Frame(left, bg="#ffffff", width=45, height=45)
        mark.pack(anchor="w")
        mark.pack_propagate(False)
        tk.Label(mark, text="⚡", bg="#ffffff", fg=BLUE, font=("Segoe UI", 20, "bold")).place(relx=.5, rely=.5, anchor="center")
        tk.Label(left, text="fittrack.", bg=LEFT, fg="#ffffff", font=("Segoe UI", 23, "bold")).pack(anchor="w", pady=(14, 0))
        tk.Label(left, text="TRAIN WITH PURPOSE", bg=LEFT, fg="#bcd3ff", font=("Segoe UI", 8, "bold")).pack(anchor="w")
        tk.Frame(left, bg=LEFT, height=45).pack()
        tk.Label(left, text="YOUR FITNESS, IN FOCUS", bg=LEFT, fg="#bcd3ff", font=("Segoe UI", 9, "bold")).pack(anchor="w")
        tk.Label(left, text="Show up today.\nGet stronger tomorrow.", bg=LEFT, fg="#ffffff", font=("Segoe UI", 31, "bold"), justify="left").pack(anchor="w", pady=(16, 12))
        tk.Label(left, text="Create routines, track your workouts, and celebrate progress — one rep at a time.", bg=LEFT, fg="#dbe7ff", font=("Segoe UI", 12), wraplength=410, justify="left").pack(anchor="w")
        for title, subtitle in [("Plan your workouts", "Routines that match your goals"), ("Track every set", "Weights, reps, and training volume"), ("See your progress", "Workout history and personal records")]:
            row = tk.Frame(left, bg=ROW, padx=13, pady=12, highlightbackground="#5a86ee", highlightthickness=1)
            row.pack(fill="x", pady=(16, 0))
            tk.Label(row, text="✓", fg="#ffffff", bg=ROW, font=("Segoe UI", 17, "bold")).pack(side="left", padx=(0, 12))
            col = tk.Frame(row, bg=ROW); col.pack(side="left", fill="x")
            tk.Label(col, text=title, bg=ROW, fg="#ffffff", font=("Segoe UI", 11, "bold")).pack(anchor="w")
            tk.Label(col, text=subtitle, bg=ROW, fg="#dbe7ff", font=("Segoe UI", 9)).pack(anchor="w", pady=(4, 0))

        # right side scrolls so the taller signup form still fits small windows
        self.auth_scroll = ScrollFrame(root, bg=BG, center=True)
        self.auth_scroll.pack(side="right", fill="both", expand=True)
        card = tk.Frame(self.auth_scroll.inner, bg=PANEL, padx=28, pady=28, highlightbackground=BORDER, highlightthickness=1)
        card.pack(expand=True, fill="x", padx=35, pady=25)
        self.auth_card = card
        self._render_auth_card()

    def _show_toggle(self, parent, entry):
        var = tk.BooleanVar(value=False)
        tk.Checkbutton(parent, text="Show password", variable=var,
                       command=lambda: entry.configure(show="" if var.get() else "•"),
                       bg=PANEL, fg=MUTED, activebackground=PANEL, activeforeground=BLUE, selectcolor=PANEL_2,
                       relief="flat", font=("Segoe UI", 9), cursor="hand2").pack(anchor="w", pady=(4, 8))
        return var

    def _render_auth_card(self):
        for child in self.auth_card.winfo_children(): child.destroy()
        signup = self.auth_signup
        self.label(self.auth_card, "YOUR PERSONAL WORKOUT SPACE", 9, BLUE, True).pack(anchor="w")
        self.label(self.auth_card, "Create your account" if signup else "Welcome back.", 23, TEXT, True).pack(anchor="w", pady=(12, 4))
        self.label(self.auth_card, "Sign up to start tracking." if signup else "Log in to continue your fitness journey.", 10, MUTED).pack(anchor="w", pady=(0, 18))
        self.auth_name = tk.StringVar()
        self.auth_email = tk.StringVar()
        self.auth_pass = tk.StringVar()
        self.auth_confirm = tk.StringVar()
        if signup:
            wrap, _ = self.field(self.auth_card, "DISPLAY NAME", self.auth_name)
            wrap.pack(fill="x", pady=(0, 12))
        wrap, self.email_entry = self.field(self.auth_card, "EMAIL", self.auth_email)
        wrap.pack(fill="x", pady=(0, 12))
        # Spaces are blocked only when creating an account; login stays open so older accounts still work.
        wrap, self.password_entry = self.field(self.auth_card, "PASSWORD", self.auth_pass, show="•", no_space=signup)
        wrap.pack(fill="x", pady=(0, 2))
        self.show_password_var = self._show_toggle(self.auth_card, self.password_entry)
        self.auth_error_label = tk.Label(self.auth_card, text="", bg=PANEL, fg=RED, font=("Segoe UI", 9), wraplength=340, justify="left")
        self.indicator_labels = []
        self.match_label = None
        if signup:
            box = tk.Frame(self.auth_card, bg=PANEL); box.pack(fill="x", pady=(0, 8))
            self.indicator_box = box
            for _ in range(5):
                lbl = tk.Label(box, text="", bg=PANEL, fg=MUTED, font=("Segoe UI", 9), anchor="w")
                lbl.pack(fill="x"); self.indicator_labels.append(lbl)
            self.match_label = tk.Label(box, text="", bg=PANEL, fg=MUTED, font=("Segoe UI", 9), anchor="w")
            wrap, self.confirm_entry = self.field(self.auth_card, "CONFIRM PASSWORD", self.auth_confirm, show="•", no_space=True)
            wrap.pack(fill="x", pady=(6, 2))
            self.show_confirm_var = self._show_toggle(self.auth_card, self.confirm_entry)
        self.auth_error_label.pack(anchor="w", pady=(0, 7))
        self.submit_btn = self.button(self.auth_card, "CREATE ACCOUNT" if signup else "LOG IN", self._submit_auth, primary=True)
        self.submit_btn.pack(fill="x")
        row = tk.Frame(self.auth_card, bg=PANEL); row.pack(pady=(16, 8))
        self.label(row, "Already have an account?" if signup else "New to FitTrack?", 9, MUTED).pack(side="left")
        link = self.button(row, "Log in" if signup else "Sign up", self._toggle_auth_mode)
        link.configure(bg=PANEL, fg=BLUE, padx=8, pady=4, activebackground=PANEL, activeforeground=BLUE_DARK)
        link.pack(side="left")
        self.label(self.auth_card, "Your workout data is saved in a local SQLite database on this computer.", 9, MUTED, wraplength=340, justify="center").pack(fill="x", pady=(14, 0))
        if signup:
            for v in (self.auth_name, self.auth_email, self.auth_pass, self.auth_confirm):
                v.trace_add("write", lambda *_: self._update_signup_state())
            self._update_signup_state()
        for w in (self.email_entry, self.password_entry):
            w.bind("<Return>", lambda _e: self._submit_auth())
        self.email_entry.focus_set()

    def _update_signup_state(self):
        """Live password indicators + enable/disable the Create Account button."""
        if not self.auth_signup or not self.indicator_labels:
            return
        pw, confirm = self.auth_pass.get(), self.auth_confirm.get()
        checks = password_checks(pw, confirm)
        n = len(self.indicator_labels)  # 5 fixed rules; "Passwords match" is checks[5]
        for lbl, (text, ok) in zip(self.indicator_labels, checks[:n]):
            lbl.configure(text=("✓  " if ok else "○  ") + text, fg=OK if ok else (MUTED if not pw else RED))
        if confirm != "":
            text, ok = checks[n]
            self.match_label.configure(text=("✓  " if ok else "✗  ") + text, fg=OK if ok else RED)
            if not self.match_label.winfo_ismapped():
                self.match_label.pack(fill="x")
        else:
            self.match_label.pack_forget()
        ready = all(ok for _, ok in checks) and confirm != "" and bool(self.auth_name.get().strip()) and bool(self.auth_email.get().strip())
        self.submit_btn.configure(state="normal" if ready else "disabled", cursor="hand2" if ready else "arrow")

    def _set_auth_msg(self, text, ok=False):
        self.auth_error_label.configure(text=text, fg=OK if ok else RED)

    def _toggle_auth_mode(self):
        self.auth_signup = not self.auth_signup
        self._render_auth_card()

    def _submit_auth(self):
        email = normalize_email(self.auth_email.get())
        password = self.auth_pass.get()
        if self.auth_signup:
            name = self.auth_name.get().strip()
            if not name:
                self._set_auth_msg("Enter your display name."); return
            err = validate_email(email)
            if err:
                self._set_auth_msg(err); return
            failed = [t for t, ok in password_checks(password) if not ok]
            if failed:
                self._set_auth_msg("Your password still needs: " + "; ".join(t.lower() for t in failed) + "."); return
            if password != self.auth_confirm.get():
                self._set_auth_msg("The passwords do not match. Please re-enter them."); return
            uid = self.db.create_user(email, name, password)
            if not uid:
                self._set_auth_msg("That email is already registered. Try logging in instead."); return
            # Registration does not sign the user in: return to the login form.
            self.auth_signup = False
            self._render_auth_card()
            self.auth_email.set(email)
            self._set_auth_msg("Account created successfully. Please log in to continue.", ok=True)
            self.password_entry.focus_set()
            return
        if not email:
            self._set_auth_msg("Enter your email address."); return
        if not password:
            self._set_auth_msg("Enter your password."); return
        self.user = self.db.verify_user(email, password)
        if not self.user:
            self._set_auth_msg("Email or password is incorrect."); return
        self._after_login()

    # ------------------------------------------------------------ shell / navigation
    def _after_login(self):
        """Required flow: Login -> (profile setup if incomplete) -> dashboard."""
        if self.db.profile_complete(self.user["id"]):
            self.show_shell()
        else:
            self.show_setup()

    def show_shell(self, open_builder=None):
        if self.user is None or not self.db.profile_complete(self.user["id"]):
            if self.user is not None:
                self.show_setup()
            return  # never reach the dashboard without a login and a completed profile
        for child in self.winfo_children(): child.destroy()
        shell = tk.Frame(self, bg=BG); shell.pack(fill="both", expand=True)
        sidebar = tk.Frame(shell, bg=SIDEBAR, width=235, padx=15, pady=20, highlightbackground=BORDER, highlightthickness=1)
        sidebar.pack(side="left", fill="y"); sidebar.pack_propagate(False)
        tk.Label(sidebar, text="⚡  fittrack.", bg=SIDEBAR, fg=BLUE, font=("Segoe UI", 22, "bold")).pack(anchor="w", padx=7, pady=(4, 1))
        tk.Label(sidebar, text="TRAIN WITH PURPOSE", bg=SIDEBAR, fg=MUTED, font=("Segoe UI", 8, "bold")).pack(anchor="w", padx=9, pady=(0, 24))
        self.label(sidebar, "WORKSPACE", 8, MUTED, True).pack(anchor="w", padx=10, pady=(0, 10))
        nav_items = [("Overview", "⌂"), ("Routines", "▤"), ("Exercise Library", "▦"), ("Track Workout", "◉"), ("Progress", "▥"), ("Workout History", "◷"), ("Personal Records", "♛"), ("Recommendations", "✦"), ("Profile", "♙")]
        self.nav_buttons = {}
        for name, icon in nav_items:
            row = tk.Frame(sidebar, bg=SIDEBAR); row.pack(fill="x", pady=2)
            ind = tk.Frame(row, bg=SIDEBAR, width=4); ind.pack(side="left", fill="y")
            b = tk.Button(row, text=f"{icon}   {name}", command=lambda n=name: self.show_page(n), anchor="w", bg=SIDEBAR, fg=TEXT,
                          activebackground=BLUE_LIGHT, activeforeground=BLUE, relief="flat", bd=0, padx=12, pady=10,
                          font=("Segoe UI", 10, "bold"), cursor="hand2")
            b.pack(side="left", fill="x", expand=True)
            self.nav_buttons[name] = (ind, b)
        bottom = tk.Frame(sidebar, bg=SIDEBAR); bottom.pack(side="bottom", fill="x", pady=5)
        tk.Frame(bottom, bg=BORDER, height=1).pack(fill="x", pady=(0, 12))
        tk.Label(bottom, text=self.user["display_name"], bg=SIDEBAR, fg=TEXT, font=("Segoe UI", 10, "bold")).pack(anchor="w", padx=8)
        tk.Label(bottom, text=self.user["email"], bg=SIDEBAR, fg=MUTED, font=("Segoe UI", 8)).pack(anchor="w", padx=8, pady=(3, 10))
        self.button(bottom, "Sign out", self.sign_out).pack(fill="x", padx=4)
        main = tk.Frame(shell, bg=BG); main.pack(side="right", fill="both", expand=True)
        header = tk.Frame(main, bg=BG, padx=25, pady=17); header.pack(fill="x")
        self.breadcrumb = tk.Label(header, text="Workspace  /  Overview", bg=BG, fg=MUTED, font=("Segoe UI", 10)); self.breadcrumb.pack(side="left")
        tk.Label(header, text="●  YOUR FITNESS, IN FOCUS", bg=BG, fg=BLUE, font=("Segoe UI", 8, "bold")).pack(side="right")
        self.content_host = tk.Frame(main, bg=BG, padx=25, pady=8)
        self.content_host.pack(fill="both", expand=True)
        self.content = self.content_host
        self.show_page("Routines" if open_builder else "Overview")
        if open_builder:
            self.after(120, lambda: self.create_routine_dialog(open_builder))

    def _highlight_nav(self, name):
        for n, (ind, b) in self.nav_buttons.items():
            active = n == name
            ind.configure(bg=BLUE if active else SIDEBAR)
            b.configure(bg=BLUE_LIGHT if active else SIDEBAR, fg=BLUE_DARK if active else TEXT)

    def clear_content(self):
        for child in self.content_host.winfo_children():
            child.destroy()
        self.content = self.content_host

    def scroll_body(self, fixed_top=False):
        """Create a ScrollFrame filling the page. Returns its inner frame (also set as self.content)."""
        sf = ScrollFrame(self.content_host, bg=BG)
        sf.pack(fill="both", expand=True)
        self.content = sf.inner
        return sf

    def heading(self, eyebrow, title, subtitle=""):
        self.label(self.content, eyebrow.upper(), 8, BLUE, True).pack(anchor="w")
        self.label(self.content, title, 25, TEXT, True).pack(anchor="w", pady=(7, 3))
        if subtitle: self.label(self.content, subtitle, 10, MUTED, wraplength=900, justify="left").pack(anchor="w", pady=(0, 14))
        else: tk.Frame(self.content, bg=BG, height=15).pack()

    def show_page(self, name):
        self.page = name
        self.breadcrumb.configure(text=f"Workspace  /  {name}")
        self._highlight_nav(name)
        self.clear_content()
        method = {
            "Overview": self.page_overview, "Routines": self.page_routines,
            "Exercise Library": self.page_library, "Track Workout": self.page_track,
            "Progress": self.page_progress, "Workout History": self.page_history,
            "Personal Records": self.page_records, "Recommendations": self.page_recommendations,
            "Profile": self.page_profile,
        }[name]
        method()

    # ------------------------------------------------------------ required profile setup
    def _unit_field(self, parent, caption, var, unit):
        wrap = tk.Frame(parent, bg=parent.cget("bg"))
        self.label(wrap, caption, 9, MUTED, True).pack(anchor="w", pady=(0, 6))
        row = tk.Frame(wrap, bg=parent.cget("bg")); row.pack(fill="x")
        ent = self.entry(row, var, 12); ent.pack(side="left", fill="x", expand=True, ipady=9)
        self.label(row, unit, 10, BLUE, True, bg=parent.cget("bg")).pack(side="left", padx=(10, 0))
        return wrap, ent

    def show_setup(self):
        for child in self.winfo_children(): child.destroy()
        p = self.db.profile(self.user["id"])
        sf = ScrollFrame(self, bg=BG, center=True); sf.pack(fill="both", expand=True)
        card = tk.Frame(sf.inner, bg=PANEL, padx=32, pady=28, highlightbackground=BORDER, highlightthickness=1)
        card.pack(expand=True, padx=40, pady=28)
        self.label(card, "STEP 1 OF 2  ·  PERSONAL PROFILE SETUP", 9, BLUE, True).pack(anchor="w")
        self.label(card, "Tell us about you", 23, TEXT, True).pack(anchor="w", pady=(10, 4))
        self.label(card, f"Welcome, {p['display_name']}. Age, height and weight are required so FitTrack can tailor your workouts "
                         "safely. You can update them later in Profile.", 10, MUTED, wraplength=460, justify="left").pack(anchor="w", pady=(0, 16))
        fmt = lambda v: "" if v is None else f"{v:g}"
        v = {"age": tk.StringVar(value=fmt(p["age"])), "height": tk.StringVar(value=fmt(p["height_cm"])),
             "weight": tk.StringVar(value=fmt(p["body_weight"])), "goal": tk.StringVar(value=p["fitness_goal"]),
             "level": tk.StringVar(value=p["experience_level"]), "confirm": tk.BooleanVar(value=False)}
        self.setup_vars = v
        for cap, key, unit in (("AGE", "age", "years"), ("HEIGHT", "height", "cm"), ("WEIGHT", "weight", "kg")):
            wrap, ent = self._unit_field(card, cap + " *", v[key], unit); wrap.pack(fill="x", pady=(0, 12))
            if key == "age": ent.focus_set()
        self.label(card, "FITNESS GOAL", 9, MUTED, True).pack(anchor="w", pady=(0, 5))
        self.combo(card, v["goal"], GOALS).pack(fill="x", ipady=5, pady=(0, 12))
        self.label(card, "TRAINING EXPERIENCE", 9, MUTED, True).pack(anchor="w", pady=(0, 5))
        self.combo(card, v["level"], LEVELS).pack(fill="x", ipady=5, pady=(0, 12))
        tk.Checkbutton(card, text="I confirm these details are correct", variable=v["confirm"], bg=PANEL, fg=TEXT,
                       activebackground=PANEL, activeforeground=BLUE, selectcolor=BLUE_LIGHT, font=("Segoe UI", 10),
                       cursor="hand2").pack(anchor="w", pady=(4, 8))
        self.setup_error = tk.Label(card, text="", bg=PANEL, fg=RED, font=("Segoe UI", 9), wraplength=460, justify="left")
        self.setup_error.pack(anchor="w", pady=(0, 8))
        self.button(card, "Save & see my recommendations", self._submit_setup, primary=True).pack(fill="x")
        row = tk.Frame(card, bg=PANEL); row.pack(fill="x", pady=(10, 0))
        self.button(row, "Sign out", self.sign_out).pack(side="left")

    def _submit_setup(self):
        v = self.setup_vars
        vals, errors = validate_body(v["age"].get(), v["height"].get(), v["weight"].get())
        if errors:
            self.setup_error.configure(text="\n".join("• " + e for e in errors)); return
        if not v["confirm"].get():
            self.setup_error.configure(text="• Please tick the box to confirm your details are correct."); return
        try:
            self.db.save_body(self.user["id"], v["age"].get(), v["height"].get(), v["weight"].get(), v["goal"].get(), v["level"].get())
        except ValueError as err:
            self.setup_error.configure(text="\n".join("• " + e for e in str(err).splitlines())); return
        self.show_recommendation_screen()

    def show_recommendation_screen(self):
        for child in self.winfo_children(): child.destroy()
        root = tk.Frame(self, bg=BG); root.pack(fill="both", expand=True)
        bar = tk.Frame(root, bg=PANEL, padx=22, pady=12, highlightbackground=BORDER, highlightthickness=1)
        bar.pack(side="bottom", fill="x")
        self.button(bar, "← Edit my details", self.show_setup).pack(side="left")
        self.button(bar, "Continue to dashboard ▸", lambda: self.show_shell(), primary=True).pack(side="right")
        self.button(bar, "Create this workout", lambda: self._feed_create_workout(True)).pack(side="right", padx=(0, 10))
        sf = ScrollFrame(root, bg=BG); sf.pack(fill="both", expand=True)
        body = tk.Frame(sf.inner, bg=BG, padx=28, pady=20); body.pack(fill="both", expand=True)
        self.label(body, "STEP 2 OF 2  ·  YOUR PERSONALIZED PLAN", 8, BLUE, True).pack(anchor="w")
        self.label(body, "Your workout recommendations", 25, TEXT, True).pack(anchor="w", pady=(7, 3))
        self.label(body, "Review the cards, tap “Add to routine” on the ones you like, then continue to your dashboard to build a routine.",
                   10, MUTED, wraplength=820, justify="left").pack(anchor="w", pady=(0, 14))
        self._build_feed(body, in_setup=True)

    def _feed_create_workout(self, in_setup):
        st = self.feed
        names = [n for n in st["names"] if n in st["selected"]] or list(st["names"])
        goal = st["goal"].get()
        preset = {"name": f"{goal} Plan", "focus": goal, "exercises": names}
        if in_setup:
            self.show_shell(open_builder=preset)
        else:
            self.create_routine_dialog(preset)

    def _build_feed(self, parent, in_setup=False):
        """Recommendation feed of workout cards; shared by the setup flow and the Recommendations page."""
        goal = tk.StringVar(value=self.db.profile(self.user["id"])["fitness_goal"])
        st = self.feed = {"selected": set(), "names": [], "goal": goal}
        panel = self.card(parent); panel.pack(fill="x", pady=(0, 12))
        self.label(panel, "WHAT'S YOUR FOCUS?", 9, BLUE, True).pack(anchor="w")
        top = tk.Frame(panel, bg=PANEL); top.pack(fill="x", pady=(8, 0))
        cb = self.combo(top, goal, GOALS); cb.pack(side="left", fill="x", expand=True, ipady=5)
        self.button(top, "↻ Refresh recommendation", lambda: render()).pack(side="left", padx=(8, 0))
        note = self.label(panel, "", 9, MUTED, wraplength=760, justify="left"); note.pack(anchor="w", pady=(8, 0))
        count = self.label(panel, "", 9, BLUE, True); count.pack(anchor="w", pady=(4, 0))
        result = tk.Frame(parent, bg=BG); result.pack(fill="both", expand=True)

        def update_count():
            n = len(st["selected"])
            count.configure(text=f"{n} exercise{'s' if n != 1 else ''} added to your routine" if n else "Tap “Add to routine” on any card to build a workout.")

        def toggle(name, btn):
            if name in st["selected"]:
                st["selected"].discard(name); btn.configure(text="＋ Add to routine", bg=BLUE, fg="#ffffff")
            else:
                if len(st["selected"]) >= MAX_ROUTINE_EXERCISES:
                    messagebox.showwarning("Exercise limit reached", f"A routine can have at most {MAX_ROUTINE_EXERCISES} exercises."); return
                st["selected"].add(name); btn.configure(text="✓ Added", bg=OK, fg="#ffffff")
            update_count()

        def render():
            for w in result.winfo_children(): w.destroy()
            prof = self.db.profile(self.user["id"])  # always the newest saved profile
            level, g, args = prof["experience_level"], goal.get(), profile_args(prof)
            bits = [f"{prof['age']} yrs" if prof["age"] is not None else None, f"{prof['height_cm']:g} cm" if prof["height_cm"] is not None else None,
                    f"{prof['body_weight']:g} kg" if prof["body_weight"] is not None else None, level]
            note.configure(text="Personalized for: " + " · ".join(b for b in bits if b) +
                           ". Age, experience and exercise difficulty shape the sets, reps and loads; height and weight add context only and never set exact weights.")
            rows = list(self.db.exercises())
            chosen = select_exercises(rows, g, level, prof["age"])
            st["names"] = [e["name"] for e in chosen]
            st["selected"] &= set(st["names"])
            self.label(result, f"RECOMMENDED FOR YOU · {g.upper()}", 9, BLUE, True).pack(anchor="w", pady=(0, 6))
            for ex in chosen:
                self._rec_card(result, ex, recommend(ex, g, level, **args), toggle)
            hidden = [n for n in EXERCISE_FOCUS_MAP.get(g, []) if n not in st["names"]]
            if hidden:
                tip = self.card(result); tip.pack(fill="x", pady=6)
                self.label(tip, "WHEN YOU'RE READY TO PROGRESS", 9, BLUE, True).pack(anchor="w")
                self.label(tip, "Master the basics above first. After a few consistent weeks with steady form, you can add: " + ", ".join(hidden) +
                           " - starting with bodyweight or very light resistance.", 9, MUTED, wraplength=760, justify="left").pack(anchor="w", pady=(4, 0))
            self.label(result, WEIGHT_DISCLAIMER, 8, MUTED, wraplength=760, justify="left").pack(anchor="w", pady=(8, 0))
            if not in_setup:
                self.button(result, "Create This Workout", lambda: self._feed_create_workout(False), primary=True).pack(anchor="w", pady=12)
            update_count()
        st["render"] = render
        cb.bind("<<ComboboxSelected>>", lambda _e: render())
        render()

    def _rec_card(self, parent, ex, rec, toggle):
        outer = tk.Frame(parent, bg=PANEL, highlightbackground=BORDER, highlightthickness=1)
        outer.pack(fill="x", pady=6)
        banner = tk.Frame(outer, bg=BLUE_LIGHT, padx=14, pady=6); banner.pack(fill="x")
        self.label(banner, "★  RECOMMENDED FOR YOU", 8, BLUE_DARK, True, bg=BLUE_LIGHT).pack(side="left")
        self.label(banner, f"{ex['level']}  ·  {ex['equipment']}", 8, BLUE_DARK, True, bg=BLUE_LIGHT).pack(side="right")
        body = tk.Frame(outer, bg=PANEL, padx=16, pady=12); body.pack(fill="x")
        art = tk.Frame(body, bg=BLUE_LIGHT, width=92, height=92, highlightbackground=HERO_BORDER, highlightthickness=1)
        art.pack(side="left", anchor="n", padx=(0, 14)); art.pack_propagate(False)
        tk.Label(art, text="✦", bg=BLUE_LIGHT, fg=BLUE, font=("Segoe UI", 34)).pack(expand=True)
        btns = tk.Frame(body, bg=PANEL); btns.pack(side="right", anchor="n", padx=(10, 0))
        self.button(btns, "View details", lambda e=dict(ex): self.tutorial_dialog(e)).pack(fill="x", pady=2)
        add = self.button(btns, "＋ Add to routine", lambda: None, primary=True); add.pack(fill="x", pady=2)
        add.configure(command=lambda n=ex["name"], b=add: toggle(n, b))
        if ex["name"] in self.feed["selected"]: add.configure(text="✓ Added", bg=OK)
        col = tk.Frame(body, bg=PANEL); col.pack(side="left", fill="x", expand=True)
        W = 520
        self.label(col, ex["name"], 14, TEXT, True).pack(anchor="w")
        self.label(col, f"Target muscles: {ex['muscles']}", 9, MUTED).pack(anchor="w", pady=(3, 0))
        self.label(col, f"Equipment: {ex['equipment']}", 9, MUTED).pack(anchor="w")
        self.label(col, f"{rec['sets']} sets × {rec['reps_text']}   ·   Rest {rec['rest']}", 10, BLUE, True, wraplength=W, justify="left").pack(anchor="w", pady=(6, 0))
        if rec["weight_text"]:
            self.label(col, f"Suggested start: {rec['weight_text']}", 9, TEXT, wraplength=W, justify="left").pack(anchor="w", pady=(2, 0))
        if rec["steps"]:
            self.label(col, "How to do it:", 9, TEXT, True).pack(anchor="w", pady=(8, 0))
            self.label(col, "\n".join(f"{i}. {t}" for i, t in enumerate(rec["steps"], 1)), 9, MUTED, wraplength=W, justify="left").pack(anchor="w")
        self.label(col, f"Why this for you: {rec['reason']}", 9, TEXT, wraplength=W, justify="left").pack(anchor="w", pady=(8, 0))
        for line in rec["personal"] + ([rec["note"]] if rec["note"] else []):
            self.label(col, "• " + line, 9, MUTED, wraplength=W, justify="left").pack(anchor="w", pady=(2, 0))
        self.label(col, f"Progress gradually: {rec['progression']}", 9, MUTED, wraplength=W, justify="left").pack(anchor="w", pady=(6, 0))

    # ------------------------------------------------------------ shared recommendation block
    def rec_block(self, parent, ex, rec, bg=PANEL):
        self.label(parent, f"{rec['sets']} sets × {rec['reps_text']}", 10, BLUE, True, bg=bg).pack(anchor="w", pady=(4, 0))
        self.label(parent, f"Equipment: {ex['equipment']}", 9, MUTED, bg=bg).pack(anchor="w", pady=(2, 0))
        self.label(parent, f"Rest: {rec['rest']}", 9, MUTED, bg=bg, wraplength=560, justify="left").pack(anchor="w", pady=(2, 0))
        if rec["weight_text"]:
            self.label(parent, f"Suggested start: {rec['weight_text']}", 9, TEXT, bg=bg, wraplength=560, justify="left").pack(anchor="w", pady=(2, 0))
        self.label(parent, f"Why: {rec['reason']}", 9, MUTED, bg=bg, wraplength=560, justify="left").pack(anchor="w", pady=(2, 0))
        for line in rec.get("personal", []) + ([rec["note"]] if rec.get("note") else []):
            self.label(parent, "• " + line, 9, MUTED, bg=bg, wraplength=560, justify="left").pack(anchor="w", pady=(2, 0))

    # ------------------------------------------------------------ pages
    def page_overview(self):
        self.scroll_body()
        p = self.db.profile(self.user["id"]); stats = self.db.stats(self.user["id"])
        self.heading("Your training space", f"Let's get stronger, {p['display_name']}.", "A little progress today goes a long way. Ready for your next session?")
        hero = tk.Frame(self.content, bg=HERO, padx=25, pady=20, highlightbackground=HERO_BORDER, highlightthickness=1)
        hero.pack(fill="x", pady=(0, 18))
        tk.Label(hero, text="YOUR WEEKLY MOMENTUM", bg=HERO, fg=BLUE, font=("Segoe UI", 8, "bold")).pack(anchor="w")
        tk.Label(hero, text="Progress isn't always loud.\nKeep showing up.", bg=HERO, fg=TEXT, font=("Segoe UI", 22, "bold"), justify="left").pack(anchor="w", pady=(10, 4))
        tk.Label(hero, text="Build a routine that fits your life. Track the work, celebrate the wins.", bg=HERO, fg=MUTED, font=("Segoe UI", 10)).pack(anchor="w", pady=(0, 14))
        self.button(hero, "＋  Plan a workout", lambda: self.show_page("Routines"), primary=True).pack(anchor="w")
        metrics = tk.Frame(self.content, bg=BG); metrics.pack(fill="x", pady=(0, 18))
        vals = [("Workouts logged", stats["workouts"], "Total sessions"), ("Time invested", f"{stats['minutes']} min", "Across all workouts"), ("Total volume", f"{stats['volume']:,.0f} kg", "Weight × reps logged"), ("Sets completed", stats["sets"], "One set at a time")]
        for i, (t, v, n) in enumerate(vals):
            m = self.metric_card(metrics, t, v, n); m.grid(row=0, column=i, sticky="nsew", padx=(0 if i == 0 else 6, 0 if i == 3 else 6)); metrics.grid_columnconfigure(i, weight=1, uniform="metric")
        row = tk.Frame(self.content, bg=BG); row.pack(fill="both", expand=True)
        left = self.card(row); left.pack(side="left", fill="both", expand=True, padx=(0, 8))
        self.label(left, "Your routines", 13, TEXT, True).pack(anchor="w")
        for r in self.db.routines(self.user["id"])[:4]:
            line = tk.Frame(left, bg=PANEL, pady=10); line.pack(fill="x")
            tk.Label(line, text="▤", bg=BLUE_LIGHT, fg=BLUE, width=3, pady=8, font=("Segoe UI", 12, "bold")).pack(side="left", padx=(0, 10))
            col = tk.Frame(line, bg=PANEL); col.pack(side="left", fill="x", expand=True)
            self.label(col, r["name"], 10, TEXT, True).pack(anchor="w")
            self.label(col, f"{r['focus']} · {len(r['exercise_names'])} exercises", 8, MUTED).pack(anchor="w", pady=(4, 0))
            self.button(line, "Start", lambda rid=r["id"]: self.begin_workout(rid)).pack(side="right")
        right = self.card(row); right.pack(side="right", fill="both", expand=True, padx=(8, 0))
        self.label(right, "Recent sessions", 13, TEXT, True).pack(anchor="w", pady=(0, 8))
        recent = self.db.workouts(self.user["id"])[:4]
        if not recent: self.label(right, "No sessions yet. Start a routine to log your first workout.", 9, MUTED, wraplength=300).pack(anchor="w", pady=20)
        for s in recent:
            self.label(right, s["routine_name"], 10, TEXT, True).pack(anchor="w", pady=(7, 0))
            self.label(right, f"{s['started_at'][:10]} · {s['duration_minutes']} min · {s['sets_completed']} sets", 8, MUTED).pack(anchor="w", pady=(2, 5))

    def page_routines(self):
        self.heading("Plan your training", "Your workout routines", "Create a plan that works for you, then start tracking when you're ready.")
        toolbar = tk.Frame(self.content, bg=BG); toolbar.pack(fill="x", pady=(0, 10))
        self.button(toolbar, "＋ Create routine", self.create_routine_dialog, primary=True).pack(side="left")
        sf = ScrollFrame(self.content, bg=BG); sf.pack(fill="both", expand=True)
        routines = self.db.routines(self.user["id"])
        if not routines:
            self.label(sf.inner, "No routines yet. Create one to get started.", 10, MUTED).pack(anchor="w", pady=10)
        for r in routines:
            c = self.card(sf.inner); c.pack(fill="x", pady=6, padx=(0, 8))
            left = tk.Frame(c, bg=PANEL); left.pack(side="left", fill="x", expand=True)
            self.label(left, r["name"], 13, TEXT, True).pack(anchor="w")
            self.label(left, f"{r['focus']}  ·  {len(r['exercise_names'])} exercises", 9, BLUE).pack(anchor="w", pady=(4, 3))
            self.label(left, " · ".join(r["exercise_names"]), 9, MUTED, wraplength=560, justify="left").pack(anchor="w")
            actions = tk.Frame(c, bg=PANEL); actions.pack(side="right", padx=(10, 0))
            self.button(actions, "▶ Start", lambda rid=r["id"]: self.begin_workout(rid), primary=True).pack(pady=3, fill="x")
            self.button(actions, "Delete", lambda rid=r["id"]: self.remove_routine(rid)).pack(pady=3, fill="x")

    def create_routine_dialog(self, preset=None):
        uid = self.user["id"]
        exercises = list(self.db.exercises())
        win = tk.Toplevel(self); win.title("Create workout routine"); win.configure(bg=BG)
        win.geometry("780x780"); win.minsize(640, 560); win.transient(self); win.grab_set()
        outer = tk.Frame(win, bg=BG, padx=22, pady=16); outer.pack(fill="both", expand=True)

        self.label(outer, "NEW ROUTINE", 9, BLUE, True).pack(anchor="w")
        name_var = tk.StringVar(value=(preset or {}).get("name", ""))
        requested_focus = (preset or {}).get("focus", "Full body")
        # Original Training Focus choices are kept; recommendation goals map onto them.
        focus_aliases = {"Build strength": "Strength", "Get moving": "Full body", "Stay consistent": "Full body"}
        if requested_focus not in ROUTINE_FOCUSES:
            requested_focus = focus_aliases.get(requested_focus, "Full body")
        focus_var = tk.StringVar(value=requested_focus)
        wrap, _ = self.field(outer, "ROUTINE NAME", name_var); wrap.pack(fill="x", pady=(10, 8))
        top = tk.Frame(outer, bg=BG); top.pack(fill="x")
        self.label(top, "TRAINING FOCUS", 9, MUTED, True).pack(anchor="w", pady=(0, 5))
        focus_row = tk.Frame(top, bg=BG); focus_row.pack(fill="x")
        focus_box = self.combo(focus_row, focus_var, ROUTINE_FOCUSES)
        focus_box.pack(side="left", fill="x", expand=True, ipady=5)
        self.button(focus_row, "↻ Refresh exercises", lambda: refresh()).pack(side="left", padx=(8, 0))
        self.label(outer, "Suggestions update when you change the focus or press refresh. Tick the exercises you want.", 8, MUTED).pack(anchor="w", pady=(4, 0))
        info = self.label(outer, "", 8, MUTED, wraplength=700, justify="left"); info.pack(anchor="w", pady=(2, 0))
        bar = tk.Frame(outer, bg=BG); bar.pack(fill="x", pady=(8, 6))
        counter = self.label(bar, "", 10, BLUE, True); counter.pack(side="left")
        self.button(bar, "Clear", lambda: clear_all()).pack(side="right")
        self.button(bar, "Add all suggested", lambda: add_suggested()).pack(side="right", padx=(0, 8))

        # bottom items first so they never get pushed out of view
        self.label(outer, WEIGHT_DISCLAIMER, 8, MUTED, wraplength=700, justify="left").pack(side="bottom", anchor="w", pady=(6, 0))
        self.button(outer, "Save routine", lambda: save(), primary=True).pack(side="bottom", fill="x", pady=(10, 0))
        sf = ScrollFrame(outer, bg=BG); sf.pack(fill="both", expand=True)
        inner = sf.inner

        variables = {ex["id"]: tk.BooleanVar(value=False) for ex in exercises}
        for ex in exercises:  # preselect recommended exercises (no duplicates, never above the limit)
            if ex["name"] in set((preset or {}).get("exercises", [])) and sum(v.get() for v in variables.values()) < MAX_ROUTINE_EXERCISES:
                variables[ex["id"]].set(True)
        checks, display_order, suggested_ids = {}, [], []

        def selected_count():
            return sum(1 for v in variables.values() if v.get())

        def update_counter():
            n = selected_count()
            counter.configure(text=f"{n}/{MAX_ROUTINE_EXERCISES} exercises selected", fg=RED if n >= MAX_ROUTINE_EXERCISES else BLUE)
            for eid, cb in checks.items():
                if cb.winfo_exists():
                    cb.configure(state="disabled" if (n >= MAX_ROUTINE_EXERCISES and not variables[eid].get()) else "normal")

        def on_toggle(eid):
            if variables[eid].get() and selected_count() > MAX_ROUTINE_EXERCISES:
                variables[eid].set(False)
                messagebox.showwarning("Exercise limit reached", f"A routine can have at most {MAX_ROUTINE_EXERCISES} exercises.", parent=win)
            update_counter()

        def add_suggested():
            for eid in suggested_ids:
                if selected_count() >= MAX_ROUTINE_EXERCISES: break
                variables[eid].set(True)
            update_counter()

        def clear_all():
            for v in variables.values(): v.set(False)
            update_counter()

        def exercise_card(ex, rec, detailed):
            c = tk.Frame(inner, bg=PANEL, padx=12, pady=8, highlightbackground=BORDER, highlightthickness=1)
            c.pack(fill="x", pady=4, padx=(0, 8))
            cb = tk.Checkbutton(c, text=f"{ex['name']}   ·   {ex['muscles']}", variable=variables[ex["id"]], anchor="w",
                                bg=PANEL, fg=TEXT, activebackground=PANEL, activeforeground=BLUE, selectcolor=BLUE_LIGHT,
                                font=("Segoe UI", 10, "bold"), relief="flat", command=lambda e=ex["id"]: on_toggle(e))
            cb.pack(anchor="w")
            checks[ex["id"]] = cb
            body = tk.Frame(c, bg=PANEL); body.pack(fill="x", padx=(24, 0))
            if detailed:
                self.rec_block(body, ex, rec)
            else:
                self.label(body, f"{ex['equipment']}  ·  {rec['sets']} sets × {rec['reps_text']}", 9, MUTED, bg=PANEL).pack(anchor="w")

        def refresh():
            prof = self.db.profile(uid)  # always read the latest saved profile
            level = prof["experience_level"]; pargs = profile_args(prof)
            msg = (f"Personalized for your {level.lower()} level, age {prof['age']} and {focus_var.get().lower()} focus. "
                   "Height and weight never set exact loads; adjust any suggestion to what feels right.")
            info.configure(text=msg)
            for ch in inner.winfo_children(): ch.destroy()
            checks.clear(); display_order.clear(); suggested_ids.clear()
            focus = focus_var.get()
            suggested = select_exercises(exercises, focus, level, prof["age"])
            sugg_names = {e["name"] for e in suggested}
            others = [ex for ex in exercises if ex["name"] not in sugg_names]
            self.label(inner, f"SUGGESTED FOR {focus.upper()}", 9, BLUE, True).pack(anchor="w", pady=(2, 2))
            for ex in suggested:
                suggested_ids.append(ex["id"]); display_order.append(ex["id"])
                exercise_card(ex, recommend(ex, focus, level, **pargs), True)
            if others:
                self.label(inner, "OTHER EXERCISES (OPTIONAL)", 9, MUTED, True).pack(anchor="w", pady=(12, 2))
                for ex in others:
                    display_order.append(ex["id"])
                    exercise_card(ex, recommend(ex, focus, level, **pargs), False)
            update_counter()
            sf.to_top()

        focus_box.bind("<<ComboboxSelected>>", lambda _e: refresh())

        def save():
            ids = [eid for eid in display_order if variables[eid].get()]
            try:
                self.db.create_routine(uid, name_var.get(), focus_var.get(), ids)
            except ValueError as err:
                messagebox.showwarning("Check your routine", str(err), parent=win); return
            win.destroy(); self.show_page("Routines")
        refresh()
        return win

    def remove_routine(self, rid):
        if messagebox.askyesno("Delete routine", "Delete this workout routine? Past workout history will be retained."):
            self.db.delete_routine(self.user["id"], rid); self.show_page("Routines")

    # ---- exercise library
    def page_library(self):
        self.heading("Learn the movement", "Exercise library", "Search exercises, preview the video spot, and open a step-by-step tutorial.")
        row = tk.Frame(self.content, bg=BG); row.pack(fill="x", pady=(0, 10))
        q = tk.StringVar(); search = self.entry(row, q); search.pack(side="left", fill="x", expand=True, ipady=10, padx=(0, 10))
        self.button(row, "Search", lambda: render()).pack(side="left")
        sf = ScrollFrame(self.content, bg=BG); sf.pack(fill="both", expand=True)
        listbox = sf.inner

        def render():
            for w in listbox.winfo_children(): w.destroy()
            data = self.db.exercises(q.get())
            if not data:
                self.label(listbox, "No exercises match your search.", 10, MUTED).pack(anchor="w", pady=12)
            for ex in data:
                self._library_card(listbox, ex)
            sf.to_top()
        render()
        search.bind("<Return>", lambda e: render())
        search.bind("<KeyRelease>", lambda e: render() if e.keysym not in ("Return", "Tab") else None)

    def _video_preview(self, parent, ex, bg=PANEL, w=170, h=96):
        kind, _ = resolve_video(ex["name"])
        box = tk.Frame(parent, bg=BLUE_LIGHT, width=w, height=h, highlightbackground=HERO_BORDER, highlightthickness=1)
        box.pack_propagate(False)
        ready = kind in ("url", "file")
        tk.Label(box, text="▶", bg=BLUE_LIGHT, fg=BLUE, font=("Segoe UI", 22, "bold")).pack(expand=True, pady=(8, 0))
        tk.Label(box, text="Video ready" if ready else ("Video file not found" if kind == "missing" else "Video coming soon"),
                 bg=BLUE_LIGHT, fg=BLUE_DARK, font=("Segoe UI", 8, "bold")).pack(pady=(0, 10))
        return box

    def _library_card(self, parent, ex):
        card = self.card(parent); card.pack(fill="x", pady=5, padx=(0, 8))
        self._video_preview(card, ex).pack(side="left", padx=(0, 14))
        col = tk.Frame(card, bg=PANEL); col.pack(side="left", fill="x", expand=True)
        self.label(col, ex["name"], 12, TEXT, True).pack(anchor="w")
        self.label(col, f"Target: {ex['muscles']}", 9, MUTED).pack(anchor="w", pady=(4, 0))
        self.label(col, f"Difficulty: {ex['level']}   ·   Equipment: {ex['equipment']}", 9, MUTED).pack(anchor="w", pady=(2, 4))
        self.label(col, f"Recommended: {ex['recommended_sets']} sets · {ex['recommended_reps']}", 9, BLUE, True).pack(anchor="w")
        btns = tk.Frame(card, bg=PANEL); btns.pack(side="right", padx=(10, 0))
        self.button(btns, "View tutorial", lambda e=dict(ex): self.tutorial_dialog(e), primary=True).pack(fill="x", pady=2)
        self.button(btns, "▶ Watch video", lambda n=ex["name"]: self.open_video(n)).pack(fill="x", pady=2)

    def open_video(self, name):
        kind, value = resolve_video(name)
        if kind == "none":
            messagebox.showinfo("Video coming soon", f"No video has been added for {name} yet.\n\nTo add one, put a file path or web link for it in:\n{VIDEO_CONFIG_PATH}")
            return
        if kind == "missing":
            messagebox.showwarning("Video file not found", f"The video configured for {name} could not be found:\n{value}")
            return
        try:
            if kind == "url":
                webbrowser.open(value)
            elif sys.platform.startswith("win"):
                os.startfile(value)  # type: ignore[attr-defined]
            elif sys.platform == "darwin":
                subprocess.Popen(["open", value])
            else:
                subprocess.Popen(["xdg-open", value])
        except Exception as err:  # noqa: BLE001 - show any launch problem to the user
            messagebox.showwarning("Could not open video", f"{err}")

    def tutorial_dialog(self, ex):
        win = tk.Toplevel(self); win.title(f"Tutorial — {ex['name']}"); win.configure(bg=BG); win.geometry("600x700"); win.minsize(460, 420); win.transient(self)
        sf = ScrollFrame(win, bg=BG); sf.pack(fill="both", expand=True)
        pad = tk.Frame(sf.inner, bg=BG, padx=25, pady=22); pad.pack(fill="both", expand=True)
        self._video_preview(pad, ex, w=300, h=150).pack(anchor="w")
        self.button(pad, "▶ Watch video", lambda: self.open_video(ex["name"])).pack(anchor="w", pady=(8, 0))
        self.label(pad, ex["name"], 22, TEXT, True).pack(anchor="w", pady=(14, 4))
        self.label(pad, f"{ex['muscles']}  ·  {ex['level']}  ·  {ex['equipment']}", 10, BLUE, True).pack(anchor="w")
        self.label(pad, ex["cue"], 10, MUTED, wraplength=500, justify="left").pack(anchor="w", pady=(12, 15))
        self.label(pad, "HOW TO PERFORM", 9, BLUE, True).pack(anchor="w", pady=(0, 7))
        for idx, step in enumerate(ex["steps"].splitlines(), 1):
            row = tk.Frame(pad, bg=PANEL, padx=10, pady=9, highlightbackground=BORDER, highlightthickness=1); row.pack(fill="x", pady=4)
            tk.Label(row, text=f"{idx:02d}", bg=BLUE_LIGHT, fg=BLUE, font=("Segoe UI", 9, "bold"), padx=8, pady=5).pack(side="left", padx=(0, 10))
            tk.Label(row, text=step, bg=PANEL, fg=TEXT, font=("Segoe UI", 9), wraplength=400, justify="left").pack(side="left", fill="x")
        tk.Label(pad, text="Use a comfortable range of motion and stop if you feel sharp pain.", bg=BG, fg=MUTED, font=("Segoe UI", 9), wraplength=500, justify="left").pack(anchor="w", pady=12)
        return win

    # ---- track workout
    def page_track(self):
        self.heading("One rep at a time", "Track a workout", "Start a routine, enter each set's weight and reps, and mark completed sets.")
        if self.active_routine is None:
            sf = ScrollFrame(self.content, bg=BG); sf.pack(fill="both", expand=True)
            routines = self.db.routines(self.user["id"])
            if not routines:
                self.label(sf.inner, "Create a routine before tracking a workout.", 11, MUTED).pack(anchor="w")
                self.button(sf.inner, "Create routine", self.create_routine_dialog, primary=True).pack(anchor="w", pady=10)
            else:
                for r in routines:
                    c = self.card(sf.inner); c.pack(fill="x", pady=6, padx=(0, 8))
                    col = tk.Frame(c, bg=PANEL); col.pack(side="left", fill="x", expand=True)
                    self.label(col, r["name"], 12, TEXT, True).pack(anchor="w")
                    self.label(col, f"{r['focus']} · {len(r['exercise_names'])} exercises", 9, MUTED).pack(anchor="w", pady=(4, 0))
                    self.button(c, "▶ Start tracking", lambda rid=r["id"]: self.begin_workout(rid), primary=True).pack(side="right")
            return
        r = self.active_routine
        prof = self.db.profile(self.user["id"]); level = prof["experience_level"]; pargs = profile_args(prof)
        summary = self.card(self.content); summary.pack(fill="x", pady=(0, 10))
        self.label(summary, f"SESSION IN PROGRESS · {r['name']}", 12, BLUE, True).pack(anchor="w")
        self.label(summary, "Targets are suggestions - edit weight and reps freely, then tick Done for each completed set.", 9, MUTED).pack(anchor="w", pady=(5, 0))
        actions = tk.Frame(self.content, bg=BG); actions.pack(side="bottom", fill="x", pady=(10, 4))
        self.button(actions, "Discard workout", self.discard_workout).pack(side="left")
        self.button(actions, "Finish & save workout", self.finish_workout, primary=True).pack(side="right")
        sf = ScrollFrame(self.content, bg=BG); sf.pack(fill="both", expand=True)
        self.tracking_rows = []
        for ex in r["exercises"]:
            rec = recommend(ex, r["focus"], level, **pargs)
            c = self.card(sf.inner); c.pack(fill="x", pady=5, padx=(0, 8))
            self.label(c, ex["name"], 12, TEXT, True).pack(anchor="w")
            self.label(c, f"{ex['muscles']} · {ex['equipment']}", 8, MUTED).pack(anchor="w", pady=(3, 4))
            self.label(c, f"Recommended: {rec['sets']} sets × {rec['reps_text']}", 10, BLUE, True).pack(anchor="w")
            if rec["weight_text"]:
                self.label(c, f"Suggested starting weight: {rec['weight_text']}", 9, TEXT, wraplength=640, justify="left").pack(anchor="w", pady=(2, 0))
            if rec["note"]:
                self.label(c, rec["note"], 9, MUTED, wraplength=640, justify="left").pack(anchor="w", pady=(2, 0))
            unit_head = "SEC" if rec["unit"] == "sec" else "REPS"
            row_head = tk.Frame(c, bg=PANEL); row_head.pack(fill="x", pady=(8, 0))
            for txt, w in [("SET", 5), ("TARGET", 14), ("WEIGHT KG", 11), (unit_head, 8), ("DONE", 8)]:
                tk.Label(row_head, text=txt, width=w, anchor="w", bg=PANEL, fg=BLUE, font=("Segoe UI", 8, "bold")).pack(side="left", padx=3)
            for i in range(rec["sets"]): self.add_tracking_set(c, ex, i + 1, rec)
            self.button(c, "＋ Add set", lambda parent=c, exercise=dict(ex), rc=rec: self.add_tracking_set(parent, exercise, None, rc)).pack(anchor="w", pady=(8, 0))

    def add_tracking_set(self, parent, ex, number, rec):
        if number is None:
            number = 1 + sum(1 for row in self.tracking_rows if row["exercise_id"] == ex["id"])
        row = tk.Frame(parent, bg=PANEL, pady=3); row.pack(fill="x")
        tk.Label(row, text=f"{number:02d}", width=5, anchor="w", bg=PANEL, fg=MUTED, font=("Segoe UI", 9)).pack(side="left", padx=3)
        tk.Label(row, text=rec["reps_text"], width=14, anchor="w", bg=PANEL, fg=MUTED, font=("Segoe UI", 9)).pack(side="left", padx=3)
        weight = tk.StringVar(value="0"); reps = tk.StringVar(value=str((rec["lo"] + rec["hi"]) // 2)); done = tk.BooleanVar(value=False)
        ew = self.entry(row, weight, width=10); ew.pack(side="left", padx=3, ipady=5)
        er = self.entry(row, reps, width=8); er.pack(side="left", padx=3, ipady=5)
        tk.Checkbutton(row, variable=done, bg=PANEL, activebackground=PANEL, selectcolor=BLUE_LIGHT, text="Done", fg=TEXT).pack(side="left", padx=8)
        fb = tk.Label(row, text="", bg=PANEL, fg=MUTED, font=("Segoe UI", 8), wraplength=280, justify="left", anchor="w")
        fb.pack(side="left", padx=4, fill="x", expand=True)

        def update(*_):
            if not done.get():
                fb.configure(text=""); return
            try:
                w, r_ = float(weight.get() or 0), int(reps.get() or 0)
                if w < 0 or r_ < 0: raise ValueError
            except ValueError:
                fb.configure(text="Enter a number for weight and a whole number for reps."); return
            fb.configure(text=set_feedback(rec, w, r_))
        for v in (weight, reps, done): v.trace_add("write", update)
        self.tracking_rows.append({"exercise_id": ex["id"], "exercise_name": ex["name"], "set_number": number, "weight_var": weight, "reps_var": reps, "done_var": done})

    def begin_workout(self, rid):
        self.active_routine = self.db.routine(self.user["id"], rid)
        if not self.active_routine or not self.active_routine["exercises"]:
            messagebox.showwarning("Empty routine", "This routine has no exercises."); self.active_routine = None; return
        self.workout_started = datetime.now(); self.show_page("Track Workout")

    def discard_workout(self):
        if messagebox.askyesno("Discard workout", "Discard this workout session without saving?"):
            self.active_routine = None; self.workout_started = None; self.tracking_rows = []; self.show_page("Track Workout")

    def finish_workout(self):
        saved = []
        for row in self.tracking_rows:
            try: weight = float(row["weight_var"].get() or 0); reps = int(row["reps_var"].get() or 0)
            except ValueError:
                messagebox.showwarning("Check set values", "Weight must be a number and reps must be a whole number."); return
            if weight < 0 or reps < 0:
                messagebox.showwarning("Invalid values", "Weight and reps cannot be negative."); return
            if weight > 1000 or reps > 10000:
                messagebox.showwarning("Check set values", "Those numbers look too large. Please check the weight and reps."); return
            saved.append({"exercise_id": row["exercise_id"], "set_number": row["set_number"], "weight": weight, "reps": reps, "done": row["done_var"].get()})
        if not any(s["done"] for s in saved):
            messagebox.showwarning("No completed sets", "Mark at least one set as Done before saving."); return
        name = self.active_routine["name"]
        self.db.save_workout(self.user["id"], name, self.workout_started or datetime.now(), saved)
        self.active_routine = None; self.workout_started = None; self.tracking_rows = []
        messagebox.showinfo("Workout saved", "Great work! Your workout has been saved to the database.")
        self.show_page("Overview")

    # ---- history / progress / records
    def _tree_with_scroll(self, parent, columns, height):
        wrap = tk.Frame(parent, bg=BG)
        tree = ttk.Treeview(wrap, columns=columns, show="headings", height=height)
        sb = ttk.Scrollbar(wrap, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=sb.set)
        tree.pack(side="left", fill="both", expand=True); sb.pack(side="right", fill="y")
        return wrap, tree

    def page_history(self):
        self.heading("Every session counts", "Workout history", "Review past sessions saved to your FitTrack database.")
        bar = tk.Frame(self.content, bg=BG); bar.pack(fill="x", pady=(0, 10))
        q = tk.StringVar(); ent = self.entry(bar, q); ent.pack(side="left", fill="x", expand=True, ipady=9, padx=(0, 8))
        row = tk.Frame(self.content, bg=BG); row.pack(side="bottom", fill="x", pady=10)
        wrap, tree = self._tree_with_scroll(self.content, ("date", "routine", "duration", "sets", "volume"), 15)
        wrap.pack(fill="both", expand=True)
        for col, title, width in [("date", "DATE", 160), ("routine", "WORKOUT", 250), ("duration", "MINUTES", 90), ("sets", "SETS", 80), ("volume", "VOLUME KG", 110)]: tree.heading(col, text=title); tree.column(col, width=width, anchor="w")
        def render():
            tree.delete(*tree.get_children())
            for w in self.db.workouts(self.user["id"], q.get()): tree.insert("", "end", iid=str(w["id"]), values=(w["started_at"][:16].replace("T", " "), w["routine_name"], w["duration_minutes"], w["sets_completed"], f"{w['volume_kg']:,.0f}"))
        render(); ent.bind("<Return>", lambda e: render())
        self.button(row, "Search history", render).pack(side="left")
        def delete():
            sel = tree.selection()
            if not sel: messagebox.showinfo("Select a workout", "Choose a session first."); return
            if messagebox.askyesno("Delete session", "Permanently delete the selected workout from history?"):
                self.db.delete_workout(self.user["id"], int(sel[0])); render()
        self.button(row, "Delete selected", delete).pack(side="right")

    def page_progress(self):
        self.scroll_body()
        self.heading("The work adds up", "Your progress", "A snapshot of your training consistency, time, and total volume.")
        s = self.db.stats(self.user["id"]); profile = self.db.profile(self.user["id"])
        row = tk.Frame(self.content, bg=BG); row.pack(fill="x", pady=(0, 18))
        for i, (t, v, n) in enumerate([("Workouts", s["workouts"], "All time"), ("Training time", f"{s['minutes']} min", "Recorded sessions"), ("Volume moved", f"{s['volume']:,.0f} kg", "Weight × reps"), ("Completed sets", s["sets"], "Logged sets")]):
            c = self.metric_card(row, t, v, n); c.grid(row=0, column=i, sticky="nsew", padx=(0 if i == 0 else 6, 0 if i == 3 else 6)); row.grid_columnconfigure(i, weight=1, uniform="progress")
        panel = self.card(self.content); panel.pack(fill="x", pady=5)
        self.label(panel, "Weekly consistency", 13, TEXT, True).pack(anchor="w")
        self.label(panel, f"{s['week']} sessions this week  /  target {profile['weekly_target']}", 10, MUTED).pack(anchor="w", pady=(6, 10))
        progress = min(100, int(s["week"] / max(1, profile["weekly_target"]) * 100))
        bar = tk.Frame(panel, bg=PANEL_2, height=12); bar.pack(fill="x"); bar.pack_propagate(False)
        tk.Frame(bar, bg=BLUE).place(relx=0, rely=0, relheight=1, relwidth=max(0.01, progress / 100))
        self.label(panel, f"{progress}% of weekly target", 9, BLUE, True).pack(anchor="w", pady=(8, 0))
        c = self.card(self.content); c.pack(fill="both", expand=True, pady=8)
        self.label(c, "Strength highlights", 13, TEXT, True).pack(anchor="w", pady=(0, 8))
        if not s["prs"]: self.label(c, "No personal records yet. Log a completed set with a weight to get started.", 9, MUTED).pack(anchor="w", pady=8)
        else:
            for pr in s["prs"][:7]:
                row = tk.Frame(c, bg=PANEL, pady=8); row.pack(fill="x")
                self.label(row, pr["name"], 10, TEXT, True).pack(side="left")
                self.label(row, f"{pr['best']:g} kg", 10, BLUE, True).pack(side="right")

    def page_records(self):
        self.heading("Celebrate your wins", "Personal records", "Your highest completed weight for each exercise, calculated from workout history.")
        prs = self.db.stats(self.user["id"])["prs"]
        if not prs: self.label(self.content, "Your leaderboard is waiting. Complete a weighted set to see your records here.", 10, MUTED).pack(anchor="w", pady=10)
        wrap, tree = self._tree_with_scroll(self.content, ("exercise", "muscle", "weight"), 18)
        wrap.pack(fill="both", expand=True)
        for col, title, width in [("exercise", "EXERCISE", 270), ("muscle", "MUSCLES", 280), ("weight", "BEST WEIGHT", 140)]: tree.heading(col, text=title); tree.column(col, width=width, anchor="w")
        for pr in prs: tree.insert("", "end", values=(pr["name"], pr["muscles"], f"{pr['best']:g} kg"))

    # ---- recommendations
    def page_recommendations(self):
        self.scroll_body()
        self.heading("A plan that fits you", "Workout recommendations", "Cards are built from your saved profile. Add the ones you like, then create a workout.")
        self._build_feed(self.content, in_setup=False)

    # ---- profile
    def page_profile(self):
        self.scroll_body()
        self.heading("Your baseline", "Your profile", "Personalize FitTrack around your goals, body measurements and weekly schedule.")
        p = self.db.profile(self.user["id"])
        form = self.card(self.content); form.pack(fill="x", pady=(0, 12))
        fmt = lambda v: "" if v is None else f"{v:g}"
        name = tk.StringVar(value=p["display_name"]); goal = tk.StringVar(value=p["fitness_goal"]); level = tk.StringVar(value=p["experience_level"])
        target = tk.IntVar(value=p["weekly_target"]); weight = tk.StringVar(value=fmt(p["body_weight"])); height = tk.StringVar(value=fmt(p["height_cm"]))
        gender = tk.StringVar(value=p["gender"] or "Prefer not to say"); age = tk.StringVar(value=fmt(p["age"]))
        wrap, _ = self.field(form, "DISPLAY NAME", name); wrap.pack(fill="x", pady=(0, 13))
        for cap, var, vals in [("FITNESS GOAL", goal, GOALS), ("EXPERIENCE LEVEL", level, LEVELS), ("WEEKLY WORKOUT TARGET (SESSIONS)", target, [1, 2, 3, 4, 5, 6, 7]), ("GENDER (OPTIONAL)", gender, GENDERS)]:
            self.label(form, cap, 9, MUTED, True).pack(anchor="w", pady=(0, 5))
            self.combo(form, var, vals).pack(fill="x", ipady=5, pady=(0, 13))
        wrap, _ = self._unit_field(form, "AGE (REQUIRED)", age, "years"); wrap.pack(fill="x", pady=(0, 13))
        wrap, _ = self._unit_field(form, "HEIGHT (REQUIRED)", height, "cm"); wrap.pack(fill="x", pady=(0, 13))
        wrap, _ = self._unit_field(form, "WEIGHT (REQUIRED)", weight, "kg"); wrap.pack(fill="x", pady=(0, 8))
        self.label(form, "Age, height and weight are required. They add context to your recommendations but never set exact lifting loads, and gender does not change your sets, reps or weights.", 8, MUTED, wraplength=700, justify="left").pack(anchor="w", pady=(0, 14))
        def save():
            try:
                self.db.save_profile(self.user["id"], name.get(), goal.get(), level.get(), int(target.get()), weight.get(), height.get(), gender.get(), age.get())
            except (ValueError, tk.TclError) as err:
                messagebox.showwarning("Check your profile", str(err) if isinstance(err, ValueError) else "Check the weekly target value."); return
            self.user["display_name"] = name.get().strip() or "Athlete"
            messagebox.showinfo("Profile saved", "Your profile has been saved and your recommendations have been refreshed.")
            self.show_page("Profile")
        self.button(form, "Save profile", save, primary=True).pack(anchor="w")

    def sign_out(self):
        self.user = None; self.active_routine = None; self.tracking_rows = []; self.show_auth()

    def _on_close(self):
        try: self.db.close()
        finally: self.destroy()


if __name__ == "__main__":
    app = FitTrackApp()
    app.mainloop()