/// Main monitor controller
use super::{get_monitors, DdcController, MonitorInfo, OverlayWindow};
use crate::config::MonitorConfig;
use crate::error::Result;
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::Arc;
use std::time::Instant;
use tauri::AppHandle;
use tracing::{debug, info, warn};

/// Monitor controller handles dimming and activity detection for a single monitor
pub struct MonitorController {
    /// Monitor configuration
    pub config: MonitorConfig,

    /// Monitor information (geometry, etc.)
    pub info: MonitorInfo,

    /// DDC/CI controller for hardware dimming
    ddc: Option<DdcController>,

    /// Overlay window for software dimming
    overlay: Option<OverlayWindow>,

    /// Whether the monitor is currently dimmed
    is_dimmed: Arc<AtomicBool>,

    /// Last time this monitor was active
    last_active: Arc<tokio::sync::Mutex<Instant>>,

    /// Application handle for creating windows
    app_handle: AppHandle,
}

// SAFETY: MonitorController is designed to be used in a multi-threaded async context.
// All shared state is protected by appropriate synchronization primitives.
unsafe impl Send for MonitorController {}
unsafe impl Sync for MonitorController {}

impl MonitorController {
    /// Create a new monitor controller
    pub fn new(
        app_handle: AppHandle,
        config: MonitorConfig,
        info: MonitorInfo,
    ) -> Result<Self> {
        let mut controller = Self {
            config,
            info,
            ddc: None,
            overlay: None,
            is_dimmed: Arc::new(AtomicBool::new(false)),
            last_active: Arc::new(tokio::sync::Mutex::new(Instant::now())),
            app_handle,
        };

        controller.init()?;
        Ok(controller)
    }

    /// Initialize DDC and overlay
    fn init(&mut self) -> Result<()> {
        info!(
            "Initializing monitor {} ({}x{} at {}, {}) - HW enabled: {}, SW enabled: {}",
            self.config.monitor_index,
            self.info.width,
            self.info.height,
            self.info.x,
            self.info.y,
            self.config.enable_hardware_dimming,
            self.config.enable_software_dimming
        );

        // Initialize DDC/CI if hardware dimming is enabled
        if self.config.enable_hardware_dimming {
            let mut ddc = DdcController::new(self.config.ddc_index);
            match ddc.init() {
                Ok(_) => {
                    info!(
                        "Initialized hardware dimming for monitor {}",
                        self.config.monitor_index
                    );
                    self.ddc = Some(ddc);
                }
                Err(e) => {
                    warn!(
                        "Failed to initialize hardware dimming for monitor {}: {}",
                        self.config.monitor_index, e
                    );
                    // Continue without hardware dimming
                }
            }
        }

        // Initialize overlay if software dimming is enabled
        if self.config.enable_software_dimming {
            let overlay = OverlayWindow::new(
                self.app_handle.clone(),
                self.config.monitor_index,
                self.info.x,
                self.info.y,
                self.info.width,
                self.info.height,
                self.config.overlay_color.clone(),
            );

            match overlay.init() {
                Ok(_) => {
                    info!(
                        "Initialized software dimming for monitor {}",
                        self.config.monitor_index
                    );
                    self.overlay = Some(overlay);
                }
                Err(e) => {
                    warn!(
                        "Failed to initialize software dimming for monitor {}: {}",
                        self.config.monitor_index, e
                    );
                }
            }
        }

        Ok(())
    }

    /// Dim the monitor
    pub async fn dim(&self, fade_time: f32, fade_steps: u32) -> Result<()> {
        if self.is_dimmed.load(Ordering::Relaxed) {
            debug!("Monitor {} already dimmed", self.config.monitor_index);
            return Ok(());
        }

        info!("Dimming monitor {}", self.config.monitor_index);
        self.is_dimmed.store(true, Ordering::Relaxed);

        // Software dimming - only if enabled in config
        if self.config.enable_software_dimming {
            if let Some(overlay) = &self.overlay {
                overlay.show()?;
                // Clone overlay for async operation
                let mut overlay_clone = OverlayWindow::new(
                    self.app_handle.clone(),
                    self.config.monitor_index,
                    self.info.x,
                    self.info.y,
                    self.info.width,
                    self.info.height,
                    self.config.overlay_color.clone(),
                );
                overlay_clone.fade_to(self.config.software_dimming_level, fade_time, fade_steps).await;
            }
        }

        // Hardware dimming - only if enabled in config
        if self.config.enable_hardware_dimming {
            if let Some(ddc) = &self.ddc {
                if let Err(e) = ddc.dim(self.config.hardware_dimming_level) {
                    warn!(
                        "Failed to dim monitor {} via DDC: {}",
                        self.config.monitor_index, e
                    );
                }
            }
        }

        Ok(())
    }

