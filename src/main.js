const invoke = window.__TAURI__.core.invoke;
const listen = window.__TAURI__.event.listen;
const getCurrentWindow = window.__TAURI__.window.getCurrentWindow;

// State
let config = null;
let monitors = [];
let presets = JSON.parse(localStorage.getItem('monitornapPresets') || '[]');
let logs = JSON.parse(localStorage.getItem('monitornapLogs') || '[]');
let hasUnsavedChanges = false;

// Utility Functions
function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

function markUnsaved() {
    hasUnsavedChanges = true;
    document.getElementById('last-saved').textContent = 'Unsaved changes';
}

function markSaved() {
    hasUnsavedChanges = false;
    const now = new Date().toLocaleTimeString();
    document.getElementById('last-saved').textContent = `Saved at ${now}`;
}

// Logs
function addLog(type, message) {
    const entry = { time: new Date().toLocaleTimeString(), type, message };
    logs.unshift(entry);
    if (logs.length > 100) logs = logs.slice(0, 100);
    localStorage.setItem('monitornapLogs', JSON.stringify(logs));
    renderLogs();
}

function renderLogs() {
    const viewer = document.getElementById('logs-viewer');
    if (logs.length === 0) {
        viewer.innerHTML = '<p class="empty-state">No activity logs yet</p>';
        return;
    }
    viewer.innerHTML = logs.map(log => `
        <div class="log-entry">
            <span class="log-time">${escapeHtml(log.time)}</span>
            <span class="log-type">${escapeHtml(log.type)}</span>
            <span class="log-message">${escapeHtml(log.message)}</span>
        </div>
    `).join('');
}

// Show confirmation dialog
function showConfirm(title, message) {
    return new Promise((resolve) => {
        const dialog = document.getElementById('confirm-dialog');
        document.getElementById('dialog-title').textContent = title;
        document.getElementById('dialog-message').textContent = message;
        dialog.classList.remove('hidden');
        
        const confirm = () => { dialog.classList.add('hidden'); resolve(true); };
        const cancel = () => { dialog.classList.add('hidden'); resolve(false); };
        
        document.getElementById('dialog-confirm').onclick = confirm;
        document.getElementById('dialog-cancel').onclick = cancel;
    });
}

// Show notification
function showNotification(message, type = 'success') {
    const notification = document.getElementById('notification');
    notification.textContent = message;
    notification.className = `notification ${type === 'error' ? 'error' : ''}`;
    setTimeout(() => notification.className = 'notification hidden', 3000);
}

// Initialize
async function init() {
    try {
        config = await invoke('get_config');
        monitors = await invoke('get_monitors_info');
        populateSettings();
        renderMonitors();
        renderLogs();
        setupEventListeners();
        setupKeyboardShortcuts();
        await setupBackendListeners();
        showNotification('MonitorNap loaded successfully', 'success');
        addLog('INFO', 'Application started');
        markSaved();
    } catch (error) {
        console.error('Failed to initialize:', error);
        showNotification('Failed to load configuration: ' + error, 'error');
        addLog('ERROR', 'Failed to load: ' + error);
    }
}

function populateSettings() {
    document.getElementById('inactivity').value = config.inactivity_limit;
    document.getElementById('inactivity-num').value = config.inactivity_limit;
    document.getElementById('awake-mode').checked = config.awake_mode;
    document.getElementById('hotkey').value = config.awake_mode_shortcut;
    document.getElementById('start-on-startup').checked = config.start_on_startup;
    document.getElementById('start-minimized').checked = config.start_minimized;
    updateStatusDisplay();
}

