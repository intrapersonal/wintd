import math

import cv2
import numpy as np

from .names import HAND_BONES, POSE_BONES, TIPS

LEFT = (230, 138, 164, 255)
RIGHT = (143, 197, 92, 255)
ACCENT = (63, 152, 227, 255)
INK = (236, 236, 232, 255)
SOFT = (236, 236, 232, 150)
FAINT = (236, 236, 232, 90)
SHADOW = (12, 12, 14, 170)
FONT = cv2.FONT_HERSHEY_DUPLEX
AA = cv2.LINE_AA


def label_for(g):
    if g["pinch"]:
        return "pinch"
    for k, name in (("spidey", "spidey"), ("thumbsup", "thumbs up"), ("peace", "peace"),
                    ("point", "point"), ("fist", "fist"), ("open", "open")):
        if g[k]:
            return name
    return f"{int(g['fingers'])}"


class Overlay:
    def __init__(self, width, height):
        self.resize(width, height)

    def resize(self, width, height):
        self.w = width
        self.h = height
        self.canvas = np.zeros((height, width, 4), np.uint8)
        self.s = max(0.6, height / 720)

    def px(self, pts):
        out = np.empty((len(pts), 2), np.int32)
        out[:, 0] = np.round(pts[:, 0] * self.w * 16)
        out[:, 1] = np.round(pts[:, 1] * self.h * 16)
        return out

    def line(self, a, b, color, w):
        cv2.line(self.canvas, tuple(a), tuple(b), color, max(1, int(round(w))), AA, 4)

    def poly(self, p, color, w, closed=False):
        cv2.polylines(self.canvas, [p.reshape(-1, 1, 2)], closed, color, max(1, int(round(w))), AA, 4)

    def measure(self, s, scale=0.42):
        sc = scale * self.s
        th = max(1, int(round(self.s)))
        (tw, tht), _ = cv2.getTextSize(s, FONT, sc, th)
        return tw, tht, sc, th

    def tag(self, s, x, y, color):
        tw, tht, sc, th = self.measure(s)
        pad = int(5 * self.s)
        x0, y0 = int(x), int(y - tht - pad * 2)
        cv2.rectangle(self.canvas, (x0, y0), (x0 + tw + pad * 2, int(y)), SHADOW, -1)
        cv2.rectangle(self.canvas, (x0, y0), (x0 + int(2 * self.s), int(y)), color, -1)
        cv2.putText(self.canvas, s, (x0 + pad + int(2 * self.s), int(y) - pad), FONT, sc, INK, th, AA)

    def draw(self, hands=None, face=None, pose=None):
        c = self.canvas
        c[:] = 0
        if pose:
            self.draw_pose(pose)
        if face:
            self.draw_face(face)
        if hands:
            self.draw_hands(hands)
        return c

    def draw_hands(self, data):
        s = self.s
        palms = []
        for h in data["hands"]:
            color = LEFT if h["left"] else RIGHT
            p = self.px(h["lm"])
            for a, b in HAND_BONES:
                self.line(p[a], p[b], color[:3] + (200,), 1.6 * s)
            for i, q in enumerate(p):
                x, y = int(q[0] / 16), int(q[1] / 16)
                if i in TIPS:
                    r = int(6 * s)
                    cv2.line(self.canvas, (x - r, y), (x + r, y), INK, max(1, int(s)), AA)
                    cv2.line(self.canvas, (x, y - r), (x, y + r), INK, max(1, int(s)), AA)
                else:
                    r = max(2, int(2.5 * s))
                    cv2.rectangle(self.canvas, (x - r, y - r), (x + r, y + r), color, 1, AA)
            g = h["g"]
            px = int(g["palm_x"] * self.w)
            py = int((1 - g["palm_y"]) * self.h)
            palms.append((px, py))
            rad = int(g["size"] * self.h * 0.42)
            cv2.circle(self.canvas, (px, py), rad, color[:3] + (110,), 1, AA)
            for k in range(4):
                a = math.radians(g["angle"]) + k * math.pi / 2
                x1, y1 = px + math.cos(a) * rad, py - math.sin(a) * rad
                x2, y2 = px + math.cos(a) * (rad + 7 * s), py - math.sin(a) * (rad + 7 * s)
                cv2.line(self.canvas, (int(x1), int(y1)), (int(x2), int(y2)), color, max(1, int(s)), AA)
            t4, t8 = p[4], p[8]
            amt = min(1.0, g["pinch_amt"] / 0.6)
            mx, my = (t4 + t8) // 2
            if g["pinch"]:
                cv2.circle(self.canvas, (int(mx / 16), int(my / 16)), int(7 * s), ACCENT, -1, AA)
            else:
                self.line(t4, t8, color[:3] + (int(90 + 120 * (1 - amt)),), 1 * s)
            name = ("L " if h["left"] else "R ") + label_for(g)
            tw = self.measure(name)[0]
            wx, wy = p[0] // 16
            self.tag(name, wx - tw / 2 - 6 * s, wy + 30 * s, color)
        if len(palms) == 2:
            (ax, ay), (bx, by) = palms
            n = max(2, int(math.hypot(bx - ax, by - ay) / (9 * s)))
            for k in range(0, n, 2):
                u0, u1 = k / n, min(1, (k + 1) / n)
                cv2.line(self.canvas, (int(ax + (bx - ax) * u0), int(ay + (by - ay) * u0)),
                         (int(ax + (bx - ax) * u1), int(ay + (by - ay) * u1)), FAINT, 1, AA)
            if data["pair"].get("clap"):
                cv2.circle(self.canvas, ((ax + bx) // 2, (ay + by) // 2), int(30 * s), ACCENT, 2, AA)

    def draw_face(self, f):
        s = self.s
        self.poly(self.px(f["oval"]), FAINT, 1, True)
        for k in ("eye_l", "eye_r", "lips"):
            self.poly(self.px(f[k]), SOFT, 1, True)
        for k in ("brow_l", "brow_r"):
            self.poly(self.px(f[k]), SOFT, 1.4 * s)
        if f.get("iris") is not None:
            for q in self.px(f["iris"]):
                cv2.circle(self.canvas, (int(q[0] / 16), int(q[1] / 16)), max(2, int(2.5 * s)), ACCENT, -1, AA)
        chin = self.px(f["oval"][18:19])[0] // 16
        bw = int(46 * s)
        x0, y0 = int(chin[0] - bw / 2), int(chin[1] + 12 * s)
        cv2.rectangle(self.canvas, (x0, y0), (x0 + bw, y0 + int(4 * s)), FAINT, 1)
        fill = int(bw * min(1.0, f["mouth"] / 0.25))
        if fill > 0:
            cv2.rectangle(self.canvas, (x0, y0), (x0 + fill, y0 + int(4 * s)), ACCENT, -1)

    def draw_pose(self, pose):
        s = self.s
        p = self.px(pose["lm"])
        vis = pose["vis"]
        for a, b in POSE_BONES:
            if vis[a] > 0.5 and vis[b] > 0.5:
                self.line(p[a], p[b], SOFT, 2 * s)
        for i, q in enumerate(p):
            if vis[i] > 0.5 and i > 10:
                cv2.circle(self.canvas, (int(q[0] / 16), int(q[1] / 16)), max(2, int(3 * s)), INK, 1, AA)
