package main

import (
	"archive/zip"
	"bufio"
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net"
	"net/http"
	"os"
	"os/exec"
	"path/filepath"
	"runtime"
	"strings"
	"sync"
	"time"
)

const (
	repoZip     = "https://codeload.github.com/intrapersonal/wintd/zip/refs/heads/main"
	appletdTox  = "https://github.com/ojrgb/appletd/raw/main/appletd.tox"
	appletdRepo = "https://github.com/ojrgb/appletd"
	pyEmbed     = "https://www.python.org/ftp/python/3.11.9/python-3.11.9-embed-amd64.zip"
	getPip      = "https://bootstrap.pypa.io/get-pip.py"
	version     = "0.1.0"
)

type Info struct {
	OS        string   `json:"os"`
	Arch      string   `json:"arch"`
	Pretty    string   `json:"pretty"`
	Tool      string   `json:"tool"`
	Reason    string   `json:"reason"`
	Folder    string   `json:"folder"`
	Root      string   `json:"root"`
	Pythons   []string `json:"pythons"`
	Version   string   `json:"version"`
	Supported bool     `json:"supported"`
}

type Request struct {
	Tool    string   `json:"tool"`
	Folder  string   `json:"folder"`
	Root    string   `json:"root"`
	Python  string   `json:"python"`
	Streams []string `json:"streams"`
	Host    string   `json:"host"`
	Keep    bool     `json:"keep"`
	DryRun  bool     `json:"dryRun"`
}

type Job struct {
	mu     sync.Mutex
	Lines  []string `json:"lines"`
	Step   string   `json:"step"`
	Done   bool     `json:"done"`
	Error  string   `json:"error"`
	Output string   `json:"output"`
	active bool
}

func (j *Job) log(format string, a ...any) {
	j.mu.Lock()
	defer j.mu.Unlock()
	line := fmt.Sprintf(format, a...)
	j.Lines = append(j.Lines, line)
	if len(j.Lines) > 400 {
		j.Lines = j.Lines[len(j.Lines)-400:]
	}
}

func (j *Job) step(s string) {
	j.mu.Lock()
	j.Step = s
	j.mu.Unlock()
	j.log("== %s", s)
}

func (j *Job) snapshot() map[string]any {
	j.mu.Lock()
	defer j.mu.Unlock()
	lines := make([]string, len(j.Lines))
	copy(lines, j.Lines)
	return map[string]any{"lines": lines, "step": j.Step, "done": j.Done, "error": j.Error, "output": j.Output, "active": j.active}
}

var job = &Job{}

func home() string {
	h, _ := os.UserHomeDir()
	return h
}

func appleSilicon() bool {
	if runtime.GOOS != "darwin" {
		return false
	}
	if runtime.GOARCH == "arm64" {
		return true
	}
	out, err := exec.Command("sysctl", "-n", "hw.optional.arm64").Output()
	return err == nil && strings.TrimSpace(string(out)) == "1"
}

func pythons() []string {
	var found []string
	for _, n := range []string{"python3.11", "python3.12", "python3.10", "python3.9", "python3"} {
		if p, err := exec.LookPath(n); err == nil {
			found = append(found, p)
		}
	}
	return found
}

func defaultRoot() string {
	switch runtime.GOOS {
	case "windows":
		if v := os.Getenv("LOCALAPPDATA"); v != "" {
			return filepath.Join(v, "wintd")
		}
		return filepath.Join(home(), "AppData", "Local", "wintd")
	case "darwin":
		return filepath.Join(home(), "Library", "Application Support", "wintd")
	default:
		if v := os.Getenv("XDG_DATA_HOME"); v != "" {
			return filepath.Join(v, "wintd")
		}
		return filepath.Join(home(), ".local", "share", "wintd")
	}
}

