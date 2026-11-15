use tokio::process::Command;
use std::path::PathBuf;
use anyhow::{Result, ensure};

pub const VERIFIED_TAG_FILE: &str = "config/last_verified_release.txt";

#[derive(Clone)]
pub struct GitRecovery {
    repo_path: PathBuf,
}

impl GitRecovery {
    pub fn new(repo_path: PathBuf) -> Self {
        Self { repo_path }
    }

    /// Roll back working tree to the last verified release tag
    pub async fn rollback_to_verified_tag(&self) -> Result<String> {
        let tag = self.find_verified_tag().await?;
        tracing::warn!("[GitRecovery] Initiating automated rollback to: {}", tag);

        let status = Command::new("git")
            .args(["reset", "--hard", &tag])
            .current_dir(&self.repo_path)
            .status()
            .await?;
        ensure!(status.success(), "git reset --hard failed with exit status {:?}", status);

        tracing::info!("[GitRecovery] Rollback to {} succeeded", tag);
        Ok(tag)
    }

    pub async fn find_verified_tag(&self) -> Result<String> {
        let tag_file = self.repo_path.join(VERIFIED_TAG_FILE);
        if tag_file.exists() {
            let tag = tokio::fs::read_to_string(&tag_file).await?.trim().to_string();
            if !tag.is_empty() {
                return Ok(tag);
            }
        }

        // Fallback: use git rev-parse HEAD as safe fallback
        let output = Command::new("git")
            .args(["rev-parse", "HEAD"])
            .current_dir(&self.repo_path)
            .output()
            .await?;
        ensure!(output.status.success(), "Failed to query git rev-parse HEAD");
        Ok(String::from_utf8(output.stdout)?.trim().to_string())
    }

    pub async fn pin_verified_release(&self, tag: &str) -> Result<()> {
        let tag_file = self.repo_path.join(VERIFIED_TAG_FILE);
        if let Some(parent) = tag_file.parent() {
            tokio::fs::create_dir_all(parent).await?;
        }
        tokio::fs::write(&tag_file, tag).await?;
        tracing::info!("[GitRecovery] Pinned verified release tag: {}", tag);
        Ok(())
    }
}
