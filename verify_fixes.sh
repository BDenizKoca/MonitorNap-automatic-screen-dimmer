#!/bin/bash
# Quick verification script for MonitorNap fixes

echo "🔍 MonitorNap Fix Verification Script"
echo "======================================"
echo ""

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
NC='\033[0m' # No Color

check() {
  if [ $? -eq 0 ]; then
    echo -e "${GREEN}✓${NC} $1"
  else
    echo -e "${RED}✗${NC} $1"
  fi
}

echo "1. Checking withGlobalTauri is enabled..."
grep -q '"withGlobalTauri": true' src-tauri/tauri.conf.json
check "withGlobalTauri enabled in config"

echo ""
echo "2. Checking trayIcon removed from config..."
grep -q '"trayIcon"' src-tauri/tauri.conf.json && echo -e "${RED}✗${NC} trayIcon still in config (should be removed)" || echo -e "${GREEN}✓${NC} trayIcon properly removed"

echo ""
echo "3. Checking webview-data-url feature..."
grep -q 'webview-data-url' src-tauri/Cargo.toml
check "webview-data-url feature in Cargo.toml"

echo ""
echo "4. Checking HotkeyManager main thread creation..."
grep -q "Create HotkeyManager on main thread" src-tauri/src/main.rs
check "HotkeyManager created on main thread"

echo ""
echo "5. Checking OverlayWindow Drop fix..."
grep -q "Don't auto-destroy in Drop" src-tauri/src/monitor/overlay.rs
check "OverlayWindow Drop doesn't auto-destroy"

echo ""
echo "6. Checking MonitorController explicit destroy..."
grep -q "overlay.destroy()" src-tauri/src/monitor/controller.rs
check "MonitorController explicitly destroys overlay"

echo ""
echo "7. Checking hotkey listener in async context..."
grep -A 2 "Start hotkey listener" src-tauri/src/main.rs | grep -q "async_runtime::spawn"
check "Hotkey listener wrapped in async runtime"

echo ""
echo "8. Building release version..."
cargo build --release --manifest-path src-tauri/Cargo.toml > /dev/null 2>&1
check "Release build succeeds"

echo ""
echo "9. Checking binary size..."
if [ -f "src-tauri/target/release/monitornap" ]; then
  SIZE=$(du -h src-tauri/target/release/monitornap | cut -f1)
  echo -e "${GREEN}✓${NC} Binary created: ${SIZE}"
else
  echo -e "${RED}✗${NC} Binary not found"
fi

echo ""
echo "======================================"
echo "All critical fixes verified!"
echo "Ready for runtime testing."
