"""Local credentials + secrets loader.

Credentials live in a local file under the user's control, always. Drufiy's
servers never receive them. This is the whole trust model of Lear, so the
loader is deliberately small and dependency-free.

Format is a simple ``KEY=VALUE`` line file (``.env`` style). ``#`` starts a
comment. The same file also carries the secrets Prash has been given (e.g. the
missing-secret action), with ``PRASH_SECRET_<name>`` keys.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Mapping, Optional

_LINE_RE = re.compile(r"^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*?)\s*$")
_SECRET_PREFIX = "PRASH_SECRET_"


@dataclass
class CredentialStore:
    path: Path

    @classmethod
    def from_env(cls) -> "CredentialStore":
        explicit = os.environ.get("PRASH_ENV")
        if explicit:
            return cls(path=Path(explicit).expanduser())
        cwd_env = Path(".env")
        if cwd_env.exists():
            return cls(path=cwd_env)
        return cls(path=Path("~/.prash/.env").expanduser())

    def load(self) -> Dict[str, Any]:
        if not self.path.exists():
            return {}
        data: Dict[str, Any] = {}
        for raw in self.path.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            match = _LINE_RE.match(line)
            if match:
                key, value = match.groups()
                data[key] = value.strip('"').strip("'")
        return data

    def secrets(self) -> Dict[str, str]:
        """Only the PRASH_SECRET_* entries, keys without the prefix."""
        all_data = self.load()
        return {
            k[len(_SECRET_PREFIX):]: str(v)
            for k, v in all_data.items()
            if k.startswith(_SECRET_PREFIX)
        }

    def set_secret(self, name: str, value: str) -> None:
        """Write a secret value to the local file. Appends; never rewrites."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.touch(exist_ok=True)
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(f"{_SECRET_PREFIX}{name}={value}\n")

    def sanitized(self) -> Dict[str, Any]:
        """Credentials safe for display: secret values redacted."""
        return {k: ("<redacted>" if k.startswith(_SECRET_PREFIX) else v) for k, v in self.load().items()}
