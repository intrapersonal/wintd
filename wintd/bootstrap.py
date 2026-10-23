import json
import os
import shutil
import ssl
import subprocess
import sys
import urllib.request
import zipfile
from pathlib import Path

PY_VERSION = "3.11.9"
EMBED_URL = f"https://www.python.org/ftp/python/{PY_VERSION}/python-{PY_VERSION}-embed-amd64.zip"
GET_PIP = "https://bootstrap.pypa.io/get-pip.py"

REQS_COMMON = [
    "numpy==1.26.4",
    "opencv-contrib-python==4.10.0.84",
    "mediapipe==0.10.14",
]
REQS_WIN = REQS_COMMON + ["onnxruntime-directml==1.18.0"]
REQS_POSIX = REQS_COMMON + ["onnxruntime==1.18.0"]
OPTIONAL_WIN = ["SpoutGL", "cv2_enumerate_cameras"]
OPTIONAL_POSIX = ["cv2_enumerate_cameras"]

NO_WINDOW = 0x08000000 if os.name == "nt" else 0


def default_root():
    if os.name == "nt":
        return Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local")) / "wintd"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "wintd"
    return Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share")) / "wintd"


def python_path(root):
    root = Path(root)
    if os.name == "nt":
        return root / "python" / "python.exe"
    return root / "venv" / "bin" / "python"


def fetch(url, dest, progress=None, label=""):
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    part = dest.with_name(dest.name + ".part")
    req = urllib.request.Request(url, headers={"User-Agent": "wintd-installer"})
    with urllib.request.urlopen(req, context=ssl.create_default_context(), timeout=90) as r, open(part, "wb") as f:
        total = int(r.headers.get("Content-Length") or 0)
        got = 0
        while True:
            b = r.read(1 << 16)
            if not b:
                break
            f.write(b)
            got += len(b)
            if progress and total:
                progress("download", f"{label} {got * 100 // total}%")
    shutil.move(str(part), str(dest))
    return dest


def run(cmd, progress=None, label="", env=None):
    p = subprocess.Popen([str(c) for c in cmd], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                         creationflags=NO_WINDOW, env=env)
    tail = []
    for line in p.stdout:
        line = line.rstrip()
        if not line:
            continue
        tail = (tail + [line])[-25:]
        if progress and (line.startswith("Collecting") or line.startswith("Installing") or line.startswith("Successfully")):
            progress(label, line[:90])
    if p.wait() != 0:
        raise RuntimeError(f"{label} failed:\n" + "\n".join(tail))


def setup_python(root, progress, base_python=None):
    root = Path(root)
    py = python_path(root)
    if py.exists():
        return py
    if os.name == "nt":
        progress("python", "downloading python")
        z = fetch(EMBED_URL, root / "dl" / "python.zip", progress, "python")
        target = root / "python"
        if target.exists():
            shutil.rmtree(target)
        with zipfile.ZipFile(z) as zf:
            zf.extractall(target)
        for pth in target.glob("python*._pth"):
            lines = pth.read_text().splitlines()
            out = []
            for ln in lines:
                out.append("import site" if ln.strip() == "#import site" else ln)
            if "..\\pkg" not in out:
                out.append("..\\pkg")
            pth.write_text("\n".join(out) + "\n")
        progress("python", "installing pip")
        gp = fetch(GET_PIP, root / "dl" / "get-pip.py", progress, "pip")
        run([py, gp, "--no-warn-script-location"], progress, "pip")
        return py
    progress("python", "creating venv")
    base = base_python or shutil.which("python3.11") or shutil.which("python3.12") or shutil.which("python3")
    if not base:
        raise RuntimeError("no python3 found, install python 3.11 first")
    run([base, "-m", "venv", root / "venv"], progress, "venv")
    return py


def pip_install(py, progress):
    reqs = REQS_WIN if os.name == "nt" else REQS_POSIX
    opt = OPTIONAL_WIN if os.name == "nt" else OPTIONAL_POSIX
    run([py, "-m", "pip", "install", "--upgrade", "pip", "--no-warn-script-location"], progress, "pip")
    run([py, "-m", "pip", "install", "--no-warn-script-location", *reqs], progress, "packages")
    for o in opt:
        try:
            run([py, "-m", "pip", "install", "--no-warn-script-location", o], progress, "extras")
        except RuntimeError:
            progress("extras", f"skipped {o}")


def copy_package(src, root):
    dst = Path(root) / "pkg" / "wintd"
    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(src, dst, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    return dst


def write_package(files, root):
    dst = Path(root) / "pkg" / "wintd"
    dst.mkdir(parents=True, exist_ok=True)
    for name, text in files.items():
        (dst / name).write_text(text, encoding="utf-8")
    return dst


def pkg_env(root):
    env = dict(os.environ)
    env["PYTHONPATH"] = str(Path(root) / "pkg")
    env["WINTD_HOME"] = str(root)
    return env


def fetch_models(py, root, streams, progress):
    code = (
        "import sys\nfrom wintd import models\n"
        "for s in sys.argv[1:]:\n"
        "    for k in models.STREAM_MODELS.get(s, []):\n"
        "        if k == 'pose_full':\n            continue\n"
        "        print('Installing model', k, flush=True)\n"
        "        models.ensure(k)\n"
    )
    run([py, "-c", code, *streams], progress, "models", env=pkg_env(root))


def verify(py, root):
    code = (
        "import json\nout = {}\n"
        "for m in ('numpy', 'cv2', 'mediapipe', 'onnxruntime', 'SpoutGL'):\n"
        "    try:\n        __import__(m)\n        out[m] = True\n"
        "    except Exception:\n        out[m] = False\n"
        "print(json.dumps(out))\n"
    )
    r = subprocess.run([str(py), "-c", code], capture_output=True, text=True, env=pkg_env(root), creationflags=NO_WINDOW)
    try:
        return json.loads(r.stdout.strip().splitlines()[-1])
    except Exception:
        return {}


def install(root=None, src=None, files=None, streams=("hands",), progress=None, base_python=None):
    progress = progress or (lambda step, msg: print(f"[{step}] {msg}", flush=True))
    root = Path(root or default_root())
    root.mkdir(parents=True, exist_ok=True)
    py = setup_python(root, progress, base_python)
    pip_install(py, progress)
    if files:
        write_package(files, root)
    elif src:
        copy_package(src, root)
    else:
        copy_package(Path(__file__).resolve().parent, root)
    progress("models", "downloading models")
    fetch_models(py, root, list(streams), progress)
    status = verify(py, root)
    if not status.get("mediapipe"):
        raise RuntimeError("mediapipe did not import after install")
    (root / "installed.json").write_text(json.dumps({"python": str(py), "status": status}))
    progress("done", "installed")
    return py, status


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default="")
    ap.add_argument("--streams", default="hands,face,pose,segment,depth")
    ap.add_argument("--python", default="")
    a = ap.parse_args()
    install(a.root or None, streams=[s for s in a.streams.split(",") if s], base_python=a.python or None)
