import multiprocessing as mp
import os
import queue
import sys
import time

import cv2
import numpy as np

from . import streams
from .camera import Blank, Camera, VideoFile
from .control import ControlServer, parent_alive
from .osc import ChannelSender
from .overlay import Overlay
from .publish import FacePublisher, HandsPublisher, PosePublisher
from .shm import SlotWriter
from .synthetic import Replay, SyntheticHands
from .textures import ImageOut

KINDS = ("hands", "face", "pose", "segment", "depth")
STATUS = (
    "alive", "fps", "width", "height", "spout_video", "spout_overlay",
    "hands_fps", "face_fps", "pose_fps", "segment_fps", "depth_fps", "errors",
)
BOOL_KEYS = {"hands", "face", "pose", "segment", "depth", "overlay", "mirror", "world", "pixel", "video"}
NUM_KEYS = {"num_hands": int, "smoothing": float, "depth_size": int}
STR_KEYS = {"pose_model", "record"}


class Log:
    def __init__(self, path=None):
        self.f = open(path, "w", buffering=1, encoding="utf-8") if path else None

    def __call__(self, *parts):
        line = time.strftime("%H:%M:%S ") + " ".join(str(p) for p in parts)
        print(line, file=sys.stderr, flush=True)
        if self.f:
            self.f.write(line + "\n")


