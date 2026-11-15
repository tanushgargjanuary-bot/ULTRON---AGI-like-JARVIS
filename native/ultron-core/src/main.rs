use anyhow::Result;
use tracing_subscriber::{layer::SubscriberExt, util::SubscriberInitExt};

#[tokio::main]
async fn main() -> Result<()> {
    tracing_subscriber::registry()
        .with(tracing_subscriber::EnvFilter::try_from_default_env()
            .unwrap_or_else(|_| "info".into()))
        .with(tracing_subscriber::fmt::layer())
        .init();

    tracing::info!("🦀 Starting ULTRON Native Core v2.0.0");

    // Initialize Shared Audio Ring
    let _ring = ultron_core::audio::shared_ring::SharedAudioRing::create()?;
    tracing::info!("✅ Shared Audio Ring initialized ('Local\\UltronAudioRing')");

    // Start Named Pipe IPC Server
    ultron_core::ipc::server::start_ipc_server().await?;

    Ok(())
}
