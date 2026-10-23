# universal

`universal.exe` (windows), `universal-macos` (apple silicon), `universal-linux`.

run it, it opens a page in your browser, figures out what you're on and installs the right thing:

- windows → wintd (component + python + models)
- mac (apple silicon) → [appletd](https://github.com/ojrgb/appletd)
- linux → the wintd tracker as a network sender, since td doesn't run on linux. point it at the td machine's ip

open **Advanced** to pick the tool yourself, change folders, prefetch more models or do a dry run.

the binaries aren't signed. on windows click More info → Run anyway, on mac right click → Open.

build from source with go 1.22+:

```
GOOS=windows GOARCH=amd64 go build -o universal.exe .
GOOS=darwin GOARCH=arm64 go build -o universal-macos .
GOOS=linux GOARCH=amd64 go build -o universal-linux .
```
