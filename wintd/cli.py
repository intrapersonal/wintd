import argparse
import json
import multiprocessing as mp
import sys

from . import __version__


def parse(argv=None):
    ap = argparse.ArgumentParser(prog="wintd", description="vision sidecar for touchdesigner")
    ap.add_argument("--version", action="version", version=f"wintd {__version__}")
    ap.add_argument("--list-cameras", action="store_true")
    ap.add_argument("--camera", type=int, default=0)
    ap.add_argument("--video-file", default="")
    ap.add_argument("--synthetic", action="store_true")
    ap.add_argument("--replay", default="")
    ap.add_argument("--record", default="")
    ap.add_argument("--width", type=int, default=1280)
    ap.add_argument("--height", type=int, default=720)
    ap.add_argument("--fps", type=int, default=60)
    ap.add_argument("--no-mirror", action="store_true")
    ap.add_argument("--streams", default="hands")
    ap.add_argument("--num-hands", type=int, default=2)
    ap.add_argument("--pose-model", choices=("lite", "full"), default="lite")
    ap.add_argument("--depth-size", type=int, default=518)
    ap.add_argument("--smoothing", type=float, default=0.5)
    ap.add_argument("--world", action="store_true")
    ap.add_argument("--pixel", action="store_true")
    ap.add_argument("--no-overlay", action="store_true")
    ap.add_argument("--no-video", action="store_true")
    ap.add_argument("--transport", choices=("auto", "spout", "shm"), default="auto")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=7400)
    ap.add_argument("--control-port", type=int, default=0)
    ap.add_argument("--parent", type=int, default=0)
    ap.add_argument("--log", default="")
    return ap.parse_args(argv)


def config(a):
    s = {x.strip() for x in a.streams.split(",") if x.strip()}
    return {
        "camera": a.camera, "video_file": a.video_file, "synthetic": a.synthetic, "replay": a.replay,
        "record": a.record, "width": a.width, "height": a.height, "fps": a.fps, "mirror": not a.no_mirror,
        "hands": "hands" in s, "face": "face" in s, "pose": "pose" in s, "segment": "segment" in s,
        "depth": "depth" in s, "num_hands": a.num_hands, "pose_model": a.pose_model, "depth_size": a.depth_size,
        "smoothing": a.smoothing, "world": a.world, "pixel": a.pixel, "overlay": not a.no_overlay,
        "video": not a.no_video, "transport": a.transport, "host": a.host, "port": a.port,
        "control_port": a.control_port or a.port + 9, "parent": a.parent,
    }


def main(argv=None):
    mp.freeze_support()
    a = parse(argv)
    if a.list_cameras:
        from .camera import list_cameras
        print(json.dumps(list_cameras()))
        return
    from .sidecar import Log, Sidecar
    Sidecar(config(a), Log(a.log or None)).run()


if __name__ == "__main__":
    main(sys.argv[1:])
