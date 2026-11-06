// sidecar/watchd — the supervisor that outlives the assistant.
//
// # WHY THIS IS THE ONE COMPONENT IN GO
//
// The language matrix in docs/LANGUAGE_MATRIX.md keeps one case for a compiled
// language: a component that must survive the program it supervises. Everything
// else stayed in Python, and that decision is measured, not stylistic — the audio
// leaf is 0.005 % of a frame and a turn waits on the network, so a rewrite of the
// shell would move no number the owner can feel.
//
// This file is the exception, and it is an exception for a reason that has
// nothing to do with arithmetic:
//
//   - If the assistant crashes, a supervisor written inside the assistant dies
//     with it. That is the one job that cannot live in the same process.
//   - It must start in single-digit milliseconds and sit at ~10 MB, because it
//     runs all day beside a program that already uses 52 MB.
//   - It ships as one static binary per platform, with no interpreter to install
//     and no package to import.
//
// Go wins that trade over Rust here for three concrete reasons: a static binary
// in one command with no toolchain on the owner's machine, goroutines that make
// "poll and supervise at the same time" four lines, and a Windows build that is
// `GOOS=windows go build`. Rust would win if this file needed to be a hot loop or
// to make fine-grained memory promises. It does neither.
//
// # THE SAME SAFETY RULE AS THE PYTHON WATCHER
//
// It observes. It never ends, pauses or re-prioritises a program it did not
// start. The only process it may start or restart is the assistant itself, and
// only when the owner asked for that with -supervise. A supervisor that can kill
// is a supervisor that will one day kill the wrong thing.
package main

import (
	"encoding/json"
	"errors"
	"flag"
	"fmt"
	"io"
	"os"
	"os/exec"
	"os/signal"
	"path/filepath"
	"runtime"
	"sort"
	"strings"
	"sync"
	"syscall"
	"time"
)

// version is printed by -version and by the heartbeat, so a field log says which
// build produced it.
const version = "1.0.0"

// Proc is one observation of one process.
//
// Identity is PID *and* start time. PIDs are reused by every operating system
// within seconds, and a watcher that trusts a bare PID eventually reports that a
// job finished because an unrelated program inherited its number.
type Proc struct {
	PID   int
	Name  string
	Start uint64 // platform-specific start stamp; 0 when the platform has none
}

func (p Proc) key() string { return fmt.Sprintf("%d:%d", p.PID, p.Start) }

// Event is one finished job, written as a single JSON line so a reader can tail
// the file without a protocol.
type Event struct {
	TS      string  `json:"ts"`
	PID     int     `json:"pid"`
	Name    string  `json:"name"`
	Seconds float64 `json:"seconds"`
	How     string  `json:"how"` // "ended" — never "succeeded"; see below
	Watch   string  `json:"watch"`
}

// Options is everything the owner can change without a rebuild.
type Options struct {
	Watch     []string
	Events    string
	Poll      time.Duration
	Once      bool
	Supervise string
	Restart   bool
	Heartbeat string
	Version   bool
}

func parseFlags(args []string) (Options, error) {
	// A fresh set per call: a global flag set can only be parsed once, and a
	// program that cannot be asked twice for its options is hard to test.
	set := flag.NewFlagSet("watchd", flag.ContinueOnError)
	set.SetOutput(io.Discard)
	var (
		watch     = set.String("watch", "", "comma separated process names to watch")
		events    = set.String("events", "watch-events.jsonl", "event log (JSON lines)")
		poll      = set.Duration("poll", 2*time.Second, "how often to look")
		once      = set.Bool("once", false, "one sweep, then exit (for tests)")
		supervise = set.String("supervise", "", "command to keep alive")
		restart   = set.Bool("restart", true, "restart the supervised command if it exits")
		heartbeat = set.String("heartbeat", "", "write a timestamp here every poll")
		showVer   = set.Bool("version", false, "print the version and exit")
	)
	if err := set.Parse(args); err != nil {
		return Options{}, err
	}
	opts := Options{
		Events:    *events,
		Poll:      *poll,
		Once:      *once,
		Supervise: *supervise,
		Restart:   *restart,
		Heartbeat: *heartbeat,
		Version:   *showVer,
	}
	for _, part := range strings.Split(*watch, ",") {
		part = strings.TrimSpace(strings.ToLower(part))
		if part != "" {
			opts.Watch = append(opts.Watch, part)
		}
	}
	if opts.Poll < 100*time.Millisecond {
		return Options{}, errors.New("-poll must be at least 100ms")
	}
	if len(opts.Watch) == 0 && opts.Supervise == "" {
		return Options{}, errors.New("nothing to do: set -watch and/or -supervise")
	}
	return opts, nil
}

