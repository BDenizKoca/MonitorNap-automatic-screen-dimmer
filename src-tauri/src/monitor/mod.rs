/// Monitor control module
///
/// This module handles all monitor-related functionality including:
/// - Hardware brightness control via DDC/CI
/// - Software dimming via overlay windows
/// - Activity detection
/// - Monitor geometry management
pub mod controller;
pub mod ddc;
pub mod overlay;

pub use controller::MonitorController;
pub use ddc::DdcController;
pub use overlay::OverlayWindow;

use serde::{Deserialize, Serialize};

/// Monitor information
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct MonitorInfo {
    /// Logical monitor index
    pub index: usize,

    /// Monitor name/description
    pub name: String,

    /// Screen position X
    pub x: i32,

    /// Screen position Y
    pub y: i32,

    /// Screen width in pixels
    pub width: u32,

    /// Screen height in pixels
    pub height: u32,

    /// Whether this is the primary monitor
    pub is_primary: bool,
}

/// Get all connected monitors
pub fn get_monitors() -> Vec<MonitorInfo> {
    match display_info::DisplayInfo::all() {
        Ok(displays) => {
            let monitors: Vec<MonitorInfo> = displays
                .into_iter()
                .enumerate()
                .map(|(i, disp)| {
                    tracing::debug!(
                        "Detected monitor {}: {}x{} at ({}, {}), primary: {}",
                        i,
                        disp.width,
                        disp.height,
                        disp.x,
                        disp.y,
                        disp.is_primary
                    );
                    MonitorInfo {
                        index: i,
                        name: format!("Display {}", i + 1),
                        x: disp.x,
                        y: disp.y,
                        width: disp.width,
                        height: disp.height,
                        is_primary: disp.is_primary,
                    }
                })
                .collect();
            tracing::info!("Detected {} monitor(s)", monitors.len());
            monitors
        }
        Err(e) => {
            tracing::error!("Failed to get display info: {}", e);
            Vec::new()
        }
    }
}