func detect() Info {
	i := Info{OS: runtime.GOOS, Arch: runtime.GOARCH, Root: defaultRoot(), Version: version, Supported: true}
	docs := filepath.Join(home(), "Documents", "TouchDesigner")
	switch runtime.GOOS {
	case "windows":
		i.Pretty = "Windows " + runtime.GOARCH
		i.Tool = "wintd"
		i.Reason = "wintd runs hands, face, pose, masks and depth in its own process and feeds TouchDesigner over OSC + Spout."
		i.Folder = filepath.Join(docs, "wintd")
		if runtime.GOARCH != "amd64" {
			i.Reason = "wintd needs an x64 Windows install. ARM Windows isn't supported by mediapipe yet."
			i.Supported = false
		}
	case "darwin":
		i.Folder = filepath.Join(docs, "appletd")
		if appleSilicon() {
			i.Pretty = "macOS · Apple Silicon"
			i.Tool = "appletd"
			i.Reason = "On Apple Silicon, appletd by ojrgb uses Apple's own vision models on the Neural Engine. It's the fastest option on a Mac."
		} else {
			i.Pretty = "macOS · Intel"
			i.Tool = "mediapipe-td"
			i.Reason = "appletd needs Apple Silicon. On an Intel Mac the mediapipe TouchDesigner plugin is the way to go."
			i.Supported = false
		}
	default:
		i.Pretty = strings.ToUpper(runtime.GOOS[:1]) + runtime.GOOS[1:] + " " + runtime.GOARCH
		i.Tool = "sidecar"
		i.Reason = "TouchDesigner doesn't run on Linux. This installs the wintd tracker as a network sender: it tracks here and streams channels over OSC to TouchDesigner on another machine."
		i.Folder = filepath.Join(home(), "wintd")
	}
	i.Pythons = pythons()
	return i
}

func download(ctx context.Context, url, dest string, label string) error {
	if err := os.MkdirAll(filepath.Dir(dest), 0o755); err != nil {
		return err
	}
	req, _ := http.NewRequestWithContext(ctx, "GET", url, nil)
	req.Header.Set("User-Agent", "wintd-universal/"+version)
	resp, err := http.DefaultClient.Do(req)
	if err != nil {
		return err
	}
	defer resp.Body.Close()
	if resp.StatusCode == 404 {
		return fmt.Errorf("%s: not found (404). if the repo is private the launcher can't download it", label)
	}
	if resp.StatusCode >= 400 {
		return fmt.Errorf("%s: http %d", label, resp.StatusCode)
	}
	tmp := dest + ".part"
	f, err := os.Create(tmp)
	if err != nil {
		return err
	}
	total := resp.ContentLength
	var got int64
	buf := make([]byte, 1<<16)
	last := time.Now()
	for {
		n, rerr := resp.Body.Read(buf)
		if n > 0 {
			if _, werr := f.Write(buf[:n]); werr != nil {
				f.Close()
				return werr
			}
			got += int64(n)
			if time.Since(last) > 700*time.Millisecond {
				last = time.Now()
				if total > 0 {
					job.log("%s %d%%", label, got*100/total)
				} else {
					job.log("%s %.1f MB", label, float64(got)/1e6)
				}
			}
		}
		if rerr == io.EOF {
			break
		}
		if rerr != nil {
			f.Close()
			return rerr
		}
	}
	f.Close()
	return os.Rename(tmp, dest)
}

func unzip(src, dest string, strip bool) error {
	r, err := zip.OpenReader(src)
	if err != nil {
		return err
	}
	defer r.Close()
	for _, f := range r.File {
		name := f.Name
		if strip {
			if i := strings.Index(name, "/"); i >= 0 {
				name = name[i+1:]
			} else {
				continue
			}
		}
		if name == "" {
			continue
		}
		p := filepath.Join(dest, filepath.FromSlash(name))
		if !strings.HasPrefix(p, filepath.Clean(dest)+string(os.PathSeparator)) {
			return fmt.Errorf("bad path in zip: %s", f.Name)
		}
		if f.FileInfo().IsDir() {
			os.MkdirAll(p, 0o755)
			continue
		}
		os.MkdirAll(filepath.Dir(p), 0o755)
		rc, err := f.Open()
		if err != nil {
			return err
		}
		out, err := os.OpenFile(p, os.O_CREATE|os.O_WRONLY|os.O_TRUNC, f.Mode()|0o600)
		if err != nil {
			rc.Close()
			return err
		}
		_, err = io.Copy(out, rc)
		rc.Close()
		out.Close()
		if err != nil {
			return err
		}
	}
	return nil
}

