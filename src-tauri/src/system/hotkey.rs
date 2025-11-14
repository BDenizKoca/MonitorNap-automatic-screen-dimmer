/// Global hotkey management
use crate::error::{MonitorNapError, Result};
use global_hotkey::{
    hotkey::{Code, HotKey, Modifiers},
    GlobalHotKeyEvent, GlobalHotKeyManager,
};
use std::sync::Arc;
use tokio::sync::Mutex;
use tracing::{debug, info};

/// Callback type for hotkey events
pub type HotkeyCallback = Arc<dyn Fn() + Send + Sync>;

/// Global hotkey manager
pub struct HotkeyManager {
    manager: Arc<Mutex<GlobalHotKeyManager>>,
    current_hotkey: Arc<Mutex<Option<HotKey>>>,
    callback: Arc<Mutex<Option<HotkeyCallback>>>,
}

impl HotkeyManager {
    /// Create a new hotkey manager
    pub fn new() -> Result<Self> {
        let manager = GlobalHotKeyManager::new()
            .map_err(|e| MonitorNapError::Hotkey(format!("Failed to create hotkey manager: {}", e)))?;

        Ok(Self {
            manager: Arc::new(Mutex::new(manager)),
            current_hotkey: Arc::new(Mutex::new(None)),
            callback: Arc::new(Mutex::new(None)),
        })
    }

    /// Parse hotkey string (e.g., "Ctrl+Alt+A") into HotKey
    fn parse_hotkey(hotkey_str: &str) -> Result<HotKey> {
        let parts: Vec<&str> = hotkey_str.split('+').map(|s| s.trim()).collect();

        if parts.is_empty() {
            return Err(MonitorNapError::Hotkey("Empty hotkey string".to_string()));
        }

        let mut modifiers = Modifiers::empty();
        let mut key_code: Option<Code> = None;

        for part in parts {
            let part_lower = part.to_lowercase();
            match part_lower.as_str() {
                "ctrl" | "control" => modifiers |= Modifiers::CONTROL,
                "alt" => modifiers |= Modifiers::ALT,
                "shift" => modifiers |= Modifiers::SHIFT,
                "super" | "win" | "meta" | "cmd" => modifiers |= Modifiers::SUPER,
                // Single letter keys
                "a" => key_code = Some(Code::KeyA),
                "b" => key_code = Some(Code::KeyB),
                "c" => key_code = Some(Code::KeyC),
                "d" => key_code = Some(Code::KeyD),
                "e" => key_code = Some(Code::KeyE),
                "f" => key_code = Some(Code::KeyF),
                "g" => key_code = Some(Code::KeyG),
                "h" => key_code = Some(Code::KeyH),
                "i" => key_code = Some(Code::KeyI),
                "j" => key_code = Some(Code::KeyJ),
                "k" => key_code = Some(Code::KeyK),
                "l" => key_code = Some(Code::KeyL),
                "m" => key_code = Some(Code::KeyM),
                "n" => key_code = Some(Code::KeyN),
                "o" => key_code = Some(Code::KeyO),
                "p" => key_code = Some(Code::KeyP),
                "q" => key_code = Some(Code::KeyQ),
                "r" => key_code = Some(Code::KeyR),
                "s" => key_code = Some(Code::KeyS),
                "t" => key_code = Some(Code::KeyT),
                "u" => key_code = Some(Code::KeyU),
                "v" => key_code = Some(Code::KeyV),
                "w" => key_code = Some(Code::KeyW),
                "x" => key_code = Some(Code::KeyX),
                "y" => key_code = Some(Code::KeyY),
                "z" => key_code = Some(Code::KeyZ),
                // Function keys
                "f1" => key_code = Some(Code::F1),
                "f2" => key_code = Some(Code::F2),
                "f3" => key_code = Some(Code::F3),
                "f4" => key_code = Some(Code::F4),
                "f5" => key_code = Some(Code::F5),
                "f6" => key_code = Some(Code::F6),
                "f7" => key_code = Some(Code::F7),
                "f8" => key_code = Some(Code::F8),
                "f9" => key_code = Some(Code::F9),
                "f10" => key_code = Some(Code::F10),
                "f11" => key_code = Some(Code::F11),
                "f12" => key_code = Some(Code::F12),
                // Number keys
                "0" => key_code = Some(Code::Digit0),
                "1" => key_code = Some(Code::Digit1),
                "2" => key_code = Some(Code::Digit2),
                "3" => key_code = Some(Code::Digit3),
                "4" => key_code = Some(Code::Digit4),
                "5" => key_code = Some(Code::Digit5),
                "6" => key_code = Some(Code::Digit6),
                "7" => key_code = Some(Code::Digit7),
                "8" => key_code = Some(Code::Digit8),
                "9" => key_code = Some(Code::Digit9),
                // Special keys
                "space" => key_code = Some(Code::Space),
                "enter" | "return" => key_code = Some(Code::Enter),
                "esc" | "escape" => key_code = Some(Code::Escape),
                "tab" => key_code = Some(Code::Tab),
                "backspace" => key_code = Some(Code::Backspace),
                _ => {
                    return Err(MonitorNapError::Hotkey(format!(
                        "Unknown key: {}",
                        part
                    )))
                }
            }
        }

        if let Some(code) = key_code {
            Ok(HotKey::new(Some(modifiers), code))
        } else {
            Err(MonitorNapError::Hotkey(
                "No key code found in hotkey string".to_string(),
            ))
        }
    }

