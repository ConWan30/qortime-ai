"""Left-stick log from a QorCap ``qorcap-inputs/v0`` file (records with ``type == "in"`` and ``lx``/``ly``).

Stick values are mapped to [-1, 1] with +x = right and +y = down, i.e. the same axes as screen pixels.
Only the left stick is used. Nothing here is written anywhere; the raw timeline never reaches a sidecar.
"""
from __future__ import annotations

import io
import json
import zipfile
from pathlib import Path
from typing import Any, Iterable

import numpy as np

ACTIVE = 0.35            # stick deflection that counts as "moving the stick" (dead zone is well below this)
HALF_WINDOW_US = 50_000  # stick sample = mean over +-50 ms (reports arrive on change, at most every ~4 ms)


class StickLog:
    def __init__(self, records: Iterable[dict[str, Any]], name: str = "log"):
        t, s, b = [], [], []
        for d in records:
            if d.get("type") != "in" or "lx" not in d:
                continue
            t.append(int(d["t_us"]))
            s.append((d["lx"], d["ly"]))
            b.append(int(d.get("b", 0)))
        if not t:
            raise ValueError(f"{name}: no left-stick records (lx/ly)")
        o = np.argsort(t, kind="stable")
        self.name = name
        self.T = np.asarray(t, np.int64)[o]
        self.S = (np.asarray(s, float)[o] - 127.5) / 127.5
        self.cs = np.vstack([[0.0, 0.0], np.cumsum(self.S, 0)])
        self.B = np.asarray(b, np.int64)[o]

    def press_times(self, bit: int) -> np.ndarray:
        """Input-clock times (t_us) at which button ``bit`` goes from up to down. Used only to DROP frames."""
        down = (self.B & bit) != 0
        rise = down & ~np.concatenate([[False], down[:-1]])
        return self.T[rise]

    @classmethod
    def from_path(cls, p: str | Path, name: str | None = None) -> "StickLog":
        """``inputs.jsonl`` or ``archive.zip::member.jsonl``."""
        p = str(p)
        if "::" in p:
            z, m = p.split("::", 1)
            with zipfile.ZipFile(z) as zf:
                lines = io.TextIOWrapper(zf.open(m), encoding="utf-8").read().splitlines()
            return cls((json.loads(x) for x in lines if x.strip()), name or Path(z).stem)
        lines = Path(p).read_text(encoding="utf-8").splitlines()
        return cls((json.loads(x) for x in lines if x.strip()), name or Path(p).parent.name or Path(p).stem)

    @property
    def span_us(self) -> tuple[int, int]:
        return int(self.T[0]), int(self.T[-1])

    def stick_at(self, t_us) -> np.ndarray:
        """Mean stick over [t - 50 ms, t + 50 ms]; with no report in that span, the last report before t."""
        t_us = np.asarray(t_us, np.int64)
        i0 = np.searchsorted(self.T, t_us - HALF_WINDOW_US)
        i1 = np.searchsorted(self.T, t_us + HALF_WINDOW_US)
        n = (i1 - i0)[:, None]
        mean = (self.cs[i1] - self.cs[i0]) / np.maximum(n, 1)
        j = np.clip(np.searchsorted(self.T, t_us) - 1, 0, len(self.T) - 1)
        return np.where(n > 0, mean, self.S[j])
