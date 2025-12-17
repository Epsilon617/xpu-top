#!/usr/bin/env python3
"""Lightweight terminal dashboard for Intel XPU metrics via xpumcli/xpu-smi."""

from __future__ import annotations

import argparse
import csv
import json
import os
import shutil
import signal
import subprocess
import sys
from dataclasses import dataclass
from typing import Dict, List, Optional


RESET = '\033[0m'
COLOR_GREEN = '\033[38;5;40m'
COLOR_YELLOW = '\033[38;5;214m'
COLOR_RED = '\033[38;5;203m'
COLOR_DIM = '\033[2m'
COLOR_BOLD = '\033[1m'
CLEAR_SCREEN = '\033[2J'
CURSOR_HOME = '\033[H'
ALT_SCREEN_ENABLE = '\033[?1049h'
ALT_SCREEN_DISABLE = '\033[?1049l'
HIDE_CURSOR = '\033[?25l'
SHOW_CURSOR = '\033[?25h'
BLOCK = '█'
DEFAULT_METRICS = '18,5,1,3'  # Mem used/util, power, temperature
AUTO_CMD = 'auto'
DEFAULT_CMD = os.environ.get('XPUM_MONITOR_CMD', AUTO_CMD)
CMD_FALLBACKS = ('xpumcli', 'xpu-smi')


@dataclass
class DeviceMetadata:
    name: Optional[str] = None
    memory_total_mib: Optional[float] = None


@dataclass
class DeviceSample:
    timestamp: str
    mem_used_mib: Optional[float] = None
    mem_util_percent: Optional[float] = None
    power_watts: Optional[float] = None
    temp_c: Optional[float] = None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description='Render a colorful terminal dashboard for Intel XPU metrics. '
        'Requires xpumcli or xpu-smi to be available in PATH.'
    )
    parser.add_argument(
        '--cmd',
        default=DEFAULT_CMD,
        help='Executable to run. Defaults to auto-detect (xpumcli → xpu-smi). Override via XPUM_MONITOR_CMD.',
    )
    parser.add_argument(
        '--metrics',
        default=DEFAULT_METRICS,
        help='Metric ids to request from xpumcli dump. Default covers memory, power, and temperature.',
    )
    parser.add_argument(
        '--bar-width',
        type=int,
        default=None,
        help='Override progress bar width (characters). Auto-detected when omitted.',
    )
    return parser.parse_args()


def resolve_command(binary: str) -> str:
    candidates = CMD_FALLBACKS if binary == AUTO_CMD else (binary,)
    errors = []
    for candidate in candidates:
        if os.path.isabs(candidate):
            if os.path.exists(candidate) and os.access(candidate, os.X_OK):
                return candidate
            errors.append(candidate)
            continue
        resolved = shutil.which(candidate)
        if resolved:
            return resolved
        errors.append(candidate)
    tried = ', '.join(errors)
    raise FileNotFoundError(f'Unable to find any of: {tried}. '
                            'Set --cmd or XPUM_MONITOR_CMD to xpumcli/xpu-smi full path.')


def color_for_percent(percent: float) -> str:
    if percent >= 85:
        return COLOR_RED
    if percent >= 60:
        return COLOR_YELLOW
    return COLOR_GREEN


def format_bar(percent: float, width: int) -> str:
    percent = max(0.0, min(100.0, percent))
    filled = int((percent / 100.0) * width)
    remaining = width - filled
    bar = f'{color_for_percent(percent)}{BLOCK * filled}{RESET}'
    if remaining > 0:
        bar += f'{COLOR_DIM}{BLOCK * remaining}{RESET}'
    return f'{bar} {percent:5.1f}%'


def clear_and_write(payload: str) -> None:
    sys.stdout.write(CLEAR_SCREEN + CURSOR_HOME + payload)
    sys.stdout.flush()


def enter_alt_screen() -> bool:
    if not sys.stdout.isatty():
        return False
    sys.stdout.write(ALT_SCREEN_ENABLE + HIDE_CURSOR)
    sys.stdout.flush()
    return True


def exit_alt_screen(active: bool) -> None:
    if not active:
        return
    sys.stdout.write(SHOW_CURSOR + ALT_SCREEN_DISABLE)
    sys.stdout.flush()


def parse_csv_line(line: str) -> List[str]:
    reader = csv.reader([line], skipinitialspace=True)
    return next(reader, [])


def to_float(value: Optional[str]) -> Optional[float]:
    if value is None:
        return None
    value = value.strip()
    if not value:
        return None
    try:
        return float(value)
    except ValueError:
        return None


def parse_int(value: Optional[str]) -> Optional[int]:
    if value is None:
        return None
    value = value.strip()
    if not value:
        return None
    try:
        return int(value)
    except ValueError:
        return None


def parse_mib(value: Optional[str]) -> Optional[float]:
    if value is None:
        return None
    cleaned = value.replace('MiB', '').strip()
    return to_float(cleaned)


