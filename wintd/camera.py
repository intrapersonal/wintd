import json
import os
import threading
import time

import cv2
import numpy as np


def backend():
    if os.name == "nt":
        return cv2.CAP_MSMF
    if hasattr(cv2, "CAP_V4L2") and os.uname().sysname == "Linux":
        return cv2.CAP_V4L2
    return cv2.CAP_ANY


def list_cameras(limit=8):
    found = []
    try:
        from cv2_enumerate_cameras import enumerate_cameras
        seen = set()
        for c in enumerate_cameras(backend()):
            key = c.name
            if key in seen:
                continue
            seen.add(key)
            found.append({"index": int(c.index), "name": c.name})
        if found:
            return found
    except Exception:
        pass
    for i in range(limit):
        cap = cv2.VideoCapture(i, backend())
        ok = cap.isOpened() and cap.read()[0]
        cap.release()
        if ok:
            found.append({"index": i, "name": f"Camera {i}"})
    return found


class Source:
    def __init__(self):
        self.lock = threading.Lock()
        self.frame = None
        self.count = 0
        self.stamp = 0.0
        self.running = False
        self.thread = None
        self.fps = 0.0
        self.error = ""
        self.new = threading.Condition(self.lock)

    def publish(self, bgr):
        with self.new:
            self.frame = bgr
            self.count += 1
            self.stamp = time.perf_counter()
            self.new.notify_all()

    def wait(self, last, timeout=0.5):
        with self.new:
            if self.count == last:
                self.new.wait(timeout)
            return self.count, self.frame, self.stamp

    def start(self):
        self.running = True
        self.thread = threading.Thread(target=self._loop, daemon=True)
        self.thread.start()

    def stop(self):
        self.running = False
        if self.thread:
            self.thread.join(timeout=2)


class Camera(Source):
    def __init__(self, index, width, height, fps, mirror=True):
        super().__init__()
        self.index = index
        self.width = width
        self.height = height
        self.want_fps = fps
        self.mirror = mirror
        self.cap = None

    def open(self):
        cap = cv2.VideoCapture(self.index, backend())
        if not cap.isOpened():
            cap = cv2.VideoCapture(self.index)
        cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)
        cap.set(cv2.CAP_PROP_FPS, self.want_fps)
        try:
            cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        except Exception:
            pass
        if not cap.isOpened():
            raise RuntimeError(f"camera {self.index} would not open")
        self.cap = cap
        self.width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)) or self.width
        self.height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)) or self.height

    def _loop(self):
        n, t0 = 0, time.perf_counter()
        fails = 0
        while self.running:
            ok, img = self.cap.read()
            if not ok or img is None:
                fails += 1
                if fails > 60:
                    self.error = "camera stopped sending frames"
                    time.sleep(0.2)
                time.sleep(0.005)
                continue
            fails = 0
            if self.mirror:
                img = cv2.flip(img, 1)
            self.publish(img)
            n += 1
            now = time.perf_counter()
            if now - t0 >= 1:
                self.fps = n / (now - t0)
                n, t0 = 0, now
        self.cap.release()


class VideoFile(Source):
    def __init__(self, path, mirror=False, loop=True):
        super().__init__()
        self.path = path
        self.mirror = mirror
        self.loop = loop
        cap = cv2.VideoCapture(path)
        if not cap.isOpened():
            raise RuntimeError(f"can't open {path}")
        self.cap = cap
        self.width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        self.height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        self.rate = cap.get(cv2.CAP_PROP_FPS) or 30

    def _loop(self):
        step = 1.0 / self.rate
        nxt = time.perf_counter()
        while self.running:
            ok, img = self.cap.read()
            if not ok:
                if not self.loop:
                    break
                self.cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                continue
            if self.mirror:
                img = cv2.flip(img, 1)
            self.publish(img)
            nxt += step
            delay = nxt - time.perf_counter()
            if delay > 0:
                time.sleep(delay)
            else:
                nxt = time.perf_counter()
        self.cap.release()


class Blank(Source):
    def __init__(self, width, height, fps=60):
        super().__init__()
        self.width = width
        self.height = height
        self.rate = fps
        self.fps = float(fps)
        yy, xx = np.mgrid[0:height, 0:width]
        grid = ((xx % 64 == 0) | (yy % 64 == 0)).astype(np.uint8)
        base = np.full((height, width, 3), 22, np.uint8)
        base[grid == 1] = (40, 40, 40)
        self.base = base

    def _loop(self):
        step = 1.0 / self.rate
        while self.running:
            self.publish(self.base.copy())
            time.sleep(step)


if __name__ == "__main__":
    print(json.dumps(list_cameras()))
