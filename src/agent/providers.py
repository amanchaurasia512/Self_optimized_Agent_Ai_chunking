"""Answer providers for the agent's ask mode (spec/agent_v1.md, Answer providers): an ordered list of provider entries,
tried in order. A daily limit marks an entry exhausted until its reset (state file) and moves on; a per-minute limit or
an overload waits and retries the same entry. Keys are read only here, from each entry's key_file, at call time; they
are never printed, logged or stored, and error messages are redacted before they are raised."""
import json
import logging
import re
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from scripts.aq_run import ANSWER_PROMPT

CONFIG_DIR = Path.home() / ".config" / "pdf-agent"
CONFIG_FILE, STATE_FILE = CONFIG_DIR / "providers.json", CONFIG_DIR / "state.json"
FIELDS = ("name", "provider", "model", "key_file")
RETRY_WAITS = (15, 30, 60, 120, 240)  # seconds, as src/chunk/llm.py
RESET_ZONE = ZoneInfo("America/Los_Angeles")  # Gemini's free-tier daily quota resets at midnight Pacific
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
DAILY = re.compile(r"per\s*day", re.IGNORECASE)
RETRY_DELAY = re.compile(r"retryDelay\W+(\d+(?:\.\d+)?)s")
log = logging.getLogger(__name__)


class RateLimit(Exception):
    """A 429 from a provider: kind 'daily' or 'minute', with the provider's retry delay in seconds when it gives one."""

    def __init__(self, kind, retry_after=None):
        super().__init__(f"{kind} rate limit")
        self.kind, self.retry_after = kind, retry_after


class Overloaded(Exception):
    """A temporary overload (503): wait and retry the same entry."""


class ProviderError(RuntimeError):
    """Stops the agent with a clear message; the message never holds a key."""


def limit_kind(detail):
    return "daily" if DAILY.search(detail) else "minute"


def ask_gemini(model, key, prompt):
    from google import genai
    from google.genai import errors, types
    try:
        # The client is held for the whole call: a temporary genai.Client is garbage-collected once .models is taken,
        # and its __del__ closes the HTTP connection before the request is sent ("client has been closed").
        with genai.Client(api_key=key) as client:
            response = client.models.generate_content(model=model, contents=prompt,
                                                      config=types.GenerateContentConfig(temperature=0))
    except errors.APIError as error:
        detail = f"{error.message} {error.details}"
        if error.code == 429:
            delay = RETRY_DELAY.search(detail)
            raise RateLimit(limit_kind(detail), float(delay.group(1)) if delay else None) from None
        if error.code == 503:
            raise Overloaded() from None
        raise
    return response.text or ""


def ask_groq(model, key, prompt):
    import httpx
    with httpx.Client(timeout=120) as client:  # held open for the request and the reading of its response
        response = client.post(GROQ_URL, headers={"Authorization": f"Bearer {key}"},
                               json={"model": model, "temperature": 0, "messages": [{"role": "user", "content": prompt}]})
        response.read()
    if response.status_code == 429:
        retry_after = response.headers.get("retry-after")
        raise RateLimit(limit_kind(response.text), float(retry_after) if retry_after else None)
    if response.status_code == 503:
        raise Overloaded()
    response.raise_for_status()
    return response.json()["choices"][0]["message"]["content"] or ""


ADAPTERS = {"gemini": ask_gemini, "groq": ask_groq}


def load_entries(config_file, adapters):
    if not Path(config_file).exists():
        raise ProviderError(f"no provider list at {config_file}; copy docs/providers.example.json there and edit it")
    entries = json.loads(Path(config_file).read_text(encoding="utf-8"))
    problems = [f"entry {index}: missing {field}" for index, entry in enumerate(entries) for field in FIELDS if field not in entry]
    problems += [f"entry '{entry['name']}': unknown provider '{entry['provider']}' (use {' or '.join(adapters)})"
                 for entry in entries if "provider" in entry and entry["provider"] not in adapters]
    names = [entry.get("name") for entry in entries]
    problems += [f"duplicate name '{name}'" for name in sorted({name for name in names if names.count(name) > 1})]
    if not entries or problems:
        raise ProviderError(f"provider list {config_file} is not usable: {'; '.join(problems) or 'it is empty'}")
    return [{**entry, "key_path": key_path(entry, config_file)} for entry in entries]


def key_path(entry, config_file):
    """The entry's key file: absolute or ~ paths as given, others relative to the providers.json folder (so the same
    list works inside a container that mounts the folder elsewhere)."""
    path = Path(entry["key_file"]).expanduser()
    return path if path.is_absolute() else Path(config_file).parent / path


def load_state(state_file):
    return json.loads(Path(state_file).read_text(encoding="utf-8")) if Path(state_file).exists() else {}


def save_state(state_file, state, moment):
    """Entry name -> exhausted-until time (ISO, UTC); expired entries are dropped. No keys are ever stored."""
    current = {name: until for name, until in state.items() if datetime.fromisoformat(until) > moment}
    Path(state_file).parent.mkdir(parents=True, exist_ok=True)
    Path(state_file).write_text(json.dumps(current, indent=2), encoding="utf-8")


def next_reset(moment):
    local = moment.astimezone(RESET_ZONE)
    midnight = datetime.combine(local.date() + timedelta(days=1), datetime.min.time(), tzinfo=RESET_ZONE)
    return midnight.astimezone(timezone.utc)


