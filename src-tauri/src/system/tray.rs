/// System tray management
use tauri::{
    AppHandle, Emitter, Manager,
    menu::{Menu, MenuItem, PredefinedMenuItem, Submenu},
    tray::{MouseButton, MouseButtonState, TrayIconBuilder, TrayIconEvent},
};
use tracing::{debug, error, info};

/// System tray manager
pub struct TrayManager {
    app_handle: AppHandle,
}

impl TrayManager {
    /// Create a new tray manager
    pub fn new(app_handle: AppHandle) -> Self {
        Self { app_handle }
    }

    /// Initialize and build the system tray
    pub fn init(&self) -> Result<(), Box<dyn std::error::Error>> {
        info!("Initializing system tray");

        // Create menu items
        let show_hide = MenuItem::with_id(
            &self.app_handle,
            "show_hide",
            "Show/Hide",
            true,
            None::<&str>,
        )?;

        let toggle_awake = MenuItem::with_id(
            &self.app_handle,
            "toggle_awake",
            "Toggle Awake Mode",
            true,
            None::<&str>,
        )?;

        let nap_now = MenuItem::with_id(
            &self.app_handle,
            "nap_now",
            "Nap Now",
            true,
            None::<&str>,
        )?;

        // Pause submenu
        let pause_15 = MenuItem::with_id(
            &self.app_handle,
            "pause_15",
            "15 minutes",
            true,
            None::<&str>,
        )?;

        let pause_30 = MenuItem::with_id(
            &self.app_handle,
            "pause_30",
            "30 minutes",
            true,
            None::<&str>,
        )?;

        let pause_60 = MenuItem::with_id(
            &self.app_handle,
            "pause_60",
            "60 minutes",
            true,
            None::<&str>,
        )?;

        let pause_menu = Submenu::with_items(
            &self.app_handle,
            "Pause Dimming",
            true,
            &[&pause_15, &pause_30, &pause_60],
        )?;

        let resume_now = MenuItem::with_id(
            &self.app_handle,
            "resume_now",
            "Resume Now",
            true,
            None::<&str>,
        )?;

        let separator = PredefinedMenuItem::separator(&self.app_handle)?;

        let quit = MenuItem::with_id(
            &self.app_handle,
            "quit",
            "Exit",
            true,
            None::<&str>,
        )?;

        // Build the menu
        let menu = Menu::with_items(
            &self.app_handle,
            &[
                &show_hide,
                &toggle_awake,
                &separator,
                &nap_now,
                &pause_menu,
                &resume_now,
                &separator,
                &quit,
            ],
        )?;

        // Build the tray icon
        let _tray = TrayIconBuilder::new()
            .menu(&menu)
            .tooltip("MonitorNap")
            .on_menu_event(|app, event| {
                debug!("Tray menu event: {:?}", event.id);

                match event.id.as_ref() {
                    "show_hide" => {
                        if let Some(window) = app.get_webview_window("main") {
                            if window.is_visible().unwrap_or(false) {
                                let _ = window.hide();
                            } else {
                                let _ = window.show();
                                let _ = window.set_focus();
                            }
                        }
                    }
                    "toggle_awake" => {
                        let _ = app.emit("toggle-awake-mode", ());
                    }
                    "nap_now" => {
                        let _ = app.emit("nap-now", ());
                    }
                    "pause_15" => {
                        let _ = app.emit("pause-dimming", 15);
                    }
                    "pause_30" => {
                        let _ = app.emit("pause-dimming", 30);
                    }
                    "pause_60" => {
                        let _ = app.emit("pause-dimming", 60);
                    }
                    "resume_now" => {
                        let _ = app.emit("resume-now", ());
                    }
                    "quit" => {
                        info!("Quit requested from tray menu");
                        app.exit(0);
                    }
                    _ => {}
                }
            })
            .on_tray_icon_event(|tray, event| {
                if let TrayIconEvent::Click {
                    button: MouseButton::Left,
                    button_state: MouseButtonState::Up,
                    ..
                } = event
                {
                    debug!("Tray icon left-clicked");
                    let app = tray.app_handle();
                    if let Some(window) = app.get_webview_window("main") {
                        if window.is_visible().unwrap_or(false) {
                            let _ = window.hide();
                        } else {
                            let _ = window.show();
                            let _ = window.set_focus();
                        }
                    }
                }
            })
            .build(&self.app_handle)?;

        info!("System tray initialized successfully");
        Ok(())
    }

    /// Update tray tooltip
    #[allow(dead_code)]
    pub fn update_tooltip(&self, text: &str) {
        if let Some(tray) = self.app_handle.tray_by_id("main") {
            if let Err(e) = tray.set_tooltip(Some(text)) {
                error!("Failed to update tray tooltip: {}", e);
            }
        }
    }

    /// Update tray icon (for different states)
    #[allow(dead_code)]
    pub fn update_icon(&self, icon_path: &str) {
        // This can be implemented if you want different icons for different states
        debug!("Update tray icon: {}", icon_path);
    }
}
