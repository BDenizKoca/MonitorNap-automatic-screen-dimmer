// Prevents additional console window on Windows in release builds
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

mod config;
mod error;
mod monitor;
mod system;

use config::{AppConfig, ConfigManager, MonitorConfig};
use error::{MonitorNapError, Result};
use monitor::{get_monitors, MonitorController, MonitorInfo};
use system::{ActivityMonitor, HotkeyManager, TrayManager};

use std::sync::Arc;
use std::time::Duration;
use tauri::{AppHandle, Emitter, Manager, State};
use tokio::sync::Mutex;
use tracing::{error, info, warn};

/// Monitoring loop poll interval in seconds
const MONITOR_POLL_INTERVAL_SECS: u64 = 2;

/// Application state
pub struct AppState {
    config_manager: Arc<Mutex<ConfigManager>>,
    monitors: Arc<Mutex<Vec<MonitorController>>>,
    activity_monitor: Arc<ActivityMonitor>,
    hotkey_manager: Arc<HotkeyManager>,
    awake_mode: Arc<Mutex<bool>>,
    pause_end_time: Arc<Mutex<Option<std::time::Instant>>>,
}

impl AppState {
    async fn new(app_handle: AppHandle, hotkey_manager: Arc<HotkeyManager>) -> Result<Self> {
        // Load configuration
        let config_manager = ConfigManager::new()?;
        let config = config_manager.get().clone();

        // Initialize activity monitor
        let activity_monitor = Arc::new(ActivityMonitor::new());
        activity_monitor.clone().start();

        // Initialize monitors
        let monitor_infos = get_monitors();
        let mut monitors = Vec::new();

        // Auto-detect monitors if config is empty or mismatched
        let mut config_manager = config_manager;
        let needs_auto_detect = config.monitors.is_empty() || config.monitors.len() != monitor_infos.len();

        let monitor_configs = if needs_auto_detect {
            info!("Auto-detecting {} monitors", monitor_infos.len());
            let auto_configs: Vec<MonitorConfig> = monitor_infos
                .iter()
                .enumerate()
                .map(|(i, _)| MonitorConfig {
                    monitor_index: i,
                    display_index: i,
                    ddc_index: i,
                    ..Default::default()
                })
                .collect();

            // Save auto-detected configs
            config_manager.get_mut().monitors = auto_configs.clone();
            if let Err(e) = config_manager.save() {
                warn!("Failed to save auto-detected monitor configs: {}", e);
            } else {
                info!("Saved auto-detected monitor configurations");
            }

            auto_configs
        } else {
            config.monitors.clone()
        };

        for (cfg, info) in monitor_configs.iter().zip(monitor_infos.iter()) {
            match MonitorController::new(app_handle.clone(), cfg.clone(), info.clone()) {
                Ok(controller) => {
                    monitors.push(controller);
                }
                Err(e) => {
                    warn!("Failed to initialize monitor {}: {}", cfg.monitor_index, e);
                }
            }
        }

        info!("Initialized {} monitor controllers", monitors.len());

        Ok(Self {
            config_manager: Arc::new(Mutex::new(config_manager)),
            monitors: Arc::new(Mutex::new(monitors)),
            activity_monitor,
            hotkey_manager,
            awake_mode: Arc::new(Mutex::new(config.awake_mode)),
            pause_end_time: Arc::new(Mutex::new(None)),
        })
    }

