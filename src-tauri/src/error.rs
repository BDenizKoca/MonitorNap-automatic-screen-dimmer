/// Error types for MonitorNap application
use std::fmt;

#[derive(Debug, thiserror::Error)]
pub enum MonitorNapError {
    #[error("Monitor error: {0}")]
    Monitor(String),

    #[error("DDC communication error: {0}")]
    Ddc(String),

    #[error("Configuration error: {0}")]
    Config(String),

    #[error("IO error: {0}")]
    Io(#[from] std::io::Error),

    #[error("Serialization error: {0}")]
    Serialization(#[from] serde_json::Error),

    #[error("Hotkey error: {0}")]
    Hotkey(String),

    #[error("System error: {0}")]
    System(String),

    #[error("Window error: {0}")]
    Window(String),
}

/// Result type alias for MonitorNap operations
pub type Result<T> = std::result::Result<T, MonitorNapError>;

// Note: ddc_hi::Error is private, so we can't impl From for it
// Use .map_err(|e| MonitorNapError::Ddc(e.to_string())) instead

/// Convert global-hotkey errors to our error type
impl From<global_hotkey::Error> for MonitorNapError {
    fn from(err: global_hotkey::Error) -> Self {
        MonitorNapError::Hotkey(err.to_string())
    }
}
