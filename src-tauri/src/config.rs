/// Configuration management for MonitorNap
use serde::{Deserialize, Serialize};
use std::fs;
use std::path::{Path, PathBuf};
use crate::error::{MonitorNapError, Result};
use tracing::{info, warn};

/// Global application configuration
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(default)]
pub struct AppConfig {
    /// List of monitor configurations
    pub monitors: Vec<MonitorConfig>,

    /// Inactivity timeout in seconds before dimming
    pub inactivity_limit: u32,

    /// Overlay fade animation time in seconds
    pub overlay_fade_time: f32,

    /// Number of steps in fade animation
    pub overlay_fade_steps: u32,

    /// Awake mode (prevents dimming when true)
    pub awake_mode: bool,

    /// Debug mode
    pub debug_mode: bool,

    /// Start on system startup
    pub start_on_startup: bool,

    /// Start minimized to tray
    pub start_minimized: bool,

    /// Global hotkey for awake mode toggle
    pub awake_mode_shortcut: String,
}

impl Default for AppConfig {
    fn default() -> Self {
        Self {
            monitors: Vec::new(),
            inactivity_limit: 10,
            overlay_fade_time: 0.5,
            overlay_fade_steps: 10,
            awake_mode: false,
            debug_mode: false,
            start_on_startup: false,
            start_minimized: false,
            awake_mode_shortcut: "Ctrl+Alt+A".to_string(),
        }
    }
}

/// Per-monitor configuration
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(default)]
pub struct MonitorConfig {
    /// Logical monitor index
    pub monitor_index: usize,

    /// Display index for overlay positioning
    pub display_index: usize,

    /// DDC/CI index for hardware control
    pub ddc_index: usize,

    /// Enable hardware dimming via DDC/CI
    pub enable_hardware_dimming: bool,

    /// Enable software dimming via overlay
    pub enable_software_dimming: bool,

    /// Hardware dimming level (0-100%)
    pub hardware_dimming_level: u8,

    /// Software dimming level (0.0-1.0 opacity)
    pub software_dimming_level: f32,

    /// Overlay color in hex format
    pub overlay_color: String,
}

impl Default for MonitorConfig {
    fn default() -> Self {
        Self {
            monitor_index: 0,
            display_index: 0,
            ddc_index: 0,
            enable_hardware_dimming: true,
            enable_software_dimming: true,
            hardware_dimming_level: 30,
            software_dimming_level: 0.5,
            overlay_color: "#000000".to_string(),
        }
    }
}

/// Configuration manager handles loading and saving configuration
pub struct ConfigManager {
    config_path: PathBuf,
    pub config: AppConfig,
}

impl ConfigManager {
    /// Create a new configuration manager
    pub fn new() -> Result<Self> {
        let config_path = Self::get_config_path()?;
        let config = Self::load_from_path(&config_path)?;

        Ok(Self {
            config_path,
            config,
        })
    }

    /// Get the platform-specific configuration file path
    fn get_config_path() -> Result<PathBuf> {
        #[cfg(target_os = "windows")]
        {
            if let Some(appdata) = std::env::var_os("APPDATA") {
                let config_dir = PathBuf::from(appdata).join("MonitorNap");
                fs::create_dir_all(&config_dir)
                    .map_err(|e| MonitorNapError::Config(format!("Failed to create config directory: {}", e)))?;
                Ok(config_dir.join("monitornap_config.json"))
            } else {
                Err(MonitorNapError::Config("APPDATA environment variable not found".to_string()))
            }
        }

        #[cfg(target_os = "macos")]
        {
            if let Some(home) = dirs::home_dir() {
                let config_dir = home.join(".monitornap");
                fs::create_dir_all(&config_dir)
                    .map_err(|e| MonitorNapError::Config(format!("Failed to create config directory: {}", e)))?;
                Ok(config_dir.join("monitornap_config.json"))
            } else {
                Err(MonitorNapError::Config("Failed to get home directory".to_string()))
            }
        }

        #[cfg(target_os = "linux")]
        {
            if let Some(config_home) = std::env::var_os("XDG_CONFIG_HOME") {
                let config_dir = PathBuf::from(config_home).join("monitornap");
                fs::create_dir_all(&config_dir)
                    .map_err(|e| MonitorNapError::Config(format!("Failed to create config directory: {}", e)))?;
                Ok(config_dir.join("monitornap_config.json"))
            } else if let Some(home) = dirs::home_dir() {
                let config_dir = home.join(".config").join("monitornap");
                fs::create_dir_all(&config_dir)
                    .map_err(|e| MonitorNapError::Config(format!("Failed to create config directory: {}", e)))?;
                Ok(config_dir.join("monitornap_config.json"))
            } else {
                Err(MonitorNapError::Config("Failed to get config directory".to_string()))
            }
        }
    }

    /// Load configuration from file
    fn load_from_path(path: &Path) -> Result<AppConfig> {
        if !path.exists() {
            info!("Config file not found at {:?}, creating default", path);
            let default_config = AppConfig::default();
            let json = serde_json::to_string_pretty(&default_config)?;
            fs::write(path, json)?;
            return Ok(default_config);
        }

        let content = fs::read_to_string(path)
            .map_err(|e| MonitorNapError::Config(format!("Failed to read config file: {}", e)))?;

        match serde_json::from_str::<AppConfig>(&content) {
            Ok(config) => {
                info!("Loaded configuration from {:?}", path);
                Ok(config)
            }
            Err(e) => {
                warn!("Failed to parse config file: {}. Using default config.", e);
                Ok(AppConfig::default())
            }
        }
    }

    /// Save current configuration to file
    pub fn save(&self) -> Result<()> {
        let json = serde_json::to_string_pretty(&self.config)?;
        fs::write(&self.config_path, json)
            .map_err(|e| MonitorNapError::Config(format!("Failed to save config: {}", e)))?;
        info!("Configuration saved to {:?}", self.config_path);
        Ok(())
    }

    /// Update configuration and save
    pub fn update(&mut self, config: AppConfig) -> Result<()> {
        self.config = config;
        self.save()
    }

    /// Get a reference to the current configuration
    pub fn get(&self) -> &AppConfig {
        &self.config
    }

    /// Get a mutable reference to the configuration
    pub fn get_mut(&mut self) -> &mut AppConfig {
        &mut self.config
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_default_config() {
        let config = AppConfig::default();
        assert_eq!(config.inactivity_limit, 10);
        assert_eq!(config.awake_mode, false);
        assert_eq!(config.awake_mode_shortcut, "Ctrl+Alt+A");
    }

    #[test]
    fn test_monitor_config_default() {
        let config = MonitorConfig::default();
        assert_eq!(config.hardware_dimming_level, 30);
        assert_eq!(config.software_dimming_level, 0.5);
        assert_eq!(config.overlay_color, "#000000");
    }
}