// matches reports whether a process name contains any pattern. Patterns, not
// regular expressions: a name typed into a settings file must not be able to
// become a slow expression by accident.
func matches(name string, patterns []string) bool {
	name = strings.ToLower(name)
	for _, pattern := range patterns {
		if pattern != "" && strings.Contains(name, pattern) {
			return true
		}
	}
	return false
}

// diff compares two sweeps and returns the jobs that have finished.
//
// A job is finished when an identity that was seen is no longer present. A
// process whose start stamp changed under the same PID is a *different* process,
// so the old one counts as finished and the new one is adopted. Reporting that
// honestly matters more than being tidy about it.
func diff(before map[string]Proc, now map[string]Proc, startedAt map[string]time.Time, at time.Time) []Event {
	var events []Event
	for key, was := range before {
		if _, still := now[key]; still {
			continue
		}
		since, seen := startedAt[key]
		seconds := 0.0
		if seen {
			seconds = at.Sub(since).Seconds()
		}
		events = append(events, Event{
			TS:      at.UTC().Format(time.RFC3339),
			PID:     was.PID,
			Name:    was.Name,
			Seconds: seconds,
			// "ended", never "succeeded": a process this program did not start
			// has no exit code to read, and a guess in a suit is still a guess.
			How: "ended",
		})
	}
	sort.Slice(events, func(i, j int) bool { return events[i].PID < events[j].PID })
	return events
}

// backoff is the restart delay after the nth consecutive failure. Doubling, with
// a ceiling, because a program that dies in a loop must not become a busy loop.
func backoff(failures int) time.Duration {
	if failures <= 0 {
		return 0
	}
	delay := 500 * time.Millisecond
	for i := 1; i < failures && delay < 30*time.Second; i++ {
		delay *= 2
	}
	if delay > 30*time.Second {
		delay = 30 * time.Second
	}
	return delay
}

// --- process tables -------------------------------------------------------
//
// Two platforms, two implementations, one shape. No dependency is imported for
// either: a supervisor should be buildable with nothing but the standard library,
// because it may be the only thing still running.

var errNoTable = errors.New("the process table could not be read")

// scanLinux reads /proc. The start stamp is field 22 of stat: the boot ticks at
// which the process started.
func scanLinux() ([]Proc, error) {
	entries, err := os.ReadDir("/proc")
	if err != nil {
		return nil, errNoTable
	}
	procs := make([]Proc, 0, len(entries))
	for _, entry := range entries {
		pid, convErr := parsePID(entry.Name())
		if convErr != nil {
			continue
		}
		raw, readErr := os.ReadFile(filepath.Join("/proc", entry.Name(), "stat"))
		if readErr != nil {
			continue // the process exited between the listing and the read
		}
		name, start, statErr := parseStat(string(raw))
		if statErr != nil {
			continue
		}
		procs = append(procs, Proc{PID: pid, Name: name, Start: start})
	}
	if len(procs) == 0 {
		return nil, errNoTable
	}
	return procs, nil
}

