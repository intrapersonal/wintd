import math

import numpy as np

from .filters import OneEuro, smoothing_params
from .gestures import HandState, PairState, palm
from .names import (
    BLENDSHAPES, BROW_L, BROW_R, EYE_L, EYE_R, FACE_OVAL, FACE_POINTS, HAND_FLAGS, HAND_JOINTS,
    LIPS, PAIR_FLAGS, POSE_JOINTS,
)
from .osc import ChannelSender


class Coords:
    def __init__(self, width, height, world=False, pixel=False):
        self.w = width
        self.h = height
        self.asp = width / height
        self.world = world
        self.pixel = pixel

    def suffixes(self, z=True):
        s = ["x", "y"] + (["z"] if z else [])
        if self.world:
            s += ["tx", "ty"]
        if self.pixel:
            s += ["px", "py"]
        return s

    def expand(self, pts, z=True):
        x = pts[:, 0]
        y = pts[:, 1]
        cols = [x, 1 - y]
        if z:
            cols.append(pts[:, 2] if pts.shape[1] > 2 else np.zeros_like(x))
        if self.world:
            cols += [x - 0.5, (0.5 - y) / self.asp]
        if self.pixel:
            cols += [x * self.w, (1 - y) * self.h]
        return np.stack(cols, axis=1)


class Publisher:
    port_offset = 0

    def __init__(self, cfg):
        self.cfg = dict(cfg)
        self.sender = None
        self.configure(cfg)

    def configure(self, cfg):
        self.cfg = dict(cfg)
        self.coords = Coords(cfg["width"], cfg["height"], cfg.get("world", False), cfg.get("pixel", False))
        self.names = self.build_names()
        self.values = np.zeros(len(self.names), dtype=np.float32)
        port = int(cfg["port"]) + self.port_offset
        if self.sender is None:
            self.sender = ChannelSender(cfg.get("host", "127.0.0.1"), port, self.names)
        else:
            self.sender.target = (cfg.get("host", "127.0.0.1"), port)
            self.sender.set_names(self.names)
        self.index = {n: i for i, n in enumerate(self.names)}
        mc, beta = smoothing_params(cfg.get("smoothing", 0.5))
        self.filter_args = (mc, beta)

    def emit(self):
        self.sender.send(self.values)

    def build_names(self):
        raise NotImplementedError


class HandsPublisher(Publisher):
    port_offset = 0

    def configure(self, cfg):
        self.slots = max(1, min(4, int(cfg.get("num_hands", 2))))
        self.states = [HandState() for _ in range(self.slots)]
        self.pair = PairState()
        self.prev_palms = [None] * self.slots
        super().configure(cfg)
        self.filters = [OneEuro(*self.filter_args) for _ in range(self.slots)]

    def build_names(self):
        names = []
        suf = self.coords.suffixes()
        for s in range(self.slots):
            for j in HAND_JOINTS:
                names += [f"h{s}_{j}_{k}" for k in suf]
            names += [f"h{s}_{f}" for f in HAND_FLAGS]
        names += [f"hands_{f}" for f in PAIR_FLAGS]
        return names

    def assign(self, hands):
        slots = [None] * self.slots
        free = list(range(len(hands)))
        if self.slots >= 2:
            for pref, label in ((0, "Left"), (1, "Right")):
                cands = [i for i in free if hands[i][1] == label]
                if not cands:
                    continue
                if len(cands) > 1 and self.prev_palms[pref] is not None:
                    pp = self.prev_palms[pref]
                    cands.sort(key=lambda i: np.linalg.norm(palm(hands[i][0]) - pp))
                slots[pref] = cands[0]
                free.remove(cands[0])
        for s in range(self.slots):
            if slots[s] is not None or not free:
                continue
            pp = self.prev_palms[s]
            if pp is not None:
                free.sort(key=lambda i: np.linalg.norm(palm(hands[i][0]) - pp))
            slots[s] = free.pop(0)
        return slots

    def publish(self, hands, t):
        asp = self.coords.asp
        v = self.values
        v[:] = 0
        per = len(HAND_JOINTS) * len(self.coords.suffixes()) + len(HAND_FLAGS)
        slots = self.assign(hands)
        smooth = []
        summary = []
        for s, hi in enumerate(slots):
            base = s * per
            if hi is None:
                self.states[s].reset()
                self.filters[s].reset()
                self.prev_palms[s] = None
                smooth.append(None)
                continue
            lm, label, score = hands[hi]
            lm = self.filters[s](lm, t)
            smooth.append(lm)
            self.prev_palms[s] = palm(lm)
            g = self.states[s].update(lm, asp, t)
            block = self.coords.expand(lm).reshape(-1)
            v[base:base + block.size] = block
            f0 = base + block.size
            flags = dict(g, present=1.0, left=float(label == "Left"), score=float(score))
            for k, name in enumerate(HAND_FLAGS):
                v[f0 + k] = flags.get(name, 0.0)
            summary.append({"slot": s, "lm": lm[:, :2].copy(), "left": label == "Left", "g": g})
        a = smooth[0] if self.slots > 0 else None
        b = smooth[1] if self.slots > 1 else None
        pair = self.pair.update(a, b, asp, t)
        pair["count"] = float(sum(x is not None for x in smooth))
        p0 = self.slots * per
        for k, name in enumerate(PAIR_FLAGS):
            v[p0 + k] = pair.get(name, 0.0)
        self.emit()
        return {"hands": summary, "pair": pair}


