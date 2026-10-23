import math

import numpy as np


class OneEuro:
    def __init__(self, min_cutoff=1.2, beta=0.04, d_cutoff=1.0):
        self.min_cutoff = min_cutoff
        self.beta = beta
        self.d_cutoff = d_cutoff
        self.x = None
        self.dx = None
        self.t = None

    def reset(self):
        self.x = None
        self.dx = None
        self.t = None

    @staticmethod
    def _alpha(cutoff, dt):
        tau = 1.0 / (2 * math.pi * cutoff)
        return 1.0 / (1.0 + tau / dt)

    def __call__(self, x, t):
        x = np.asarray(x, dtype=np.float64)
        if self.x is None or self.x.shape != x.shape:
            self.x = x.copy()
            self.dx = np.zeros_like(x)
            self.t = t
            return self.x.copy()
        dt = max(t - self.t, 1e-4)
        self.t = t
        dx = (x - self.x) / dt
        ad = self._alpha(self.d_cutoff, dt)
        self.dx = self.dx + ad * (dx - self.dx)
        cutoff = self.min_cutoff + self.beta * np.abs(self.dx)
        tau = 1.0 / (2 * math.pi * cutoff)
        a = 1.0 / (1.0 + tau / dt)
        self.x = self.x + a * (x - self.x)
        return self.x.copy()


def smoothing_params(amount):
    amount = min(max(float(amount), 0.0), 1.0)
    return 4.0 * (1 - amount) + 0.15 * amount, 0.3 * (1 - amount) + 0.004 * amount