    /// Start the monitoring loop
    async fn start_monitoring(state: Arc<Mutex<Self>>, app_handle: AppHandle) {
        tokio::spawn(async move {
            loop {
                tokio::time::sleep(Duration::from_secs(MONITOR_POLL_INTERVAL_SECS)).await;

                // Minimize lock scope - extract values needed and release immediately
                let (awake, cursor_x, cursor_y, inactivity_limit, fade_time, fade_steps) = {
                    let state_lock = state.lock().await;

                    // Check and handle pause timer
                    let mut pause_end = state_lock.pause_end_time.lock().await;
                    if let Some(end_time) = *pause_end {
                        if std::time::Instant::now() >= end_time {
                            *pause_end = None;
                            drop(pause_end); // Release pause_end lock before acquiring awake_mode

                            // Disable awake mode after pause expires
                            *state_lock.awake_mode.lock().await = false;
                            let _ = app_handle.emit("awake-mode-changed", false);
                            info!("Pause timer expired, resuming dimming");
                        }
                    } else {
                        drop(pause_end); // Release explicitly
                    }

                    let awake = *state_lock.awake_mode.lock().await;
                    let cursor_pos = state_lock.activity_monitor.get_cursor_pos().await;

                    let config_lock = state_lock.config_manager.lock().await;
                    let config_values = (
                        config_lock.get().inactivity_limit as u64,
                        config_lock.get().overlay_fade_time,
                        config_lock.get().overlay_fade_steps,
                    );
                    drop(config_lock); // Release config lock

                    (awake, cursor_pos.0, cursor_pos.1, config_values.0, config_values.1, config_values.2)
                    // state_lock is dropped here
                };

                // Handle awake mode restoration without holding state lock
                if awake {
                    let state_lock = state.lock().await;
                    let monitors = state_lock.monitors.lock().await;
                    for monitor in monitors.iter() {
                        if monitor.is_dimmed() {
                            let _ = monitor.restore_immediate();
                        }
                    }
                    drop(monitors);
                    drop(state_lock);
                    continue;
                }

                // Check each monitor without holding state lock continuously
                {
                    let state_lock = state.lock().await;
                    let monitors = state_lock.monitors.lock().await;

                    for monitor in monitors.iter() {
                        // Check if cursor is on this monitor
                        if monitor.is_cursor_on_monitor(cursor_x, cursor_y) {
                            monitor.update_activity().await;

                            // Restore if dimmed
                            if monitor.is_dimmed() {
                                let _ = monitor.restore(fade_time, fade_steps).await;
                            }
                        } else {
                            // Check inactivity
                            let idle_time = monitor.get_idle_time().await;

                            if idle_time >= inactivity_limit && !monitor.is_dimmed() {
                                // Dim this monitor
                                let _ = monitor.dim(fade_time, fade_steps).await;
                            }
                        }
                    }
                    // monitors and state_lock dropped here
                }
            }
        });
    }
}

// Tauri Commands

#[tauri::command]
async fn get_config(state: State<'_, Arc<Mutex<AppState>>>) -> Result<AppConfig> {
    let state = state.lock().await;
    let config = state.config_manager.lock().await;
    Ok(config.get().clone())
}

#[tauri::command]
async fn save_config(
    config: AppConfig,
    state: State<'_, Arc<Mutex<AppState>>>,
) -> Result<()> {
    let state = state.lock().await;
    let mut config_manager = state.config_manager.lock().await;
    config_manager.update(config)?;
    info!("Configuration saved");
    Ok(())
}

#[tauri::command]
async fn get_monitors_info() -> Result<Vec<MonitorInfo>> {
    Ok(get_monitors())
}

#[tauri::command]
async fn toggle_awake_mode(
    state: State<'_, Arc<Mutex<AppState>>>,
    app_handle: AppHandle,
) -> Result<bool> {
    let state_lock = state.lock().await;
    let mut awake = state_lock.awake_mode.lock().await;
    *awake = !*awake;

    let new_state = *awake;
    info!("Awake mode toggled: {}", new_state);

    // Clear pause timer when manually toggling
    *state_lock.pause_end_time.lock().await = None;

    // Emit event to frontend
    let _ = app_handle.emit("awake-mode-changed", new_state);

    // Update config
    let mut config_manager = state_lock.config_manager.lock().await;
    config_manager.get_mut().awake_mode = new_state;
    let _ = config_manager.save();

    Ok(new_state)
}

#[tauri::command]
async fn set_awake_mode(
    enabled: bool,
    state: State<'_, Arc<Mutex<AppState>>>,
    app_handle: AppHandle,
) -> Result<()> {
    let state_lock = state.lock().await;
    let mut awake = state_lock.awake_mode.lock().await;
    *awake = enabled;

    info!("Awake mode set to: {}", enabled);

    let _ = app_handle.emit("awake-mode-changed", enabled);

    let mut config_manager = state_lock.config_manager.lock().await;
    config_manager.get_mut().awake_mode = enabled;
    let _ = config_manager.save();

    Ok(())
}

