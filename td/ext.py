import json
import os
import queue
import socket
import struct
import subprocess
import sys
import threading
from pathlib import Path

NO_WINDOW = 0x08000000 if os.name == "nt" else 0
LIVE = {
    "Hands": "hands", "Face": "face", "Pose": "pose", "Segment": "segment", "Depth": "depth",
    "Numhands": "num_hands", "Smoothing": "smoothing", "Coordsworld": "world", "Coordspixel": "pixel",
    "Overlay": "overlay", "Mirror": "mirror", "Posemodel": "pose_model",
}
RESTART = {"Camera", "Resolution", "Fps", "Transport", "Port", "Synthetic", "Replay", "Replayfolder", "Sidecarpython", "Installroot"}


def _pad(b):
    return b + b"\0" * (4 - len(b) % 4)


def _osc(addr, *args):
    tags, body = ",", b""
    for a in args:
        if isinstance(a, bool) or isinstance(a, int):
            tags += "i"
            body += struct.pack(">i", int(a))
        elif isinstance(a, float):
            tags += "f"
            body += struct.pack(">f", a)
        else:
            tags += "s"
            body += _pad(str(a).encode())
    return _pad(addr.encode()) + _pad(tags.encode()) + body


class WintdExt:
    def __init__(self, ownerComp):
        self.ownerComp = ownerComp
        self.proc = None
        self.log_file = None
        self.q = queue.Queue()
        self.worker = None
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.CheckInstall()

    @property
    def par(self):
        return self.ownerComp.par

    def bootstrap(self):
        return self.ownerComp.op("pkg/m_bootstrap").module

    def Root(self):
        p = self.par.Installroot.eval()
        return Path(p) if p else self.bootstrap().default_root()

    def Python(self):
        p = self.par.Sidecarpython.eval()
        return Path(p) if p else self.bootstrap().python_path(self.Root())

    def Files(self):
        pkg = self.ownerComp.op("pkg")
        return {d.name[2:] + ".py": d.text for d in pkg.findChildren(type=textDAT, depth=1) if d.name.startswith("m_")}

    def Version(self):
        for line in self.ownerComp.op("pkg/m___init__").text.splitlines():
            if line.startswith("__version__"):
                return line.split("=")[1].strip().strip('"')
        return "?"

    def State(self, text):
        self.par.Installstate = text

    def Installed(self):
        return self.Python().exists() and (self.Root() / "installed.json").exists()

    def CheckInstall(self):
        if not self.Installed():
            self.State("Not installed")
            return False
        marker = self.Root() / "pkg" / "wintd" / "__init__.py"
        try:
            have = marker.read_text().split("=")[1].strip().strip('"')
        except Exception:
            have = ""
        self.State("Installed" if have == self.Version() else "Update ready - press Start")
        return True

    def Install(self):
        if self.worker and self.worker.is_alive():
            return
        self.Stop()
        streams = ["hands", "face", "pose", "segment"]
        root, files, boot = self.Root(), self.Files(), self.bootstrap()
        base = self.par.Sidecarpython.eval() or None

        def job():
            try:
                boot.install(root, files=files, streams=streams, progress=lambda s, m: self.q.put(("progress", f"{s} - {m}")), base_python=base)
                self.q.put(("done", "Installed"))
            except Exception as e:
                self.q.put(("fail", f"Install failed - {str(e).splitlines()[0][:120]}"))

        self.State("Installing - starting")
        self.worker = threading.Thread(target=job, daemon=True)
        self.worker.start()
        run("args[0].Poll()", self, delayFrames=10)

    def Poll(self):
        last = None
        while True:
            try:
                last = self.q.get_nowait()
            except queue.Empty:
                break
        if last:
            kind, text = last
            if kind == "progress":
                self.State("Installing - " + text)
            else:
                self.State(text)
                if kind == "done":
                    self.RefreshCameras()
                    if self.par.Active.eval():
                        self.Start()
                return
        if self.worker and self.worker.is_alive():
            run("args[0].Poll()", self, delayFrames=10)

    def Args(self):
        p = self.par
        res = p.Resolution.eval().split("x")
        streams = [s for s, par in (("hands", p.Hands), ("face", p.Face), ("pose", p.Pose), ("segment", p.Segment), ("depth", p.Depth)) if par.eval()]
        a = [
            "-m", "wintd",
            "--camera", p.Camera.eval() or "0",
            "--width", res[0], "--height", res[1], "--fps", p.Fps.eval(),
            "--streams", ",".join(streams) or "none",
            "--num-hands", str(p.Numhands.eval()),
            "--pose-model", p.Posemodel.eval(),
            "--smoothing", str(p.Smoothing.eval()),
            "--transport", p.Transport.eval(),
            "--port", str(p.Port.eval()),
            "--parent", str(os.getpid()),
            "--log", str(self.Root() / "sidecar.log"),
        ]
        if not p.Mirror.eval():
            a.append("--no-mirror")
        if not p.Overlay.eval():
            a.append("--no-overlay")
        if p.Coordsworld.eval():
            a.append("--world")
        if p.Coordspixel.eval():
            a.append("--pixel")
        if p.Synthetic.eval():
            a.append("--synthetic")
        if p.Replay.eval() and p.Replayfolder.eval():
            a += ["--replay", p.Replayfolder.eval()]
        if p.Record.eval() and p.Recordfolder.eval():
            a += ["--record", p.Recordfolder.eval()]
        return a

    def Start(self):
        if self.Running():
            return
        if not self.Installed():
            self.State("Not installed - press Install first")
            self.par.Active = False
            return
        root = self.Root()
        self.bootstrap().write_package(self.Files(), root)
        env = dict(os.environ)
        for k in ("PYTHONHOME", "PYTHONPATH"):
            env.pop(k, None)
        env["PYTHONPATH"] = str(root / "pkg")
        env["WINTD_HOME"] = str(root)
        cmd = [str(self.Python())] + self.Args()
        self.log_file = open(root / "sidecar.out", "w")
        self.proc = subprocess.Popen(cmd, cwd=str(root), env=env, stdout=self.log_file, stderr=subprocess.STDOUT, creationflags=NO_WINDOW)
        self.State("Running")
        self.ownerComp.op("oscin_status").par.active = True

    def Stop(self):
        if self.proc is None:
            return
        try:
            self.Send("/quit")
            self.proc.wait(timeout=2)
        except Exception:
            try:
                self.proc.kill()
            except Exception:
                pass
        self.proc = None
        if self.log_file:
            self.log_file.close()
            self.log_file = None
        if self.Installed():
            self.State("Installed")

    def Restart(self):
        self.Stop()
        if self.par.Active.eval():
            self.Start()

    def Running(self):
        return self.proc is not None and self.proc.poll() is None

    def Send(self, addr, *args):
        port = int(self.par.Port.eval()) + 9
        try:
            self.sock.sendto(_osc(addr, *args), ("127.0.0.1", port))
        except OSError:
            pass

    def Set(self, key, value):
        if isinstance(value, bool):
            value = int(value)
        self.Send("/set", key, value)

    def OnPar(self, par):
        name = par.name
        if name == "Install":
            self.Install()
        elif name == "Active":
            self.Start() if par.eval() else self.Stop()
        elif name == "Restart":
            self.Restart()
        elif name == "Refreshcameras":
            self.RefreshCameras()
        elif name == "Openlog":
            log = self.Root() / "sidecar.log"
            if log.exists():
                ui.viewFile(str(log))
        elif name in ("Record", "Recordfolder"):
            folder = self.par.Recordfolder.eval() if self.par.Record.eval() else ""
            self.Set("record", folder)
        elif name in LIVE and self.Running():
            v = par.eval()
            self.Set(LIVE[name], v if isinstance(v, str) else (float(v) if isinstance(v, float) else int(v)))
        elif name in RESTART and self.Running():
            self.Restart()

    def RefreshCameras(self):
        if not self.Installed():
            return
        py, root = str(self.Python()), self.Root()
        env = dict(os.environ)
        env.pop("PYTHONHOME", None)
        env["PYTHONPATH"] = str(root / "pkg")
        boot, files = self.bootstrap(), self.Files()

        def job():
            try:
                boot.write_package(files, root)
                r = subprocess.run([py, "-m", "wintd", "--list-cameras"], capture_output=True, text=True, timeout=30, env=env, creationflags=NO_WINDOW)
                cams = json.loads(r.stdout.strip().splitlines()[-1])
                self.q.put(("cams", cams))
            except Exception:
                self.q.put(("cams", []))

        threading.Thread(target=job, daemon=True).start()
        run("args[0].PollCams()", self, delayFrames=15)

    def PollCams(self):
        try:
            kind, cams = self.q.get_nowait()
        except queue.Empty:
            run("args[0].PollCams()", self, delayFrames=15)
            return
        if kind != "cams":
            self.q.put((kind, cams))
            return
        p = self.par.Camera
        cur = p.eval()
        if cams:
            p.menuNames = [str(c["index"]) for c in cams]
            p.menuLabels = [c["name"] for c in cams]
            if cur in p.menuNames:
                p.val = cur

    def Flag(self, name):
        c = self.ownerComp.op("oscin_status")
        for n in (f"wintd_{name}", f"/wintd_{name}"):
            ch = c.chan(n)
            if ch is not None:
                return ch.eval()
        return 0.0

    def OnExit(self):
        self.Stop()
