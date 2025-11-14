/// Activity monitoring for user input
use crate::error::Result;
use rdev::{listen, Event, EventType};
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::Arc;
use std::time::Instant;
use tokio::sync::Mutex;
use tracing::{debug, error, info};

/// Activity monitor tracks mouse and keyboard input
pub struct ActivityMonitor {
    last_input_time: Arc<Mutex<Instant>>,
    last_cursor_pos: Arc<Mutex<(i32, i32)>>,
    is_running: Arc<AtomicBool>,
}

impl ActivityMonitor {
    /// Create a new activity monitor
    pub fn new() -> Self {
        Self {
            last_input_time: Arc::new(Mutex::new(Instant::now())),
            last_cursor_pos: Arc::new(Mutex::new((0, 0))),
            is_running: Arc::new(AtomicBool::new(false)),
        }
    }

    /// Start monitoring user activity
    pub fn start(self: Arc<Self>) {
        if self.is_running.load(Ordering::Relaxed) {
            debug!("Activity monitor already running");
            return;
        }

        self.is_running.store(true, Ordering::Relaxed);
        info!("Starting activity monitor");

        let last_input_time = self.last_input_time.clone();
        let last_cursor_pos = self.last_cursor_pos.clone();
        let is_running = self.is_running.clone();

        // Spawn rdev listener in a separate thread (not async)
        std::thread::spawn(move || {
            let callback = move |event: Event| {
                // Update last input time for any input
                match event.event_type {
                    EventType::KeyPress(_) | EventType::KeyRelease(_) => {
                        if let Ok(mut last) = last_input_time.try_lock() {
                            *last = Instant::now();
                        }
                        debug!("Keyboard activity detected");
                    }
                    EventType::ButtonPress(_) | EventType::ButtonRelease(_) => {
                        if let Ok(mut last) = last_input_time.try_lock() {
                            *last = Instant::now();
                        }
                        debug!("Mouse button activity detected");
                    }
                    EventType::MouseMove { x, y } => {
                        if let Ok(mut pos) = last_cursor_pos.try_lock() {
                            *pos = (x as i32, y as i32);
                        }
                        if let Ok(mut last) = last_input_time.try_lock() {
                            *last = Instant::now();
                        }
                    }
                    EventType::Wheel { .. } => {
                        if let Ok(mut last) = last_input_time.try_lock() {
                            *last = Instant::now();
                        }
                        debug!("Mouse wheel activity detected");
                    }
                }
            };

            // Run the event listener
            if let Err(e) = listen(callback) {
                error!("Error in activity monitor listener: {:?}", e);
                is_running.store(false, Ordering::Relaxed);
            }
        });
    }

    /// Get time since last input activity in seconds
    pub async fn get_idle_time(&self) -> u64 {
        self.last_input_time.lock().await.elapsed().as_secs()
    }

    /// Get current cursor position
    pub async fn get_cursor_pos(&self) -> (i32, i32) {
        *self.last_cursor_pos.lock().await
    }

    /// Update activity (mark as active now)
    pub async fn update_activity(&self) {
        *self.last_input_time.lock().await = Instant::now();
    }

    /// Check if monitor is running
    pub fn is_running(&self) -> bool {
        self.is_running.load(Ordering::Relaxed)
    }

    /// Stop the activity monitor
    pub fn stop(&self) {
        info!("Stopping activity monitor");
        self.is_running.store(false, Ordering::Relaxed);
        // Note: rdev doesn't provide a clean way to stop listening
        // The thread will exit when the callback returns an error
    }
}

impl Default for ActivityMonitor {
    fn default() -> Self {
        Self::new()
    }
}

impl Drop for ActivityMonitor {
    fn drop(&mut self) {
        self.stop();
    }
}
