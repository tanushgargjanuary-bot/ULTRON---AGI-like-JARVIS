use anyhow::Result;
use tracing_subscriber::{layer::SubscriberExt, util::SubscriberInitExt};

#[tokio::main]
async fn main() -> Result<()> {
    tracing_subscriber::registry()
        .with(tracing_subscriber::EnvFilter::try_from_default_env()
            .unwrap_or_else(|_| "info".into()))
        // The output goes to a file or a pipe and never to a terminal, so no colour codes in it.
        .with(tracing_subscriber::fmt::layer().with_ansi(false))
        .init();

    tracing::info!("🦀 Starting ULTRON Native Core v2.0.0");

    // `--once`, `--wait-seconds=N` and `--stall-seconds=N`: what Ultron passes when it starts the helper.
    let options = ultron_core::ipc::server::Options::from_arguments(std::env::args().skip(1))?;

    // Initialize Shared Audio Ring
    let _ring = ultron_core::audio::shared_ring::SharedAudioRing::create()?;
    tracing::info!("✅ Shared Audio Ring initialized ('Local\\UltronAudioRing')");

    // Start Named Pipe IPC Server
    ultron_core::ipc::server::start_ipc_server(options).await?;

    Ok(())
}
