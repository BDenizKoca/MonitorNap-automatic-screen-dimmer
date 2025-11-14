const invoke = window.__TAURI__.core.invoke;
const listen = window.__TAURI__.event.listen;
const getCurrentWindow = window.__TAURI__.window.getCurrentWindow;

// State
let config = null;
let monitors = [];

// DOM Elements
const inactivitySlider = document.getElementById('inactivity');
const inactivityNum = document.getElementById('inactivity-num');
const awakeCheckbox = document.getElementById('awake-mode');
const hotkeyInput = document.getElementById('hotkey');
const setHotkeyBtn = document.getElementById('set-hotkey');
const startupCheckbox = document.getElementById('start-on-startup');
const minimizedCheckbox = document.getElementById('start-minimized');
const monitorsContainer = document.getElementById('monitors-container');
const statusDiv = document.getElementById('status');
const applyBtn = document.getElementById('apply-settings');
const minimizeBtn = document.getElementById('minimize');
const napNowBtn = document.getElementById('nap-now');
const resumeNowBtn = document.getElementById('resume-now');

// Initialize
async function init() {
    try {
        // Load configuration
        config = await invoke('get_config');
        monitors = await invoke('get_monitors_info');

        // Populate UI
        populateSettings();
        renderMonitors();

        // Setup event listeners
        setupEventListeners();

        // Listen for backend events
        setupBackendListeners();

        showNotification('MonitorNap loaded successfully', 'success');
    } catch (error) {
        console.error('Failed to initialize:', error);
        showNotification('Failed to load configuration: ' + error, 'error');
    }
}

// Populate settings from config
function populateSettings() {
    inactivitySlider.value = config.inactivity_limit;
    inactivityNum.value = config.inactivity_limit;
    awakeCheckbox.checked = config.awake_mode;
    hotkeyInput.value = config.awake_mode_shortcut;
    startupCheckbox.checked = config.start_on_startup;
    minimizedCheckbox.checked = config.start_minimized;

    updateStatusDisplay();
}

// Render monitor settings
function renderMonitors() {
    monitorsContainer.innerHTML = '';

    monitors.forEach((monitor, index) => {
        const monitorConfig = config.monitors[index] || {
            monitor_index: index,
            display_index: index,
            ddc_index: index,
            enable_hardware_dimming: true,
            enable_software_dimming: true,
            hardware_dimming_level: 30,
            software_dimming_level: 0.5,
            overlay_color: '#000000'
        };

        // Ensure config has this monitor
        if (!config.monitors[index]) {
            config.monitors[index] = monitorConfig;
        }

        const card = document.createElement('div');
        card.className = 'monitor-card';
        card.innerHTML = `
            <div class="monitor-header">
                <div class="monitor-title">
                    Monitor ${index + 1} - ${monitor.name || 'Unknown'}
                    <div class="monitor-info">
                        ${monitor.width}x${monitor.height} at (${monitor.x}, ${monitor.y})
                        ${monitor.is_primary ? ' [PRIMARY]' : ''}
                    </div>
                </div>
                <button class="btn btn-small btn-primary" data-action="identify" data-monitor="${index}">
                    Identify
                </button>
            </div>

            <div class="monitor-settings-grid">
                <!-- Display and DDC selectors -->
                <div class="setting-row">
                    <label>Display Index:</label>
                    <input type="number" min="0" max="${monitors.length - 1}" value="${monitorConfig.display_index}"
                           data-monitor="${index}" data-setting="display_index" class="input-small">

                    <label style="margin-left: 20px;">DDC Index:</label>
                    <input type="number" min="0" max="${monitors.length - 1}" value="${monitorConfig.ddc_index}"
                           data-monitor="${index}" data-setting="ddc_index" class="input-small">
                </div>

                <!-- Hardware Dimming -->
                <div class="setting-group">
                    <label class="checkbox-label">
                        <input type="checkbox" ${monitorConfig.enable_hardware_dimming ? 'checked' : ''}
                               data-monitor="${index}" data-setting="enable_hardware_dimming">
                        Enable Hardware Dimming (DDC/CI)
                    </label>
                    <div class="slider-group">
                        <label class="slider-label" id="hw-label-${index}">
                            HW Level: ${monitorConfig.hardware_dimming_level}%
                        </label>
                        <input type="range" min="0" max="100" value="${monitorConfig.hardware_dimming_level}"
                               data-monitor="${index}" data-setting="hardware_dimming_level" class="slider">
                    </div>
                </div>

                <!-- Software Dimming -->
                <div class="setting-group">
                    <label class="checkbox-label">
                        <input type="checkbox" ${monitorConfig.enable_software_dimming ? 'checked' : ''}
                               data-monitor="${index}" data-setting="enable_software_dimming">
                        Enable Software Dimming (Overlay)
                    </label>
                    <div class="slider-group">
                        <label class="slider-label" id="sw-label-${index}">
                            SW Level: ${Math.round(monitorConfig.software_dimming_level * 100)}%
                        </label>
                        <input type="range" min="0" max="100" value="${Math.round(monitorConfig.software_dimming_level * 100)}"
                               data-monitor="${index}" data-setting="software_dimming_level" class="slider">
                    </div>
                </div>

                <!-- Overlay Color -->
                <div class="setting-row">
                    <label>Overlay Color:</label>
                    <input type="color" value="${monitorConfig.overlay_color}"
                           data-monitor="${index}" data-setting="overlay_color" class="color-picker">
                    <span class="color-value">${monitorConfig.overlay_color}</span>
                </div>
            </div>
        `;

        monitorsContainer.appendChild(card);
    });

    // Attach event listeners to monitor controls
    attachMonitorListeners();
}

