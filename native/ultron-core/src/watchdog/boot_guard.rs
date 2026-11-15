use tokio::time::{Duration, Instant};
use std::collections::VecDeque;

pub const HEARTBEAT_INTERVAL: Duration = Duration::from_secs(5);
pub const HEARTBEAT_TIMEOUT: Duration = Duration::from_secs(30);
pub const BOOT_LOOP_WINDOW: Duration = Duration::from_secs(90);
pub const BOOT_LOOP_THRESHOLD: usize = 3;

#[derive(Debug, Clone)]
pub struct CrashRecord {
    pub timestamp: Instant,
    pub exit_code: Option<i32>,
    pub uptime_s: u64,
}

pub struct BootLoopGuard {
    crash_history: VecDeque<CrashRecord>,
}

impl BootLoopGuard {
    pub fn new() -> Self {
        Self {
            crash_history: VecDeque::with_capacity(BOOT_LOOP_THRESHOLD + 1),
        }
    }

    pub fn record_crash(&mut self, record: CrashRecord) {
        self.crash_history.push_back(record);
        while self.crash_history.len() > BOOT_LOOP_THRESHOLD + 2 {
            self.crash_history.pop_front();
        }
    }

    /// Evaluates if 3 or more crashes occurred within the rolling 90-second window
    pub fn is_boot_loop(&self) -> bool {
        let now = Instant::now();
        let recent_count = self
            .crash_history
            .iter()
            .filter(|r| now.duration_since(r.timestamp) <= BOOT_LOOP_WINDOW)
            .count();
        recent_count >= BOOT_LOOP_THRESHOLD
    }

    pub fn clear(&mut self) {
        self.crash_history.clear();
    }
}
