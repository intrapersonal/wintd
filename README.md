"why not just use the mediapipe plugin?"

the mediapipe touchdesigner plugin runs its models inside a hidden chromium browser.
every frame goes td → browser → back to td, and the results show up as json that
python has to parse on td's main thread. that round trip and the python work are
what DEMOLISH your frames.

wintd skips all of that:
- runs in its own process, so if it stalls your td project keeps rendering
- opens the camera itself, no sending frames out of td and back
- inference on the gpu through onnxruntime + directml (nvidia, amd and intel)
- landmarks come in over osc into a stock osc in chop, zero python in your cook
- masks and depth come in through spout, gpu to gpu, no copying pixels around
- every stream is off until you turn it on, so you only pay for what you use
- press install and it grabs its own python + models, it never touches your setup

thanks to **@ojrgb** for developing "appletd" (uses apple NN's and has no framedrop, good if ur using a mac) check out his repo which inspired this one.
