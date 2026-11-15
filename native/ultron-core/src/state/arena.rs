use windows::Win32::System::Memory::*;
use windows::Win32::Foundation::HANDLE;
use std::sync::atomic::{AtomicU64, AtomicU8, Ordering};
use anyhow::{Result, ensure};

pub const ARENA_MAGIC: u64 = 0x554C54524F4E5342; // "ULTRONS B"
pub const ARENA_SIZE: usize = 64 * 1024 * 1024;  // 64 MB
pub const ARENA_NAME: windows::core::PCWSTR = windows::core::w!("Local\\ultron-state-arena");

// Page-aligned (64 KB allocation granularity) non-overlapping partitions
pub const HEADER_OFFSET:       usize = 0x0000_0000; // Reserved 64 KB for headers
pub const CONVERSATION_OFFSET: usize = 0x0001_0000; // 64 KB offset (Capacity: 32 MB)
pub const TOOL_CTX_OFFSET:     usize = 0x0201_0000; // 32 MB + 64 KB offset (Capacity: 16 MB)
pub const SETTINGS_OFFSET:     usize = 0x0301_0000; // 48 MB + 64 KB offset (Capacity: 4 MB)
pub const AUDIO_CTX_OFFSET:    usize = 0x0341_0000; // 52 MB + 64 KB offset (Capacity: 11 MB)

pub const MAX_CONVERSATION_LEN: usize = 32 * 1024 * 1024;
pub const MAX_TOOL_CTX_LEN:     usize = 16 * 1024 * 1024;
pub const MAX_SETTINGS_LEN:     usize =  4 * 1024 * 1024;
pub const MAX_AUDIO_CTX_LEN:    usize = 11 * 1024 * 1024;

#[repr(C, align(64))]
pub struct ArenaHeader {
    pub magic:            u64,
    pub version:          u32,
    pub writer_pid:       u32,
    pub reader_pid:       u32,
    pub _pad0:            u32,
    pub write_epoch:      AtomicU64,
    pub conversation_len: u32,
    pub tool_ctx_len:     u32,
    pub settings_len:     u32,
    pub audio_ctx_len:    u32,
    pub checksum:         [u8; 32],
    pub handoff_ready:    AtomicU8, // 0 = not ready, 1 = ready, 2 = consumed
    pub _pad1:            [u8; 175],
}

pub struct StateArena {
    mapping_handle: HANDLE,
    base_ptr:       *mut u8,
}

unsafe impl Send for StateArena {}
unsafe impl Sync for StateArena {}

impl StateArena {
    pub fn create_or_open() -> Result<Self> {
        unsafe {
            let handle = CreateFileMappingW(
                HANDLE(-1isize as *mut _), // pagefile-backed
                None,
                PAGE_READWRITE,
                (ARENA_SIZE >> 32) as u32,
                (ARENA_SIZE & 0xFFFF_FFFF) as u32,
                ARENA_NAME,
            )?;

            let base = MapViewOfFile(handle, FILE_MAP_ALL_ACCESS, 0, 0, ARENA_SIZE);
            ensure!(!base.Value.is_null(), "MapViewOfFile failed to map shared arena");

            let arena = Self {
                mapping_handle: handle,
                base_ptr: base.Value as *mut u8,
            };

            let header = arena.header_mut();
            if header.magic != ARENA_MAGIC {
                std::ptr::write_bytes(arena.base_ptr, 0, 64 * 1024); // zero-initialize 64KB header
                header.magic = ARENA_MAGIC;
                header.version = 1;
                header.handoff_ready.store(0, Ordering::SeqCst);
            }

            Ok(arena)
        }
    }

    pub fn header(&self) -> &ArenaHeader {
        unsafe { &*(self.base_ptr.add(HEADER_OFFSET) as *const ArenaHeader) }
    }

    pub fn header_mut(&self) -> &mut ArenaHeader {
        unsafe { &mut *(self.base_ptr.add(HEADER_OFFSET) as *mut ArenaHeader) }
    }

    pub fn write_handoff_state(
        &self,
        conversation: &[u8],
        tool_ctx:     &[u8],
        settings:     &[u8],
        audio_ctx:    &[u8],
        writer_pid:   u32,
    ) -> Result<()> {
        ensure!(conversation.len() <= MAX_CONVERSATION_LEN, "Conversation exceeds partition limit");
        ensure!(tool_ctx.len()     <= MAX_TOOL_CTX_LEN,     "Tool context exceeds partition limit");
        ensure!(settings.len()     <= MAX_SETTINGS_LEN,     "Settings exceed partition limit");
        ensure!(audio_ctx.len()    <= MAX_AUDIO_CTX_LEN,    "Audio context exceeds partition limit");

        unsafe {
            self.write_section(CONVERSATION_OFFSET, conversation);
            self.write_section(TOOL_CTX_OFFSET,     tool_ctx);
            self.write_section(SETTINGS_OFFSET,     settings);
            self.write_section(AUDIO_CTX_OFFSET,    audio_ctx);

            let checksum = self.compute_checksum(conversation, tool_ctx, settings, audio_ctx);

            let h = self.header_mut();
            h.writer_pid       = writer_pid;
            h.conversation_len = conversation.len() as u32;
            h.tool_ctx_len     = tool_ctx.len() as u32;
            h.settings_len     = settings.len() as u32;
            h.audio_ctx_len    = audio_ctx.len() as u32;
            h.checksum         = checksum;
            h.write_epoch.fetch_add(1, Ordering::SeqCst);

            h.handoff_ready.store(1, Ordering::SeqCst);
        }
        Ok(())
    }

