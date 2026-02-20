"""
Centralised LLM factory with provider fallback.

Primary: Groq (round-robin across keys).
Fallback: OpenAI (single key).

Usage:
    from app.llm import get_llm
    llm = get_llm()                      # uses default temp
    llm = get_llm(temperature=0.0)       # override temp
"""
from __future__ import annotations

import itertools
import logging
import threading

from langchain_groq import ChatGroq
from langchain_openai import ChatOpenAI

from app.config import (
    GROQ_API_KEYS,
    GROQ_MODEL,
    GROQ_TEMPERATURE,
    OPENAI_API_KEY,
    OPENAI_MODEL,
    OPENAI_TEMPERATURE,
)

logger = logging.getLogger("rift.llm")

# ── Thread-safe round-robin key iterator ────────────────────

_lock = threading.Lock()
_cycle: itertools.cycle[str] | None = None


def _next_key() -> str:
    """Return the next API key in round-robin order (thread-safe)."""
    global _cycle
    with _lock:
        if _cycle is None:
            if not GROQ_API_KEYS:
                raise RuntimeError(
                    "No Groq API keys configured. "
                    "Set GROQ_API_KEYS as a comma-separated list in .env"
                )
            _cycle = itertools.cycle(GROQ_API_KEYS)
            logger.info("Initialised Groq key rotator with %d keys", len(GROQ_API_KEYS))
        return next(_cycle)


# ── Public factory ──────────────────────────────────────────

def get_llm(
    *,
    temperature: float | None = None,
    model: str | None = None,
) -> ChatGroq | ChatOpenAI:
    """
    Return an LLM client with fallback strategy:
      1) Groq round-robin, if GROQ_API_KEYS is configured
      2) OpenAI, if OPENAI_API_KEY is configured
    """
    if GROQ_API_KEYS:
        key = _next_key()
        return ChatGroq(
            model=model or GROQ_MODEL,
            temperature=temperature if temperature is not None else GROQ_TEMPERATURE,
            api_key=key,
        )

    if OPENAI_API_KEY:
        return ChatOpenAI(
            model=model or OPENAI_MODEL,
            temperature=temperature if temperature is not None else OPENAI_TEMPERATURE,
            api_key=OPENAI_API_KEY,
        )

    raise RuntimeError(
        "No LLM keys configured. Set GROQ_API_KEYS or OPENAI_API_KEY in environment."
    )


def has_llm_keys() -> bool:
    """Return True if at least one configured provider is available."""
    return bool(GROQ_API_KEYS or OPENAI_API_KEY)
