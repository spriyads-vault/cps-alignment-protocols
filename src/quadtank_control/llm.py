"""Thin, testable layer between the harness and a language-model API.

Everything that talks to a model goes through the LLMClient protocol, so the
supervisor and monitor can be tested with a fake and wrapped with a spend guard
and an on-disk cache. Nothing in here is exercised against a live API by the test
suite. The Anthropic client has only been checked against a stub of the SDK.
"""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol


class LLMError(RuntimeError):
    """The call failed in a way the caller should treat as a lost response."""


class LLMRefusal(LLMError):
    """The model declined (stop_reason == "refusal")."""


class BudgetExceeded(RuntimeError):
    """The call budget is spent. Raised before the call is made.

    Deliberately NOT an LLMError. Supervisors and monitors treat LLMError as a lost response and carry
    on, which would let a run continue in silently degraded form after the cap. This one must stop it.
    """


def missing_credentials_message() -> str | None:
    """None when an Anthropic credential is visible, otherwise a message saying how to supply one.

    Checks that the variable is set and non-empty. It never reads or prints the value.
    """
    if os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN"):
        return None
    return (
        "No Anthropic credential found. ANTHROPIC_API_KEY is not set (or is empty) in this process.\n"
        "In a notebook, run the cell that sets it in the SAME runtime before this command. A restarted\n"
        "runtime has forgotten it. Nothing was sent to the API and nothing was spent."
    )


class LLMClient(Protocol):
    def complete(self, system: str, user: str) -> str: ...


@dataclass(frozen=True)
class AnthropicConfig:
    model: str
    max_tokens: int = 1024
    effort: str | None = None  # "low" to "max". Leave None for models without effort (Haiku 4.5).
    max_retries: int = 2  # SDK-level retries on 429 and 5xx


class AnthropicClient:
    """Plain messages.create call. No tools, no forced tool choice, no prefill.

    Pass `sdk_client` to inject a stub in tests. Without it the real SDK is imported
    lazily, so the rest of the package works without the `llm` extra installed.
    """

    def __init__(self, cfg: AnthropicConfig, sdk_client: Any | None = None) -> None:
        self.cfg = cfg
        if sdk_client is None:
            import anthropic  # local import: optional dependency

            sdk_client = anthropic.Anthropic(max_retries=cfg.max_retries)
        self._sdk = sdk_client

    def complete(self, system: str, user: str) -> str:
        kwargs: dict[str, Any] = {
            "model": self.cfg.model,
            "max_tokens": self.cfg.max_tokens,
            "system": system,
            "messages": [{"role": "user", "content": user}],
        }
        if self.cfg.effort is not None:
            kwargs["output_config"] = {"effort": self.cfg.effort}
        response = self._sdk.messages.create(**kwargs)
        if getattr(response, "stop_reason", None) == "refusal":
            details = getattr(response, "stop_details", None)
            category = getattr(details, "category", None)
            raise LLMRefusal(f"{self.cfg.model} refused (category={category})")
        text = "".join(b.text for b in response.content if getattr(b, "type", "") == "text")
        if not text:
            raise LLMError(
                f"{self.cfg.model} returned no text (stop_reason={response.stop_reason})"
            )
        return text


class CallBudget:
    """A count of calls that several clients can share, so one cap covers a whole run.

    Counts attempts made by this code. The SDK's own retries on 429 and 5xx errors can add requests
    beyond this count, so treat the cap as a close bound and not an exact one.
    """

    def __init__(self, max_calls: int) -> None:
        self.max_calls = max_calls
        self.used = 0

    def spend(self) -> None:
        if self.used >= self.max_calls:
            raise BudgetExceeded(f"call budget of {self.max_calls} spent")
        self.used += 1  # counted before the call, so a failed call still uses the budget


class BudgetedClient:
    """Refuses to exceed a call budget. A hard stop against runaway spend."""

    def __init__(self, inner: LLMClient, max_calls: int | CallBudget) -> None:
        self._inner = inner
        self.budget = max_calls if isinstance(max_calls, CallBudget) else CallBudget(max_calls)

    @property
    def calls(self) -> int:
        return self.budget.used

    @property
    def max_calls(self) -> int:
        return self.budget.max_calls

    def complete(self, system: str, user: str) -> str:
        self.budget.spend()
        return self._inner.complete(system, user)


class CachingClient:
    """Append-only JSONL cache keyed on the exact (system, user) pair.

    Reruns of an identical experiment cost nothing. Not safe across processes
    writing the same file, so use one cache file per worker.
    """

    def __init__(self, inner: LLMClient, path: Path, namespace: str = "") -> None:
        self._inner = inner
        self._path = path
        self._ns = namespace  # include the model id so a model swap never hits stale entries
        self._store: dict[str, str] = {}
        self.hits = 0
        self.misses = 0
        if path.exists():
            for line in path.read_text().splitlines():
                rec = json.loads(line)
                self._store[rec["key"]] = rec["text"]

    def _key(self, system: str, user: str) -> str:
        return hashlib.sha256(json.dumps([self._ns, system, user]).encode()).hexdigest()

    def complete(self, system: str, user: str) -> str:
        key = self._key(system, user)
        if key in self._store:
            self.hits += 1
            return self._store[key]
        self.misses += 1
        text = self._inner.complete(system, user)
        self._store[key] = text
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with open(self._path, "a") as f:
            f.write(json.dumps({"key": key, "text": text}) + "\n")
        return text


def extract_json_object(text: str) -> dict[str, Any]:
    """First balanced {...} in the text, tolerating prose and code fences around it."""
    start = text.find("{")
    while start != -1:
        depth = 0
        in_str = False
        esc = False
        for i in range(start, len(text)):
            c = text[i]
            if in_str:
                if esc:
                    esc = False
                elif c == "\\":
                    esc = True
                elif c == '"':
                    in_str = False
            elif c == '"':
                in_str = True
            elif c == "{":
                depth += 1
            elif c == "}":
                depth -= 1
                if depth == 0:
                    try:
                        obj = json.loads(text[start : i + 1])
                    except json.JSONDecodeError:
                        break
                    if isinstance(obj, dict):
                        return obj
                    break
        start = text.find("{", start + 1)
    raise ValueError("no JSON object found")