    /// Restore the monitor from dimmed state
    pub async fn restore(&self, fade_time: f32, fade_steps: u32) -> Result<()> {
        if !self.is_dimmed.load(Ordering::Relaxed) {
            debug!("Monitor {} already restored", self.config.monitor_index);
            return Ok(());
        }

        info!("Restoring monitor {}", self.config.monitor_index);
        self.is_dimmed.store(false, Ordering::Relaxed);

        // Software dimming - fade out quickly
        if let Some(overlay) = &self.overlay {
            let mut overlay_clone = OverlayWindow::new(
                self.app_handle.clone(),
                self.config.monitor_index,
                self.info.x,
                self.info.y,
                self.info.width,
                self.info.height,
                self.config.overlay_color.clone(),
            );
            // Faster restore for instant wake-up feel
            overlay_clone.fade_to(0.0, fade_time * 0.05, fade_steps.min(3)).await;
            overlay.hide()?;
        }

        // Hardware dimming
        if let Some(ddc) = &self.ddc {
            if let Err(e) = ddc.restore() {
                warn!(
                    "Failed to restore monitor {} via DDC: {}",
                    self.config.monitor_index, e
                );
            }
        }

        Ok(())
    }

    /// Immediately restore without fade
    pub fn restore_immediate(&self) -> Result<()> {
        if !self.is_dimmed.load(Ordering::Relaxed) {
            return Ok(());
        }

        info!("Immediately restoring monitor {}", self.config.monitor_index);
        self.is_dimmed.store(false, Ordering::Relaxed);

        // Hide overlay immediately
        if let Some(overlay) = &self.overlay {
            overlay.hide()?;
        }

        // Restore hardware brightness
        if let Some(ddc) = &self.ddc {
            if let Err(e) = ddc.restore() {
                warn!(
                    "Failed to restore monitor {} via DDC: {}",
                    self.config.monitor_index, e
                );
            }
        }

        Ok(())
    }

    /// Update last active time
    pub async fn update_activity(&self) {
        *self.last_active.lock().await = Instant::now();
    }

    /// Get seconds since last activity
    pub async fn get_idle_time(&self) -> u64 {
        self.last_active.lock().await.elapsed().as_secs()
    }

    /// Check if monitor is currently dimmed
    pub fn is_dimmed(&self) -> bool {
        self.is_dimmed.load(Ordering::Relaxed)
    }

    /// Check if cursor is on this monitor
    pub fn is_cursor_on_monitor(&self, cursor_x: i32, cursor_y: i32) -> bool {
        cursor_x >= self.info.x
            && cursor_x < self.info.x + self.info.width as i32
            && cursor_y >= self.info.y
            && cursor_y < self.info.y + self.info.height as i32
    }

    /// Flash the overlay to identify this monitor
    pub async fn identify(&self) {
        if let Some(overlay) = &self.overlay {
            let _ = overlay.show();
            let mut temp_overlay = OverlayWindow::new(
                self.app_handle.clone(),
                self.config.monitor_index,
                self.info.x,
                self.info.y,
                self.info.width,
                self.info.height,
                self.config.overlay_color.clone(),
            );
            temp_overlay.fade_to(0.6, 0.2, 5).await;
            tokio::time::sleep(tokio::time::Duration::from_millis(1000)).await;
            temp_overlay.fade_to(0.0, 0.2, 5).await;
            let _ = overlay.hide();
        }
    }

    /// Get monitor index
    pub fn index(&self) -> usize {
        self.config.monitor_index
    }