// parseStat pulls the name and start stamp out of /proc/<pid>/stat.
//
// The name is inside parentheses and may itself contain spaces and parentheses —
// "Antigravity Helper (Renderer)" is a real shape — so the split has to start
// after the LAST ')'. Splitting on spaces first is the classic bug in this
// parser, and it fails on exactly the processes worth watching.
func parseStat(line string) (string, uint64, error) {
	open := strings.IndexByte(line, '(')
	close := strings.LastIndexByte(line, ')')
	if open < 0 || close < open {
		return "", 0, errors.New("no name in stat")
	}
	name := line[open+1 : close]
	rest := strings.Fields(line[close+1:])
	// After the name come state (0) ... starttime (19).
	if len(rest) < 20 {
		return "", 0, errors.New("stat line too short")
	}
	var start uint64
	if _, err := fmt.Sscanf(rest[19], "%d", &start); err != nil {
		return "", 0, errors.New("no start stamp in stat")
	}
	return name, start, nil
}

func parsePID(text string) (int, error) {
	pid := 0
	if _, err := fmt.Sscanf(text, "%d", &pid); err != nil || pid <= 0 {
		return 0, errors.New("not a pid")
	}
	return pid, nil
}

// scanTasklist asks Windows for the process list in CSV form.
//
// Windows does not hand an unprivileged program a start stamp, so `Start` is 0
// here and identity is the PID alone. That is a real limitation and the event
// format says so: a reused PID on Windows is indistinguishable from a running
// process, and the honest consequence is that this sidecar reports a finish only
// when the PID disappears.
func scanTasklist() ([]Proc, error) {
	out, err := exec.Command("tasklist", "/FO", "CSV", "/NH").Output()
	if err != nil {
		return nil, errNoTable
	}
	return parseTasklist(string(out))
}

// parseTasklist reads `tasklist /FO CSV /NH` output:
//
//	"chrome.exe","1234","Console","1","120,000 K"
func parseTasklist(text string) ([]Proc, error) {
	var procs []Proc
	for _, line := range strings.Split(text, "\n") {
		line = strings.TrimRight(line, "\r")
		if !strings.HasPrefix(line, "\"") {
			continue // the "INFO: No tasks are running" line
		}
		fields := strings.Split(line, "\",\"")
		if len(fields) < 2 {
			continue
		}
		name := strings.Trim(strings.TrimSpace(fields[0]), "\"")
		pid, err := parsePID(strings.Trim(strings.TrimSpace(fields[1]), "\""))
		if err != nil {
			continue
		}
		procs = append(procs, Proc{PID: pid, Name: name})
	}
	if len(procs) == 0 {
		return nil, errNoTable
	}
	return procs, nil
}

func scan() ([]Proc, error) {
	if runtime.GOOS == "windows" {
		return scanTasklist()
	}
	return scanLinux()
}

// --- output ---------------------------------------------------------------

// writer appends one JSON object per line and flushes each line, so a reader
// tailing the file sees the finish while it is still news.
type writer struct {
	mu   sync.Mutex
	file *os.File
}

func newWriter(path string) (*writer, error) {
	file, err := os.OpenFile(path, os.O_CREATE|os.O_WRONLY|os.O_APPEND, 0o644)
	if err != nil {
		return nil, err
	}
	return &writer{file: file}, nil
}

func (w *writer) write(events []Event) error {
	if len(events) == 0 {
		return nil
	}
	w.mu.Lock()
	defer w.mu.Unlock()
	for _, event := range events {
		line, err := json.Marshal(event)
		if err != nil {
			return err
		}
		if _, err := w.file.Write(append(line, '\n')); err != nil {
			return err
		}
	}
	return w.file.Sync()
}

func (w *writer) close() { _ = w.file.Close() }

// --- watching -------------------------------------------------------------

// watcher holds the state between sweeps: what was seen, and since when.
type watcher struct {
	patterns  []string
	seen      map[string]Proc
	startedAt map[string]time.Time
}

func newWatcher(patterns []string) *watcher {
	return &watcher{
		patterns:  patterns,
		seen:      map[string]Proc{},
		startedAt: map[string]time.Time{},
	}
}