func copyFile(src, dst string) error {
	in, err := os.Open(src)
	if err != nil {
		return err
	}
	defer in.Close()
	os.MkdirAll(filepath.Dir(dst), 0o755)
	out, err := os.Create(dst)
	if err != nil {
		return err
	}
	defer out.Close()
	_, err = io.Copy(out, in)
	return err
}

func copyDir(src, dst string) error {
	return filepath.Walk(src, func(p string, info os.FileInfo, err error) error {
		if err != nil {
			return err
		}
		rel, _ := filepath.Rel(src, p)
		t := filepath.Join(dst, rel)
		if info.IsDir() {
			return os.MkdirAll(t, 0o755)
		}
		return copyFile(p, t)
	})
}

func runCmd(ctx context.Context, label string, env []string, name string, args ...string) error {
	cmd := exec.CommandContext(ctx, name, args...)
	hide(cmd)
	if env != nil {
		cmd.Env = append(os.Environ(), env...)
	}
	stdout, _ := cmd.StdoutPipe()
	cmd.Stderr = cmd.Stdout
	if err := cmd.Start(); err != nil {
		return err
	}
	sc := bufio.NewScanner(stdout)
	sc.Buffer(make([]byte, 1<<20), 1<<20)
	var tail []string
	for sc.Scan() {
		line := strings.TrimSpace(sc.Text())
		if line == "" {
			continue
		}
		tail = append(tail, line)
		if len(tail) > 20 {
			tail = tail[1:]
		}
		job.log("%s", line)
	}
	if err := cmd.Wait(); err != nil {
		return fmt.Errorf("%s failed: %v\n%s", label, err, strings.Join(tail, "\n"))
	}
	return nil
}

func fetchRepo(ctx context.Context, tmp string) (string, error) {
	job.step("downloading wintd")
	z := filepath.Join(tmp, "wintd.zip")
	if err := download(ctx, repoZip, z, "wintd"); err != nil {
		return "", err
	}
	src := filepath.Join(tmp, "src")
	os.RemoveAll(src)
	if err := unzip(z, src, true); err != nil {
		return "", err
	}
	return src, nil
}

func installWindows(ctx context.Context, r Request, tmp string) error {
	src, err := fetchRepo(ctx, tmp)
	if err != nil {
		return err
	}
	job.step("copying the component")
	os.MkdirAll(r.Folder, 0o755)
	if _, err := os.Stat(filepath.Join(src, "wintd.tox")); err == nil {
		if err := copyFile(filepath.Join(src, "wintd.tox"), filepath.Join(r.Folder, "wintd.tox")); err != nil {
			return err
		}
	} else {
		job.log("wintd.tox isn't in the repo yet, skipping")
	}
	if _, err := os.Stat(filepath.Join(src, "examples")); err == nil {
		copyDir(filepath.Join(src, "examples"), filepath.Join(r.Folder, "examples"))
	}
	py := filepath.Join(r.Root, "python", "python.exe")
	if r.Python != "" {
		py = r.Python
	}
	if _, err := os.Stat(py); err != nil {
		job.step("getting python")
		z := filepath.Join(tmp, "python.zip")
		if err := download(ctx, pyEmbed, z, "python"); err != nil {
			return err
		}
		target := filepath.Join(r.Root, "python")
		os.RemoveAll(target)
		if err := unzip(z, target, false); err != nil {
			return err
		}
		matches, _ := filepath.Glob(filepath.Join(target, "python*._pth"))
		for _, m := range matches {
			b, _ := os.ReadFile(m)
			s := strings.ReplaceAll(string(b), "#import site", "import site")
			if !strings.Contains(s, "..\\pkg") {
				s = strings.TrimRight(s, "\r\n") + "\r\n..\\pkg\r\n"
			}
			os.WriteFile(m, []byte(s), 0o644)
		}
		gp := filepath.Join(tmp, "get-pip.py")
		if err := download(ctx, getPip, gp, "pip"); err != nil {
			return err
		}
		job.step("installing pip")
		if err := runCmd(ctx, "pip", nil, py, gp, "--no-warn-script-location"); err != nil {
			return err
		}
	}
	job.step("installing packages + models (takes a few minutes)")
	streams := strings.Join(r.Streams, ",")
	if streams == "" {
		streams = "hands"
	}
	env := []string{"WINTD_HOME=" + r.Root}
	if err := runCmd(ctx, "install", env, py, filepath.Join(src, "wintd", "bootstrap.py"), "--root", r.Root, "--streams", streams); err != nil {
		return err
	}
	job.mu.Lock()
	job.Output = r.Folder
	job.mu.Unlock()
	return nil
}

