/// Overlay window for software dimming
use crate::error::{MonitorNapError, Result};
use tauri::{AppHandle, LogicalPosition, LogicalSize, Manager, WebviewUrl, WebviewWindowBuilder};
use tracing::{debug, error, info};

/// Sanitize color string to prevent JavaScript injection
fn sanitize_color(color: &str) -> Result<String> {
    // Only allow hex colors (#RGB, #RRGGBB, #RRGGBBAA)
    if color.starts_with('#')
        && (color.len() == 4 || color.len() == 7 || color.len() == 9)
        && color[1..].chars().all(|c| c.is_ascii_hexdigit())
    {
        return Ok(color.to_string());
    }
    Err(MonitorNapError::Window(format!(
        "Invalid color format: {}. Must be hex (#RGB or #RRGGBB)",
        color
    )))
}

/// Overlay window for software dimming
pub struct OverlayWindow {
    label: String,
    x: i32,
    y: i32,
    width: u32,
    height: u32,
    color: String,
    opacity: f32,
    app_handle: AppHandle,
}

impl OverlayWindow {
    /// Create a new overlay window
    pub fn new(
        app_handle: AppHandle,
        monitor_index: usize,
        x: i32,
        y: i32,
        width: u32,
        height: u32,
        color: String,
    ) -> Self {
        Self {
            label: format!("overlay-{}", monitor_index),
            x,
            y,
            width,
            height,
            color,
            opacity: 0.0,
            app_handle,
        }
    }

    /// Initialize the overlay window
    pub fn init(&self) -> Result<()> {
        // Sanitize color to prevent injection
        let safe_color = sanitize_color(&self.color)?;

        // Create a simple data URL for the overlay content
        let html_content = format!(
            r#"<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <style>
        * {{ margin: 0; padding: 0; overflow: hidden; }}
        body {{
            background-color: {};
            width: 100vw;
            height: 100vh;
            pointer-events: none;
            opacity: 0;
            transition: opacity 0.3s;
        }}
    </style>
</head>
<body></body>
</html>"#,
            safe_color
        );

        let data_url = format!("data:text/html,{}", urlencoding::encode(&html_content));

        // Create the overlay window
        let parsed_url = data_url.parse()
            .map_err(|e| MonitorNapError::Window(format!("Invalid data URL: {}", e)))?;

        match WebviewWindowBuilder::new(
            &self.app_handle,
            &self.label,
            WebviewUrl::External(parsed_url),
        )
        .title("MonitorNap Overlay")
        .position(self.x as f64, self.y as f64)
        .inner_size(self.width as f64, self.height as f64)
        .resizable(false)
        .decorations(false)
        .transparent(true)
        .always_on_top(true)
        .skip_taskbar(true)
        .visible(false)
        .focused(false)
        .build()
        {
            Ok(window) => {
                // Set the HTML content using safe JSON encoding
                let script = format!(
                    "document.body.style.backgroundColor = {}",
                    serde_json::to_string(&safe_color)
                        .unwrap_or_else(|_| String::from("\"#000000\""))
                );
                if let Err(e) = window.eval(script) {
                    error!("Failed to set overlay color: {}", e);
                }

                info!(
                    "Created overlay window {} at ({}, {}) size {}x{}",
                    self.label, self.x, self.y, self.width, self.height
                );
                Ok(())
            }
            Err(e) => {
                error!("Failed to create overlay window: {}", e);
                Err(MonitorNapError::Window(format!(
                    "Failed to create overlay: {}",
                    e
                )))
            }
        }
    }

    /// Show the overlay window
    pub fn show(&self) -> Result<()> {
        if let Some(window) = self.app_handle.get_webview_window(&self.label) {
            window
                .show()
                .map_err(|e| MonitorNapError::Window(format!("Failed to show overlay: {}", e)))?;
            debug!("Showed overlay {}", self.label);
            Ok(())
        } else {
            Err(MonitorNapError::Window(format!(
                "Overlay window {} not found",
                self.label
            )))
        }
    }

