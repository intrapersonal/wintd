import os
import time
from multiprocessing import shared_memory

import numpy as np

HEADER = 64
DTYPES = {0: np.uint8, 1: np.float16, 2: np.float32}
CODES = {np.dtype(np.uint8): 0, np.dtype(np.float16): 1, np.dtype(np.float32): 2}


def _open(name, size, create):
    if create:
        try:
            old = shared_memory.SharedMemory(name=name)
            if old.size >= size:
                return old
            old.close()
            try:
                old.unlink()
            except Exception:
                pass
        except FileNotFoundError:
            pass
        return shared_memory.SharedMemory(name=name, create=True, size=size)
    return shared_memory.SharedMemory(name=name)


def untrack(shm):
    if os.name == "nt":
        return
    try:
        from multiprocessing import resource_tracker
        resource_tracker.unregister(shm._name, "shared_memory")
    except Exception:
        pass


class SlotWriter:
    def __init__(self, name, capacity):
        self.name = name
        self.shm = _open(name, HEADER + capacity, True)
        self.capacity = self.shm.size - HEADER
        self.head = np.ndarray((16,), dtype=np.uint32, buffer=self.shm.buf[:HEADER])
        self.head[:] = 0

    def write(self, arr, stamp=0):
        arr = np.ascontiguousarray(arr)
        if arr.ndim == 2:
            arr = arr[:, :, None]
        h, w, c = arr.shape
        n = arr.nbytes
        if n > self.capacity:
            return False
        seq = int(self.head[0])
        self.head[0] = seq + 1
        self.shm.buf[HEADER:HEADER + n] = arr.reshape(-1).view(np.uint8)
        self.head[1] = w
        self.head[2] = h
        self.head[3] = c
        self.head[4] = CODES[arr.dtype]
        self.head[5] = int(stamp) & 0xFFFFFFFF
        self.head[0] = seq + 2
        return True

    def close(self, unlink=True):
        try:
            del self.head
            self.shm.close()
            if unlink:
                self.shm.unlink()
        except Exception:
            pass


class SlotReader:
    def __init__(self, name):
        self.name = name
        self.shm = None
        self.last = 0
        self.stamp = 0

    def _ensure(self):
        if self.shm is None:
            try:
                self.shm = shared_memory.SharedMemory(name=self.name)
                untrack(self.shm)
                self.head = np.ndarray((16,), dtype=np.uint32, buffer=self.shm.buf[:HEADER])
            except FileNotFoundError:
                return False
        return True

    def seq(self):
        if not self._ensure():
            return 0
        return int(self.head[0])

    def read(self, only_new=True):
        if not self._ensure():
            return None
        for _ in range(3):
            s1 = int(self.head[0])
            if s1 & 1:
                time.sleep(0.0002)
                continue
            if only_new and s1 == self.last:
                return None
            w, h, c, code, stamp = (int(x) for x in self.head[1:6])
            if w == 0 or h == 0:
                return None
            dt = np.dtype(DTYPES.get(code, np.uint8))
            n = w * h * c * dt.itemsize
            out = np.frombuffer(bytes(self.shm.buf[HEADER:HEADER + n]), dtype=dt).reshape(h, w, c)
            if int(self.head[0]) == s1:
                self.last = s1
                self.stamp = stamp
                return out
        return None

    def close(self):
        try:
            del self.head
            self.shm.close()
        except Exception:
            pass
