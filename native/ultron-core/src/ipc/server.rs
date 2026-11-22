use tokio::net::windows::named_pipe::{ServerOptions, NamedPipeServer};
use tokio::io::{AsyncReadExt, AsyncWriteExt};
use anyhow::{Result, ensure};

pub const PIPE_NAME: &str = r"\\.\pipe\ultron-core";
pub const MAGIC: u8 = 0xA1;
pub const HEADER_LEN: usize = 6;
/// Largest frame body this server will allocate for (`core/ipc_client.py` has the same
/// number as `MAX_PAYLOAD`). The length field is a `u32`: without this check a corrupt or
/// hostile header makes `vec![0u8; payload_len]` ask for up to 4 GiB before one byte of
/// the body has been read, and the supervisor, which is meant to outlive a crashed
/// worker, is the process that dies.
pub const MAX_PAYLOAD_LEN: usize = 1 << 20;

pub async fn start_ipc_server() -> Result<()> {
    tracing::info!("[IPC] Initializing Named Pipe server on {}", PIPE_NAME);
    let mut is_first = true;

    loop {
        let server = ServerOptions::new()
            .first_pipe_instance(is_first)
            .create(PIPE_NAME)?;
        is_first = false;

        tracing::info!("[IPC] Waiting for connection from Python agent...");
        server.connect().await?;
        tracing::info!("[IPC] Connection established.");

        tokio::spawn(async move {
            if let Err(e) = handle_client(server).await {
                tracing::warn!("[IPC] Session ended: {}", e);
            }
        });
    }
}

async fn handle_client(mut pipe: NamedPipeServer) -> Result<()> {
    let mut header = [0u8; HEADER_LEN];

    loop {
        pipe.read_exact(&mut header).await?;
        ensure!(
            header[0] == MAGIC,
            "Protocol magic mismatch: expected 0xA1, got 0x{:02X}",
            header[0]
        );

        let channel_id = header[1];
        let payload_len = u32::from_le_bytes(header[2..6].try_into()?) as usize;
        ensure!(
            payload_len <= MAX_PAYLOAD_LEN,
            "Frame too large: {} bytes (limit {})",
            payload_len,
            MAX_PAYLOAD_LEN
        );

        let mut payload = vec![0u8; payload_len];
        pipe.read_exact(&mut payload).await?;

        match channel_id {
            0x06 => {
                // Heartbeat echo back
                pipe.write_all(&header).await?;
                pipe.write_all(&payload).await?;
            }
            0xFF => {
                tracing::info!("[IPC] Graceful shutdown received from Python agent.");
                break;
            }
            _ => {
                tracing::debug!("[IPC] Received channel 0x{:02X} ({} bytes)", channel_id, payload_len);
            }
        }
    }
    Ok(())
}