class Sidecar:
    def __init__(self, cfg, log=None):
        self.cfg = cfg
        self.log = log or Log()
        self.procs = {}
        self.fps = {k: 0.0 for k in KINDS}
        self.latest = {"hands": None, "face": None, "pose": None}
        self.errors = 0
        self.running = True
        self.ctx = mp.get_context("spawn")
        self.info_q = self.ctx.Queue()
        self.frame_name = f"wintd_frame_{os.getpid()}"
        self.synth = None
        self.replays = {}
        self.local_pubs = {}

    def source(self):
        c = self.cfg
        if c.get("video_file"):
            return VideoFile(c["video_file"], mirror=c.get("mirror", True))
        if c.get("synthetic") or c.get("replay"):
            return Blank(c["width"], c["height"], c["fps"])
        cam = Camera(int(c.get("camera", 0)), c["width"], c["height"], c["fps"], c.get("mirror", True))
        cam.open()
        return cam

    def stream_cfg(self):
        c = dict(self.cfg)
        c["width"] = self.width
        c["height"] = self.height
        return c

    def remote(self):
        return not (self.cfg.get("synthetic") or self.cfg.get("replay"))

    def start_stream(self, kind):
        if kind in self.procs:
            return
        out_q = self.ctx.Queue(maxsize=1)
        cfg_q = self.ctx.Queue()
        stop = self.ctx.Event()
        p = self.ctx.Process(target=streams.run, args=(kind, self.stream_cfg(), self.frame_name, out_q, self.info_q, cfg_q, stop), daemon=True)
        p.start()
        self.procs[kind] = (p, out_q, cfg_q, stop)
        self.log("start", kind)

    def stop_stream(self, kind):
        item = self.procs.pop(kind, None)
        if not item:
            return
        p, _, _, stop = item
        stop.set()
        p.join(timeout=3)
        if p.is_alive():
            p.terminate()
        if kind in self.latest:
            self.latest[kind] = None
        self.fps[kind] = 0.0
        self.log("stop", kind)

    def sync_streams(self):
        for k in KINDS:
            want = bool(self.cfg.get(k))
            if self.remote():
                if want and k not in self.procs:
                    self.start_stream(k)
                elif not want and k in self.procs:
                    self.stop_stream(k)
            if not want and k in self.latest:
                self.latest[k] = None

    def push_cfg(self):
        c = self.stream_cfg()
        for _, _, cfg_q, _ in self.procs.values():
            cfg_q.put(c)
        for pub in self.local_pubs.values():
            pub.configure(c)

    def handle(self, addr, args):
        if addr == "/quit":
            self.running = False
            return
        if addr != "/set" or len(args) < 2:
            return
        key, value = str(args[0]), args[1]
        if key in BOOL_KEYS:
            value = bool(int(float(value)))
        elif key in NUM_KEYS:
            value = NUM_KEYS[key](value)
        elif key in STR_KEYS:
            value = str(value)
        else:
            return
        if self.cfg.get(key) == value:
            return
        self.cfg[key] = value
        self.log("set", key, value)
        if key == "mirror" and hasattr(self.src, "mirror"):
            self.src.mirror = value
        if key in KINDS:
            self.sync_streams()
        else:
            self.push_cfg()

    def drain(self):
        while True:
            try:
                kind, what, val = self.info_q.get_nowait()
            except queue.Empty:
                break
            if what == "fps":
                self.fps[kind] = val
            elif what == "error":
                self.errors += 1
                self.log("error", kind, val)
            elif what == "ready":
                self.log("ready", kind, val)
        for kind, (p, out_q, _, _) in list(self.procs.items()):
            try:
                while True:
                    _, what, val = out_q.get_nowait()
                    if what == "data" and kind in self.latest:
                        self.latest[kind] = val
            except queue.Empty:
                pass
            if not p.is_alive():
                self.procs.pop(kind, None)
                self.fps[kind] = 0.0
                self.log("exited", kind, p.exitcode)

    def local(self, now):
        c = self.cfg
        sc = self.stream_cfg()
        if c.get("synthetic") and c.get("hands"):
            pub = self.local_pubs.get("hands") or self.local_pubs.setdefault("hands", HandsPublisher(sc))
            if self.synth is None:
                self.synth = SyntheticHands(self.width / self.height)
            self.latest["hands"] = pub.publish(self.synth(now), now)
        if c.get("replay"):
            for kind, cls, worker in (("hands", HandsPublisher, streams.HandsWorker), ("face", FacePublisher, streams.FaceWorker), ("pose", PosePublisher, streams.PoseWorker)):
                if not c.get(kind):
                    continue
                rp = self.replays.get(kind) or self.replays.setdefault(kind, Replay(c["replay"], kind))
                pub = self.local_pubs.get(kind) or self.local_pubs.setdefault(kind, cls(sc))
                for _, d in rp.due(now):
                    self.latest[kind] = pub.publish(worker.load(d), now)

    def run(self):
        c = self.cfg
        self.src = self.source()
        self.width, self.height = self.src.width, self.src.height
        cap = max(1920 * 1080 * 4, self.width * self.height * 4)
        self.frames = SlotWriter(self.frame_name, self.width * self.height * 3)
        self.video = ImageOut("wintd_video", cap, c.get("transport", "auto")) if c.get("video", True) else None
        self.ovl = ImageOut("wintd_overlay", cap, c.get("transport", "auto"))
        self.drawer = Overlay(self.width, self.height)
        self.status = ChannelSender(c.get("host", "127.0.0.1"), int(c["port"]) + 3, [f"wintd_{s}" for s in STATUS])
        ctl = ControlServer(int(c.get("control_port", int(c["port"]) + 9)), self.handle)
        self.src.start()
        self.sync_streams()
        self.log("running", f"{self.width}x{self.height}", "video:" + (self.video.mode if self.video else "off"))
        last, t_status, alive = -1, 0.0, 0.0
        t0 = time.perf_counter()
        overlay_was = False
        try:
            while self.running:
                count, frame, stamp = self.src.wait(last, 0.1)
                now = time.perf_counter()
                if frame is not None and count != last:
                    last = count
                    ms = int((stamp - t0) * 1000)
                    self.frames.write(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB), ms)
                    if self.video:
                        self.video.send_bgr(frame)
                    self.local(now - t0)
                    self.drain()
                    if c.get("overlay", True):
                        img = self.drawer.draw(
                            self.latest["hands"] if c.get("hands") else None,
                            self.latest["face"] if c.get("face") else None,
                            self.latest["pose"] if c.get("pose") else None,
                        )
                        self.ovl.send_bgra(img)
                        overlay_was = True
                    elif overlay_was:
                        self.drawer.canvas[:] = 0
                        self.ovl.send_bgra(self.drawer.canvas)
                        overlay_was = False
                else:
                    self.drain()
                if now - t_status > 0.25:
                    t_status = now
                    alive = 1.0 - alive
                    self.status.send(np.array([
                        alive, getattr(self.src, "fps", 0.0), self.width, self.height,
                        float(bool(self.video) and self.video.mode == "spout"), float(self.ovl.mode == "spout"),
                        self.fps["hands"], self.fps["face"], self.fps["pose"], self.fps["segment"], self.fps["depth"],
                        self.errors,
                    ], np.float32))
                    if not parent_alive(c.get("parent")):
                        self.log("parent gone, exiting")
                        break
                    err = getattr(self.src, "error", "")
                    if err:
                        self.log("source", err)
                        self.src.error = ""
        except KeyboardInterrupt:
            pass
        finally:
            ctl.close()
            for k in list(self.procs):
                self.stop_stream(k)
            self.src.stop()
            for o in (self.video, self.ovl, self.frames):
                if o:
                    o.close()
            self.log("stopped")
