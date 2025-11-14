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
const recordHotkeyBtn = document.getElementById('record-hotkey');
const startupCheckbox = document.getElementById('start-on-startup');
const minimizedCheckbox = document.getElementById('start-minimized');
const monitorsContainer = document.getElementById('monitors-container');
const statusDiv = document.getElementById('status');
const saveBtn = document.getElementById('save-config');
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
                    Monitor ${index + 1} - ${monitor.name}
                    <div style="font-size: 0.9rem; color: var(--text-secondary); margin-top: 5px;">
                        ${monitor.width}x${monitor.height} at (${monitor.x}, ${monitor.y})
                    </div>
                </div>
                <button class="btn btn-small btn-primary" onclick="identifyMonitor(${index})">
                    🔍 Identify
                </button>
            </div>
            <div class="monitor-settings">
                <div class="setting-item">
                    <label>
                        <input type="checkbox"
                               data-monitor="${index}"
                               data-setting="enable_hardware_dimming"
                               ${monitorConfig.enable_hardware_dimming ? 'checked' : ''}>
                        Enable Hardware Dimming (DDC/CI)
                    </label>
                </div>
                <div class="setting-item">
                    <label>Hardware Dim Level: ${monitorConfig.hardware_dimming_level}%</label>
                    <input type="range"
                           min="0" max="100"
                           value="${monitorConfig.hardware_dimming_level}"
                           data-monitor="${index}"
                           data-setting="hardware_dimming_level">
                </div>
                <div class="setting-item">
                    <label>
                        <input type="checkbox"
                               data-monitor="${index}"
                               data-setting="enable_software_dimming"
                               ${monitorConfig.enable_software_dimming ? 'checked' : ''}>
                        Enable Software Dimming (Overlay)
                    </label>
                </div>
                <div class="setting-item">
                    <label>Software Dim Level: ${Math.round(monitorConfig.software_dimming_level * 100)}%</label>
                    <input type="range"
                           min="0" max="100"
                           value="${Math.round(monitorConfig.software_dimming_level * 100)}"
                           data-monitor="${index}"
                           data-setting="software_dimming_level">
                </div>
                <div class="setting-item">
                    <label>Overlay Color</label>
                    <input type="color"
                           value="${monitorConfig.overlay_color}"
                           data-monitor="${index}"
                           data-setting="overlay_color">
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
    document.querySelectorAll('[data-monitor]').forEach(input => {
        input.addEventListener('change', (e) => {
            const monitorIndex = parseInt(e.target.dataset.monitor);
            const setting = e.target.dataset.setting;
            let value = e.target.type === 'checkbox' ? e.target.checked : e.target.value;

            if (setting === 'software_dimming_level') {
                value = parseInt(value) / 100.0;
            } else if (setting === 'hardware_dimming_level') {
                value = parseInt(value);
                // Update label
                e.target.previousElementSibling.textContent = `Hardware Dim Level: ${value}%`;
            }

            config.monitors[monitorIndex][setting] = value;
        });

        // Live update for range sliders
        if (input.type === 'range') {
            input.addEventListener('input', (e) => {
                const setting = e.target.dataset.setting;
                const value = parseInt(e.target.value);

                if (setting === 'software_dimming_level') {
                    e.target.previousElementSibling.textContent = `Software Dim Level: ${value}%`;
                } else if (setting === 'hardware_dimming_level') {
                    e.target.previousElementSibling.textContent = `Hardware Dim Level: ${value}%`;
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
        config.inactivity_limit = parseInt(e.target.value);
    });

    inactivityNum.addEventListener('input', (e) => {
        inactivitySlider.value = e.target.value;
        config.inactivity_limit = parseInt(e.target.value);
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

    // Hotkey recording
    recordHotkeyBtn.addEventListener('click', () => {
        showNotification('Hotkey recording not implemented in web UI. Use the input field to type your hotkey.', 'error');
    });

    hotkeyInput.addEventListener('change', async (e) => {
        try {
            await invoke('register_hotkey', { hotkey: e.target.value });
            config.awake_mode_shortcut = e.target.value;
            showNotification('Hotkey registered successfully', 'success');
        } catch (error) {
            showNotification('Failed to register hotkey: ' + error, 'error');
        }
    });

    // Startup options
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

    // Save configuration
    saveBtn.addEventListener('click', async () => {
        try {
            await invoke('save_config', { config });
            showNotification('Settings saved successfully!', 'success');
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

// Identify monitor
async function identifyMonitor(index) {
    try {
        await invoke('identify_monitor', { monitorIndex: index });
        showNotification(`Identifying Monitor ${index + 1}...`, 'success');
    } catch (error) {
        showNotification('Failed to identify monitor: ' + error, 'error');
    }
}

// Make identifyMonitor available globally
window.identifyMonitor = identifyMonitor;

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
