"""Research LLM for LLM-based chunkers: Gemini 3.5 Flash-Lite through google-genai. Every call's tokens, the model version
Google reports, and the response are recorded, so cost and noise can be measured."""
from functools import cache
from importlib.metadata import version
from pathlib import Path
import asyncio
from google.genai import errors
from google import genai
from google.genai import types

MODEL = "gemini-3.5-flash-lite"
KEY_FILE = Path.home() / ".config" / "gemini" / "api_key"
CALLS = []


@cache
def client():
    return genai.Client(api_key=KEY_FILE.read_text(encoding="utf-8").strip())


def llm_info():
    return {"provider": "google", "model": MODEL, "sdk": f"google-genai-{version('google-genai')}", "temperature_requested": 0}


RETRY_WAITS = (15, 30, 60, 120, 240)  # seconds; for temporary overload (503) or rate limits (429), not for other errors


async def complete(prompt):
    for attempt, wait in enumerate((*RETRY_WAITS, None), start=1):
        try:
            response = await client().aio.models.generate_content(model=MODEL, contents=prompt,
                                                                  config=types.GenerateContentConfig(temperature=0))
            break
        except errors.APIError as error:
            if error.code not in (429, 503) or wait is None:
                raise
            await asyncio.sleep(wait)
    usage = response.usage_metadata
    CALLS.append({"model_version": response.model_version, "attempts": attempt, "input_tokens": usage.prompt_token_count or 0,
                  "output_tokens": usage.candidates_token_count or 0, "thinking_tokens": usage.thoughts_token_count or 0,
                  "response": response.text or ""})
    return response.text or ""


def take_calls():
    """The calls made since the last take, for the runner's cost log."""
    calls = CALLS.copy()
    CALLS.clear()
    return calls