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
