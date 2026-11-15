use windows::Win32::System::JobObjects::*;
use windows::Win32::Foundation::*;
use windows::core::PCWSTR;
use anyhow::Result;

pub struct SandboxJob {
    handle: HANDLE,
}

impl SandboxJob {
    pub fn new_restricted(max_memory_bytes: usize, cpu_time_seconds: u32) -> Result<Self> {
        unsafe {
            let handle = CreateJobObjectW(None, PCWSTR::null())?;

            let mut limit_info = JOBOBJECT_BASIC_LIMIT_INFORMATION::default();
            limit_info.LimitFlags = JOB_OBJECT_LIMIT_PROCESS_TIME
                | JOB_OBJECT_LIMIT_JOB_TIME
                | JOB_OBJECT_LIMIT_ACTIVE_PROCESS;
            limit_info.PerJobUserTimeLimit = (cpu_time_seconds as i64) * 10_000_000;
            limit_info.ActiveProcessLimit = 4;

            SetInformationJobObject(
                handle,
                JobObjectBasicLimitInformation,
                &limit_info as *const _ as _,
                std::mem::size_of_val(&limit_info) as u32,
            )?;

            let mut ext_limit = JOBOBJECT_EXTENDED_LIMIT_INFORMATION::default();
            ext_limit.BasicLimitInformation.LimitFlags |= JOB_OBJECT_LIMIT_JOB_MEMORY;
            ext_limit.JobMemoryLimit = max_memory_bytes;

            SetInformationJobObject(
                handle,
                JobObjectExtendedLimitInformation,
                &ext_limit as *const _ as _,
                std::mem::size_of_val(&ext_limit) as u32,
            )?;

            Ok(Self { handle })
        }
    }

    pub fn attach_process(&self, pid: u32) -> Result<()> {
        unsafe {
            use windows::Win32::System::Threading::{OpenProcess, PROCESS_ALL_ACCESS};
            let proc = OpenProcess(PROCESS_ALL_ACCESS, false, pid)?;
            AssignProcessToJobObject(self.handle, proc)?;
            let _ = CloseHandle(proc);
        }
        Ok(())
    }
}

impl Drop for SandboxJob {
    fn drop(&mut self) {
        unsafe {
            let _ = CloseHandle(self.handle);
        }
    }
}
