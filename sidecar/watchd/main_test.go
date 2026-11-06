// Tests for the parts of watchd that can be wrong without crashing.
//
// The parser tests matter most: /proc/<pid>/stat puts the process name inside
// parentheses, and a name such as "Antigravity Helper (Renderer)" breaks the
// obvious implementation. Those are exactly the processes worth watching, so the
// fixture below is the real shape, not a tidy one.

package main

import (
	"os"
	"path/filepath"
	"testing"
	"time"
)

func TestParseStatHandlesParenthesesInTheName(t *testing.T) {
	line := `4242 (Antigravity Helper (Renderer)) S 1 4242 4242 0 -1 4194304 100 0 0 0 5 3 0 0 20 0 8 0 987654 123456789 4321 18446744073709551615`
	name, start, err := parseStat(line)
	if err != nil {
		t.Fatalf("parseStat: %v", err)
	}
	if name != "Antigravity Helper (Renderer)" {
		t.Fatalf("name is %q", name)
	}
	if start != 987654 {
		t.Fatalf("start stamp is %d, want 987654", start)
	}
}

func TestParseStatRejectsAShortLine(t *testing.T) {
	if _, _, err := parseStat("1 (x) S 1 2"); err == nil {
		t.Fatal("a short stat line was accepted")
	}
}

func TestParseTasklist(t *testing.T) {
	text := "\"chrome.exe\",\"1234\",\"Console\",\"1\",\"120,000 K\"\r\n" +
		"\"Antigravity Helper.exe\",\"99\",\"Console\",\"1\",\"80,000 K\"\r\n" +
		"INFO: No tasks are running which match the specified criteria.\r\n"
	procs, err := parseTasklist(text)
	if err != nil {
		t.Fatalf("parseTasklist: %v", err)
	}
	if len(procs) != 2 {
		t.Fatalf("got %d processes", len(procs))
	}
	if procs[1].PID != 99 || procs[1].Name != "Antigravity Helper.exe" {
		t.Fatalf("second process is %+v", procs[1])
	}
}

func TestMatchesIsSubstringAndCaseInsensitive(t *testing.T) {
	if !matches("Antigravity Helper", []string{"antigravity"}) {
		t.Fatal("a matching name was missed")
	}
	if matches("explorer.exe", []string{"antigravity"}) {
		t.Fatal("an unrelated name matched")
	}
	if matches("anything", nil) {
		t.Fatal("an empty pattern list matched")
	}
}

func TestDiffReportsOnlyTheJobThatEnded(t *testing.T) {
	now := time.Now()
	before := map[string]Proc{
		"10:1": {PID: 10, Name: "agent", Start: 1},
		"11:2": {PID: 11, Name: "other", Start: 2},
	}
	current := map[string]Proc{
		"10:1": {PID: 10, Name: "agent", Start: 1},
	}
	started := map[string]time.Time{}
	events := diff(before, current, started, now)
	if len(events) != 1 || events[0].PID != 11 {
		t.Fatalf("events are %+v", events)
	}
	if events[0].How != "ended" {
		t.Fatalf("how is %q; an unowned process must not claim success", events[0].How)
	}
}

func TestDiffTreatsAReusedPIDAsANewProcess(t *testing.T) {
	// The same PID, a different start stamp: the old process ended.
	before := map[string]Proc{"10:1": {PID: 10, Name: "agent", Start: 1}}
	now := map[string]Proc{"10:9": {PID: 10, Name: "agent", Start: 9}}
	events := diff(before, now, map[string]time.Time{}, time.Now())
	if len(events) != 1 {
		t.Fatalf("a reused pid was not reported as a finish: %+v", events)
	}
}

func TestBackoffDoublesAndStops(t *testing.T) {
	if backoff(0) != 0 {
		t.Fatal("no failures should mean no wait")
	}
	if backoff(1) != 500*time.Millisecond {
		t.Fatalf("first backoff is %s", backoff(1))
	}
	if backoff(3) != 2*time.Second {
		t.Fatalf("third backoff is %s", backoff(3))
	}
	if backoff(99) != 30*time.Second {
		t.Fatalf("the ceiling is %s", backoff(99))
	}
}

func TestParseFlagsNeedsSomethingToDo(t *testing.T) {
	if _, err := parseFlags([]string{}); err == nil {
		t.Fatal("an empty run was accepted")
	}
	opts, err := parseFlags([]string{"-watch", " Antigravity , cursor ", "-poll", "500ms"})
	if err != nil {
		t.Fatalf("parseFlags: %v", err)
	}
	if len(opts.Watch) != 2 || opts.Watch[0] != "antigravity" || opts.Watch[1] != "cursor" {
		t.Fatalf("watch list is %v", opts.Watch)
	}
	if _, err := parseFlags([]string{"-watch", "x", "-poll", "1ms"}); err == nil {
		t.Fatal("a 1ms poll was accepted; it would spin")
	}
}

func TestParseFlagsIsRepeatable(t *testing.T) {
	// The first version of this used the global flag set, which can only be
	// parsed once, so the second call silently reused the first call's values.
	for i := 0; i < 3; i++ {
		if _, err := parseFlags([]string{"-watch", "antigravity"}); err != nil {
			t.Fatalf("call %d: %v", i, err)
		}
	}
}

func TestStepWritesAnEventWhenAProcessDisappears(t *testing.T) {
	if testing.Short() {
		t.Skip("needs a real process table")
	}
	state := newWatcher(nil) // no patterns: every process is a candidate
	if _, err := state.step(time.Now()); err != nil {
		t.Skipf("no process table here: %v", err)
	}
	if len(state.seen) == 0 {
		t.Skip("the table came back empty")
	}
	// Removing every entry is the same shape as every job finishing at once.
	state.seen = map[string]Proc{
		"999999:1": {PID: 999999, Name: "a job that is not running", Start: 1},
	}
	state.startedAt = map[string]time.Time{"999999:1": time.Now().Add(-2 * time.Second)}
	events, err := state.step(time.Now())
	if err != nil {
		t.Fatalf("step: %v", err)
	}
	found := false
	for _, event := range events {
		if event.PID == 999999 {
			found = true
			if event.Seconds < 1.0 {
				t.Fatalf("duration is %.2fs", event.Seconds)
			}
		}
	}
	if !found {
		t.Fatal("a vanished process produced no event")
	}
}

func TestWriterAppendsJSONLines(t *testing.T) {
	dir := t.TempDir()
	path := filepath.Join(dir, "events.jsonl")
	out, err := newWriter(path)
	if err != nil {
		t.Fatalf("newWriter: %v", err)
	}
	if err := out.write([]Event{{PID: 1, Name: "a", How: "ended"}}); err != nil {
		t.Fatalf("write: %v", err)
	}
	out.close()
	if err := out.write([]Event{{PID: 2, Name: "b", How: "ended"}}); err == nil {
		t.Fatal("writing after close reported success")
	}
	data, err := os.ReadFile(path)
	if err != nil {
		t.Fatalf("read: %v", err)
	}
	if len(data) == 0 || data[len(data)-1] != '\n' {
		t.Fatalf("the line was not terminated: %q", data)
	}
}