    /// Register a hotkey with a callback
    pub async fn register<F>(&self, hotkey_str: &str, callback: F) -> Result<()>
    where
        F: Fn() + Send + Sync + 'static,
    {
        // Unregister existing hotkey
        self.unregister().await?;

        // Parse and create new hotkey
        let hotkey = Self::parse_hotkey(hotkey_str)?;

        // Register with the system
        let manager = self.manager.lock().await;
        manager
            .register(hotkey)
            .map_err(|e| MonitorNapError::Hotkey(format!("Failed to register hotkey: {}", e)))?;

        info!("Registered global hotkey: {}", hotkey_str);

        // Store hotkey and callback
        *self.current_hotkey.lock().await = Some(hotkey);
        *self.callback.lock().await = Some(Arc::new(callback));

        Ok(())
    }

    /// Unregister the current hotkey
    pub async fn unregister(&self) -> Result<()> {
        let mut current = self.current_hotkey.lock().await;

        if let Some(hotkey) = current.take() {
            let manager = self.manager.lock().await;
            manager.unregister(hotkey).map_err(|e| {
                MonitorNapError::Hotkey(format!("Failed to unregister hotkey: {}", e))
            })?;
            info!("Unregistered global hotkey");
        }

        *self.callback.lock().await = None;
        Ok(())
    }

    /// Start listening for hotkey events
    pub fn start_listening(self: Arc<Self>) {
        tokio::spawn(async move {
            let receiver = GlobalHotKeyEvent::receiver();

            loop {
                if let Ok(event) = receiver.try_recv() {
                    debug!("Hotkey event received: {:?}", event);

                    // Check if this matches our registered hotkey
                    let current = self.current_hotkey.lock().await;
                    if let Some(hotkey) = current.as_ref() {
                        if event.id == hotkey.id() {
                            debug!("Hotkey matched, executing callback");
                            let callback = self.callback.lock().await;
                            if let Some(cb) = callback.as_ref() {
                                cb();
                            }
                        }
                    }
                }

                tokio::time::sleep(tokio::time::Duration::from_millis(10)).await;
            }
        });
    }
}

impl Default for HotkeyManager {
    fn default() -> Self {
        Self::new().expect("Failed to create default HotkeyManager")
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_parse_hotkey() {
        assert!(HotkeyManager::parse_hotkey("Ctrl+Alt+A").is_ok());
        assert!(HotkeyManager::parse_hotkey("Shift+F1").is_ok());
        assert!(HotkeyManager::parse_hotkey("Ctrl+Shift+Esc").is_ok());
        assert!(HotkeyManager::parse_hotkey("").is_err());
        assert!(HotkeyManager::parse_hotkey("InvalidKey").is_err());
    }
}
