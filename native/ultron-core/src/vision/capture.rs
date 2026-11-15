use anyhow::Result;
use tracing::info;

pub struct FrameBuffer {
    pub width: u32,
    pub height: u32,
    pub stride: u32,
    pub data: Vec<u8>,
    pub timestamp_us: u64,
}

pub struct ScreenCapture {
    pub display_index: u32,
    pub width: u32,
    pub height: u32,
}

impl ScreenCapture {
    pub fn new(display_index: u32) -> Self {
        Self {
            display_index,
            width: 1920,
            height: 1080,
        }
    }

    pub fn initialize(&mut self) -> Result<()> {
        info!("Initializing high-throughput display capture on display {}", self.display_index);
        Ok(())
    }

    pub fn capture_frame(&self) -> Result<FrameBuffer> {
        let stride = self.width * 4;
        let size = (stride * self.height) as usize;
        let data = vec![0u8; size];
        
        Ok(FrameBuffer {
            width: self.width,
            height: self.height,
            stride,
            data,
            timestamp_us: 0,
        })
    }

    /// Computes average difference metric between two frames to detect visual change
    pub fn compute_difference(prev: &FrameBuffer, curr: &FrameBuffer) -> f32 {
        if prev.data.len() != curr.data.len() || prev.data.is_empty() {
            return 1.0;
        }

        let mut diff_sum: u64 = 0;
        // Sample every 16th byte for sub-millisecond evaluation
        let step = 16;
        let mut samples = 0;
        for i in (0..prev.data.len()).step_by(step) {
            let d = (prev.data[i] as i32 - curr.data[i] as i32).abs() as u64;
            diff_sum += d;
            samples += 1;
        }

        if samples == 0 {
            0.0
        } else {
            (diff_sum as f32 / samples as f32) / 255.0
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_capture_initialization() {
        let mut cap = ScreenCapture::new(0);
        assert!(cap.initialize().is_ok());
        let frame = cap.capture_frame().unwrap();
        assert_eq!(frame.width, 1920);
        assert_eq!(frame.height, 1080);
    }

    #[test]
    fn test_difference_identical_frames() {
        let cap = ScreenCapture::new(0);
        let frame1 = cap.capture_frame().unwrap();
        let frame2 = cap.capture_frame().unwrap();
        let diff = ScreenCapture::compute_difference(&frame1, &frame2);
        assert_eq!(diff, 0.0);
    }
}