    pub fn read_handoff_state(&self) -> Result<HandoffState> {
        let h = self.header();
        ensure!(h.handoff_ready.load(Ordering::SeqCst) == 1, "State arena not ready for consumption");

        unsafe {
            let conversation = self.read_section(CONVERSATION_OFFSET, h.conversation_len as usize);
            let tool_ctx     = self.read_section(TOOL_CTX_OFFSET,     h.tool_ctx_len     as usize);
            let settings     = self.read_section(SETTINGS_OFFSET,     h.settings_len     as usize);
            let audio_ctx    = self.read_section(AUDIO_CTX_OFFSET,    h.audio_ctx_len    as usize);

            let expected = self.compute_checksum(&conversation, &tool_ctx, &settings, &audio_ctx);
            ensure!(expected == h.checksum, "State arena checksum mismatch");

            h.handoff_ready.store(2, Ordering::SeqCst);

            Ok(HandoffState { conversation, tool_ctx, settings, audio_ctx })
        }
    }

    fn compute_checksum(&self, c: &[u8], t: &[u8], s: &[u8], a: &[u8]) -> [u8; 32] {
        // Complete 32-byte hash computed across ALL payload bytes (no truncation)
        let mut hash = [0u8; 32];
        let total_len = (c.len() + t.len() + s.len() + a.len()) as u64;
        hash[0..8].copy_from_slice(&total_len.to_le_bytes());
        hash[8..12].copy_from_slice(&(c.len() as u32).to_le_bytes());
        hash[12..16].copy_from_slice(&(t.len() as u32).to_le_bytes());
        hash[16..20].copy_from_slice(&(s.len() as u32).to_le_bytes());
        hash[20..24].copy_from_slice(&(a.len() as u32).to_le_bytes());

        // Full FNV-1a streaming accumulation over all slice bytes
        let mut acc1: u64 = 0xCBF29CE484222325;
        let mut acc2: u64 = 0x100000001B3;

        for slice in [c, t, s, a] {
            for &byte in slice {
                acc1 = (acc1 ^ (byte as u64)).wrapping_mul(0x100000001B3);
                acc2 = acc2.rotate_left(5) ^ (byte as u64).wrapping_add(acc1);
            }
        }

        hash[24..28].copy_from_slice(&(acc1 as u32).to_le_bytes());
        hash[28..32].copy_from_slice(&(acc2 as u32).to_le_bytes());
        hash
    }

    unsafe fn write_section(&self, offset: usize, data: &[u8]) {
        std::ptr::copy_nonoverlapping(data.as_ptr(), self.base_ptr.add(offset), data.len());
    }

    unsafe fn read_section(&self, offset: usize, len: usize) -> Vec<u8> {
        let mut buf = vec![0u8; len];
        std::ptr::copy_nonoverlapping(self.base_ptr.add(offset), buf.as_mut_ptr(), len);
        buf
    }
}

pub struct HandoffState {
    pub conversation: Vec<u8>,
    pub tool_ctx:     Vec<u8>,
    pub settings:     Vec<u8>,
    pub audio_ctx:    Vec<u8>,
}

impl Drop for StateArena {
    fn drop(&mut self) {
        unsafe {
            if !self.base_ptr.is_null() {
                let _ = UnmapViewOfFile(MEMORY_MAPPED_VIEW_ADDRESS { Value: self.base_ptr as *mut _ });
            }
            if !self.mapping_handle.is_invalid() {
                let _ = windows::Win32::Foundation::CloseHandle(self.mapping_handle);
            }
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_partition_offsets_non_overlapping() {
        assert_eq!(HEADER_OFFSET, 0);
        assert_eq!(CONVERSATION_OFFSET, 64 * 1024);
        assert!(CONVERSATION_OFFSET + MAX_CONVERSATION_LEN <= TOOL_CTX_OFFSET);
        assert!(TOOL_CTX_OFFSET + MAX_TOOL_CTX_LEN <= SETTINGS_OFFSET);
        assert!(SETTINGS_OFFSET + MAX_SETTINGS_LEN <= AUDIO_CTX_OFFSET);
        assert!(AUDIO_CTX_OFFSET + MAX_AUDIO_CTX_LEN <= ARENA_SIZE);
    }

    #[test]
    fn test_full_checksum_tamper_detection() {
        let arena_mock = StateArena {
            mapping_handle: HANDLE(std::ptr::null_mut()),
            base_ptr: std::ptr::null_mut(),
        };

        // Create 1000-byte payload (beyond old 256B limit)
        let c1 = vec![0xAA; 1000];
        let c2 = vec![0xAA; 1000];
        let mut c3 = c1.clone();
        c3[500] = 0xBB; // tamper at byte 500

        let hash1 = arena_mock.compute_checksum(&c1, b"tools", b"settings", b"audio");
        let hash2 = arena_mock.compute_checksum(&c2, b"tools", b"settings", b"audio");
        let hash3 = arena_mock.compute_checksum(&c3, b"tools", b"settings", b"audio");

        assert_eq!(hash1, hash2);
        assert_ne!(hash1, hash3); // successfully detects tampering past byte 256
    }
}
