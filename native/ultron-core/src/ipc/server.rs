use std::sync::{Arc, Mutex};
use std::time::{Duration, Instant};

use anyhow::{bail, ensure, Context, Result};
use tokio::io::{AsyncReadExt, AsyncWriteExt};
use tokio::net::windows::named_pipe::{NamedPipeServer, ServerOptions};

use crate::watchdog::{Note, StallWatch, HEARTBEAT_TIMEOUT};

pub const PIPE_NAME: &str = r"\\.\pipe\ultron-core";
pub const MAGIC: u8 = 0xA1;
pub const HEADER_LEN: usize = 6;
/// Largest frame body this server will allocate for (`core/ipc_client.py` has the same
/// number as `MAX_PAYLOAD`). The length field is a `u32`: without this check a corrupt or
/// hostile header makes `vec![0u8; payload_len]` ask for up to 4 GiB before one byte of
/// the body has been read, and the supervisor, which is meant to outlive a crashed
/// worker, is the process that dies.
pub const MAX_PAYLOAD_LEN: usize = 1 << 20;

const CHANNEL_HEARTBEAT: u8 = 0x06;
const CHANNEL_SHUTDOWN: u8 = 0xFF;
/// A heartbeat is a `u64` time in milliseconds and then a `u32` sequence number
/// (`send_heartbeat` in `core/ipc_client.py`).
const HEARTBEAT_LEN: usize = 12;

/// How the server runs.
#[derive(Debug, Clone)]
pub struct Options {
    /// Silence from Ultron that is worth a line in the log.
    pub stall_after: Duration,
    /// Serve the first session and then end, instead of waiting for the next one. Ultron starts the
    /// helper this way, so that the helper does not outlive it.
    pub once: bool,
    /// With `once`: how long to wait for Ultron to connect before ending.
    pub wait_for_first: Duration,
}

impl Default for Options {
    fn default() -> Self {
        Self { stall_after: HEARTBEAT_TIMEOUT, once: false, wait_for_first: Duration::from_secs(120) }
    }
}

impl Options {
    /// The helper's whole command line. Ultron starts it with `--once --wait-seconds=120 --stall-seconds=30`.
    /// By hand, with none of them, it serves one session after another until it is stopped.
    pub fn from_arguments<I: IntoIterator<Item = String>>(arguments: I) -> Result<Self> {
        let mut options = Self::default();
        for argument in arguments {
            if argument == "--once" {
                options.once = true;
            } else if let Some(value) = argument.strip_prefix("--stall-seconds=") {
                options.stall_after = seconds(value)?;
            } else if let Some(value) = argument.strip_prefix("--wait-seconds=") {
                options.wait_for_first = seconds(value)?;
            } else {
                bail!("unknown argument {argument:?}: the options are --once, --stall-seconds=N and --wait-seconds=N");
            }
        }
        Ok(options)
    }
}

fn seconds(text: &str) -> Result<Duration> {
    let value: f64 = text.parse().with_context(|| format!("{text:?} is not a number of seconds"))?;
    ensure!(
        value.is_finite() && value > 0.0 && value <= 86_400.0,
        "seconds must be above 0 and at most a day, not {value}"
    );
    Ok(Duration::from_secs_f64(value))
}

pub async fn start_ipc_server(options: Options) -> Result<()> {
    tracing::info!("[IPC] Initializing Named Pipe server on {}", PIPE_NAME);
    let mut is_first = true;

    loop {
        let server = ServerOptions::new()
            .first_pipe_instance(is_first)
            .create(PIPE_NAME)?;
        is_first = false;

        tracing::info!("[IPC] Waiting for connection from Python agent...");
        if options.once {
            match tokio::time::timeout(options.wait_for_first, server.connect()).await {
                Ok(connected) => connected?,
                Err(_) => {
                    tracing::info!("[IPC] Nobody connected within {:?}; ending.", options.wait_for_first);
                    return Ok(());
                }
            }
        } else {
            server.connect().await?;
        }
        tracing::info!("[IPC] Connection established.");

        if options.once {
            if let Err(e) = handle_client(server, options.stall_after).await {
                tracing::warn!("[IPC] Session ended: {}", e);
            }
            tracing::info!("[IPC] The one session is over, so the helper ends too.");
            return Ok(());
        }

        let stall_after = options.stall_after;
        tokio::spawn(async move {
            if let Err(e) = handle_client(server, stall_after).await {
                tracing::warn!("[IPC] Session ended: {}", e);
            }
        });
    }
}

