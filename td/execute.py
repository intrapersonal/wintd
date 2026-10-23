def onStart():
    c = parent()
    if c.CheckInstall():
        c.RefreshCameras()
    if c.par.Active.eval():
        run("args[0].Start()", c, delayFrames=30)


def onExit():
    parent().OnExit()


def onProjectPreSave():
    return


def onCreate():
    onStart()


def onFrameStart(frame):
    if frame % 15:
        return
    c = parent()
    for k in ("video", "overlay"):
        v = 1 if c.Flag("spout_" + k) > 0.5 else 0
        p = c.op("pick_" + k).par.index
        if p.eval() != v:
            p.val = v
