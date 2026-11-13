"""Answer-provider switch (spec/agent_v1.md, Answer providers) with fake providers only: no network, no real keys.
Config, keys and state live in pytest's temporary folder."""
import json
import logging
from datetime import datetime, timezone

import pytest

from scripts.aq_run import ANSWER_PROMPT
from src.agent.providers import ProviderError, RateLimit, answer, limit_kind, next_reset

NOW = datetime(2026, 11, 13, 12, 0, tzinfo=timezone.utc)
SECRETS = {"a": "FAKE-SECRET-KEY-a-7f3c9e1b", "b": "FAKE-SECRET-KEY-b-2d8a4f60"}


class FakeProvider:
    """Scripted outcomes per model: each call takes the next one (an exception is raised, a string is returned)."""

    def __init__(self, script):
        self.script, self.calls = {model: list(outcomes) for model, outcomes in script.items()}, []

    def __call__(self, model, key, prompt):
        self.calls.append({"model": model, "key_matches": key == SECRETS[model[-1]], "prompt": prompt})
        outcome = self.script[model].pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


@pytest.fixture
def setup(tmp_path):
    entries = []
    for name, secret in SECRETS.items():
        key_file = tmp_path / "keys" / name
        key_file.parent.mkdir(exist_ok=True)
        key_file.write_text(secret + "\n", encoding="utf-8")
        entries.append({"name": f"entry-{name}", "provider": "fake", "model": f"model-{name}", "key_file": str(key_file)})
    config = tmp_path / "providers.json"
    config.write_text(json.dumps(entries), encoding="utf-8")
    return {"config_file": config, "state_file": tmp_path / "state" / "state.json"}


def run(setup, provider, sleeps=None):
    return answer("What is the term?", "The term is five years.", adapters={"fake": provider},
                  sleep=(sleeps if sleeps is not None else []).append, now=lambda: NOW, **setup)


def test_daily_limit_switches_and_marks_exhausted(setup):
    provider = FakeProvider({"model-a": [RateLimit("daily")], "model-b": ["five years", "still five years"]})
    result = run(setup, provider)
    assert result == {"answer": "five years", "entry": "entry-b", "provider": "fake", "model": "model-b"}
    state = json.loads(setup["state_file"].read_text(encoding="utf-8"))
    assert state == {"entry-a": next_reset(NOW).isoformat(timespec="seconds")}
    assert state["entry-a"] == "2026-11-14T08:00:00+00:00"  # midnight US Pacific (PST, UTC-8)
    assert run(setup, provider)["entry"] == "entry-b"
    assert [call["model"] for call in provider.calls] == ["model-a", "model-b", "model-b"]  # exhausted entry skipped
    assert all(call["key_matches"] for call in provider.calls)


def test_daily_limit_uses_provider_retry_delay(setup):
    provider = FakeProvider({"model-a": [RateLimit("daily", retry_after=3600)], "model-b": ["ok"]})
    run(setup, provider)
    assert json.loads(setup["state_file"].read_text(encoding="utf-8")) == {"entry-a": "2026-11-13T13:00:00+00:00"}


def test_minute_limit_waits_and_retries_same_entry(setup):
    provider = FakeProvider({"model-a": [RateLimit("minute", retry_after=7), RateLimit("minute"), "five years"],
                             "model-b": ["never used"]})
    sleeps = []
    result = run(setup, provider, sleeps)
    assert result["entry"] == "entry-a" and result["answer"] == "five years"
    assert sleeps == [7, 30]  # the provider's delay first, then the second fallback wait
    assert [call["model"] for call in provider.calls] == ["model-a"] * 3
    assert not setup["state_file"].exists()  # a per-minute limit never marks an entry exhausted


def test_minute_limit_moves_on_after_last_wait(setup):
    provider = FakeProvider({"model-a": [RateLimit("minute")] * 6, "model-b": ["from b"]})
    sleeps = []
    assert run(setup, provider, sleeps)["entry"] == "entry-b"
    assert sleeps == [15, 30, 60, 120, 240]
    assert not setup["state_file"].exists()


def test_all_exhausted_stops_with_clear_message(setup):
    provider = FakeProvider({"model-a": [RateLimit("daily")], "model-b": [RateLimit("daily")]})
    with pytest.raises(ProviderError) as first:
        run(setup, provider)
    message = str(first.value)
    assert message.startswith("every answer provider is exhausted")
    assert "entry-a: daily limit, exhausted until 2026-11-14T08:00:00+00:00" in message
    assert "entry-b: daily limit, exhausted until 2026-11-14T08:00:00+00:00" in message
    with pytest.raises(ProviderError, match="every answer provider is exhausted"):
        run(setup, provider)
    assert len(provider.calls) == 2  # the second call tried nothing


