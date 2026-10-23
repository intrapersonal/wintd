import os

import numpy as np

from .shm import SlotWriter

GL_BGRA = 0x80E1
GL_RGBA = 0x1908


class SpoutOut:
    def __init__(self, name):
        import SpoutGL
        self.sender = SpoutGL.SpoutSender()
        self.sender.setSenderName(name)
        self.name = name
        self.fails = 0

    def send(self, img, fmt):
        h, w = img.shape[:2]
        ok = self.sender.sendImage(np.ascontiguousarray(img), w, h, fmt, False, 0)
        try:
            self.sender.setFrameSync(self.name)
        except Exception:
            pass
        self.fails = 0 if ok else self.fails + 1
        return ok

    def close(self):
        try:
            self.sender.releaseSender()
        except Exception:
            pass


class ImageOut:
    def __init__(self, name, capacity, mode="auto"):
        self.name = name
        self.mode = "shm"
        self.spout = None
        self.shm = None
        self.capacity = capacity
        if mode in ("auto", "spout") and os.name == "nt":
            try:
                self.spout = SpoutOut(name)
                self.mode = "spout"
            except Exception:
                self.spout = None
        if self.spout is None:
            self.shm = SlotWriter(name + "_px", capacity)

    def send_bgr(self, bgr, alpha=None):
        if self.mode == "spout":
            if alpha is None:
                img = np.empty(bgr.shape[:2] + (4,), np.uint8)
                img[:, :, :3] = bgr[:, :, ::-1]
                img[:, :, 3] = 255
            else:
                img = np.dstack([bgr[:, :, ::-1], alpha])
            if self.spout.send(img, GL_RGBA) or self.spout.fails < 30:
                return
            self.spout.close()
            self.spout = None
            self.mode = "shm"
            self.shm = SlotWriter(self.name + "_px", self.capacity)
        rgb = bgr[::-1, :, ::-1]
        if alpha is not None:
            alpha = alpha[::-1]
        img = rgb if alpha is None else np.dstack([rgb, alpha])
        self.shm.write(img)

    def send_bgra(self, bgra):
        self.send_bgr(bgra[:, :, :3], bgra[:, :, 3])

    def close(self):
        if self.spout:
            self.spout.close()
        if self.shm:
            self.shm.close()


class DataOut:
    def __init__(self, name, capacity):
        self.shm = SlotWriter(name + "_px", capacity)

    def send(self, arr):
        self.shm.write(arr)

    def close(self):
        self.shm.close()
