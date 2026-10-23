import gzip
import json
import math
import os

import numpy as np

BASE = np.array([
    [0, 0.5], [-0.25, 0.35], [-0.4, 0.2], [-0.5, 0.05], [-0.55, -0.1],
    [-0.2, 0], [-0.22, -0.3], [-0.23, -0.48], [-0.24, -0.62],
    [0, 0], [0, -0.33], [0, -0.52], [0, -0.68],
    [0.18, 0.02], [0.2, -0.28], [0.21, -0.45], [0.22, -0.58],
    [0.33, 0.08], [0.36, -0.15], [0.38, -0.3], [0.39, -0.42],
])


def curl(pts, f, k):
    mcp = (1, 5, 9, 13, 17)[f]
    for j in range(1, 4):
        tgt = pts[mcp] + np.array([0.0, 0.07 * j])
        pts[mcp + j] = pts[mcp + j] * (1 - k) + tgt * k


def hand(cx, cy, size, asp, side, angle=0.0, pinch=0.0, fist=0.0):
    pts = BASE.copy()
    if side < 0:
        pts[:, 0] *= -1
    for f in range(1, 5):
        curl(pts, f, fist)
    if pinch > 0:
        pts[4] = pts[4] * (1 - pinch) + pts[8] * pinch
    c, s = math.cos(angle), math.sin(angle)
    rot = pts @ np.array([[c, s], [-s, c]])
    out = np.zeros((21, 3))
    out[:, 0] = cx + rot[:, 0] * size / asp
    out[:, 1] = cy + rot[:, 1] * size
    out[:, 2] = -0.02
    return out


class SyntheticHands:
    def __init__(self, asp, period=8.0):
        self.asp = asp
        self.period = period

    def __call__(self, t):
        ph = (t % self.period) / self.period
        a = t * 0.9
        gap = 0.18 + 0.1 * math.sin(a)
        if 0.82 < ph < 0.93:
            k = min(1.0, (ph - 0.82) / 0.05)
            gap = (0.18 + 0.1 * math.sin(a)) * (1 - k) + 0.012 * k
        pinch_l = max(0.0, math.sin(t * 2.1)) ** 4
        fist_r = 1.0 if 0.5 < ph < 0.62 else 0.0
        cy = 0.5 + 0.06 * math.sin(a * 0.7)
        left = hand(0.5 - gap, cy, 0.2, self.asp, -1, 0.15 * math.sin(a), pinch_l)
        right = hand(0.5 + gap, cy, 0.2, self.asp, 1, -0.15 * math.sin(a), 0.0, fist_r)
        return [(left, "Left", 1.0), (right, "Right", 1.0)]


class Replay:
    def __init__(self, folder, kind):
        self.items = []
        path = os.path.join(folder, f"{kind}.jsonl.gz")
        if os.path.exists(path):
            with gzip.open(path, "rt") as f:
                for line in f:
                    try:
                        o = json.loads(line)
                        self.items.append((o["t"], o["d"]))
                    except Exception:
                        pass
        self.t0 = self.items[0][0] if self.items else 0.0
        self.length = (self.items[-1][0] - self.t0) if self.items else 0.0
        self.i = 0
        self.start = None

    def due(self, now):
        if not self.items:
            return []
        if self.start is None:
            self.start = now
        local = (now - self.start)
        if self.length > 0 and local > self.length:
            self.start = now
            self.i = 0
            local = 0.0
        out = []
        while self.i < len(self.items) and self.items[self.i][0] - self.t0 <= local:
            out.append(self.items[self.i])
            self.i += 1
        return out
