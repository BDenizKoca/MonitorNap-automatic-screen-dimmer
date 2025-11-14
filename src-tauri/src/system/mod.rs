/// System integration module
///
/// Handles system-level integrations including:
/// - Global hotkeys
/// - System tray
/// - Activity detection (cursor, keyboard, mouse)
/// - Startup management

pub mod activity;
pub mod hotkey;
pub mod tray;

pub use activity::ActivityMonitor;
pub use hotkey::HotkeyManager;
pub use tray::TrayManager;
