<div align="center">

# MonitorNap

<img width="650"  alt="MonitorNap" src="https://file.garden/aLboplo8eB2dIZKp/GitHub/MonitorNap.png?v=1759929131318" />

**Turn Off Your Displays with a Single Click**
A tiny, cross-platform tray utility for instantly putting your monitors to sleep without locking your computer.

[![CI](https://github.com/BDenizKoca/MonitorNap/actions/workflows/release.yml/badge.svg)](https://github.com/BDenizKoca/MonitorNap/actions/workflows/release.yml)
[![Release](https://github.com/BDenizKoca/MonitorNap/actions/workflows/release.yml/badge.svg)](https://github.com/BDenizKoca/MonitorNap/actions/workflows/release.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)


**Download:** [Latest Release](https://github.com/BDenizKoca/MonitorNap/releases/latest) - Ready-to-use apps for Windows, Linux, and macOS

<img width="400" alt="MonitorNap Logo" src="https://file.garden/aLboplo8eB2dIZKp/GitHub/monitornaplogo.png" />

</div>

## Why I Built It
I got tired of my second monitor being distracting, but I didn't want to keep turning it on and off manually. So I created MonitorNap to let me dim my monitors easily without the hassle.




## Features

MonitorNap automatically dims your monitors after a period of inactivity. It works in the background and has a hotkey to keep things awake when needed.

- Detects when you're not using each monitor (checks cursor and full-screen apps)
- Dims monitors using built-in controls or a software overlay
- Runs in the system tray for easy access
- Hotkey to temporarily disable dimming
- Starts with Windows and minimizes to tray



## Installation

### **Quick Start (Recommended)**
1. **Download:** Go to [Latest Release](https://github.com/BDenizKoca/MonitorNap/releases/latest) and download the app for your system:
   - **Windows:** `MonitorNap.exe` (~37MB)
   - **Linux:** `MonitorNap` (~40MB) - Make it executable with `chmod +x MonitorNap`
   - **macOS:** `MonitorNap.app` (~40MB)
2. **Run:** Double-click the downloaded file (no installation required!)
3. **Configure:** Use "Identify" to map your monitors
4. **Optional:** Enable "Start on system startup" (Windows only)

### **Run from Source**
```powershell
# Clone the repository
git clone https://github.com/BDenizKoca/MonitorNap.git
cd MonitorNap

# Create virtual environment
python -m venv .venv
.\.venv\Scripts\Activate.ps1

# Install dependencies
pip install -r requirements.txt

# Run the application
python monitornap.py
```



### Build the Standalone Executable
```powershell
pyinstaller --onefile --windowed --icon=myicon.ico --add-data "myicon.ico;." --noupx `
  -n MonitorNap-Windows --distpath dist/windows --workpath build/windows monitornap.py
```
This mirrors the GitHub Actions release build so the tray/taskbar icons ship correctly.

### Requirements
- **Operating System:** Windows 10/11, Linux (Ubuntu), or macOS
- **Python 3.8+** (if running from source)
- **Compatible monitors** (most modern ones work)
- **Administrator privileges** (for global hotkey registration on Windows)



## Usage

### First Time Setup
1. **Launch MonitorNap** - The main window opens
2. **Configure monitors** - Use "Identify" to see which display is which
3. **Adjust settings** - Set inactivity timer and dimming levels
4. **Test it** - Wait for inactivity or click "Nap Now"

### Main Window Controls

#### Global Settings
- **Inactivity Limit** - Seconds before dimming (1-3600)
- **Awake Mode** - Prevents all dimming when enabled
- **Global Hotkey** - Key combination to toggle Awake Mode
- **Startup Options** - Auto-start and minimize to tray

#### Per-Monitor Settings  
- **Display Selector** - Choose which display gets the overlay
- **Identify Button** - Flash overlay to identify the monitor
- **Hardware Dimming** - Enable built-in brightness control (30% default)
- **Software Dimming** - Enable overlay dimming (50% opacity default)
- **Overlay Color** - Customize the dimming overlay color

#### Quick Actions
- **Nap Now** - Immediately dim all monitors
- **Resume Now** - Immediately restore all monitors  
- **Pause 15/30/60 min** - Temporarily disable dimming
- **Awake Mode Toggle** - Keep monitors always active

### System Tray
Right-click the tray icon for quick access to:
- Show/Hide main window
- Toggle Awake Mode
- Nap Now / Resume Now
- Pause Dimming (15/30/60 minutes)
- Exit application

### Hotkeys
- **Ctrl+Alt+A** (default) - Toggle Awake Mode globally
- **Record custom hotkey** - Use "Record Shortcut" button

### Configuration
Settings are automatically saved to:
- **Windows:** `%APPDATA%\MonitorNap\monitornap_config.json`
- **Linux/macOS:** `~/.monitornap/monitornap_config.json`

## Windows SmartScreen & Antivirus
- MonitorNap binaries are unsigned open-source builds. Windows SmartScreen may warn until you choose `More info` -> `Run anyway`.
- Building from source with the PyInstaller command above produces the same binary and inherits full trust on your machine.
- If you own an Authenticode certificate you can remove the warning entirely with:  
  `signtool sign /tr http://timestamp.digicert.com /td sha256 /fd sha256 /a dist\windows\MonitorNap-Windows.exe`
- UPX compression is disabled in current builds to reduce antivirus heuristic false positives.
- Verify downloaded artifacts (for example `Get-FileHash dist\windows\MonitorNap-Windows.exe`) before running them.

## Known Limitations

- **Monitor index mapping** may differ between systems; if dimming the wrong screen, use the Display selector to map correctly
- **Fullscreen detection** is heuristic and may not catch all cases (some games/apps may still dim)
- **Built-in dimming support varies** by monitor - some monitors don't support hardware brightness control
- **USB monitors** typically don't support built-in dimming and will only use software overlay
- **Multiple identical monitors** may be harder to distinguish without using Identify



## Future Plans

Feature-complete for now but open to contributions.



## Connect With Me  
Email: [b.denizkoca@gmail.com](mailto:b.denizkoca@gmail.com)  
GitHub: [@BDenizKoca](https://github.com/BDenizKoca) 



## License

MIT License - You can use, modify, and distribute freely with attribution.
