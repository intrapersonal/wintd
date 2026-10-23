def onStart():
    c = parent()
    c.CheckInstall()
    if c.par.Active.eval():
        run("args[0].Start()", c, delayFrames=30)


def onExit():
    parent().OnExit()


def onProjectPreSave():
    return
