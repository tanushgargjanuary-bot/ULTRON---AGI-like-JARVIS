# Freeze watch

Ultron can freeze. A frozen program cannot tell you that it froze. So a second small program, **the helper**, watches from
outside. When Ultron stops answering, the helper writes a line in its log.

The freeze watch is **off until you switch it on**. It restarts nothing and ends nothing. It only notes.

Added 2026-11-27. You chose it ("watch Ultron and note when it freezes, no restarts") as the first job for the Rust helper.

## What happens

1. Ultron starts the helper when Ultron starts.
2. Every 5 seconds Ultron sends the helper a small message, a **heartbeat**.
3. A heartbeat is sent only while two things answer: the assistant's own loop, and the window. The window counts as silent
   when it has not run its one-second timer for more than 10 seconds.
4. If no heartbeat arrives for 30 seconds, the helper writes a line that contains `[Watch] STALL`. When heartbeats come
   back, it writes `[Watch] RECOVERED` and says how long the silence lasted.
5. The next time Ultron starts with the watch on, it reads that log. If the last run it watched had a freeze, one line in
   the activity log tells you. A run with the watch off is not in the log and is skipped.
6. When Ultron closes, the helper ends too. If Ultron never connects, the helper ends by itself after 120 seconds.

Example, as it appears in `logs/child-ultron-core.log`:

```
--- 2026-11-27 20:10:03 ultron-core started ---
2026-11-27T20:10:03.412Z  INFO ultron_core::ipc::server: [IPC] Connection established.
2026-11-27T20:31:08.118Z  WARN ultron_core::ipc::server: [Watch] STALL: no heartbeat from Ultron for 30 s (the last one was number 252). It may be frozen. Nothing is restarted.
2026-11-27T20:31:55.903Z  WARN ultron_core::ipc::server: [Watch] RECOVERED: heartbeats from Ultron are back after 77 s of silence.
```

## What it does not do

- It restarts nothing and ends nothing. A frozen Ultron stays frozen until you close it.
- It cannot warn you while Ultron is frozen. Nobody is awake to show you. You read the note afterwards.
- It cannot say which part froze. A heartbeat stops when the window thread hangs, when the assistant's loop hangs, and
  when the whole program hangs. The log line is the same for all three. Ultron also keeps a short note in memory when the
  window was the one (`heartbeat.lost`, "the window has not answered"). The window does not show it; a crash report includes it.
- It does not watch the helper itself. If the helper cannot start, Ultron says so in the activity log.
- A false alarm may appear after the PC wakes from sleep, because the helper's clock may count the sleep. Not verified.

## Switch it on

1. Get the helper program. It is not in the repository. There are two ways:
   - Download `ultron-core-windows-x64` from the latest "native build" run on GitHub (Actions, then the run, then
     Artifacts). It is kept for 14 days. It is not signed, so Windows may ask you to confirm before it runs it.
   - Or build it: install Rust, then run `cargo build --release` in the folder `native/ultron-core`.
2. Put it at `native\ultron-core\target\release\ultron-core.exe`. Or set the environment variable `ULTRON_NATIVE_CORE` to
   the full path of the file.
3. In Ultron, open the CONTROLS drawer and press **FREEZE WATCH**. That saves `native_watch_enabled` as `true` in
   `config/api_keys.json`. It takes effect the next time Ultron starts. The button says so.

Without the program, switching it on does nothing except print a line that says where the program should be.

## Switch it off

Press the same button. Or set `native_watch_enabled` to `false`, or delete the key. The helper then does not start.
The helper also ends when you close Ultron.

To remove the whole feature, revert the pull request that added it (the CHANGELOG entry for 2026-11-27 names it).

## What is tested, and what is not

Tested on every change (`tests/test_native_watch.py`, `tests/test_hybrid_ipc.py`, and the Rust tests in
`native/ultron-core/src/watchdog/stall.rs` and `native/ultron-core/src/ipc/server.rs`):

- The switch is off on a new install, and only a saved `true` turns it on.
- The clock: no note below the limit, one note at the limit, one more when the beats return, and a second silence is noted again.
- The real helper program, started on Windows by the `native build` check: a silent client is noted once and is not
  disconnected, the helper ends with its session, a helper nobody connects to ends by itself, and an unknown option is refused.
- The window gives the pulse, the button saves the switch and says when it takes effect, and a failed save is said.
- A beat is held back while the window is silent and sent again when it answers.

Not tested: a real frozen window on a real PC. The pieces are proven one by one, and the whole chain has not been seen on
your machine. The first time a note appears is the first real proof. Tell us what the log says.
