use windows::Win32::System::Memory::*;
use windows::Win32::Foundation::*;
use windows::core::PCWSTR;
use std::sync::atomic::{AtomicU64, Ordering};
use anyhow::{Result, ensure};

pub const RING_NAME: &str = "Local\\UltronAudioRing";
pub const FRAME_SAMPLES: usize = 320; // 20ms @ 16kHz
pub const CAPACITY_FRAMES: usize = 100; // 2-second buffer

#[repr(C, align(64))]
pub struct RingHeader {
    pub write_cursor: AtomicU64,
    pub read_cursor: AtomicU64,
    pub sample_rate: u32,
    pub channels: u8,
    pub frame_samples: u16,
    _pad: [u8; 46],
}

pub struct SharedAudioRing {
    handle: HANDLE,
    view: *mut u8,
}

unsafe impl Send for SharedAudioRing {}
unsafe impl Sync for SharedAudioRing {}

impl SharedAudioRing {
    pub fn create() -> Result<Self> {
        let frame_bytes = FRAME_SAMPLES * std::mem::size_of::<f32>();
        let total_bytes = 64 + (CAPACITY_FRAMES * frame_bytes);

        let wide_name: Vec<u16> = RING_NAME.encode_utf16().chain(Some(0)).collect();

        unsafe {
            let handle = CreateFileMappingW(
                INVALID_HANDLE_VALUE,
                None,
                PAGE_READWRITE,
                0,
                total_bytes as u32,
                PCWSTR(wide_name.as_ptr()),
            )?;

            let view_addr = MapViewOfFile(handle, FILE_MAP_ALL_ACCESS, 0, 0, total_bytes);
            ensure!(!view_addr.Value.is_null(), "MapViewOfFile returned null");

            let header = &mut *(view_addr.Value as *mut RingHeader);
            header.write_cursor.store(0, Ordering::SeqCst);
            header.read_cursor.store(0, Ordering::SeqCst);
            header.sample_rate = 16000;
            header.channels = 1;
            header.frame_samples = FRAME_SAMPLES as u16;

            Ok(Self {
                handle,
                view: view_addr.Value as *mut u8,
            })
        }
    }

    pub fn write_frame(&self, samples: &[f32]) {
        assert_eq!(samples.len(), FRAME_SAMPLES);
        unsafe {
            let header = &*(self.view as *const RingHeader);
            let cursor = header.write_cursor.load(Ordering::Relaxed);
            let slot = (cursor as usize) % CAPACITY_FRAMES;

            let frame_bytes = FRAME_SAMPLES * 4;
            let offset = 64 + (slot * frame_bytes);
            let dst = self.view.add(offset) as *mut f32;

            std::ptr::copy_nonoverlapping(samples.as_ptr(), dst, FRAME_SAMPLES);
            header.write_cursor.store(cursor + 1, Ordering::Release);
        }
    }
}

impl Drop for SharedAudioRing {
    fn drop(&mut self) {
        unsafe {
            let _ = UnmapViewOfFile(MEMORY_MAPPED_VIEW_ADDRESS { Value: self.view as _ });
            let _ = CloseHandle(self.handle);
        }
    }
}
