"""Shared memory circular audio ring buffer reader for ULTRON."""

import ctypes
from typing import List
import numpy as np

RING_NAME = "Local\\UltronAudioRing"
FRAME_SAMPLES = 320
CAPACITY_FRAMES = 100
HEADER_BYTES = 64
FRAME_BYTES = FRAME_SAMPLES * 4


class AudioRingReader:
    """Zero-copy reader mapping the shared memory ring buffer created by Rust."""

    def __init__(self, ring_name: str = RING_NAME):
        self.kernel32 = ctypes.windll.kernel32
        self.kernel32.MapViewOfFile.restype = ctypes.c_void_p
        self.kernel32.OpenFileMappingW.restype = ctypes.c_void_p

        self.handle = self.kernel32.OpenFileMappingW(0xF001F, False, ring_name)
        if not self.handle:
            raise FileNotFoundError(f"Shared memory ring '{ring_name}' not found. Is ultron-core running?")

        self.view = self.kernel32.MapViewOfFile(self.handle, 0xF001F, 0, 0, 0)
        if not self.view:
            self.kernel32.CloseHandle(self.handle)
            self.handle = None
            raise OSError("Could not map view of shared memory file mapping.")
        self.local_cursor = 0

    def read_latest_frames(self) -> List[np.ndarray]:
        """Fetch all unread frames as numpy arrays without copying memory."""
        if not self.view:
            return []
        cursor_ptr = ctypes.cast(self.view, ctypes.POINTER(ctypes.c_uint64))
        write_cursor = cursor_ptr[0]

        frames = []
        while self.local_cursor < write_cursor:
            slot = self.local_cursor % CAPACITY_FRAMES
            offset = HEADER_BYTES + (slot * FRAME_BYTES)
            addr = self.view + offset

            # Zero-copy numpy array pointing directly to shared memory
            buf = (ctypes.c_float * FRAME_SAMPLES).from_address(addr)
            arr = np.ctypeslib.as_array(buf)
            frames.append(arr)
            self.local_cursor += 1

        return frames

    def close(self):
        if getattr(self, "view", None):
            self.kernel32.UnmapViewOfFile(ctypes.c_void_p(self.view))
            self.view = None
        if getattr(self, "handle", None):
            self.kernel32.CloseHandle(self.handle)
            self.handle = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
