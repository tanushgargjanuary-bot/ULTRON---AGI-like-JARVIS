use tokio::sync::Mutex;
use std::sync::Arc;
use std::time::Instant;
use crate::state::arena::StateArena;
use anyhow::{Result, ensure, anyhow};
use windows::Win32::System::Threading::*;
use windows::Win32::Foundation::*;

#[derive(Debug, Clone, PartialEq)]
pub enum WorkerColor {
    Blue,
    Green,
}

pub struct WorkerSlot {
    pub pid: u32,
    pub color: WorkerColor,
    pub healthy: bool,
    pub joined_at: Instant,
    pub handle_raw: Option<isize>,
}

unsafe impl Send for WorkerSlot {}
unsafe impl Sync for WorkerSlot {}

impl Drop for WorkerSlot {
    fn drop(&mut self) {
        if let Some(raw) = self.handle_raw.take() {
            unsafe {
                let h = HANDLE(raw as *mut _);
                if !h.is_invalid() {
                    let _ = CloseHandle(h);
                }
            }
        }
    }
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

    /// Register a newly booted worker into active or standby slot with owned OS handle
    pub async fn register_worker(&self, pid: u32, color: WorkerColor) {
        let handle_raw = unsafe {
            OpenProcess(
                PROCESS_SYNCHRONIZE | PROCESS_TERMINATE,
                false,
                pid,
            ).ok().map(|h| h.0 as isize)
        };

        let slot = WorkerSlot {
            pid,
            color: color.clone(),
            healthy: true,
            joined_at: Instant::now(),
            handle_raw,
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

    /// Execute atomic cutover: promotes standby worker to active and gracefully retires old worker
    pub async fn execute_cutover(&self) -> Result<(u32, u32)> {
        let mut active = self.active_worker.lock().await;
        let mut standby = self.standby_worker.lock().await;

        ensure!(standby.is_some(), "No standby candidate worker available for cutover");
        let mut old_active = active.take().ok_or_else(|| anyhow!("No active worker currently assigned"))?;
        let new_active = standby.take().ok_or_else(|| anyhow!("Standby worker disappeared during cutover"))?;

        let cutover_start = Instant::now();
        *self.active_color.lock().await = new_active.color.clone();
        let old_pid = old_active.pid;
        let new_pid = new_active.pid;

        // Take the raw handle so WorkerSlot Drop doesn't close it prematurely
        let raw_opt = old_active.handle_raw.take();

        // Gracefully drain and terminate the retired worker to prevent zombie process leaks
        if let Some(raw) = raw_opt {
            tokio::spawn(async move {
                tracing::info!("[Orchestrator] Retiring old worker PID {} with 3s grace period", old_pid);
                tokio::time::sleep(tokio::time::Duration::from_millis(3000)).await;
                unsafe {
                    let h = HANDLE(raw as *mut _);
                    let _ = TerminateProcess(h, 0);
                    let _ = CloseHandle(h);
                }
                tracing::info!("[Orchestrator] Retired worker PID {} cleanly terminated", old_pid);
            });
        }

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
