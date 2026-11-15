pub struct AudioDsp {
    pub sample_rate: u32,
    pub channels: u16,
    pub energy_threshold: f32,
}

impl AudioDsp {
    pub fn new(sample_rate: u32, channels: u16, energy_threshold: f32) -> Self {
        Self {
            sample_rate,
            channels,
            energy_threshold,
        }
    }

    /// Computes Root-Mean-Square (RMS) signal level of PCM 16-bit audio samples
    pub fn calculate_rms_i16(&self, samples: &[i16]) -> f32 {
        if samples.is_empty() {
            return 0.0;
        }

        let mut sum_sq: f64 = 0.0;
        for &s in samples {
            let normalized = s as f64 / 32768.0;
            sum_sq += normalized * normalized;
        }

        (sum_sq / samples.len() as f64).sqrt() as f32
    }

    /// Fast Voice Activity Detection (VAD) classifier
    pub fn is_speech(&self, samples: &[i16]) -> bool {
        let rms = self.calculate_rms_i16(samples);
        rms > self.energy_threshold
    }

    /// Linear interpolation resampler for converting capture rate to model input rate
    pub fn resample_linear(&self, input: &[i16], in_rate: u32, out_rate: u32) -> Vec<i16> {
        if in_rate == out_rate || input.is_empty() {
            return input.to_vec();
        }

        let ratio = in_rate as f64 / out_rate as f64;
        let out_len = (input.len() as f64 / ratio).floor() as usize;
        let mut output = Vec::with_capacity(out_len);

        for i in 0..out_len {
            let src_idx = i as f64 * ratio;
            let idx_floor = src_idx.floor() as usize;
            let idx_ceil = (idx_floor + 1).min(input.len() - 1);
            let frac = (src_idx - idx_floor as f64) as f32;

            let s1 = input[idx_floor] as f32;
            let s2 = input[idx_ceil] as f32;
            let interp = s1 + frac * (s2 - s1);
            output.push(interp.round() as i16);
        }

        output
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_rms_silence() {
        let dsp = AudioDsp::new(16000, 1, 0.01);
        let samples = vec![0i16; 1600];
        assert_eq!(dsp.calculate_rms_i16(&samples), 0.0);
        assert!(!dsp.is_speech(&samples));
    }

    #[test]
    fn test_rms_signal_detected() {
        let dsp = AudioDsp::new(16000, 1, 0.01);
        let samples = vec![16384i16; 1600]; // 50% amplitude
        let rms = dsp.calculate_rms_i16(&samples);
        assert!(rms > 0.49 && rms < 0.51);
        assert!(dsp.is_speech(&samples));
    }

    #[test]
    fn test_resample_linear() {
        let dsp = AudioDsp::new(48000, 1, 0.01);
        let input = vec![0i16, 1000, 2000, 3000];
        let resampled = dsp.resample_linear(&input, 4, 2);
        assert_eq!(resampled.len(), 2);
    }
}
