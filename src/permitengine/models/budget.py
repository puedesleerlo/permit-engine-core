"""The spend meter. Stops before a call would pass a limit. Persists in ledger/spend.jsonl, so a new process keeps counting.

Every provider goes through this one meter and the one dollar limit. A call whose price is unknown records its tokens with
"price": "unknown": it adds nothing to the dollars, so the dollar limit cannot stop it, and `summary` says so.
"""
import json
import threading
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path


class BudgetExceeded(Exception):
    pass


class Budget:
    """A call first reserves its estimate, so concurrent calls cannot pass the limit together. `settle` swaps it for the real cost."""

    def __init__(self, path: Path, max_usd, max_jev_tokens: int):
        self.path = Path(path)
        self.max_usd = Decimal(str(max_usd))
        self.max_jev_tokens = int(max_jev_tokens)
        self.spent_usd = Decimal(0)
        self.jev_tokens = 0
        self.unpriced = {}  # model -> {"input_tokens": n, "output_tokens": n, "calls": n}
        self._reserved_usd = Decimal(0)
        self._reserved_tokens = 0
        self._lock = threading.Lock()
        if self.path.exists():
            for line in self.path.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    self._count(json.loads(line))

    def _count(self, entry: dict) -> None:
        if entry.get("price") == "unknown":
            row = self.unpriced.setdefault(entry.get("model") or "unknown", {"input_tokens": 0, "output_tokens": 0, "calls": 0})
            row["input_tokens"] += int(entry.get("input_tokens", 0)) + int(entry.get("cache_read_tokens", 0))
            row["output_tokens"] += int(entry.get("output_tokens", 0))
            row["calls"] += 1
        else:
            self.spent_usd += Decimal(entry.get("usd") or "0")
        self.jev_tokens += int(entry.get("jev_input_tokens", 0))

    def reserve(self, usd=0, jev_tokens: int = 0) -> None:
        usd = Decimal(str(usd))
        with self._lock:
            if self.spent_usd + self._reserved_usd + usd > self.max_usd:
                raise BudgetExceeded(f"this call would pass the ${self.max_usd} limit; ${self.spent_usd:.4f} is spent")
            if self.jev_tokens + self._reserved_tokens + jev_tokens > self.max_jev_tokens:
                raise BudgetExceeded(f"this call would pass the Jev limit of {self.max_jev_tokens} input tokens; {self.jev_tokens} are used")
            self._reserved_usd += usd
            self._reserved_tokens += jev_tokens

    def settle(self, reserved_usd=0, reserved_tokens: int = 0, usd=0, jev_tokens: int = 0, **detail) -> None:
        """`usd=None` means the price is unknown: the tokens are recorded and no dollars are guessed."""
        entry = {"when": datetime.now(timezone.utc).isoformat(timespec="seconds"), "jev_input_tokens": jev_tokens, **detail}
        if usd is None:
            entry.update(usd=None, price="unknown")
        else:
            entry["usd"] = str(Decimal(str(usd)))
        with self._lock:
            self._reserved_usd -= Decimal(str(reserved_usd))
            self._reserved_tokens -= reserved_tokens
            self._count(entry)
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(entry, sort_keys=True) + "\n")

    def release(self, reserved_usd=0, reserved_tokens: int = 0) -> None:
        with self._lock:
            self._reserved_usd -= Decimal(str(reserved_usd))
            self._reserved_tokens -= reserved_tokens

    def entries(self) -> int:
        return len(self.path.read_text(encoding="utf-8").splitlines()) if self.path.exists() else 0

    def usage_since(self, entries: int) -> dict:
        """What the calls after this point used: for the project owner at the first stop."""
        lines = self.path.read_text(encoding="utf-8").splitlines()[entries:] if self.path.exists() else []
        out = {"calls": len(lines), "usd": Decimal(0), "input_tokens": 0, "output_tokens": 0, "cache_read_tokens": 0, "cache_write_tokens": 0, "jev_input_tokens": 0, "calls_at_unknown_price": 0}
        for line in lines:
            entry = json.loads(line)
            out["usd"] += Decimal(entry.get("usd") or "0")
            out["calls_at_unknown_price"] += entry.get("price") == "unknown"
            for name in ("input_tokens", "output_tokens", "cache_read_tokens", "cache_write_tokens", "jev_input_tokens"):
                out[name] += int(entry.get(name) or 0)
        out["usd"] = str(out["usd"])
        return out

    def summary(self) -> str:
        lines = [f"Spent ${self.spent_usd:.4f} of ${self.max_usd}. Jev: {self.jev_tokens} of {self.max_jev_tokens} input tokens."]
        for model, row in sorted(self.unpriced.items()):
            lines.append(f"Price unknown for {model}: {row['calls']} calls, {row['input_tokens']} input and {row['output_tokens']} output tokens. "
                         "These are not in the dollar total, so the dollar limit cannot stop them.")
        return "\n".join(lines)
