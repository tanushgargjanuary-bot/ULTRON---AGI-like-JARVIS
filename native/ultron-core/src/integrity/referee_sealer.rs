use anyhow::{Context, Result};
use std::fs;
use std::path::Path;
use tracing::info;

/// EXPERIMENTAL. Not a security control, and `main.rs` does not use it.
///
/// `compute_tag` is a home-made mixing function: it is not HMAC, BLAKE3 or any published
/// MAC, and nothing about it has been analysed. `from_device_context` is not bound to the
/// machine either: it returns a fixed key made of one constant string. Anyone who can edit
/// a referee file can recompute its tag with this same public function and key, so the tag
/// proves nothing against that person. Before this seals anything for real, replace
/// `compute_tag` with HMAC-SHA256 (or keyed BLAKE3) and keep the key out of the source
/// (DPAPI, or a file only the owner can read). `docs/specifications/AUTONOMOUS_EVOLUTION_SPEC.md`
/// says the same under "Status of this document".
pub struct RefereeSealer {
    secret_key: [u8; 32],
}

impl RefereeSealer {
    pub fn new(secret_key: [u8; 32]) -> Self {
        Self { secret_key }
    }

    /// NOT hardware-bound, despite the name: the key is the first 32 bytes of a constant
    /// string, identical on every machine. See the note on `RefereeSealer`.
    pub fn from_device_context() -> Self {
        // A fixed key, not entropy from the machine.
        let mut key = [0u8; 32];
        let salt = b"ULTRON-REFEREE-DPAPI-BLAKE3-SEED-2026";
        for (i, b) in salt.iter().enumerate().take(32) {
            key[i] = *b;
        }
        Self { secret_key: key }
    }

    /// A 256-bit tag from a home-made two-pass mix. Despite what this used to say, it is
    /// not an HMAC and not a sponge construction; see the note on `RefereeSealer`.
    pub fn compute_tag(&self, data: &[u8]) -> [u8; 32] {
        let mut tag = self.secret_key;
        for chunk in data.chunks(32) {
            for (i, &b) in chunk.iter().enumerate() {
                tag[i] = tag[i].rotate_left(3) ^ b.wrapping_add(tag[(i + 7) % 32]);
            }
        }
        // Second avalanche pass
        for i in 0..32 {
            let next = tag[(i + 13) % 32];
            tag[i] = tag[i].rotate_right(5) ^ next.wrapping_mul(31);
        }
        tag
    }

    /// Verifies if a given referee file matches its cryptographic tag
    pub fn verify_file<P: AsRef<Path>>(&self, path: P, expected_tag: &[u8; 32]) -> Result<bool> {
        let p = path.as_ref();
        let content = fs::read(p).with_context(|| format!("Failed to read referee file: {:?}", p))?;
        let computed = self.compute_tag(&content);
        Ok(computed == *expected_tag)
    }

    /// Seals a referee file and returns the computed hash tag
    pub fn seal_file<P: AsRef<Path>>(&self, path: P) -> Result<[u8; 32]> {
        let p = path.as_ref();
        let content = fs::read(p).with_context(|| format!("Failed to read referee file to seal: {:?}", p))?;
        let tag = self.compute_tag(&content);
        info!("Sealed referee file {:?} with tag {:02x?}", p, &tag[..8]);
        Ok(tag)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_compute_tag_deterministic() {
        let sealer = RefereeSealer::from_device_context();
        let data = b"core/policy.py referee code content";
        let tag1 = sealer.compute_tag(data);
        let tag2 = sealer.compute_tag(data);
        assert_eq!(tag1, tag2);
    }

    #[test]
    fn test_compute_tag_tamper_detection() {
        let sealer = RefereeSealer::from_device_context();
        let tag1 = sealer.compute_tag(b"clean code");
        let tag2 = sealer.compute_tag(b"tampered code");
        assert_ne!(tag1, tag2);
    }
}