def fetch_device_metadata(cmd_path: str) -> Dict[int, DeviceMetadata]:
    metadata: Dict[int, DeviceMetadata] = {}
    # Try CSV dump for device id, name, and memory size.
    try:
        dump_output = subprocess.run(
            [cmd_path, 'discovery', '--dump', '1,2,16'],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        ).stdout
        rows = list(csv.reader(filter(None, dump_output.splitlines()), skipinitialspace=True))
        if rows:
            headers = rows[0]
            for row in rows[1:]:
                if len(row) != len(headers):
                    continue
                entry = dict(zip(headers, row))
                device_id = parse_int(entry.get('Device ID'))
                if device_id is None:
                    continue
                info = metadata.setdefault(device_id, DeviceMetadata())
                if entry.get('Device Name'):
                    info.name = entry['Device Name'].strip('" ')
                total_mib = parse_mib(entry.get('Memory Physical Size'))
                if total_mib is not None:
                    info.memory_total_mib = total_mib
    except subprocess.CalledProcessError:
        pass

    # Fallback to JSON discovery to ensure we have names for every device.
    try:
        json_output = subprocess.run(
            [cmd_path, 'discovery', '-j'],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        ).stdout
        data = json.loads(json_output)
        for item in data.get('device_list', []):
            device_id = item.get('device_id')
            if device_id is None:
                continue
            info = metadata.setdefault(int(device_id), DeviceMetadata())
            if item.get('device_name'):
                info.name = item['device_name']
    except (subprocess.CalledProcessError, json.JSONDecodeError):
        pass

    return metadata


def launch_xpum(cmd_path: str, args: argparse.Namespace) -> subprocess.Popen[str]:
    cmd = [cmd_path, 'dump', '-m', args.metrics]
    return subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, bufsize=1)


def compute_bar_width(args: argparse.Namespace) -> int:
    if args.bar_width and args.bar_width > 0:
        return args.bar_width
    term_width = shutil.get_terminal_size((120, 20)).columns
    return max(20, min(60, term_width - 50))


def monitor_loop(args: argparse.Namespace) -> None:
    cmd_path = resolve_command(args.cmd)
    metadata = fetch_device_metadata(cmd_path)
    proc = launch_xpum(cmd_path, args)
    bar_width = compute_bar_width(args)
    device_stats: Dict[int, DeviceSample] = {}
    headers: Optional[List[str]] = None
    alt_screen_active = enter_alt_screen()

    def handle_exit(signum, frame):
        _ = signum, frame
        raise KeyboardInterrupt

    signal.signal(signal.SIGINT, handle_exit)
    signal.signal(signal.SIGTERM, handle_exit)

    try:
        while True:
            line = proc.stdout.readline()
            if line == '' and proc.poll() is not None:
                break
            if not line:
                continue
            parsed = parse_csv_line(line)
            if not parsed:
                continue
            if parsed[0] == 'Timestamp':
                headers = parsed
                continue
            if headers is None or len(parsed) != len(headers):
                continue
            row = dict(zip(headers, parsed))
            device_id = parse_int(row.get('DeviceId'))
            if device_id is None:
                continue
            sample = DeviceSample(
                timestamp=row.get('Timestamp', ''),
                mem_used_mib=to_float(row.get('GPU Memory Used (MiB)')),
                mem_util_percent=to_float(row.get('GPU Memory Utilization (%)')),
                power_watts=to_float(row.get('GPU Power (W)')),
                temp_c=to_float(row.get('GPU Core Temperature (Celsius Degree)')),
            )
            device_stats[device_id] = sample
            render_dashboard(device_stats, metadata, bar_width)
    except KeyboardInterrupt:
        pass
    finally:
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=0.5)
            except subprocess.TimeoutExpired:
                proc.kill()
        exit_alt_screen(alt_screen_active)


def render_dashboard(
    device_stats: Dict[int, DeviceSample],
    metadata: Dict[int, DeviceMetadata],
    bar_width: int,
) -> None:
    if not device_stats:
        return
    latest_ts = max((sample.timestamp for sample in device_stats.values() if sample.timestamp), default='N/A')
    term_width = shutil.get_terminal_size((100, 20)).columns
    divider_width = max(20, min(100, term_width))
    divider = f"{COLOR_DIM}{'—' * divider_width}{RESET}"
    lines: List[str] = [
        f'{COLOR_BOLD}Intel XPU Monitor{RESET} — Last update: {latest_ts}',
        'Press CTRL+C to exit. Source: xpumcli dump',
        '',
    ]

    device_ids = sorted(device_stats)
    for idx, device_id in enumerate(device_ids):
        sample = device_stats[device_id]
        meta = metadata.get(device_id, DeviceMetadata())
        device_label = meta.name or f'Device {device_id}'
        mem_used_mib = sample.mem_used_mib or 0.0
        mem_percent = sample.mem_util_percent
        mem_line = f'{mem_used_mib / 1024.0:6.2f} GiB'
        if meta.memory_total_mib:
            mem_line += f' / {meta.memory_total_mib / 1024.0:6.2f} GiB'
            if mem_percent is None and meta.memory_total_mib > 0:
                mem_percent = (mem_used_mib / meta.memory_total_mib) * 100.0
        if mem_percent is None:
            mem_percent = 0.0
        mem_bar = format_bar(mem_percent, bar_width)
        power_str = f'{sample.power_watts:6.1f} W' if sample.power_watts is not None else '  N/A  '
        temp_str = f'{sample.temp_c:5.1f} °C' if sample.temp_c is not None else '  N/A  '

        lines.append(f'{COLOR_BOLD}{device_label}{RESET} (ID {device_id})')
        lines.append(f'  Mem {mem_line} | {mem_bar}')
        lines.append(f'  Power {power_str} | Temp {temp_str}')
        if idx < len(device_ids) - 1:
            lines.append(divider)
        lines.append('')

    payload = '\n'.join(lines).rstrip() + '\n'
    clear_and_write(payload)


def main() -> None:
    args = parse_args()
    try:
        monitor_loop(args)
    except FileNotFoundError as exc:
        sys.stderr.write(f'{exc}\n')
        sys.exit(1)


if __name__ == '__main__':
    main()