    /// Update display index and refresh geometry
    pub async fn update_display_index(&mut self, display_index: usize) -> Result<()> {
        self.config.display_index = display_index;
        // Refresh geometry for the new display
        let monitors = get_monitors();
        if display_index < monitors.len() {
            let monitor = &monitors[display_index];
            self.info.x = monitor.x;
            self.info.y = monitor.y;
            self.info.width = monitor.width as u32;
            self.info.height = monitor.height as u32;

            // Update overlay if it exists
            if let Some(overlay) = &mut self.overlay {
                overlay.update_geometry(self.info.x, self.info.y, self.info.width, self.info.height)?;
            }
        }
        Ok(())
    }

    /// Update DDC index and reinitialize hardware control
    pub async fn update_ddc_index(&mut self, ddc_index: usize) -> Result<()> {
        self.config.ddc_index = ddc_index;

        // Reinitialize DDC controller
        if self.config.enable_hardware_dimming {
            let mut ddc = DdcController::new(self.config.ddc_index);
            match ddc.init() {
                Ok(_) => {
                    self.ddc = Some(ddc);
                }
                Err(e) => {
                    warn!("Failed to reinitialize DDC for index {}: {}", ddc_index, e);
                    self.ddc = None;
                }
            }
        }
        Ok(())
    }

    /// Update overlay color
    pub async fn update_overlay_color(&mut self, color: &str) -> Result<()> {
        self.config.overlay_color = color.to_string();

        // Update existing overlay
        if let Some(overlay) = &mut self.overlay {
            overlay.set_color(color.to_string())?;
        }
        Ok(())
    }

    /// Update hardware dimming enabled state
    pub async fn update_hw_enabled(&mut self, enabled: bool) -> Result<()> {
        self.config.enable_hardware_dimming = enabled;

        // Reinitialize or remove DDC controller
        if enabled {
            let mut ddc = DdcController::new(self.config.ddc_index);
            match ddc.init() {
                Ok(_) => {
                    info!("Enabled hardware dimming for monitor {}", self.config.monitor_index);
                    self.ddc = Some(ddc);
                }
                Err(e) => {
                    warn!("Failed to enable hardware dimming for monitor {}: {}", self.config.monitor_index, e);
                    self.ddc = None;
                }
            }
        } else {
            info!("Disabled hardware dimming for monitor {}", self.config.monitor_index);
            self.ddc = None;
        }
        Ok(())
    }

    /// Update software dimming enabled state
    pub async fn update_sw_enabled(&mut self, enabled: bool) -> Result<()> {
        self.config.enable_software_dimming = enabled;

        // Reinitialize or remove overlay
        if enabled {
            let overlay = OverlayWindow::new(
                self.app_handle.clone(),
                self.config.monitor_index,
                self.info.x,
                self.info.y,
                self.info.width,
                self.info.height,
                self.config.overlay_color.clone(),
            );

            match overlay.init() {
                Ok(_) => {
                    info!("Enabled software dimming for monitor {}", self.config.monitor_index);
                    self.overlay = Some(overlay);
                }
                Err(e) => {
                    warn!("Failed to enable software dimming for monitor {}: {}", self.config.monitor_index, e);
                    self.overlay = None;
                }
            }
        } else {
            info!("Disabled software dimming for monitor {}", self.config.monitor_index);
            // Hide and destroy overlay
            if let Some(overlay) = &self.overlay {
                let _ = overlay.hide();
                let _ = overlay.destroy();
            }
            self.overlay = None;
        }
        Ok(())
    }

    /// Update hardware dimming level
    pub fn update_hw_level(&mut self, level: u8) {
        self.config.hardware_dimming_level = level;
    }

    /// Update software dimming level
    pub fn update_sw_level(&mut self, level: f32) {
        self.config.software_dimming_level = level;
    }
}

impl Drop for MonitorController {
    fn drop(&mut self) {
        // Ensure monitor is restored when controller is dropped
        let _ = self.restore_immediate();

        // Explicitly destroy the overlay window
        if let Some(overlay) = &self.overlay {
            let _ = overlay.destroy();
        }
    }
}