func installApple(ctx context.Context, r Request) error {
	job.step("downloading appletd")
	dest := filepath.Join(r.Folder, "appletd.tox")
	if err := download(ctx, appletdTox, dest, "appletd.tox"); err != nil {
		return err
	}
	job.log("saved %s", dest)
	job.log("drag appletd.tox into TouchDesigner and press Install on its Vision page. more at %s", appletdRepo)
	job.mu.Lock()
	job.Output = r.Folder
	job.mu.Unlock()
	return nil
}

func installSidecar(ctx context.Context, r Request, tmp string) error {
	src, err := fetchRepo(ctx, tmp)
	if err != nil {
		return err
	}
	base := r.Python
	if base == "" {
		if ps := pythons(); len(ps) > 0 {
			base = ps[0]
		} else {
			return errors.New("no python3 found. install python 3.11 (apt install python3.11 python3.11-venv) and try again")
		}
	}
	job.step("installing the tracker (takes a few minutes)")
	streams := strings.Join(r.Streams, ",")
	if streams == "" {
		streams = "hands"
	}
	if err := runCmd(ctx, "install", []string{"WINTD_HOME=" + r.Root}, base, filepath.Join(src, "wintd", "bootstrap.py"), "--root", r.Root, "--streams", streams, "--python", base); err != nil {
		return err
	}
	job.step("writing the start script")
	host := r.Host
	if host == "" {
		host = "127.0.0.1"
	}
	os.MkdirAll(r.Folder, 0o755)
	script := filepath.Join(r.Folder, "wintd-send")
	body := fmt.Sprintf("#!/bin/sh\nexport WINTD_HOME=\"%s\"\nexport PYTHONPATH=\"%s\"\nexec \"%s\" -m wintd --host \"${WINTD_HOST:-%s}\" --no-video --no-overlay --streams \"${WINTD_STREAMS:-%s}\" \"$@\"\n",
		r.Root, filepath.Join(r.Root, "pkg"), filepath.Join(r.Root, "venv", "bin", "python"), host, streams)
	if err := os.WriteFile(script, []byte(body), 0o755); err != nil {
		return err
	}
	job.log("run %s to start sending to %s", script, host)
	job.mu.Lock()
	job.Output = r.Folder
	job.mu.Unlock()
	return nil
}

func plan(r Request) []string {
	switch r.Tool {
	case "wintd":
		return []string{
			"download the wintd repo zip from github",
			"copy wintd.tox + examples to " + r.Folder,
			"download python 3.11 (embedded, private copy) to " + filepath.Join(r.Root, "python"),
			"pip install mediapipe, opencv, onnxruntime-directml, SpoutGL",
			"download models for: " + strings.Join(r.Streams, ", "),
		}
	case "appletd":
		return []string{"download appletd.tox from " + appletdRepo, "save it to " + r.Folder}
	case "sidecar":
		return []string{
			"download the wintd repo zip from github",
			"create a venv at " + filepath.Join(r.Root, "venv") + " using " + r.Python,
			"pip install mediapipe, opencv, onnxruntime",
			"write " + filepath.Join(r.Folder, "wintd-send") + " (sends OSC to " + r.Host + ")",
		}
	}
	return []string{"nothing to do for " + r.Tool}
}

func start(r Request) error {
	job.mu.Lock()
	if job.active {
		job.mu.Unlock()
		return errors.New("an install is already running")
	}
	job.Lines, job.Step, job.Done, job.Error, job.Output, job.active = nil, "", false, "", "", true
	job.mu.Unlock()
	go func() {
		ctx := context.Background()
		tmp, _ := os.MkdirTemp("", "wintd-universal-")
		var err error
		if r.DryRun {
			job.step("dry run")
			for _, s := range plan(r) {
				job.log("- %s", s)
			}
		} else {
			switch r.Tool {
			case "wintd":
				err = installWindows(ctx, r, tmp)
			case "appletd":
				err = installApple(ctx, r)
			case "sidecar":
				err = installSidecar(ctx, r, tmp)
			default:
				err = fmt.Errorf("no installer for %q", r.Tool)
			}
		}
		if !r.Keep {
			os.RemoveAll(tmp)
		} else {
			job.log("kept downloads in %s", tmp)
		}
		job.mu.Lock()
		job.active = false
		job.Done = true
		if err != nil {
			job.Error = err.Error()
		}
		job.mu.Unlock()
		if err != nil {
			job.log("failed: %v", err)
		} else if !r.DryRun {
			job.step("done")
		}
	}()
	return nil
}