    /// Hide the overlay window
    pub fn hide(&self) -> Result<()> {
        if let Some(window) = self.app_handle.get_webview_window(&self.label) {
            window
                .hide()
                .map_err(|e| MonitorNapError::Window(format!("Failed to hide overlay: {}", e)))?;
            debug!("Hid overlay {}", self.label);
            Ok(())
        } else {
            Err(MonitorNapError::Window(format!(
                "Overlay window {} not found",
                self.label
            )))
        }
    }

    /// Set overlay opacity (0.0-1.0)
    pub fn set_opacity(&mut self, opacity: f32) -> Result<()> {
        let clamped = opacity.clamp(0.0, 1.0);
        self.opacity = clamped;

        if let Some(window) = self.app_handle.get_webview_window(&self.label) {
            // Control opacity via JavaScript/CSS - using JSON encoding for safety
            let script = format!("document.body.style.opacity = {}", clamped);
            window
                .eval(script)
                .map_err(|e| {
                    MonitorNapError::Window(format!("Failed to set overlay opacity: {}", e))
                })?;
            debug!("Set overlay {} opacity to {}", self.label, clamped);
            Ok(())
        } else {
            Err(MonitorNapError::Window(format!(
                "Overlay window {} not found",
                self.label
            )))
        }
    }

    /// Fade overlay to target opacity
    pub async fn fade_to(&mut self, target_opacity: f32, duration_secs: f32, steps: u32) {
        let start_opacity = self.opacity;
        let step_duration = std::time::Duration::from_secs_f32(duration_secs / steps as f32);
        let opacity_delta = (target_opacity - start_opacity) / steps as f32;

        for i in 1..=steps {
            let new_opacity = start_opacity + (opacity_delta * i as f32);
            if let Err(e) = self.set_opacity(new_opacity) {
                error!("Failed to set opacity during fade: {}", e);
                break;
            }
            tokio::time::sleep(step_duration).await;
        }

        // Ensure we reach exact target
        let _ = self.set_opacity(target_opacity);
    }

    /// Update overlay geometry
    pub fn update_geometry(&mut self, x: i32, y: i32, width: u32, height: u32) -> Result<()> {
        self.x = x;
        self.y = y;
        self.width = width;
        self.height = height;

        if let Some(window) = self.app_handle.get_webview_window(&self.label) {
            window
                .set_position(LogicalPosition::new(x as f64, y as f64))
                .map_err(|e| {
                    MonitorNapError::Window(format!("Failed to set position: {}", e))
                })?;
            window
                .set_size(LogicalSize::new(width as f64, height as f64))
                .map_err(|e| MonitorNapError::Window(format!("Failed to set size: {}", e)))?;
            debug!(
                "Updated overlay {} geometry to ({}, {}) {}x{}",
                self.label, x, y, width, height
            );
            Ok(())
        } else {
            Err(MonitorNapError::Window(format!(
                "Overlay window {} not found",
                self.label
            )))
        }
    }

    /// Set overlay color
    pub fn set_color(&mut self, color: String) -> Result<()> {
        // Sanitize color to prevent JavaScript injection
        let safe_color = sanitize_color(&color)?;
        self.color = safe_color.clone();

        if let Some(window) = self.app_handle.get_webview_window(&self.label) {
            // Use JSON encoding for safety
            let script = format!(
                "document.body.style.backgroundColor = {}",
                serde_json::to_string(&safe_color)
                    .unwrap_or_else(|_| String::from("\"#000000\""))
            );
            window
                .eval(script)
                .map_err(|e| MonitorNapError::Window(format!("Failed to set color: {}", e)))?;
            debug!("Set overlay {} color to {}", self.label, safe_color);
            Ok(())
        } else {
            Err(MonitorNapError::Window(format!(
                "Overlay window {} not found",
                self.label
            )))
        }
    }

    /// Destroy the overlay window
    pub fn destroy(&self) -> Result<()> {
        if let Some(window) = self.app_handle.get_webview_window(&self.label) {
            window
                .close()
                .map_err(|e| MonitorNapError::Window(format!("Failed to close overlay: {}", e)))?;
            info!("Destroyed overlay {}", self.label);
            Ok(())
        } else {
            // Already destroyed, not an error
            Ok(())
        }
    }
}

impl Drop for OverlayWindow {
    fn drop(&mut self) {
        let _ = self.destroy();
    }
}
