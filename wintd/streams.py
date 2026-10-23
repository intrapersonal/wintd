import gzip
import json
import os
import queue
import time

import numpy as np

from . import models
from .publish import FacePublisher, HandsPublisher, PosePublisher
from .shm import SlotReader
from .textures import DataOut


class Recorder:
    def __init__(self, folder, kind):
        self.f = None
        if folder:
            os.makedirs(folder, exist_ok=True)
            self.f = gzip.open(os.path.join(folder, f"{kind}.jsonl.gz"), "at")

    def add(self, t, data):
        if self.f:
            self.f.write(json.dumps({"t": round(t, 4), "d": data}) + "\n")

    def close(self):
        if self.f:
            self.f.close()
            self.f = None


def _mp():
    import mediapipe as mp
    from mediapipe.tasks.python import BaseOptions, vision
    return mp, BaseOptions, vision


class HandsWorker:
    kind = "hands"

    def __init__(self, cfg):
        self.mp, self.Base, self.vision = _mp()
        self.cfg = cfg
        self.pub = HandsPublisher(cfg)
        self.make()

    def make(self):
        v = self.vision
        opts = v.HandLandmarkerOptions(
            base_options=self.Base(model_asset_path=str(models.ensure("hands"))),
            running_mode=v.RunningMode.VIDEO,
            num_hands=int(self.cfg.get("num_hands", 2)),
            min_hand_detection_confidence=0.5,
            min_hand_presence_confidence=0.5,
            min_tracking_confidence=0.5,
        )
        self.model = v.HandLandmarker.create_from_options(opts)
        self.n = int(self.cfg.get("num_hands", 2))

    def reconfigure(self, cfg):
        self.cfg = cfg
        self.pub.configure(cfg)
        if int(cfg.get("num_hands", 2)) != self.n:
            self.model.close()
            self.make()

    def infer(self, rgb, ms):
        res = self.model.detect_for_video(self.mp.Image(image_format=self.mp.ImageFormat.SRGB, data=rgb), ms)
        hands = []
        for i, h in enumerate(res.hand_landmarks):
            arr = np.array([[p.x, p.y, p.z] for p in h], dtype=np.float64)
            cat = res.handedness[i][0]
            label = cat.category_name
            if self.cfg.get("mirror", True):
                label = "Right" if label == "Left" else "Left"
            hands.append((arr, label, float(cat.score)))
        return hands

    def publish(self, hands, t):
        return self.pub.publish(hands, t)

    @staticmethod
    def dump(hands):
        return [[h[0].round(5).tolist(), h[1], round(h[2], 3)] for h in hands]

    @staticmethod
    def load(d):
        return [(np.array(a, dtype=np.float64), b, c) for a, b, c in d]

    def close(self):
        self.model.close()


class FaceWorker:
    kind = "face"

    def __init__(self, cfg):
        self.mp, self.Base, self.vision = _mp()
        self.cfg = cfg
        self.pub = FacePublisher(cfg)
        self.mesh = DataOut("wintd_facemesh", 478 * 4 * 4)
        v = self.vision
        opts = v.FaceLandmarkerOptions(
            base_options=self.Base(model_asset_path=str(models.ensure("face"))),
            running_mode=v.RunningMode.VIDEO,
            num_faces=1,
            output_face_blendshapes=True,
            output_facial_transformation_matrixes=True,
            min_face_detection_confidence=0.5,
            min_face_presence_confidence=0.5,
            min_tracking_confidence=0.5,
        )
        self.model = v.FaceLandmarker.create_from_options(opts)

    def reconfigure(self, cfg):
        self.cfg = cfg
        self.pub.configure(cfg)

    def infer(self, rgb, ms):
        res = self.model.detect_for_video(self.mp.Image(image_format=self.mp.ImageFormat.SRGB, data=rgb), ms)
        if not res.face_landmarks:
            return None
        pts = np.array([[p.x, p.y, p.z] for p in res.face_landmarks[0]], dtype=np.float64)
        bs = None
        if res.face_blendshapes:
            bs = np.array([c.score for c in res.face_blendshapes[0]], dtype=np.float64)
        mat = None
        if res.facial_transformation_matrixes:
            mat = np.array(res.facial_transformation_matrixes[0], dtype=np.float64).reshape(4, 4)
        return pts, bs, mat

    def publish(self, face, t):
        if face is not None:
            pts = face[0]
            mesh = np.ones((1, len(pts), 4), np.float32)
            mesh[0, :, 0] = pts[:, 0]
            mesh[0, :, 1] = 1 - pts[:, 1]
            mesh[0, :, 2] = pts[:, 2]
            self.mesh.send(mesh)
        return self.pub.publish(face, t)

    @staticmethod
    def dump(face):
        if face is None:
            return None
        pts, bs, mat = face
        return [pts.round(5).tolist(), None if bs is None else bs.round(4).tolist(), None if mat is None else mat.round(5).tolist()]

    @staticmethod
    def load(d):
        if d is None:
            return None
        return np.array(d[0]), None if d[1] is None else np.array(d[1]), None if d[2] is None else np.array(d[2])

    def close(self):
        self.model.close()
        self.mesh.close()