def test_prompt_is_the_aq_answer_prompt(setup):
    provider = FakeProvider({"model-a": ["five years"], "model-b": []})
    run(setup, provider)
    assert provider.calls[0]["prompt"] == ANSWER_PROMPT.format(context="The term is five years.", question="What is the term?")


def test_no_key_text_in_output_logs_state_or_errors(setup, capsys, caplog):
    caplog.set_level(logging.DEBUG)
    leaky = FakeProvider({"model-a": [RateLimit("daily")],
                          "model-b": [RuntimeError(f"400 bad request, key {SECRETS['b']} rejected")]})
    with pytest.raises(ProviderError) as failure:
        run(setup, leaky)
    working = FakeProvider({"model-a": [], "model-b": [RateLimit("minute"), "five years"]})
    result = run({**setup}, working)
    captured = capsys.readouterr()
    seen = [str(failure.value), repr(failure.value), captured.out, captured.err, caplog.text, json.dumps(result),
            setup["state_file"].read_text(encoding="utf-8")]
    assert "[key]" in str(failure.value) and "entry-b" in str(failure.value)
    for secret in SECRETS.values():
        assert all(secret not in text for text in seen)


@pytest.mark.parametrize("detail, kind", [
    ("Quota exceeded for metric generate_content_free_tier_requests, quotaId GenerateRequestsPerDayPerProjectPerModel-FreeTier", "daily"),
    ("Rate limit reached for model on requests per day (RPD): Limit 1000", "daily"),
    ("Quota exceeded, quotaId GenerateRequestsPerMinutePerProjectPerModel-FreeTier", "minute"),
    ("Rate limit reached for model on tokens per minute (TPM): Limit 6000", "minute")])
def test_limit_kind(detail, kind):
    assert limit_kind(detail) == kind


def test_add_entry_saves_key_owner_only_and_never_shows_it(tmp_path, capsys):
    from src.agent.providers import add_entry, list_entries
    config, keys_dir, secret = tmp_path / "providers.json", tmp_path / "keys", "FAKE-SECRET-KEY-add-4b7d10"
    entry = add_entry("gemini-a", "gemini", "gemini-3.5-flash-lite", config, keys_dir, read_secret=lambda prompt: f"  {secret}\n")
    add_entry("groq-a", "groq", "some-model", config, keys_dir, read_secret=lambda prompt: "FAKE-SECRET-KEY-add-groq")
    key_file = keys_dir / "gemini-a"
    assert entry == {"name": "gemini-a", "provider": "gemini", "model": "gemini-3.5-flash-lite", "key_file": str(key_file)}
    assert key_file.read_text(encoding="utf-8") == secret + "\n"
    assert key_file.stat().st_mode & 0o777 == 0o600 and keys_dir.stat().st_mode & 0o777 == 0o700
    assert [item["name"] for item in json.loads(config.read_text(encoding="utf-8"))] == ["gemini-a", "groq-a"]
    rows = list_entries(config, tmp_path / "state.json", now=lambda: NOW)
    assert [(row["position"], row["name"], row["status"], row["key_file_found"]) for row in rows] == [
        (1, "gemini-a", "ready", True), (2, "groq-a", "ready", True)]
    (tmp_path / "state.json").write_text(json.dumps({"gemini-a": "2026-11-14T08:00:00+00:00"}), encoding="utf-8")
    assert list_entries(config, tmp_path / "state.json", now=lambda: NOW)[0]["status"] == "exhausted until 2026-11-14T08:00:00+00:00"
    captured = capsys.readouterr()
    for text in [config.read_text(encoding="utf-8"), json.dumps(rows), json.dumps(entry), captured.out, captured.err]:
        assert secret not in text and "FAKE-SECRET-KEY-add-groq" not in text


def test_add_entry_refuses_duplicate_empty_key_and_unknown_provider(tmp_path):
    from src.agent.providers import add_entry
    config, keys_dir = tmp_path / "providers.json", tmp_path / "keys"
    add_entry("a", "gemini", "m", config, keys_dir, read_secret=lambda prompt: "FAKE-KEY")
    with pytest.raises(ProviderError, match="already exists"):
        add_entry("a", "gemini", "m", config, keys_dir, read_secret=lambda prompt: "FAKE-KEY")
    with pytest.raises(ProviderError, match="no key given"):
        add_entry("b", "gemini", "m", config, keys_dir, read_secret=lambda prompt: "   ")
    with pytest.raises(ProviderError, match="unknown provider"):
        add_entry("c", "openai", "m", config, keys_dir, read_secret=lambda prompt: "FAKE-KEY")
    with pytest.raises(ProviderError, match="names may hold"):
        add_entry("../x", "gemini", "m", config, keys_dir, read_secret=lambda prompt: "FAKE-KEY")
    assert [entry["name"] for entry in json.loads(config.read_text(encoding="utf-8"))] == ["a"]
    assert sorted(path.name for path in keys_dir.iterdir()) == ["a"]