#[tauri::command]
async fn nap_now(state: State<'_, Arc<Mutex<AppState>>>) -> Result<()> {
    info!("Nap now triggered");
    let state_lock = state.lock().await;
    let monitors = state_lock.monitors.lock().await;
    let config = state_lock.config_manager.lock().await;

    let fade_time = config.get().overlay_fade_time;
    let fade_steps = config.get().overlay_fade_steps;

    for monitor in monitors.iter() {
        let _ = monitor.dim(fade_time, fade_steps).await;
    }

    Ok(())
}

#[tauri::command]
async fn resume_now(
    state: State<'_, Arc<Mutex<AppState>>>,
    app_handle: AppHandle,
) -> Result<()> {
    info!("Resume now triggered");
    let state_lock = state.lock().await;

    // Clear pause timer
    *state_lock.pause_end_time.lock().await = None;

    // Disable awake mode
    *state_lock.awake_mode.lock().await = false;
    let _ = app_handle.emit("awake-mode-changed", false);

    let monitors = state_lock.monitors.lock().await;
    let config = state_lock.config_manager.lock().await;

    let fade_time = config.get().overlay_fade_time;
    let fade_steps = config.get().overlay_fade_steps;

    for monitor in monitors.iter() {
        let _ = monitor.restore(fade_time, fade_steps).await;
    }

    let mut config_manager = state_lock.config_manager.lock().await;
    config_manager.get_mut().awake_mode = false;
    let _ = config_manager.save();

    Ok(())
}

#[tauri::command]
async fn pause_dimming(
    minutes: u64,
    state: State<'_, Arc<Mutex<AppState>>>,
    app_handle: AppHandle,
) -> Result<()> {
    info!("Pausing dimming for {} minutes", minutes);
    let state_lock = state.lock().await;

    // Enable awake mode
    *state_lock.awake_mode.lock().await = true;

    // Set pause end time
    let end_time = std::time::Instant::now() + Duration::from_secs(minutes * 60);
    *state_lock.pause_end_time.lock().await = Some(end_time);

    let _ = app_handle.emit("awake-mode-changed", true);
    let _ = app_handle.emit("pause-started", minutes);

    Ok(())
}

#[tauri::command]
async fn identify_monitor(
    monitor_index: usize,
    state: State<'_, Arc<Mutex<AppState>>>,
) -> Result<()> {
    info!("Identifying monitor {}", monitor_index);
    let state_lock = state.lock().await;
    let monitors = state_lock.monitors.lock().await;

    if let Some(monitor) = monitors.iter().find(|m| m.index() == monitor_index) {
        monitor.identify().await;
        Ok(())
    } else {
        Err(MonitorNapError::Monitor(format!(
            "Monitor {} not found",
            monitor_index
        )))
    }
}

#[tauri::command]
async fn register_hotkey(
    hotkey: String,
    state: State<'_, Arc<Mutex<AppState>>>,
    app_handle: AppHandle,
) -> Result<()> {
    info!("Registering hotkey: {}", hotkey);
    let state_lock = state.lock().await;

    let app_handle_clone = app_handle.clone();
    state_lock
        .hotkey_manager
        .register(&hotkey, move || {
            let _ = app_handle_clone.emit("toggle-awake-mode", ());
        })?;

    // Update config
    let mut config_manager = state_lock.config_manager.lock().await;
    config_manager.get_mut().awake_mode_shortcut = hotkey;
    config_manager.save()?;

    Ok(())
}

#[tauri::command]
async fn get_pause_remaining(state: State<'_, Arc<Mutex<AppState>>>) -> Result<Option<u64>> {
    let state_lock = state.lock().await;
    let pause_end = state_lock.pause_end_time.lock().await;

    if let Some(end_time) = *pause_end {
        let now = std::time::Instant::now();
        if end_time > now {
            let remaining = (end_time - now).as_secs() / 60;
            return Ok(Some(remaining));
        }
    }

    Ok(None)
}

#[tauri::command]
async fn update_monitor_display_index(
    monitor_index: usize,
    display_index: usize,
    state: State<'_, Arc<Mutex<AppState>>>,
) -> Result<()> {
    let state_lock = state.lock().await;
    let mut monitors = state_lock.monitors.lock().await;

    if let Some(monitor) = monitors.get_mut(monitor_index) {
        monitor.update_display_index(display_index).await?;

        // Update config
        let mut config_manager = state_lock.config_manager.lock().await;
        if let Some(cfg) = config_manager.get_mut().monitors.get_mut(monitor_index) {
            cfg.display_index = display_index;
        }
        config_manager.save()?;
    }

    Ok(())
}