async fn handle_client(mut pipe: NamedPipeServer, stall_after: Duration) -> Result<()> {
    let watch = Arc::new(Mutex::new(StallWatch::new(stall_after, Instant::now())));
    let silence = tokio::spawn(note_silence(Arc::clone(&watch), stall_after));
    let outcome = read_frames(&mut pipe, &watch).await;
    silence.abort();
    outcome
}

/// Looks at the clock a few times in a limit, and writes one line when Ultron has been silent for the limit.
/// It only writes: nothing is restarted, and nothing is ended.
async fn note_silence(watch: Arc<Mutex<StallWatch>>, stall_after: Duration) {
    let every = (stall_after / 10).clamp(Duration::from_millis(50), Duration::from_secs(1));
    let mut ticker = tokio::time::interval(every);
    loop {
        ticker.tick().await;
        let note = watch.lock().unwrap_or_else(|poisoned| poisoned.into_inner()).tick(Instant::now());
        if let Some(Note::Stalled { silent_for, last_seq }) = note {
            tracing::warn!(
                "[Watch] STALL: no heartbeat from Ultron for {:.0} s (the last one was number {}). It may be frozen. Nothing is restarted.",
                silent_for.as_secs_f64(),
                number(last_seq)
            );
        }
    }
}

fn number(seq: Option<u32>) -> String {
    match seq {
        Some(n) => n.to_string(),
        None => "none".to_string(),
    }
}

async fn read_frames(pipe: &mut NamedPipeServer, watch: &Arc<Mutex<StallWatch>>) -> Result<()> {
    let mut header = [0u8; HEADER_LEN];

    loop {
        pipe.read_exact(&mut header).await?;
        ensure!(
            header[0] == MAGIC,
            "Protocol magic mismatch: expected 0xA1, got 0x{:02X}",
            header[0]
        );

        let channel_id = header[1];
        let payload_len = u32::from_le_bytes(header[2..6].try_into()?) as usize;
        ensure!(
            payload_len <= MAX_PAYLOAD_LEN,
            "Frame too large: {} bytes (limit {})",
            payload_len,
            MAX_PAYLOAD_LEN
        );

        let mut payload = vec![0u8; payload_len];
        pipe.read_exact(&mut payload).await?;

        match channel_id {
            CHANNEL_HEARTBEAT => {
                let seq = (payload.len() >= HEARTBEAT_LEN)
                    .then(|| u32::from_le_bytes([payload[8], payload[9], payload[10], payload[11]]));
                let note = watch.lock().unwrap_or_else(|poisoned| poisoned.into_inner()).beat(Instant::now(), seq);
                if let Some(Note::Recovered { silent_for }) = note {
                    tracing::warn!(
                        "[Watch] RECOVERED: heartbeats from Ultron are back after {:.0} s of silence.",
                        silent_for.as_secs_f64()
                    );
                }
                // Heartbeat echo back
                pipe.write_all(&header).await?;
                pipe.write_all(&payload).await?;
            }
            CHANNEL_SHUTDOWN => {
                tracing::info!("[IPC] Graceful shutdown received from Python agent.");
                break;
            }
            _ => {
                tracing::debug!("[IPC] Received channel 0x{:02X} ({} bytes)", channel_id, payload_len);
            }
        }
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    fn arguments(list: &[&str]) -> Vec<String> {
        list.iter().map(|text| text.to_string()).collect()
    }

    #[test]
    fn no_arguments_is_the_long_lived_supervisor_with_the_default_limit() {
        let options = Options::from_arguments(arguments(&[])).unwrap();
        assert!(!options.once);
        assert_eq!(options.stall_after, HEARTBEAT_TIMEOUT);
        assert_eq!(options.wait_for_first, Duration::from_secs(120));
    }

    #[test]
    fn the_three_options_ultron_passes_are_read() {
        let options =
            Options::from_arguments(arguments(&["--once", "--wait-seconds=120", "--stall-seconds=2.5"])).unwrap();
        assert!(options.once);
        assert_eq!(options.wait_for_first, Duration::from_secs(120));
        assert_eq!(options.stall_after, Duration::from_millis(2500));
    }

    #[test]
    fn anything_else_is_refused_and_says_what_is_accepted() {
        let error = Options::from_arguments(arguments(&["--restart"])).unwrap_err().to_string();
        assert!(error.contains("--once") && error.contains("--stall-seconds"), "{error}");
    }

    #[test]
    fn seconds_must_be_a_sensible_number() {
        for bad in ["--stall-seconds=abc", "--stall-seconds=0", "--stall-seconds=-3", "--wait-seconds=90000", "--wait-seconds=NaN"] {
            assert!(Options::from_arguments(arguments(&[bad])).is_err(), "{bad} should be refused");
        }
    }
}