class PoseWorker:
    kind = "pose"

    def __init__(self, cfg):
        self.mp, self.Base, self.vision = _mp()
        self.cfg = cfg
        self.pub = PosePublisher(cfg)
        self.make()

    def make(self):
        v = self.vision
        self.variant = self.cfg.get("pose_model", "lite")
        key = "pose_full" if self.variant == "full" else "pose_lite"
        opts = v.PoseLandmarkerOptions(
            base_options=self.Base(model_asset_path=str(models.ensure(key))),
            running_mode=v.RunningMode.VIDEO,
            num_poses=1,
            min_pose_detection_confidence=0.5,
            min_pose_presence_confidence=0.5,
            min_tracking_confidence=0.5,
        )
        self.model = v.PoseLandmarker.create_from_options(opts)

    def reconfigure(self, cfg):
        self.cfg = cfg
        self.pub.configure(cfg)
        if cfg.get("pose_model", "lite") != self.variant:
            self.model.close()
            self.make()

    def infer(self, rgb, ms):
        res = self.model.detect_for_video(self.mp.Image(image_format=self.mp.ImageFormat.SRGB, data=rgb), ms)
        if not res.pose_landmarks:
            return None
        return np.array([[p.x, p.y, p.z, p.visibility] for p in res.pose_landmarks[0]], dtype=np.float64)

    def publish(self, pose, t):
        return self.pub.publish(pose, t)

    @staticmethod
    def dump(pose):
        return None if pose is None else pose.round(5).tolist()

    @staticmethod
    def load(d):
        return None if d is None else np.array(d)

    def close(self):
        self.model.close()


class SegmentWorker:
    kind = "segment"

    def __init__(self, cfg):
        self.mp, self.Base, self.vision = _mp()
        self.cfg = cfg
        self.out = DataOut("wintd_mask", 1024 * 1024)
        v = self.vision
        opts = v.ImageSegmenterOptions(
            base_options=self.Base(model_asset_path=str(models.ensure("segment"))),
            running_mode=v.RunningMode.VIDEO,
            output_confidence_masks=True,
            output_category_mask=False,
        )
        self.model = v.ImageSegmenter.create_from_options(opts)

    def reconfigure(self, cfg):
        self.cfg = cfg

    def infer(self, rgb, ms):
        res = self.model.segment_for_video(self.mp.Image(image_format=self.mp.ImageFormat.SRGB, data=rgb), ms)
        if not res.confidence_masks:
            return None
        m = res.confidence_masks[-1].numpy_view()
        return np.clip(np.asarray(m, dtype=np.float32) * 255, 0, 255).astype(np.uint8)

    def publish(self, mask, t):
        if mask is not None:
            self.out.send(mask[::-1])
        return None

    @staticmethod
    def dump(mask):
        return None

    def close(self):
        self.model.close()
        self.out.close()