function renderMonitors() {
    const container = document.getElementById('monitors-container');
    container.innerHTML = '';

    monitors.forEach((monitor, index) => {
        const mc = config.monitors[index] || {
            monitor_index: index, display_index: index, ddc_index: index,
            enable_hardware_dimming: true, enable_software_dimming: true,
            hardware_dimming_level: 30, software_dimming_level: 0.5, overlay_color: '#000000'
        };
        if (!config.monitors[index]) config.monitors[index] = mc;

        const card = document.createElement('div');
        card.className = 'monitor-card';
        card.dataset.index = index;
        card.innerHTML = `
            <div class="monitor-header" data-monitor="${index}">
                <div class="monitor-title-section">
                    <div class="monitor-title">
                        <span class="expand-icon">▼</span>
                        Monitor ${index + 1} - ${escapeHtml(monitor.name || 'Unknown')}
                        <span class="monitor-status-badge">Active</span>
                    </div>
                    <div class="monitor-info">${monitor.width}x${monitor.height} at (${monitor.x}, ${monitor.y})</div>
                </div>
                <div class="monitor-header-actions">
                    <button class="btn btn-small btn-primary" data-action="identify" data-monitor="${index}">Identify</button>
                </div>
            </div>
            <div class="monitor-settings-grid">
                <div class="setting-row">
                    <label>Display Index:</label>
                    <input type="number" min="0" max="${monitors.length - 1}" value="${mc.display_index}"
                           data-monitor="${index}" data-setting="display_index" class="input-small">
                </div>
                <div class="setting-row">
                    <label>DDC Index:</label>
                    <input type="number" min="0" max="${monitors.length - 1}" value="${mc.ddc_index}"
                           data-monitor="${index}" data-setting="ddc_index" class="input-small">
                </div>
                <div class="setting-group">
                    <label class="checkbox-label">
                        <input type="checkbox" ${mc.enable_hardware_dimming ? 'checked' : ''}
                               data-monitor="${index}" data-setting="enable_hardware_dimming">
                        Enable Hardware Dimming (DDC/CI)
                    </label>
                    <div class="slider-group">
                        <label class="slider-label" id="hw-label-${index}">HW Level: ${mc.hardware_dimming_level}%</label>
                        <input type="range" min="0" max="100" value="${mc.hardware_dimming_level}"
                               data-monitor="${index}" data-setting="hardware_dimming_level" class="slider">
                    </div>
                </div>
                <div class="setting-group">
                    <label class="checkbox-label">
                        <input type="checkbox" ${mc.enable_software_dimming ? 'checked' : ''}
                               data-monitor="${index}" data-setting="enable_software_dimming">
                        Enable Software Dimming (Overlay)
                    </label>
                    <div class="slider-group">
                        <label class="slider-label" id="sw-label-${index}">SW Level: ${Math.round(mc.software_dimming_level * 100)}%</label>
                        <input type="range" min="0" max="100" value="${Math.round(mc.software_dimming_level * 100)}"
                               data-monitor="${index}" data-setting="software_dimming_level" class="slider">
                    </div>
                </div>
                <div class="setting-row">
                    <label>Overlay Color:</label>
                    <div style="display: flex; align-items: center; gap: 8px;">
                        <input type="color" value="${mc.overlay_color}"
                               data-monitor="${index}" data-setting="overlay_color" class="color-picker">
                        <span class="color-value">${mc.overlay_color}</span>
                    </div>
                </div>
            </div>
        `;
        container.appendChild(card);
    });
    attachMonitorListeners();
}

