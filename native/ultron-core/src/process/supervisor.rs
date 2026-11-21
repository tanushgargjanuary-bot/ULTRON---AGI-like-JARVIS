// NOT COMPILED, NOT RUN. This file was last changed by reading the Win32 documentation, on a
// machine with no Rust toolchain and no Windows, and CI does not build this crate. Nothing in
// `main.rs` calls it. Run `cargo check` on Windows, then start a process under it and read the
// limits back with `QueryInformationJobObject` before trusting any of them.

use windows::Win32::System::JobObjects::*;
use windows::Win32::Foundation::*;
use windows::core::PCWSTR;
use anyhow::Result;

/// A Windows Job Object that limits the processes attached to it.
///
/// The handle is owned by this value: `Drop` closes it, and `new_restricted` makes the value
/// before it makes anything that can fail, so an error part way through cannot leak it.
pub struct SandboxJob {
    handle: HANDLE,
}

impl SandboxJob {
    /// A job that limits what is attached to it to `max_memory_bytes` of committed memory in all,
    /// `cpu_time_seconds` of user-mode CPU time in all, and four processes at once.
    ///
    /// All three limits go in ONE `SetInformationJobObject` call. `LimitFlags` is the list of
    /// limits in force, so a second call whose flags name only the memory limit asks for the
    /// other two to be off; this file used to make exactly that second call.
    ///
    /// The flags and the fields they read go together, and only these three pairs are used:
    ///
    ///   JOB_OBJECT_LIMIT_JOB_TIME       PerJobUserTimeLimit   100-nanosecond ticks, all processes together
    ///   JOB_OBJECT_LIMIT_ACTIVE_PROCESS ActiveProcessLimit    processes alive at once
    ///   JOB_OBJECT_LIMIT_JOB_MEMORY     JobMemoryLimit        bytes committed, all processes together
    ///
    /// `JOB_OBJECT_LIMIT_PROCESS_TIME` is deliberately NOT set. It means "each process has its own
    /// user-mode time limit, read from `PerProcessUserTimeLimit`", and that field stays 0 here, so
    /// with the flag set every process would have a CPU allowance of zero and be ended at the
    /// first check. An earlier note in this file said to set all of the flags together; that was
    /// wrong for this flag.
    ///
    /// Not set: `JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE`, so dropping this value does not end the
    /// processes, and the job and its limits outlive the handle until they exit. Breakaway is not
    /// enabled either (no `JOB_OBJECT_LIMIT_BREAKAWAY_OK`), which is the default and the safer one.
    pub fn new_restricted(max_memory_bytes: usize, cpu_time_seconds: u32) -> Result<Self> {
        // SAFETY: every pointer handed to the system below points at a local that lives to the end
        // of this block, and the length passed with it is the size of exactly that local.
        unsafe {
            let handle = CreateJobObjectW(None, PCWSTR::null())?;
            // From here on `job` owns the handle, so `?` on any later line closes it.
            let job = Self { handle };

            let mut limits = JOBOBJECT_EXTENDED_LIMIT_INFORMATION::default();
            limits.BasicLimitInformation.LimitFlags = JOB_OBJECT_LIMIT_JOB_TIME
                | JOB_OBJECT_LIMIT_ACTIVE_PROCESS
                | JOB_OBJECT_LIMIT_JOB_MEMORY;
            limits.BasicLimitInformation.PerJobUserTimeLimit = i64::from(cpu_time_seconds) * 10_000_000;
            limits.BasicLimitInformation.ActiveProcessLimit = 4;
            limits.JobMemoryLimit = max_memory_bytes;

            SetInformationJobObject(
                job.handle,
                JobObjectExtendedLimitInformation,
                &limits as *const _ as _,
                std::mem::size_of_val(&limits) as u32,
            )?;

            Ok(job)
        }
    }

    /// Put the process with this id under the job's limits.
    pub fn attach_process(&self, pid: u32) -> Result<()> {
        // SAFETY: `self.handle` is a job handle this value owns and has not closed. `process` is
        // a handle this block opens and closes itself, on every path out of it.
        unsafe {
            use windows::Win32::System::Threading::{OpenProcess, PROCESS_SET_QUOTA, PROCESS_TERMINATE};
            // The two rights `AssignProcessToJobObject` documents as required, and nothing more.
            // `PROCESS_ALL_ACCESS` was asked for here, which also lets the handle read and write
            // the process's memory and create threads in it.
            let process = OpenProcess(PROCESS_SET_QUOTA | PROCESS_TERMINATE, false, pid)?;
            let assigned = AssignProcessToJobObject(self.handle, process);
            // Closed whether or not the assignment worked. `AssignProcessToJobObject(...)?` on one
            // line would return before this and leak the handle.
            let _ = CloseHandle(process);
            assigned?;
        }
        Ok(())
    }
}

impl Drop for SandboxJob {
    fn drop(&mut self) {
        // SAFETY: the handle was made by `CreateJobObjectW` and is closed here and nowhere else.
        // A failed close is ignored: there is nothing a destructor could do about it.
        unsafe {
            let _ = CloseHandle(self.handle);
        }
    }
}