class DepthWorker:
    kind = "depth"

    def __init__(self, cfg):
        import onnxruntime as ort
        self.cfg = cfg
        prefer = ["DmlExecutionProvider", "CUDAExecutionProvider", "CoreMLExecutionProvider", "CPUExecutionProvider"]
        avail = ort.get_available_providers()
        providers = [p for p in prefer if p in avail] or avail
        so = ort.SessionOptions()
        so.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
        self.sess = ort.InferenceSession(str(models.ensure("depth")), so, providers=providers)
        inp = self.sess.get_inputs()[0]
        self.in_name = inp.name
        self.in_type = np.float16 if "float16" in inp.type else np.float32
        self.provider = self.sess.get_providers()[0]
        self.out = DataOut("wintd_depth", 1036 * 1036 * 2)
        self.lo = None
        self.hi = None
        self.mean = np.array([0.485, 0.456, 0.406], np.float32)
        self.std = np.array([0.229, 0.224, 0.225], np.float32)

    def reconfigure(self, cfg):
        self.cfg = cfg

    def infer(self, rgb, ms):
        import cv2
        h, w = rgb.shape[:2]
        base = int(self.cfg.get("depth_size", 518))
        if w >= h:
            iw, ih = base, max(14, int(round(base * h / w / 14)) * 14)
        else:
            ih, iw = base, max(14, int(round(base * w / h / 14)) * 14)
        x = cv2.resize(rgb, (iw, ih), interpolation=cv2.INTER_AREA).astype(np.float32) / 255.0
        x = ((x - self.mean) / self.std).transpose(2, 0, 1)[None].astype(self.in_type)
        d = self.sess.run(None, {self.in_name: x})[0]
        d = np.asarray(d, dtype=np.float32).reshape(d.shape[-2], d.shape[-1])
        lo, hi = np.percentile(d, 2), np.percentile(d, 98)
        self.lo = lo if self.lo is None else self.lo + (lo - self.lo) * 0.2
        self.hi = hi if self.hi is None else self.hi + (hi - self.hi) * 0.2
        return np.clip((d - self.lo) / max(self.hi - self.lo, 1e-6), 0, 1).astype(np.float16)

    def publish(self, depth, t):
        if depth is not None:
            self.out.send(depth[::-1])
        return None

    @staticmethod
    def dump(depth):
        return None

    def close(self):
        self.out.close()


WORKERS = {
    "hands": HandsWorker,
    "face": FaceWorker,
    "pose": PoseWorker,
    "segment": SegmentWorker,
    "depth": DepthWorker,
}


def put_latest(q, item):
    try:
        q.put_nowait(item)
    except queue.Full:
        try:
            q.get_nowait()
        except queue.Empty:
            pass
        try:
            q.put_nowait(item)
        except queue.Full:
            pass


def run(kind, cfg, frame_name, out_q, info_q, cfg_q, stop):
    try:
        worker = WORKERS[kind](cfg)
    except Exception as e:
        info_q.put((kind, "error", f"{type(e).__name__}: {e}"))
        return
    reader = SlotReader(frame_name)
    rec = Recorder(cfg.get("record"), kind)
    last_ms = -1
    n, t0 = 0, time.perf_counter()
    info_q.put((kind, "ready", getattr(worker, "provider", "")))
    try:
        while not stop.is_set():
            try:
                while True:
                    new = cfg_q.get_nowait()
                    worker.reconfigure(new)
                    if (new.get("record") or None) != (cfg.get("record") or None):
                        rec.close()
                        rec = Recorder(new.get("record"), kind)
                    cfg = new
            except queue.Empty:
                pass
            frame = reader.read()
            if frame is None:
                time.sleep(0.001)
                continue
            ms = reader.stamp
            if ms <= last_ms:
                ms = last_ms + 1
            last_ms = ms
            raw = worker.infer(frame, ms)
            t = ms / 1000.0
            rec.add(t, worker.dump(raw))
            summary = worker.publish(raw, t)
            n += 1
            now = time.perf_counter()
            if now - t0 >= 1:
                info_q.put((kind, "fps", n / (now - t0)))
                n, t0 = 0, now
            if summary is not None:
                put_latest(out_q, (kind, "data", summary))
            elif kind in ("hands", "face", "pose"):
                put_latest(out_q, (kind, "data", None))
    except Exception as e:
        info_q.put((kind, "error", f"{type(e).__name__}: {e}"))
    finally:
        rec.close()
        try:
            worker.close()
        except Exception:
            pass
        reader.close()
