import socket
import struct

import numpy as np

BUNDLE = b"#bundle\0" + b"\0\0\0\0\0\0\0\1"
MAX_PACKET = 60000


def pad(b):
    return b + b"\0" * (4 - len(b) % 4)


def encode(address, *args):
    tags = ","
    body = b""
    for a in args:
        if isinstance(a, bool):
            tags += "i"
            body += struct.pack(">i", int(a))
        elif isinstance(a, int):
            tags += "i"
            body += struct.pack(">i", a)
        elif isinstance(a, float):
            tags += "f"
            body += struct.pack(">f", a)
        else:
            tags += "s"
            body += pad(str(a).encode())
    return pad(address.encode()) + pad(tags.encode()) + body


def decode(data):
    out = []
    _walk(data, out)
    return out


def _walk(data, out):
    if data.startswith(b"#bundle"):
        i = 16
        while i + 4 <= len(data):
            n = struct.unpack(">i", data[i:i + 4])[0]
            _walk(data[i + 4:i + 4 + n], out)
            i += 4 + n
        return
    end = data.find(b"\0")
    if end < 1:
        return
    addr = data[:end].decode(errors="replace")
    i = (end + 4) & ~3
    tend = data.find(b"\0", i)
    tags = data[i + 1:tend].decode(errors="replace") if tend > i else ""
    i = (tend + 4) & ~3
    args = []
    for t in tags:
        if t == "f":
            args.append(struct.unpack(">f", data[i:i + 4])[0])
            i += 4
        elif t == "i":
            args.append(struct.unpack(">i", data[i:i + 4])[0])
            i += 4
        elif t == "s":
            e = data.find(b"\0", i)
            args.append(data[i:e].decode(errors="replace"))
            i = (e + 4) & ~3
        elif t in "TF":
            args.append(t == "T")
    out.append((addr, args))


class ChannelSender:
    def __init__(self, host, port, names):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.target = (host, int(port))
        self.set_names(names)

    def set_names(self, names):
        self.names = list(names)
        heads = [pad(("/" + n).encode()) + b",f\0\0" for n in self.names]
        self.frames = [struct.pack(">i", len(h) + 4) + h for h in heads]
        self.chunks = []
        start, size = 0, len(BUNDLE)
        for i, f in enumerate(self.frames):
            if size + len(f) + 4 > MAX_PACKET and i > start:
                self.chunks.append((start, i))
                start, size = i, len(BUNDLE)
            size += len(f) + 4
        self.chunks.append((start, len(self.frames)))

    def send(self, values):
        raw = np.asarray(values, dtype=">f4").tobytes()
        for a, b in self.chunks:
            parts = [BUNDLE]
            for i in range(a, b):
                parts.append(self.frames[i])
                parts.append(raw[i * 4:i * 4 + 4])
            try:
                self.sock.sendto(b"".join(parts), self.target)
            except OSError:
                pass

    def close(self):
        self.sock.close()