// Attach event listeners to monitor controls
function attachMonitorListeners() {
    // Identify buttons
    document.querySelectorAll('[data-action="identify"]').forEach(btn => {
        btn.addEventListener('click', async (e) => {
            const monitorIndex = parseInt(e.target.dataset.monitor);
            try {
                await invoke('identify_monitor', { monitorIndex });
                showNotification(`Identifying Monitor ${monitorIndex + 1}...`, 'success');
            } catch (error) {
                showNotification('Failed to identify monitor: ' + error, 'error');
            }
        });
    });

    // Monitor settings inputs
    document.querySelectorAll('[data-monitor][data-setting]').forEach(input => {
        const monitorIndex = parseInt(input.dataset.monitor);
        const setting = input.dataset.setting;

        // Change event for actual updates
        input.addEventListener('change', async (e) => {
            let value = e.target.type === 'checkbox' ? e.target.checked : e.target.value;

            try {
                // Call appropriate backend command
                if (setting === 'display_index') {
                    await invoke('update_monitor_display_index', { monitorIndex, displayIndex: parseInt(value) });
                    config.monitors[monitorIndex].display_index = parseInt(value);
                } else if (setting === 'ddc_index') {
                    await invoke('update_monitor_ddc_index', { monitorIndex, ddcIndex: parseInt(value) });
                    config.monitors[monitorIndex].ddc_index = parseInt(value);
                } else if (setting === 'enable_hardware_dimming') {
                    await invoke('update_monitor_hw_enabled', { monitorIndex, enabled: value });
                    config.monitors[monitorIndex].enable_hardware_dimming = value;
                } else if (setting === 'enable_software_dimming') {
                    await invoke('update_monitor_sw_enabled', { monitorIndex, enabled: value });
                    config.monitors[monitorIndex].enable_software_dimming = value;
                } else if (setting === 'hardware_dimming_level') {
                    await invoke('update_monitor_hw_level', { monitorIndex, level: parseInt(value) });
                    config.monitors[monitorIndex].hardware_dimming_level = parseInt(value);
                } else if (setting === 'software_dimming_level') {
                    const level = parseInt(value) / 100.0;
                    await invoke('update_monitor_sw_level', { monitorIndex, level });
                    config.monitors[monitorIndex].software_dimming_level = level;
                } else if (setting === 'overlay_color') {
                    await invoke('update_monitor_color', { monitorIndex, color: value });
                    config.monitors[monitorIndex].overlay_color = value;
                    // Update color display
                    e.target.nextElementSibling.textContent = value;
                }
            } catch (error) {
                showNotification('Failed to update setting: ' + error, 'error');
            }
        });

        // Input event for live label updates (sliders only)
        if (input.type === 'range') {
            input.addEventListener('input', (e) => {
                const value = parseInt(e.target.value);
                if (setting === 'software_dimming_level') {
                    document.getElementById(`sw-label-${monitorIndex}`).textContent = `SW Level: ${value}%`;
                } else if (setting === 'hardware_dimming_level') {
                    document.getElementById(`hw-label-${monitorIndex}`).textContent = `HW Level: ${value}%`;
                }
            });
        }
    });
}