function attachMonitorListeners() {
    // Collapse/expand cards
    document.querySelectorAll('.monitor-header').forEach(header => {
        header.addEventListener('click', (e) => {
            if (e.target.closest('button')) return;
            const card = header.closest('.monitor-card');
            card.classList.toggle('collapsed');
        });
    });

    // Identify buttons
    document.querySelectorAll('[data-action="identify"]').forEach(btn => {
        btn.addEventListener('click', async (e) => {
            const index = parseInt(e.target.dataset.monitor);
            try {
                await invoke('identify_monitor', { monitorIndex: index });
                showNotification(`Identifying Monitor ${index + 1}`, 'success');
                addLog('INFO', `Identified monitor ${index + 1}`);
            } catch (error) {
                showNotification('Failed to identify monitor: ' + error, 'error');
            }
        });
    });

    // Monitor settings
    document.querySelectorAll('[data-monitor][data-setting]').forEach(input => {
        const monitorIndex = parseInt(input.dataset.monitor);
        const setting = input.dataset.setting;

        input.addEventListener('change', async (e) => {
            markUnsaved();
            let value = e.target.type === 'checkbox' ? e.target.checked : e.target.value;

            try {
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
                    e.target.nextElementSibling.textContent = value;
                }
                addLog('INFO', `Updated monitor ${monitorIndex + 1} ${setting}`);
            } catch (error) {
                showNotification('Failed to update: ' + error, 'error');
                addLog('ERROR', `Failed to update monitor ${monitorIndex + 1}: ${error}`);
            }
        });

        // Live slider updates
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

function setupEventListeners() {
    // Inactivity slider/number sync
    document.getElementById('inactivity').addEventListener('input', (e) => {
        document.getElementById('inactivity-num').value = e.target.value;
        markUnsaved();
    });
    document.getElementById('inactivity-num').addEventListener('input', (e) => {
        document.getElementById('inactivity').value = e.target.value;
        markUnsaved();
    });

    // Awake mode
    document.getElementById('awake-mode').addEventListener('change', async (e) => {
        try {
            await invoke('set_awake_mode', { enabled: e.target.checked });
            config.awake_mode = e.target.checked;
            updateStatusDisplay();
            addLog('INFO', `Awake mode ${e.target.checked ? 'enabled' : 'disabled'}`);
        } catch (error) {
            showNotification('Failed to toggle awake mode: ' + error, 'error');
        }
    });

    // Hotkey
    document.getElementById('set-hotkey').addEventListener('click', async () => {
        const newHotkey = prompt('Enter hotkey (e.g., Ctrl+Alt+A):', config.awake_mode_shortcut);
        if (newHotkey && newHotkey.trim()) {
            try {
                await invoke('register_hotkey', { hotkey: newHotkey.trim() });
                config.awake_mode_shortcut = newHotkey.trim();
                document.getElementById('hotkey').value = newHotkey.trim();
                showNotification('Hotkey registered', 'success');
                addLog('INFO', `Hotkey changed to ${newHotkey.trim()}`);
            } catch (error) {
                showNotification('Failed to register hotkey: ' + error, 'error');
            }
        }
    });

    // Startup options
    document.getElementById('start-on-startup').addEventListener('change', (e) => {
        config.start_on_startup = e.target.checked;
        markUnsaved();
    });
    document.getElementById('start-minimized').addEventListener('change', (e) => {
        config.start_minimized = e.target.checked;
        markUnsaved();
    });

    // Action buttons
    document.getElementById('nap-now').addEventListener('click', async () => {
        try {
            await invoke('nap_now');
            showNotification('Dimming all monitors', 'success');
            addLog('ACTION', 'Nap now triggered');
        } catch (error) {
            showNotification('Failed to dim: ' + error, 'error');
        }
    });

    document.getElementById('resume-now').addEventListener('click', async () => {
        try {
            await invoke('resume_now');
            showNotification('Resuming normal operation', 'success');
            addLog('ACTION', 'Resume now triggered');
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
                showNotification(`Paused for ${minutes} minutes`, 'success');
                addLog('ACTION', `Paused dimming for ${minutes} minutes`);
            } catch (error) {
                showNotification('Failed to pause: ' + error, 'error');
            }
        });
    });

    // Apply settings
    document.getElementById('apply-settings').addEventListener('click', async () => {
        try {
            config.inactivity_limit = parseInt(document.getElementById('inactivity-num').value);
            await invoke('save_config', { config });
            showNotification('Settings applied!', 'success');
            addLog('INFO', 'Settings saved');
            markSaved();
        } catch (error) {
            showNotification('Failed to save: ' + error, 'error');
        }
    });

    // Minimize
    document.getElementById('minimize').addEventListener('click', async () => {
        const window = getCurrentWindow();
        await window.hide();
    });

    // Collapse/Expand all
    document.getElementById('collapse-all').addEventListener('click', () => {
        document.querySelectorAll('.monitor-card').forEach(card => card.classList.add('collapsed'));
    });
    document.getElementById('expand-all').addEventListener('click', () => {
        document.querySelectorAll('.monitor-card').forEach(card => card.classList.remove('collapsed'));
    });

    // Logs toggle
    document.getElementById('toggle-logs').addEventListener('click', () => {
        document.querySelector('.logs-section').classList.toggle('collapsed');
    });

    document.getElementById('clear-logs').addEventListener('click', async () => {
        if (await showConfirm('Clear Logs', 'Are you sure you want to clear all activity logs?')) {
            logs = [];
            localStorage.setItem('monitornapLogs', '[]');
            renderLogs();
        }
    });

    document.getElementById('export-logs').addEventListener('click', () => {
        const text = logs.map(l => `${l.time} [${l.type}] ${l.message}`).join('\n');
        const blob = new Blob([text], { type: 'text/plain' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `monitornap-logs-${new Date().toISOString().split('T')[0]}.txt`;
        a.click();
    });

    // Presets
    document.getElementById('save-preset').addEventListener('click', () => {
        document.getElementById('preset-title').textContent = 'Save Preset';
        document.getElementById('preset-name').value = '';
        renderPresetList();
        document.getElementById('preset-dialog').classList.remove('hidden');
    });

    document.getElementById('load-preset').addEventListener('click', () => {
        document.getElementById('preset-title').textContent = 'Load Preset';
        document.getElementById('preset-name').style.display = 'none';
        renderPresetList();
        document.getElementById('preset-dialog').classList.remove('hidden');
    });

    document.getElementById('preset-cancel').addEventListener('click', () => {
        document.getElementById('preset-dialog').classList.add('hidden');
    });

    document.getElementById('preset-save').addEventListener('click', () => {
        const name = document.getElementById('preset-name').value.trim();
        if (!name) {
            showNotification('Please enter a preset name', 'error');
            return;
        }
        presets.push({ name, config: JSON.parse(JSON.stringify(config)) });
        localStorage.setItem('monitornapPresets', JSON.stringify(presets));
        document.getElementById('preset-dialog').classList.add('hidden');
        showNotification(`Preset "${name}" saved`, 'success');
        addLog('INFO', `Saved preset: ${name}`);
    });
}

function renderPresetList() {
    const list = document.getElementById('preset-list');
    if (presets.length === 0) {
        list.innerHTML = '<p class="empty-state">No presets saved</p>';
        return;
    }
    list.innerHTML = presets.map((preset, i) => `
        <div class="preset-item" data-index="${i}">
            <span>${escapeHtml(preset.name)}</span>
            <button class="btn btn-small" onclick="deletePreset(${i})">Delete</button>
        </div>
    `).join('');

    list.querySelectorAll('.preset-item').forEach(item => {
        item.addEventListener('click', async (e) => {
            if (e.target.tagName === 'BUTTON') return;
            const index = parseInt(item.dataset.index);
            config = JSON.parse(JSON.stringify(presets[index].config));
            populateSettings();
            renderMonitors();
            document.getElementById('preset-dialog').classList.add('hidden');
            showNotification(`Loaded preset "${presets[index].name}"`, 'success');
            addLog('INFO', `Loaded preset: ${presets[index].name}`);
            markUnsaved();
        });
    });
}

function deletePreset(index) {
    presets.splice(index, 1);
    localStorage.setItem('monitornapPresets', JSON.stringify(presets));
    renderPresetList();
}

function setupKeyboardShortcuts() {
    document.addEventListener('keydown', async (e) => {
        // Ctrl+S / Cmd+S - Save
        if ((e.ctrlKey || e.metaKey) && e.key === 's') {
            e.preventDefault();
            document.getElementById('apply-settings').click();
        }
        // ESC - Minimize or close dialogs
        if (e.key === 'Escape') {
            const openDialog = document.querySelector('.dialog-overlay:not(.hidden)');
            if (openDialog) {
                openDialog.classList.add('hidden');
            } else {
                const window = getCurrentWindow();
                await window.hide();
            }
        }
    });
}

async function setupBackendListeners() {
    await listen('awake-mode-changed', (event) => {
        config.awake_mode = event.payload;
        document.getElementById('awake-mode').checked = event.payload;
        updateStatusDisplay();
    });

    await listen('toggle-awake-mode', async () => {
        try {
            const newState = await invoke('toggle_awake_mode');
            config.awake_mode = newState;
            document.getElementById('awake-mode').checked = newState;
            updateStatusDisplay();
        } catch (error) {
            console.error('Failed to toggle awake mode:', error);
        }
    });
}

function updateStatusDisplay() {
    const status = document.getElementById('status');
    const statusText = document.getElementById('status-text');
    
    if (config.awake_mode) {
        statusText.textContent = 'Awake Mode ON (no dimming)';
        status.classList.add('awake');
    } else {
        statusText.textContent = 'MonitorNap is running';
        status.classList.remove('awake');
    }
}

// Initialize on load
document.addEventListener('DOMContentLoaded', init);
