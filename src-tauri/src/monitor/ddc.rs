/// DDC/CI hardware brightness control
use crate::error::{MonitorNapError, Result};
use ddc_hi::{Ddc, Display};
use std::sync::{Arc, Mutex};
use tracing::{debug, error, info, warn};

/// DDC/CI controller for hardware brightness control
pub struct DdcController {
    display: Arc<Mutex<Option<Display>>>,
    original_brightness: Option<u16>,
    index: usize,
}

// SAFETY: DdcController only accesses Display through a Mutex, ensuring exclusive access.
// The Display type contains raw pointers but we ensure thread-safety through synchronization.
unsafe impl Send for DdcController {}
unsafe impl Sync for DdcController {}

impl DdcController {
    /// Create a new DDC controller for the specified monitor index
    pub fn new(index: usize) -> Self {
        Self {
            display: Arc::new(Mutex::new(None)),
            original_brightness: None,
            index,
        }
    }

    /// Initialize DDC connection to the monitor
    pub fn init(&mut self) -> Result<()> {
        let displays = Display::enumerate();

        if self.index < displays.len() {
            let mut display = displays.into_iter().nth(self.index).unwrap();

            // Try to read current brightness
            match display.handle.get_vcp_feature(0x10) {
                Ok(brightness) => {
                    self.original_brightness = Some(brightness.value());
                    *self.display.lock().unwrap() = Some(display);
                    info!(
                        "Initialized DDC for monitor {}, brightness: {}",
                        self.index,
                        brightness.value()
                    );
                    Ok(())
                }
                Err(e) => {
                    warn!(
                        "Monitor {} does not support DDC/CI brightness control: {}",
                        self.index, e
                    );
                    Err(MonitorNapError::Ddc(format!(
                        "DDC not supported on monitor {}: {}",
                        self.index, e
                    )))
                }
            }
        } else {
            Err(MonitorNapError::Ddc(format!(
                "Monitor index {} out of range",
                self.index
            )))
        }
    }

    /// Get current brightness level (0-100)
    pub fn get_brightness(&self) -> Result<u16> {
        let mut display_lock = self.display.lock().unwrap();
        if let Some(display) = display_lock.as_mut() {
            match display.handle.get_vcp_feature(0x10) {
                Ok(brightness) => {
                    let value = brightness.value();
                    debug!("Monitor {} brightness: {}", self.index, value);
                    Ok(value)
                }
                Err(e) => Err(MonitorNapError::Ddc(format!("Failed to get brightness: {}", e))),
            }
        } else {
            Err(MonitorNapError::Ddc("DDC not initialized".to_string()))
        }
    }

    /// Set brightness level (0-100)
    pub fn set_brightness(&self, value: u16) -> Result<()> {
        let mut display_lock = self.display.lock().unwrap();
        if let Some(display) = display_lock.as_mut() {
            let clamped = value.min(100);
            match display.handle.set_vcp_feature(0x10, clamped) {
                Ok(_) => {
                    debug!("Set monitor {} brightness to {}", self.index, clamped);
                    Ok(())
                }
                Err(e) => {
                    error!("Failed to set brightness on monitor {}: {}", self.index, e);
                    Err(MonitorNapError::Ddc(format!("Failed to set brightness: {}", e)))
                }
            }
        } else {
            Err(MonitorNapError::Ddc("DDC not initialized".to_string()))
        }
    }

    /// Dim the monitor to the specified percentage reduction
    /// For example, dim_percent=30 means reduce brightness by 30%
    pub fn dim(&self, dim_percent: u8) -> Result<()> {
        if let Some(original) = self.original_brightness {
            let dim_factor = (100 - dim_percent.min(100)) as f32 / 100.0;
            let target = ((original as f32) * dim_factor) as u16;
            self.set_brightness(target)
        } else {
            // If we don't have original brightness, try to read it now
            match self.get_brightness() {
                Ok(current) => {
                    let dim_factor = (100 - dim_percent.min(100)) as f32 / 100.0;
                    let target = ((current as f32) * dim_factor) as u16;
                    self.set_brightness(target)
                }
                Err(e) => Err(e),
            }
        }
    }

    /// Restore monitor to original brightness
    pub fn restore(&self) -> Result<()> {
        if let Some(original) = self.original_brightness {
            self.set_brightness(original)
        } else {
            warn!(
                "No original brightness stored for monitor {}, setting to 100",
                self.index
            );
            self.set_brightness(100)
        }
    }

    /// Check if DDC is supported and initialized
    pub fn is_available(&self) -> bool {
        self.display.lock().unwrap().is_some()
    }

    /// Get the original brightness value
    pub fn original_brightness(&self) -> Option<u16> {
        self.original_brightness
    }
}

impl Drop for DdcController {
    fn drop(&mut self) {
        // Attempt to restore brightness on drop
        if let Err(e) = self.restore() {
            debug!("Failed to restore brightness on drop: {}", e);
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_ddc_controller_creation() {
        let controller = DdcController::new(0);
        assert_eq!(controller.index, 0);
        assert!(!controller.is_available());
    }
}