// Setup event listeners
function setupEventListeners() {
    // Inactivity slider/number sync
    inactivitySlider.addEventListener('input', (e) => {
        inactivityNum.value = e.target.value;
    });

    inactivityNum.addEventListener('input', (e) => {
        inactivitySlider.value = e.target.value;
    });

    // Awake mode
    awakeCheckbox.addEventListener('change', async (e) => {
        try {
            await invoke('set_awake_mode', { enabled: e.target.checked });
            config.awake_mode = e.target.checked;
            updateStatusDisplay();
        } catch (error) {
            showNotification('Failed to toggle awake mode: ' + error, 'error');
        }
    });

    // Hotkey
    setHotkeyBtn.addEventListener('click', async () => {
        const newHotkey = prompt('Enter hotkey (e.g., Ctrl+Alt+A):', config.awake_mode_shortcut);
        if (newHotkey && newHotkey.trim()) {
            try {
                await invoke('register_hotkey', { hotkey: newHotkey.trim() });
                config.awake_mode_shortcut = newHotkey.trim();
                hotkeyInput.value = newHotkey.trim();
                showNotification('Hotkey registered successfully', 'success');
            } catch (error) {
                showNotification('Failed to register hotkey: ' + error, 'error');
            }
        }
    });

    // Startup options (these update on apply)
    startupCheckbox.addEventListener('change', (e) => {
        config.start_on_startup = e.target.checked;
    });

    minimizedCheckbox.addEventListener('change', (e) => {
        config.start_minimized = e.target.checked;
    });

    // Action buttons
    napNowBtn.addEventListener('click', async () => {
        try {
            await invoke('nap_now');
            showNotification('Dimming all monitors...', 'success');
        } catch (error) {
            showNotification('Failed to dim monitors: ' + error, 'error');
        }
    });

    resumeNowBtn.addEventListener('click', async () => {
        try {
            await invoke('resume_now');
            showNotification('Resuming normal operation...', 'success');
        } catch (error) {
            showNotification('Failed to resume: ' + error, 'error');
        }
    });

    // Pause buttons
    document.querySelectorAll('[data-pause]').forEach(btn => {
        btn.addEventListener('click', async (e) => {
            const minutes = parseInt(e.target.dataset.pause);
            try {
                await invoke('pause_dimming', { minutes });
                showNotification(`Paused dimming for ${minutes} minutes`, 'success');
            } catch (error) {
                showNotification('Failed to pause dimming: ' + error, 'error');
            }
        });
    });

    // Apply settings
    applyBtn.addEventListener('click', async () => {
        try {
            config.inactivity_limit = parseInt(inactivityNum.value);
            await invoke('save_config', { config });
            showNotification('Settings applied successfully!', 'success');
        } catch (error) {
            showNotification('Failed to save settings: ' + error, 'error');
        }
    });

    // Minimize to tray
    minimizeBtn.addEventListener('click', async () => {
        const window = getCurrentWindow();
        await window.hide();
    });
}

// Setup backend event listeners
async function setupBackendListeners() {
    // Listen for awake mode changes from backend (e.g., hotkey press)
    await listen('awake-mode-changed', (event) => {
        config.awake_mode = event.payload;
        awakeCheckbox.checked = event.payload;
        updateStatusDisplay();
    });

    await listen('toggle-awake-mode', async () => {
        try {
            const newState = await invoke('toggle_awake_mode');
            config.awake_mode = newState;
            awakeCheckbox.checked = newState;
            updateStatusDisplay();
        } catch (error) {
            console.error('Failed to toggle awake mode:', error);
        }
    });

    await listen('pause-started', async (event) => {
        const minutes = event.payload;
        updateStatusDisplay(`Paused for ${minutes} minutes`);
    });

    await listen('nap-now', async () => {
        try {
            await invoke('nap_now');
        } catch (error) {
            console.error('Failed to nap now:', error);
        }
    });

    await listen('resume-now', async () => {
        try {
            await invoke('resume_now');
        } catch (error) {
            console.error('Failed to resume:', error);
        }
    });
}

// Update status display
function updateStatusDisplay(customText = null) {
    if (customText) {
        statusDiv.textContent = customText;
        statusDiv.className = 'status awake';
        return;
    }

    if (config.awake_mode) {
        statusDiv.textContent = 'Awake Mode ON (no dimming)';
        statusDiv.className = 'status awake';
    } else {
        statusDiv.textContent = 'MonitorNap is running';
        statusDiv.className = 'status';
    }
}

// Show notification
function showNotification(message, type = 'success') {
    const notification = document.getElementById('notification');
    notification.textContent = message;
    notification.className = `notification ${type === 'error' ? 'error' : ''}`;

    setTimeout(() => {
        notification.className = 'notification hidden';
    }, 3000);
}

// Initialize on load
document.addEventListener('DOMContentLoaded', init);
