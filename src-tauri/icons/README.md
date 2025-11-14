# Icons for MonitorNap

The icon.ico file is the main application icon.

## Generating proper icons for production

To generate all required icon sizes for Tauri, use the following command:

```bash
# Install tauri-icon if not already installed
cargo install tauri-icon

# Generate all icon sizes from a source PNG (1024x1024 recommended)
tauri-icon path/to/source-icon.png
```

This will generate:
- 32x32.png
- 128x128.png
- 128x128@2x.png
- icon.icns (macOS)
- icon.ico (Windows)

For now, we're using the existing icon.ico file from the Python version.
