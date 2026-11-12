"""Cost ledger: every LLM call recorded. Keyless runs cost exactly $0.

Usage stats live on the result meta (tokens in/out when the provider reports
them, else chars/4 estimate). Aggregate with evals/eval.py --cost or read
COSTS.jsonl appended per query when QLERIC_COST_LOG=1.
"""
from __future__ import annotations

import json
import os
import time

LEDGER: list[dict] = []


def estimate_tokens(text: str) -> int:
    return max(1, len(text) // 4)


def record(model: str, prompt_chars: int, completion_chars: int,
           prompt_tokens: int = 0, completion_tokens: int = 0,
           cost_usd: float = 0.0) -> dict:
    entry = {
        "ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "model": model,
        "prompt_tokens": prompt_tokens or estimate_tokens("x" * prompt_chars),
        "completion_tokens": completion_tokens or estimate_tokens("x" * completion_chars),
        "cost_usd": cost_usd,
    }
    LEDGER.append(entry)
    if os.getenv("QLERIC_COST_LOG") == "1":
        with open("COSTS.jsonl", "a") as f:
            f.write(json.dumps(entry) + "\n")
    return entry


def total() -> dict:
    return {
        "calls": len(LEDGER),
        "prompt_tokens": sum(e["prompt_tokens"] for e in LEDGER),
        "completion_tokens": sum(e["completion_tokens"] for e in LEDGER),
        "cost_usd": round(sum(e["cost_usd"] for e in LEDGER), 6),
    }


# Per-1M-token prices (update as providers change). Unknown models: estimate at $0.
PRICES = {
    "gpt-4o-mini": (0.15, 0.60),
    "gpt-6-luna": (0.10, 0.50),
    "gpt-6-sol": (2.00, 10.00),
    "gpt-6-astra": (10.00, 50.00),
    "gpt-4o": (2.50, 10.00),
    "claude-sonnet-4-6": (3.00, 15.00),
    "claude-haiku-4-5": (1.00, 5.00),
}


def price(model: str, prompt_tokens: int, completion_tokens: int) -> float:
    for prefix, (pin, pout) in PRICES.items():
        if model.startswith(prefix):
            return prompt_tokens / 1e6 * pin + completion_tokens / 1e6 * pout
    return 0.0