def read_key(entry):
    path = entry["key_path"]
    if not path.is_file():
        raise ProviderError(f"provider entry '{entry['name']}': key file {entry['key_file']} not found")
    return path.read_text(encoding="utf-8").strip()


def redact(text, key):
    return text.replace(key, "[key]") if key else text


def try_entry(entry, prompt, adapter, sleep, now):
    """('answer', text), ('daily', reset time) or ('minute', None) once the waits are used up."""
    key = read_key(entry)
    for wait in (*RETRY_WAITS, None):
        try:
            return "answer", adapter(entry["model"], key, prompt)
        except RateLimit as limit:
            if limit.kind == "daily":
                reset = now() + timedelta(seconds=limit.retry_after) if limit.retry_after else next_reset(now())
                return "daily", reset
            delay = limit.retry_after or wait
        except Overloaded:
            delay = wait
        except Exception as error:
            raise ProviderError(f"provider entry '{entry['name']}' ({entry['provider']}, {entry['model']}) failed: "
                                f"{redact(f'{type(error).__name__}: {error}', key)} (key file {entry['key_file']})") from None
        if wait is None:
            return "minute", None
        log.info("entry '%s': rate limited or overloaded, waiting %.0f s", entry["name"], delay)
        sleep(delay)


def answer(question, context, config_file=CONFIG_FILE, state_file=STATE_FILE, adapters=ADAPTERS, sleep=time.sleep,
           now=lambda: datetime.now(timezone.utc)):
    """The answer to one question from the retrieved context: {answer, entry, provider, model}."""
    prompt = ANSWER_PROMPT.format(context=context, question=question)
    entries, state = load_entries(config_file, adapters), load_state(state_file)
    outcomes = {}
    for entry in entries:
        name = entry["name"]
        if name in state and datetime.fromisoformat(state[name]) > now():
            outcomes[name] = f"exhausted until {state[name]}"
            continue
        kind, result = try_entry(entry, prompt, adapters[entry["provider"]], sleep, now)
        if kind == "answer":
            return {"answer": result, "entry": name, "provider": entry["provider"], "model": entry["model"]}
        if kind == "daily":
            state[name] = result.isoformat(timespec="seconds")
            save_state(state_file, state, now())
            outcomes[name] = f"daily limit, exhausted until {state[name]}"
            log.info("entry '%s': daily limit, exhausted until %s; trying the next entry", name, state[name])
        else:
            outcomes[name] = f"still rate limited after {len(RETRY_WAITS)} waits"
            log.info("entry '%s': still rate limited after the waits; trying the next entry", name)
    summary = "; ".join(f"{name}: {outcome}" for name, outcome in outcomes.items())
    raise ProviderError(f"every answer provider is exhausted ({summary}). Wait for a reset or add an entry to {config_file}.")


def add_entry(name, provider, model, config_file=CONFIG_FILE, keys_dir=CONFIG_DIR / "keys", read_secret=None):
    """Asks for the key with hidden input, saves it owner-only to keys_dir/<name>, appends the entry to the list.
    Returns the entry (which holds the key file path, never the key)."""
    import getpass
    import os
    if provider not in ADAPTERS:
        raise ProviderError(f"unknown provider '{provider}' (use {' or '.join(ADAPTERS)})")
    config_file = Path(config_file)
    entries = json.loads(config_file.read_text(encoding="utf-8")) if config_file.exists() else []
    if any(entry.get("name") == name for entry in entries):
        raise ProviderError(f"an entry named '{name}' already exists in {config_file}")
    if not re.fullmatch(r"[A-Za-z0-9_.-]+", name):
        raise ProviderError("names may hold letters, digits, '.', '_' and '-' only")
    key = (read_secret or getpass.getpass)(f"Paste the {provider} API key for '{name}' (hidden): ").strip()
    if not key:
        raise ProviderError("no key given; nothing was saved")
    keys_dir = Path(keys_dir)
    keys_dir.mkdir(parents=True, exist_ok=True)
    keys_dir.chmod(0o700)
    key_file = keys_dir / name
    descriptor = os.open(key_file, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
        handle.write(key + "\n")
    key_file.chmod(0o600)
    stored = key_file.relative_to(config_file.parent) if key_file.is_relative_to(config_file.parent) else key_file
    entry = {"name": name, "provider": provider, "model": model, "key_file": str(stored)}
    config_file.parent.mkdir(parents=True, exist_ok=True)
    config_file.write_text(json.dumps(entries + [entry], indent=2), encoding="utf-8")
    return entry


def list_entries(config_file=CONFIG_FILE, state_file=STATE_FILE, now=lambda: datetime.now(timezone.utc)):
    """One row per entry, in order: name, provider, model, whether its key file exists, status. Never the key."""
    entries, state = load_entries(config_file, ADAPTERS), load_state(state_file)
    return [{"position": position, "name": entry["name"], "provider": entry["provider"], "model": entry["model"],
             "key_file_found": entry["key_path"].is_file(),
             "status": (f"exhausted until {state[entry['name']]}"
                        if entry["name"] in state and datetime.fromisoformat(state[entry["name"]]) > now() else "ready")}
            for position, entry in enumerate(entries, start=1)]