func openPath(p string) {
	var cmd *exec.Cmd
	switch runtime.GOOS {
	case "windows":
		cmd = exec.Command("explorer", p)
	case "darwin":
		cmd = exec.Command("open", p)
	default:
		cmd = exec.Command("xdg-open", p)
	}
	hide(cmd)
	cmd.Start()
}

func openBrowser(url string) {
	var cmd *exec.Cmd
	switch runtime.GOOS {
	case "windows":
		cmd = exec.Command("rundll32", "url.dll,FileProtocolHandler", url)
	case "darwin":
		cmd = exec.Command("open", url)
	default:
		cmd = exec.Command("xdg-open", url)
	}
	hide(cmd)
	cmd.Start()
}

func writeJSON(w http.ResponseWriter, v any) {
	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(v)
}

func main() {
	noBrowser := len(os.Args) > 1 && os.Args[1] == "--no-browser"
	ln, err := net.Listen("tcp", "127.0.0.1:0")
	if err != nil {
		fmt.Println("couldn't start:", err)
		os.Exit(1)
	}
	token := fmt.Sprintf("%x", time.Now().UnixNano())
	last := time.Now()
	var lastMu sync.Mutex
	touch := func() {
		lastMu.Lock()
		last = time.Now()
		lastMu.Unlock()
	}
	mux := http.NewServeMux()
	guard := func(h http.HandlerFunc) http.HandlerFunc {
		return func(w http.ResponseWriter, r *http.Request) {
			if r.Header.Get("X-Token") != token {
				http.Error(w, "forbidden", 403)
				return
			}
			touch()
			h(w, r)
		}
	}
	mux.HandleFunc("/", func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path != "/" {
			http.NotFound(w, r)
			return
		}
		touch()
		w.Header().Set("Content-Type", "text/html; charset=utf-8")
		w.Write(bytes.Replace(page, []byte("__TOKEN__"), []byte(token), 1))
	})
	mux.HandleFunc("/api/info", guard(func(w http.ResponseWriter, r *http.Request) { writeJSON(w, detect()) }))
	mux.HandleFunc("/api/install", guard(func(w http.ResponseWriter, r *http.Request) {
		var req Request
		if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
			http.Error(w, err.Error(), 400)
			return
		}
		if req.Root == "" {
			req.Root = defaultRoot()
		}
		if req.Folder == "" {
			req.Folder = detect().Folder
		}
		if err := start(req); err != nil {
			http.Error(w, err.Error(), 409)
			return
		}
		writeJSON(w, map[string]any{"ok": true})
	}))
	mux.HandleFunc("/api/progress", guard(func(w http.ResponseWriter, r *http.Request) { writeJSON(w, job.snapshot()) }))
	mux.HandleFunc("/api/open", guard(func(w http.ResponseWriter, r *http.Request) {
		p := r.URL.Query().Get("path")
		if p != "" {
			openPath(p)
		}
		writeJSON(w, map[string]any{"ok": true})
	}))
	mux.HandleFunc("/api/quit", guard(func(w http.ResponseWriter, r *http.Request) {
		writeJSON(w, map[string]any{"ok": true})
		go func() { time.Sleep(300 * time.Millisecond); os.Exit(0) }()
	}))
	url := "http://" + ln.Addr().String() + "/"
	fmt.Println("wintd universal " + version)
	fmt.Println("open " + url + " if your browser didn't pop up")
	if !noBrowser {
		openBrowser(url)
	}
	go func() {
		for {
			time.Sleep(15 * time.Second)
			lastMu.Lock()
			idle := time.Since(last)
			lastMu.Unlock()
			job.mu.Lock()
			busy := job.active
			job.mu.Unlock()
			if idle > 3*time.Minute && !busy {
				os.Exit(0)
			}
		}
	}()
	http.Serve(ln, mux)
}
