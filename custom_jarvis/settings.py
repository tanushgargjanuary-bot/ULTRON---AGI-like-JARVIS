"""Isolated deterministic-engine defaults; MARK owns all provider configuration."""

from pathlib import Path

MAX_PLAN_STEPS = 10
MAX_RETRIES_PER_STEP = 3
COMMAND_TIMEOUT_SECONDS = 30
DEFAULT_GROQ_MODEL = "mark-selected-provider"
GROQ_TEMPERATURE = 0.2
JARVIS_PERSONA_PROMPT = (
    "Report observations accurately; never claim an unverified goal is complete."
)
SCREENSHOTS_DIR = Path.home() / ".custom-mark-jarvis" / "screenshots"


def get_groq_api_key(prompt_if_missing=False):
    return ""
