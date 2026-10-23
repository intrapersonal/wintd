import os
import shutil
import ssl
import sys
import urllib.request
from pathlib import Path

GCS = "https://storage.googleapis.com/mediapipe-models"

MODELS = {
    "hands": ("hand_landmarker.task", f"{GCS}/hand_landmarker/hand_landmarker/float16/1/hand_landmarker.task"),
    "face": ("face_landmarker.task", f"{GCS}/face_landmarker/face_landmarker/float16/1/face_landmarker.task"),
    "pose_lite": ("pose_landmarker_lite.task", f"{GCS}/pose_landmarker/pose_landmarker_lite/float16/1/pose_landmarker_lite.task"),
    "pose_full": ("pose_landmarker_full.task", f"{GCS}/pose_landmarker/pose_landmarker_full/float16/1/pose_landmarker_full.task"),
    "segment": ("selfie_segmenter_landscape.tflite", f"{GCS}/image_segmenter/selfie_segmenter_landscape/float16/latest/selfie_segmenter_landscape.tflite"),
    "depth": ("depth_anything_v2_small_fp16.onnx", "https://huggingface.co/onnx-community/depth-anything-v2-small/resolve/main/onnx/model_fp16.onnx"),
}

STREAM_MODELS = {
    "hands": ["hands"],
    "face": ["face"],
    "pose": ["pose_lite", "pose_full"],
    "segment": ["segment"],
    "depth": ["depth"],
}


def home():
    env = os.environ.get("WINTD_HOME")
    if env:
        return Path(env)
    if os.name == "nt":
        return Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local")) / "wintd"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "wintd"
    return Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share")) / "wintd"


def model_dir():
    d = home() / "models"
    d.mkdir(parents=True, exist_ok=True)
    return d


def model_path(key):
    return model_dir() / MODELS[key][0]


def have(key):
    p = model_path(key)
    return p.exists() and p.stat().st_size > 1000


def download(url, dest, progress=None, label=""):
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    part = dest.with_suffix(dest.suffix + ".part")
    req = urllib.request.Request(url, headers={"User-Agent": "wintd"})
    ctx = ssl.create_default_context()
    with urllib.request.urlopen(req, context=ctx, timeout=60) as r, open(part, "wb") as f:
        total = int(r.headers.get("Content-Length") or 0)
        got = 0
        while True:
            chunk = r.read(1 << 16)
            if not chunk:
                break
            f.write(chunk)
            got += len(chunk)
            if progress:
                progress(label, got, total)
    shutil.move(str(part), str(dest))
    return dest


def ensure(key, progress=None):
    if have(key):
        return model_path(key)
    name, url = MODELS[key]
    return download(url, model_path(key), progress, name)
