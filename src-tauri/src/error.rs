/// Error types for MonitorNap application
use serde::Serialize;

#[derive(Debug, thiserror::Error, Serialize)]
pub enum MonitorNapError {
    #[error("Monitor error: {0}")]
    Monitor(String),

    #[error("DDC communication error: {0}")]
    Ddc(String),

    #[error("Configuration error: {0}")]
    Config(String),

    #[error("IO error: {0}")]
    Io(String),

    #[error("Serialization error: {0}")]
    Serialization(String),

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

/// Convert IO errors to our error type
impl From<std::io::Error> for MonitorNapError {
    fn from(err: std::io::Error) -> Self {
        MonitorNapError::Io(err.to_string())
    }
}

/// Convert serde_json errors to our error type
impl From<serde_json::Error> for MonitorNapError {
    fn from(err: serde_json::Error) -> Self {
        MonitorNapError::Serialization(err.to_string())
    }
}

/// Convert global-hotkey errors to our error type
impl From<global_hotkey::Error> for MonitorNapError {
    fn from(err: global_hotkey::Error) -> Self {
        MonitorNapError::Hotkey(err.to_string())
    }
}
