import numpy as np
from multiprocessing import shared_memory

DT = (np.uint8, np.float16, np.float32)
cache = {}


def read(name):
    r = cache.get(name)
    if r is None:
        try:
            shm = shared_memory.SharedMemory(name=name)
        except Exception:
            return None
        r = cache[name] = [shm, np.ndarray((16,), np.uint32, buffer=shm.buf[:64]), 0]
    shm, head, last = r
    s = int(head[0])
    if s & 1 or s == last:
        return None
    w, h, c, code = (int(x) for x in head[1:5])
    if w == 0 or h == 0 or code > 2:
        return None
    dt = np.dtype(DT[code])
    n = w * h * c * dt.itemsize
    if 64 + n > shm.size:
        return None
    a = np.frombuffer(shm.buf[64:64 + n], dtype=dt).reshape(h, w, c).copy()
    if int(head[0]) != s:
        return None
    r[2] = s
    return a


def onSetupParameters(scriptOp):
    page = scriptOp.appendCustomPage("Slot")
    page.appendStr("Slot", label="Slot")
    page.appendInt("Tick", label="Tick")
    scriptOp.par.Tick.expr = "absTime.frame"


def onPulse(par):
    return


def onCook(scriptOp):
    a = read(scriptOp.par.Slot.eval())
    if a is None:
        return
    if a.dtype == np.float16:
        a = a.astype(np.float32)
    scriptOp.copyNumpyArray(a)