#[tauri::command]
async fn update_monitor_ddc_index(
    monitor_index: usize,
    ddc_index: usize,
    state: State<'_, Arc<Mutex<AppState>>>,
) -> Result<()> {
    let state_lock = state.lock().await;
    let mut monitors = state_lock.monitors.lock().await;

    if let Some(monitor) = monitors.get_mut(monitor_index) {
        monitor.update_ddc_index(ddc_index).await?;

        // Update config
        let mut config_manager = state_lock.config_manager.lock().await;
        if let Some(cfg) = config_manager.get_mut().monitors.get_mut(monitor_index) {
            cfg.ddc_index = ddc_index;
        }
        config_manager.save()?;
    }

    Ok(())
}

#[tauri::command]
async fn update_monitor_hw_enabled(
    monitor_index: usize,
    enabled: bool,
    state: State<'_, Arc<Mutex<AppState>>>,
) -> Result<()> {
    let state_lock = state.lock().await;
    let mut config_manager = state_lock.config_manager.lock().await;

    // Update config
    if let Some(cfg) = config_manager.get_mut().monitors.get_mut(monitor_index) {
        cfg.enable_hardware_dimming = enabled;
        config_manager.save()?;
    }

    // Update monitor controller
    let mut monitors = state_lock.monitors.lock().await;
    if let Some(controller) = monitors.get_mut(monitor_index) {
        controller.update_hw_enabled(enabled).await?;
    }

    Ok(())
}

#[tauri::command]
async fn update_monitor_sw_enabled(
    monitor_index: usize,
    enabled: bool,
    state: State<'_, Arc<Mutex<AppState>>>,
) -> Result<()> {
    let state_lock = state.lock().await;
    let mut config_manager = state_lock.config_manager.lock().await;

    // Update config
    if let Some(cfg) = config_manager.get_mut().monitors.get_mut(monitor_index) {
        cfg.enable_software_dimming = enabled;
        config_manager.save()?;
    }

    // Update monitor controller
    let mut monitors = state_lock.monitors.lock().await;
    if let Some(controller) = monitors.get_mut(monitor_index) {
        controller.update_sw_enabled(enabled).await?;
    }

    Ok(())
}

#[tauri::command]
async fn update_monitor_hw_level(
    monitor_index: usize,
    level: u8,
    state: State<'_, Arc<Mutex<AppState>>>,
) -> Result<()> {
    let state_lock = state.lock().await;
    let mut config_manager = state_lock.config_manager.lock().await;

    // Update config
    if let Some(cfg) = config_manager.get_mut().monitors.get_mut(monitor_index) {
        cfg.hardware_dimming_level = level.min(100);
        config_manager.save()?;
    }

    // Update monitor controller
    let mut monitors = state_lock.monitors.lock().await;
    if let Some(controller) = monitors.get_mut(monitor_index) {
        controller.update_hw_level(level.min(100));
    }

    Ok(())
}

#[tauri::command]
async fn update_monitor_sw_level(
    monitor_index: usize,
    level: f32,
    state: State<'_, Arc<Mutex<AppState>>>,
) -> Result<()> {
    let state_lock = state.lock().await;
    let mut config_manager = state_lock.config_manager.lock().await;

    // Update config
    if let Some(cfg) = config_manager.get_mut().monitors.get_mut(monitor_index) {
        cfg.software_dimming_level = level.clamp(0.0, 1.0);
        config_manager.save()?;
    }

    // Update monitor controller
    let mut monitors = state_lock.monitors.lock().await;
    if let Some(controller) = monitors.get_mut(monitor_index) {
        controller.update_sw_level(level.clamp(0.0, 1.0));
    }

    Ok(())
}

