//! The clock that notices a silent Ultron. It only notes: nothing in this file starts, stops or ends a process.

use std::time::{Duration, Instant};

/// What the helper says about Ultron's heartbeats.
#[derive(Debug, Clone, PartialEq)]
pub enum Note {
    /// No heartbeat for `silent_for`, which has just reached the limit. Said once for each silence.
    Stalled { silent_for: Duration, last_seq: Option<u32> },
    /// A heartbeat came after a stall that had been noted. `silent_for` is the whole silence.
    Recovered { silent_for: Duration },
}

/// Keeps the time of the last heartbeat, and whether the silence in progress has already been noted.
///
/// It is given the time instead of reading a clock, so a test can run a minute of silence in no time.
#[derive(Debug)]
pub struct StallWatch {
    limit: Duration,
    last_beat: Instant,
    last_seq: Option<u32>,
    noted: bool,
}

impl StallWatch {
    /// A session that starts at `now`. A session that never sends a heartbeat is a silence like any other.
    pub fn new(limit: Duration, now: Instant) -> Self {
        Self { limit, last_beat: now, last_seq: None, noted: false }
    }

    /// A heartbeat arrived. Returns `Recovered` when the silence it ends had been noted as a stall.
    pub fn beat(&mut self, now: Instant, seq: Option<u32>) -> Option<Note> {
        let silent_for = now.saturating_duration_since(self.last_beat);
        self.last_beat = now;
        self.last_seq = seq.or(self.last_seq);
        if self.noted {
            self.noted = false;
            Some(Note::Recovered { silent_for })
        } else {
            None
        }
    }

    /// Time has passed. Returns `Stalled` the first time the silence reaches the limit, and nothing after
    /// that until a heartbeat has come and the silence has begun again.
    pub fn tick(&mut self, now: Instant) -> Option<Note> {
        let silent_for = now.saturating_duration_since(self.last_beat);
        if silent_for >= self.limit && !self.noted {
            self.noted = true;
            Some(Note::Stalled { silent_for, last_seq: self.last_seq })
        } else {
            None
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn secs(n: u64) -> Duration {
        Duration::from_secs(n)
    }

    #[test]
    fn silence_below_the_limit_is_not_a_stall() {
        let start = Instant::now();
        let mut watch = StallWatch::new(secs(30), start);
        assert_eq!(watch.tick(start + secs(29)), None);
    }

    #[test]
    fn silence_that_reaches_the_limit_is_noted_once_with_the_last_number() {
        let start = Instant::now();
        let mut watch = StallWatch::new(secs(30), start);
        assert_eq!(watch.beat(start + secs(5), Some(7)), None);
        assert_eq!(
            watch.tick(start + secs(36)),
            Some(Note::Stalled { silent_for: secs(31), last_seq: Some(7) })
        );
        assert_eq!(watch.tick(start + secs(40)), None, "said once for each silence");
        assert_eq!(watch.tick(start + secs(400)), None);
    }

    #[test]
    fn a_session_that_never_beats_is_a_stall_too_and_has_no_number() {
        let start = Instant::now();
        let mut watch = StallWatch::new(secs(30), start);
        assert_eq!(
            watch.tick(start + secs(30)),
            Some(Note::Stalled { silent_for: secs(30), last_seq: None })
        );
    }

    #[test]
    fn a_heartbeat_after_a_noted_stall_says_how_long_it_lasted() {
        let start = Instant::now();
        let mut watch = StallWatch::new(secs(30), start);
        watch.beat(start + secs(1), Some(1));
        assert!(watch.tick(start + secs(31)).is_some());
        assert_eq!(
            watch.beat(start + secs(48), Some(2)),
            Some(Note::Recovered { silent_for: secs(47) })
        );
    }

    #[test]
    fn a_late_heartbeat_that_was_never_noted_is_not_news() {
        let start = Instant::now();
        let mut watch = StallWatch::new(secs(30), start);
        assert_eq!(watch.beat(start + secs(20), Some(1)), None);
        assert_eq!(watch.beat(start + secs(25), Some(2)), None);
    }

    #[test]
    fn a_second_silence_is_noted_again() {
        let start = Instant::now();
        let mut watch = StallWatch::new(secs(30), start);
        assert!(watch.tick(start + secs(30)).is_some());
        assert!(watch.beat(start + secs(35), Some(1)).is_some());
        assert_eq!(watch.tick(start + secs(60)), None, "the clock restarted at the heartbeat");
        assert!(watch.tick(start + secs(65)).is_some());
    }

    #[test]
    fn a_heartbeat_without_a_number_keeps_the_last_one() {
        let start = Instant::now();
        let mut watch = StallWatch::new(secs(10), start);
        watch.beat(start + secs(1), Some(9));
        watch.beat(start + secs(2), None);
        assert_eq!(
            watch.tick(start + secs(12)),
            Some(Note::Stalled { silent_for: secs(10), last_seq: Some(9) })
        );
    }
}
