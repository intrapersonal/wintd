import math

import numpy as np

from .names import TIPS, PIPS

PINCH_ON = 0.3
PINCH_OFF = 0.5


def dist(lm, a, b, asp):
    return math.hypot((lm[a, 0] - lm[b, 0]) * asp, lm[a, 1] - lm[b, 1])


def hand_size(lm, asp):
    return max(dist(lm, 0, 9, asp), 1e-3)


def palm(lm):
    return lm[[0, 5, 9, 17], :2].mean(axis=0)


def fingers(lm, asp):
    size = hand_size(lm, asp)
    ext = [False] * 5
    for f in range(1, 5):
        ext[f] = dist(lm, 0, TIPS[f], asp) > dist(lm, 0, PIPS[f], asp) * 1.18
    ext[0] = dist(lm, 4, 9, asp) > dist(lm, 3, 9, asp) * 1.12 and dist(lm, 4, 5, asp) > size * 0.45
    return ext, size


class HandState:
    def __init__(self):
        self.reset()

    def reset(self):
        self.pinch = False
        self.prev_palm = None
        self.prev_size = None
        self.prev_t = None
        self.vel = np.zeros(2)
        self.push = 0.0
        self.swipe = np.zeros(2)
        self.swipe_until = 0.0
        self.swipe_cool = 0.0

    def update(self, lm, asp, t):
        ext, size = fingers(lm, asp)
        p = palm(lm)
        if self.prev_t is not None:
            dt = max(t - self.prev_t, 1e-3)
            v = np.array([(p[0] - self.prev_palm[0]) / dt, -(p[1] - self.prev_palm[1]) / dt])
            self.vel += (v - self.vel) * 0.5
            self.push += ((size - self.prev_size) / dt / size - self.push) * 0.5
        self.prev_palm, self.prev_size, self.prev_t = p, size, t
        amt = dist(lm, 4, 8, asp) / size
        self.pinch = amt < PINCH_OFF if self.pinch else amt < PINCH_ON
        speed = math.hypot(self.vel[0] * asp, self.vel[1])
        if t > self.swipe_until:
            self.swipe[:] = 0
        if speed > 2.2 and t > self.swipe_cool:
            if abs(self.vel[0] * asp) > abs(self.vel[1]):
                self.swipe[:] = (math.copysign(1, self.vel[0]), 0)
            else:
                self.swipe[:] = (0, math.copysign(1, self.vel[1]))
            self.swipe_until = t + 0.25
            self.swipe_cool = t + 0.5
        n = sum(ext[1:])
        up_x = (lm[9, 0] - lm[0, 0]) * asp
        up_y = -(lm[9, 1] - lm[0, 1])
        thumbs = ext[0] and n == 0 and lm[4, 1] < lm[3, 1] < lm[2, 1]
        pin = (lm[4, :2] + lm[8, :2]) / 2
        return {
            "size": size,
            "palm_x": p[0],
            "palm_y": 1 - p[1],
            "angle": math.degrees(math.atan2(up_y, up_x)),
            "vel_x": self.vel[0],
            "vel_y": self.vel[1],
            "speed": speed,
            "push": self.push,
            "fingers": float(sum(ext)),
            "open": float(n == 4),
            "fist": float(n == 0 and not self.pinch and not ext[0]),
            "point": float(ext[1] and not ext[2] and not ext[3] and not ext[4]),
            "peace": float(ext[1] and ext[2] and not ext[3] and not ext[4]),
            "spidey": float(ext[1] and ext[4] and not ext[2] and not ext[3]),
            "thumbsup": float(thumbs),
            "pinch": float(self.pinch),
            "pinch_amt": amt,
            "pinch_x": pin[0],
            "pinch_y": 1 - pin[1],
            "swipe_x": self.swipe[0],
            "swipe_y": self.swipe[1],
        }


class PairState:
    def __init__(self):
        self.prev = None
        self.prev_t = None
        self.clap_until = 0.0
        self.cool = 0.0

    def update(self, a, b, asp, t):
        if a is None or b is None:
            self.prev = None
            self.prev_t = None
            return {"dist": 0.0, "angle": 0.0, "center_x": 0.0, "center_y": 0.0, "clap": float(t < self.clap_until)}
        pa, pb = palm(a), palm(b)
        dx, dy = (pb[0] - pa[0]) * asp, -(pb[1] - pa[1])
        d = math.hypot(dx, dy)
        unit = (hand_size(a, asp) + hand_size(b, asp)) / 2
        if self.prev is not None:
            closing = (self.prev - d) / max(t - self.prev_t, 1e-3) / unit
            if d / unit < 1.3 and closing > 6 and t > self.cool:
                self.clap_until = t + 0.2
                self.cool = t + 0.5
        self.prev, self.prev_t = d, t
        return {
            "dist": d,
            "angle": math.degrees(math.atan2(dy, dx)),
            "center_x": (pa[0] + pb[0]) / 2,
            "center_y": 1 - (pa[1] + pb[1]) / 2,
            "clap": float(t < self.clap_until),
        }