#[tauri::command]
async fn update_monitor_color(
    monitor_index: usize,
    color: String,
    state: State<'_, Arc<Mutex<AppState>>>,
) -> Result<()> {
    let state_lock = state.lock().await;
    let mut monitors = state_lock.monitors.lock().await;

    if let Some(monitor) = monitors.get_mut(monitor_index) {
        monitor.update_overlay_color(&color).await?;

        // Update config
        let mut config_manager = state_lock.config_manager.lock().await;
        if let Some(cfg) = config_manager.get_mut().monitors.get_mut(monitor_index) {
            cfg.overlay_color = color;
        }
        config_manager.save()?;
    }

    Ok(())
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    // Initialize tracing
    tracing_subscriber::fmt()
        .with_env_filter(
            tracing_subscriber::EnvFilter::from_default_env()
                .add_directive(tracing::Level::INFO.into()),
        )
        .init();

    tauri::Builder::default()
        .setup(|app| {
            let app_handle = app.handle().clone();

            // IMPORTANT: Create HotkeyManager on main thread (required for Windows)
            let hotkey_manager = Arc::new(
                HotkeyManager::new()
                    .expect("Failed to create hotkey manager")
            );

            // Initialize application state
            let state = tauri::async_runtime::block_on(async {
                AppState::new(app_handle.clone(), hotkey_manager.clone())
                    .await
                    .expect("Failed to initialize application state")
            });

            let state = Arc::new(Mutex::new(state));

            // Start monitoring loop
            let state_clone = state.clone();
            let app_handle_clone = app_handle.clone();
            tauri::async_runtime::spawn(async move {
                AppState::start_monitoring(state_clone, app_handle_clone).await;
            });

            // Register hotkey on main thread (required for Windows)
            let hotkey_manager_clone = hotkey_manager.clone();
            let app_handle_clone = app_handle.clone();

            // Load default hotkey from config
            let hotkey_str = tauri::async_runtime::block_on(async {
                let state_lock = state.lock().await;
                let config = state_lock.config_manager.lock().await;
                config.get().awake_mode_shortcut.clone()
            });

            // Register on main thread
            let app_handle_inner = app_handle_clone.clone();
            if let Err(e) = hotkey_manager_clone.register(&hotkey_str, move || {
                let _ = app_handle_inner.emit("toggle-awake-mode", ());
            }) {
                warn!("Failed to register default hotkey: {}", e);
            }

            // Start hotkey listener in async context
            tauri::async_runtime::spawn(async move {
                hotkey_manager_clone.start_listening().await;
            });

            // Initialize system tray
            let tray = TrayManager::new(app_handle.clone());
            if let Err(e) = tray.init() {
                error!("Failed to initialize system tray: {}", e);
            }

            // Manage app state
            app.manage(state);

            // Handle window close - minimize to tray instead
            if let Some(window) = app.get_webview_window("main") {
                let window_clone = window.clone();
                window.on_window_event(move |event| {
                    if let tauri::WindowEvent::CloseRequested { api, .. } = event {
                        // Prevent window from closing, hide it instead
                        api.prevent_close();
                        let _ = window_clone.hide();
                    }
                });

                // Check if we should start minimized
                tauri::async_runtime::block_on(async {
                    if let Some(state) = app.try_state::<Arc<Mutex<AppState>>>() {
                        let state_lock = state.lock().await;
                        let config = state_lock.config_manager.lock().await;
                        if config.get().start_minimized {
                            let _ = window.hide();
                        } else {
                            let _ = window.show();
                        }
                    }
                });
            }

            info!("MonitorNap initialized successfully");
            Ok(())
        })
        .plugin(tauri_plugin_shell::init())
        .plugin(tauri_plugin_dialog::init())
        .plugin(tauri_plugin_fs::init())
        .plugin(tauri_plugin_autostart::init(
            tauri_plugin_autostart::MacosLauncher::LaunchAgent,
            None,
        ))
        .invoke_handler(tauri::generate_handler![
            get_config,
            save_config,
            get_monitors_info,
            toggle_awake_mode,
            set_awake_mode,
            nap_now,
            resume_now,
            pause_dimming,
            identify_monitor,
            register_hotkey,
            get_pause_remaining,
            update_monitor_display_index,
            update_monitor_ddc_index,
            update_monitor_hw_enabled,
            update_monitor_sw_enabled,
            update_monitor_hw_level,
            update_monitor_sw_level,
            update_monitor_color,
        ])
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}

fn main() {
    run();
}
