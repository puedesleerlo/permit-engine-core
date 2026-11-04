"""Runs `opa eval` with the capabilities file. Any error, or an undefined result, raises PolicyError: the caller fails closed."""
import json
import subprocess
from pathlib import Path

from ..hashing import files_hash


class PolicyError(Exception):
    pass


class Policy:
    def __init__(self, rules_dir: Path, opa_bin: str = "opa", timeout: float = 120):
        self.rego_dir = Path(rules_dir) / "rego"
        self.capabilities = self.rego_dir / "capabilities.json"
        self.opa_bin = opa_bin
        self.timeout = timeout

    def _run(self, query: str, stdin: str) -> dict:
        if not self.capabilities.exists():
            raise PolicyError(f"{self.capabilities} is missing")
        command = [self.opa_bin, "eval", "--capabilities", str(self.capabilities), "--data", str(self.rego_dir),
                   "--ignore", "*_test.rego", "--format", "json", "--stdin-input", query]
        try:
            done = subprocess.run(command, input=stdin, capture_output=True, text=True, timeout=self.timeout)
        except (OSError, subprocess.SubprocessError) as exc:
            raise PolicyError(f"opa did not run: {type(exc).__name__}") from None
        if done.returncode != 0:
            raise PolicyError(f"opa failed: {done.stderr.strip()[:500] or done.stdout.strip()[:500]}")
        try:
            return json.loads(done.stdout)
        except ValueError:
            raise PolicyError("opa returned something that is not JSON") from None

    def batch(self, query: str, inputs: list) -> list:
        """One result per input, in order, from one subprocess. An undefined result for any input is an error."""
        if not inputs:
            return []
        wrapped = f"out := {{i: r | x := input.batch[i]; r := {query} with input as x}}"
        reply = self._run(wrapped, json.dumps({"batch": inputs}))
        try:
            found = reply["result"][0]["bindings"]["out"]
        except (KeyError, IndexError, TypeError):
            raise PolicyError(f"{query}: no result") from None
        out = []
        for i in range(len(inputs)):
            if str(i) not in found:
                raise PolicyError(f"{query}: undefined for input {i}")
            out.append(found[str(i)])
        return out

    def one(self, query: str, value: dict):
        return self.batch(query, [value])[0]

    def bundle_hash(self) -> str:
        return files_hash(p for p in self.rego_dir.iterdir() if p.is_file())

    def opa_version(self) -> str:
        try:
            done = subprocess.run([self.opa_bin, "version"], capture_output=True, text=True, timeout=30)
        except (OSError, subprocess.SubprocessError):
            return "unknown"
        return done.stdout.splitlines()[0].strip() if done.returncode == 0 and done.stdout else "unknown"