class FacePublisher(Publisher):
    port_offset = 2

    def configure(self, cfg):
        super().configure(cfg)
        self.f_pts = OneEuro(*self.filter_args)
        self.f_bs = OneEuro(self.filter_args[0] * 2, self.filter_args[1])
        self.f_head = OneEuro(*self.filter_args)

    def build_names(self):
        suf = self.coords.suffixes()
        names = ["f_present"]
        for n, _ in FACE_POINTS:
            names += [f"f_{n}_{k}" for k in suf]
        names += ["f_yaw", "f_pitch", "f_roll", "f_tx", "f_ty", "f_tz", "f_mouth_open", "f_blink_l", "f_blink_r"]
        names += [f"bs_{b.strip('_')}" for b in BLENDSHAPES]
        return names

    def publish(self, face, t):
        v = self.values
        v[:] = 0
        if face is None:
            self.f_pts.reset()
            self.f_bs.reset()
            self.f_head.reset()
            self.emit()
            return None
        pts, bs, mat = face
        pts = self.f_pts(pts, t)
        v[0] = 1
        idx = [i for _, i in FACE_POINTS if i < len(pts)]
        block = self.coords.expand(pts[idx]).reshape(-1)
        v[1:1 + block.size] = block
        o = 1 + len(FACE_POINTS) * len(self.coords.suffixes())
        head = np.zeros(6)
        if mat is not None:
            r = mat[:3, :3]
            head[0] = math.degrees(math.atan2(-r[2, 0], math.hypot(r[2, 1], r[2, 2])))
            head[1] = math.degrees(math.atan2(r[2, 1], r[2, 2]))
            head[2] = math.degrees(math.atan2(r[1, 0], r[0, 0]))
            head[3:] = mat[:3, 3]
        head = self.f_head(head, t)
        v[o:o + 6] = head
        asp = self.coords.asp
        fh = max(math.hypot((pts[10, 0] - pts[152, 0]) * asp, pts[10, 1] - pts[152, 1]), 1e-3)
        mouth = math.hypot((pts[13, 0] - pts[14, 0]) * asp, pts[13, 1] - pts[14, 1]) / fh
        bsv = np.zeros(len(BLENDSHAPES))
        if bs is not None:
            bsv[:min(len(bs), len(BLENDSHAPES))] = bs[:len(BLENDSHAPES)]
        bsv = self.f_bs(bsv, t)
        v[o + 6] = mouth
        v[o + 7] = bsv[9]
        v[o + 8] = bsv[10]
        v[o + 9:o + 9 + len(BLENDSHAPES)] = bsv
        self.emit()
        return {
            "oval": pts[list(FACE_OVAL), :2], "lips": pts[list(LIPS), :2],
            "eye_l": pts[list(EYE_L), :2], "eye_r": pts[list(EYE_R), :2],
            "brow_l": pts[list(BROW_L), :2], "brow_r": pts[list(BROW_R), :2],
            "iris": pts[[468, 473], :2] if len(pts) > 473 else None,
            "mouth": mouth, "yaw": head[0], "pitch": head[1],
        }


class PosePublisher(Publisher):
    port_offset = 1

    def configure(self, cfg):
        super().configure(cfg)
        self.f = OneEuro(*self.filter_args)

    def build_names(self):
        suf = self.coords.suffixes() + ["v"]
        names = ["p_present"]
        for j in POSE_JOINTS:
            names += [f"p_{j}_{k}" for k in suf]
        return names

    def publish(self, pose, t):
        v = self.values
        v[:] = 0
        if pose is None:
            self.f.reset()
            self.emit()
            return None
        pts = self.f(pose, t)
        v[0] = 1
        block = np.concatenate([self.coords.expand(pts[:, :3]), pts[:, 3:4]], axis=1).reshape(-1)
        v[1:1 + block.size] = block
        self.emit()
        return {"lm": pts[:, :2].copy(), "vis": pts[:, 3].copy()}
