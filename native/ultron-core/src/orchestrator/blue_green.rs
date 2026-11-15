use tokio::sync::Mutex;
use std::sync::Arc;
use std::time::Instant;
use crate::state::arena::StateArena;
use anyhow::{Result, ensure};

#[derive(Debug, Clone, PartialEq)]
pub enum WorkerColor {
    Blue,
    Green,
}

#[derive(Debug, Clone)]
pub struct WorkerSlot {
    pub pid: u32,
    pub color: WorkerColor,
    pub healthy: bool,
    pub joined_at: Instant,
}

pub struct BlueGreenOrchestrator {
    pub arena: Arc<StateArena>,
    pub active_worker: Arc<Mutex<Option<WorkerSlot>>>,
    pub standby_worker: Arc<Mutex<Option<WorkerSlot>>>,
    pub active_color: Arc<Mutex<WorkerColor>>,
}

impl BlueGreenOrchestrator {
    pub fn new(arena: Arc<StateArena>) -> Self {
        Self {
            arena,
            active_worker: Arc::new(Mutex::new(None)),
            standby_worker: Arc::new(Mutex::new(None)),
            active_color: Arc::new(Mutex::new(WorkerColor::Blue)),
        }
    }

    /// Register a newly booted worker into active or standby slot
    pub async fn register_worker(&self, pid: u32, color: WorkerColor) {
        let slot = WorkerSlot {
            pid,
            color: color.clone(),
            healthy: true,
            joined_at: Instant::now(),
        };

        let mut active = self.active_worker.lock().await;
        if active.is_none() {
            tracing::info!("[Orchestrator] Worker PID {} assigned as ACTIVE ({:?})", pid, color);
            *active = Some(slot);
            *self.active_color.lock().await = color;
        } else {
            tracing::info!("[Orchestrator] Worker PID {} assigned as STANDBY ({:?})", pid, color);
            *self.standby_worker.lock().await = Some(slot);
        }
    }

    /// Execute atomic cutover: promotes standby worker to active in < 5ms window
    pub async fn execute_cutover(&self) -> Result<(u32, u32)> {
        let mut active = self.active_worker.lock().await;
        let mut standby = self.standby_worker.lock().await;

        ensure!(standby.is_some(), "No standby candidate worker available for cutover");
        let old_active = active.take().unwrap();
        let new_active = standby.take().unwrap();

        let cutover_start = Instant::now();
        *self.active_color.lock().await = new_active.color.clone();
        let old_pid = old_active.pid;
        let new_pid = new_active.pid;

        *active = Some(new_active);
        let elapsed = cutover_start.elapsed();
        tracing::info!(
            "[Orchestrator] CUTOVER COMPLETE: PID {} -> PID {} in {:?}",
            old_pid,
            new_pid,
            elapsed
        );

        Ok((old_pid, new_pid))
    }
}