// step performs one sweep and returns the events it caused. An unreadable table
// returns no events and an error: "I cannot see it" is never "it finished".
func (w *watcher) step(now time.Time) ([]Event, error) {
	procs, err := scan()
	if err != nil {
		return nil, err
	}
	current := make(map[string]Proc, len(procs))
	startedAt := make(map[string]time.Time, len(procs))
	for _, proc := range procs {
		if !matches(proc.Name, w.patterns) {
			continue
		}
		key := proc.key()
		current[key] = proc
		if when, known := w.startedAt[key]; known {
			startedAt[key] = when
		} else {
			startedAt[key] = now
		}
	}
	events := diff(w.seen, current, w.startedAt, now)
	w.seen = current
	w.startedAt = startedAt
	return events, nil
}

// supervise keeps one command alive. It is the only place this program starts a
// process, and it only starts the one it was told to start.
func supervise(command string, restart bool, stop <-chan struct{}) {
	failures := 0
	for {
		select {
		case <-stop:
			return
		default:
		}
		parts := strings.Fields(command)
		if len(parts) == 0 {
			return
		}
		started := time.Now()
		cmd := exec.Command(parts[0], parts[1:]...)
		cmd.Stdout, cmd.Stderr = os.Stdout, os.Stderr
		if err := cmd.Start(); err != nil {
			fmt.Fprintf(os.Stderr, "watchd: cannot start %q: %v\n", command, err)
			failures++
			time.Sleep(backoff(failures))
			continue
		}
		err := cmd.Wait()
		ran := time.Since(started)
		if !restart {
			fmt.Fprintf(os.Stderr, "watchd: %q exited after %s\n", command, ran.Round(time.Second))
			return
		}
		if ran > time.Minute {
			failures = 0 // it had a good run; do not punish the next start
		}
		failures++
		wait := backoff(failures)
		fmt.Fprintf(os.Stderr, "watchd: %q exited after %s (%v); restarting in %s\n",
			command, ran.Round(time.Second), err, wait)
		select {
		case <-stop:
			return
		case <-time.After(wait):
		}
	}
}

func main() {
	opts, err := parseFlags(os.Args[1:])
	if err != nil {
		fmt.Fprintf(os.Stderr, "watchd: %v\n", err)
		os.Exit(2)
	}
	if opts.Version {
		fmt.Printf("watchd %s (%s/%s)\n", version, runtime.GOOS, runtime.GOARCH)
		return
	}

	out, err := newWriter(opts.Events)
	if err != nil {
		fmt.Fprintf(os.Stderr, "watchd: cannot open %s: %v\n", opts.Events, err)
		os.Exit(3)
	}
	defer out.close()

	stop := make(chan struct{})
	signals := make(chan os.Signal, 1)
	signal.Notify(signals, os.Interrupt, syscall.SIGTERM)
	go func() {
		<-signals
		close(stop)
	}()

	if opts.Supervise != "" {
		go supervise(opts.Supervise, opts.Restart, stop)
	}

	state := newWatcher(opts.Watch)
	sweep := func() {
		events, scanErr := state.step(time.Now())
		if scanErr != nil {
			// Report once per sweep at most, and never as a finish.
			fmt.Fprintf(os.Stderr, "watchd: %v\n", scanErr)
		}
		if len(events) > 0 {
			if writeErr := out.write(events); writeErr != nil {
				fmt.Fprintf(os.Stderr, "watchd: cannot write events: %v\n", writeErr)
			}
		}
		if opts.Heartbeat != "" {
			_ = os.WriteFile(opts.Heartbeat,
				[]byte(time.Now().UTC().Format(time.RFC3339)), 0o644)
		}
	}

	sweep()
	if opts.Once {
		return
	}
	ticker := time.NewTicker(opts.Poll)
	defer ticker.Stop()
	for {
		select {
		case <-stop:
			return
		case <-ticker.C:
			sweep()
		}
	}
}
