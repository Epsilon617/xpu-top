# xpu-top

Lightweight terminal dashboard for Intel XPUs that mimics the experience of `nvidia-smi`. It wraps `xpumcli` or `xpu-smi` (whichever is available) and renders colorful memory, power, and temperature bars in-place inside your terminal.

## Features
- Auto-discovers `xpumcli` or `xpu-smi`, or accept a manual `--cmd` override.
- Shows device name, memory usage/utilization, power draw, and temperature per card.
- Smooth single-screen refresh using the terminal's alternate buffer (no scrollback spam).
- Handy `xputop` launcher script so you can run the monitor with one command from anywhere.

## Requirements
- Python 3.8+
- Intel XPUM toolkit providing either `xpumcli` or `xpu-smi` on your `$PATH`
- A POSIX-like shell (for the `xputop` helper) and a terminal that supports ANSI escape sequences

## Installation
1. Clone the repository and enter it:
   ```bash
   git clone https://github.com/Epsilon617/xpu-top.git
   cd xpu-top
   ```
2. Make sure the helper script is executable (should already be, but just in case):
   ```bash
   chmod +x xputop
   ```
3. (Optional) Add the repo root to your `PATH` so `xputop` can be invoked from anywhere:
   ```bash
   export PATH="$PWD:$PATH"
   # To persist, append the line above to ~/.bashrc or your shell profile
   ```

## Usage
Run the dashboard via the helper script:
```bash
xputop
```

This launches `xpu_monitor.py` which by default tries `xpumcli` first and falls back to `xpu-smi`. The output stays within a single screen and updates until you press `Ctrl+C`.

### Sample output
```
Intel XPU Monitor — Last update: 23:36:50.211
Press CTRL+C to exit. Source: xpumcli dump

Intel(R) Data Center GPU Max 1550 (ID 0)
  Mem  22.78 GiB / 128.00 GiB | ████████████████████████████████████████████████████████████  17.8%
  Power  355.7 W | Temp  49.1 °C
————————————————————————————————————————————————————————————————————————————————————————————————————

Intel(R) Data Center GPU Max 1550 (ID 1)
  Mem  25.52 GiB / 128.00 GiB | ████████████████████████████████████████████████████████████  19.9%
  Power  378.8 W | Temp  50.5 °C
————————————————————————————————————————————————————————————————————————————————————————————————————

Intel(R) Data Center GPU Max 1550 (ID 2)
  Mem   2.67 GiB / 128.00 GiB | ████████████████████████████████████████████████████████████   2.1%
  Power  306.1 W | Temp  47.0 °C
————————————————————————————————————————————————————————————————————————————————————————————————————

Intel(R) Data Center GPU Max 1550 (ID 3)
  Mem  57.15 GiB / 128.00 GiB | ████████████████████████████████████████████████████████████  44.6%
  Power  295.5 W | Temp  48.0 °C
```

### Useful flags
- `xputop --cmd xpu-smi` — explicitly pick the backend executable.
- `xputop --metrics 18,5,1,3` — pass a comma-separated list of XPUM metric IDs to match your toolkit.
- `xputop --bar-width 60` — override the auto-detected bar width when you want wider graphs.

You can also call the Python entry point directly:
```bash
python xpu_monitor.py --cmd xpumcli
```

### Environment variables
- `XPUM_MONITOR_CMD` — set to an absolute path or binary name (e.g. `xpu-smi`) to control the backend without passing `--cmd` every time.
