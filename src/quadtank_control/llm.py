"""Thin, testable layer between the harness and a language-model API.

Everything that talks to a model goes through the LLMClient protocol, so the
supervisor and monitor can be tested with a fake and wrapped with a spend guard
and an on-disk cache. Nothing in here is exercised against a live API by the test
suite. The Anthropic client has only been checked against a stub of the SDK.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol


class LLMError(RuntimeError):
    """The call failed in a way the caller should treat as a lost response."""


class LLMRefusal(LLMError):
    """The model declined (stop_reason == "refusal")."""


class BudgetExceeded(LLMError):
    """The call budget is spent. Raised before the call is made."""


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
            raise LLMRefusal(f"{self.cfg.model} refused")
        text = "".join(b.text for b in response.content if getattr(b, "type", "") == "text")
        if not text:
            raise LLMError(f"{self.cfg.model} returned no text (stop_reason={response.stop_reason})")
        return text


class BudgetedClient:
    """Refuses to exceed max_calls. A hard stop against runaway spend."""

    def __init__(self, inner: LLMClient, max_calls: int) -> None:
        self._inner = inner
        self.max_calls = max_calls
        self.calls = 0

    def complete(self, system: str, user: str) -> str:
        if self.calls >= self.max_calls:
            raise BudgetExceeded(f"call budget of {self.max_calls} spent")
        self.calls += 1
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
