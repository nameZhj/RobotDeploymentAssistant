#!/usr/bin/env python3
"""G1 network probe, Wi-Fi scan/selection/connection and IPv4 settings.

Examples: python tools/g1_wifi_setup.py --connect / --watch-wifi / --set-ipv4
Defaults are configured below. Host-key verification remains enabled.
"""

from __future__ import annotations

# ================= 用户配置：修改后重新启动程序 =================
DEFAULT_TARGET_IP = "192.168.123.164"  # G1 有线管理地址
DEFAULT_TARGET_PORT = 22
DEFAULT_SSH_USER = "unitree"
DEFAULT_SSH_PASSWORD = "vsislab509"  # 可在这里填写 SSH/sudo 密码；留空则启动时询问
DEFAULT_SERIAL_PORT = "COM13"
DEFAULT_WIFI_IFNAME = "wlan0"
DEFAULT_SINGLE_PASSWORD = True
DEFAULT_FAST_LINK = True
# ==============================================================

import argparse
import ipaddress
import os
import queue
import shlex
import shutil
import subprocess
import sys
import threading
import time
import unicodedata
from datetime import datetime, timezone, timedelta
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

from lora_link import DEFAULT_MAX_RETRIES, DEFAULT_RTO, SERIAL_BAUD, add_link_profile_arguments


# Keep KEXINIT small on the 64-byte stop-and-wait radio. These algorithms
# were confirmed in the G1 OpenSSH_8.2p1 proposal; host-key checks still apply.
LORA_SSH_ALGORITHMS = (
    "KexAlgorithms=curve25519-sha256",
    "HostKeyAlgorithms=ssh-ed25519,ecdsa-sha2-nistp256",
    "Ciphers=chacha20-poly1305@openssh.com,aes128-ctr",
    "MACs=hmac-sha2-256-etm@openssh.com",
)
WATCH_INTERVAL_SECONDS = 10
WATCH_BEGIN_MARKER = "__G1_WIFI_SNAPSHOT_BEGIN__"
WATCH_END_MARKER = "__G1_WIFI_SNAPSHOT_END__"
WATCH_STATUS_PREFIX = "__G1_WIFI_SNAPSHOT_STATUS__:"
WATCH_INTERFACE_PREFIX = "__G1_WIFI_INTERFACE__:"
WATCH_TOTAL_PREFIX = "__G1_WIFI_TOTAL__:"
WATCH_NEXT_MARKER = "__G1_WIFI_NEXT__"
WIFI_SELECT_MARKER = "__G1_WIFI_SELECT__"

# Match a normal nmcli Wi-Fi list by default. Forced rescans can behave
# differently from cached/automatic lists on the target's NetworkManager.
WATCH_REMOTE_SCRIPT = r"""if ! command -v nmcli >/dev/null 2>&1; then
    printf 'nmcli: not found\n' >&2
    exit 127
fi
while :; do
    printf '%s\n' '__G1_WIFI_SNAPSHOT_BEGIN__'
    printf '%s%s\n' '__G1_WIFI_INTERFACE__:' "$ifname"
    scan_output=$(PAGER= TERM=dumb LC_ALL=C nmcli --mode tabular --colors no --terse --escape yes --fields IN-USE,SSID,BSSID,CHAN,FREQ,SIGNAL,SECURITY device wifi list ifname "$ifname" --rescan auto 2>&1)
    nmcli_rc=$?
    scan_total=0
    if [ "$nmcli_rc" -eq 0 ] && [ -n "$scan_output" ]; then
        scan_total=$(printf '%s\n' "$scan_output" | wc -l)
    fi
    printf '%s%s\n' '__G1_WIFI_TOTAL__:' "$scan_total"
    if [ -n "$scan_output" ]; then printf '%s\n' "$scan_output"; fi
    printf '%s%s\n' '__G1_WIFI_SNAPSHOT_STATUS__:' "$nmcli_rc"
    printf '%s\n' '__G1_WIFI_SNAPSHOT_END__'
    sleep 10
done
"""

# Every probe command is read-only.  In particular, nmcli's Wi-Fi list uses
# --rescan no so even an active scan is not requested.  Missing commands and
# inactive services are reported, then the remaining probes continue.
PROBE_SCRIPT = r"""#!/bin/sh
section() {
    printf '\n===== %s =====\n' "$1"
}
run_probe() {
    printf '\n$'
    printf ' %s' "$@"
    printf '\n'
    "$@" 2>&1
    rc=$?
    if [ "$rc" -ne 0 ]; then
        printf '[probe] unavailable or failed (status=%s)\n' "$rc"
    fi
}

section "Identity"
run_probe id
run_probe uname -a

section "NetworkManager and Wi-Fi"
if command -v nmcli >/dev/null 2>&1; then
    run_probe nmcli general status
    run_probe nmcli device status
    run_probe nmcli radio wifi
    run_probe nmcli device wifi list --rescan no
    run_probe nmcli connection show
else
    printf 'nmcli: not found\n'
fi
if command -v systemctl >/dev/null 2>&1; then
    run_probe systemctl is-active NetworkManager
    run_probe systemctl is-enabled NetworkManager
else
    printf 'systemctl: not found\n'
fi

section "systemd-networkd"
if command -v systemctl >/dev/null 2>&1; then
    run_probe systemctl is-active systemd-networkd
    run_probe systemctl is-enabled systemd-networkd
fi
if command -v networkctl >/dev/null 2>&1; then
    run_probe networkctl --no-pager status
else
    printf 'networkctl: not found\n'
fi

section "wpa_supplicant"
if command -v systemctl >/dev/null 2>&1; then
    run_probe systemctl is-active wpa_supplicant
    run_probe systemctl is-enabled wpa_supplicant
fi
if command -v wpa_cli >/dev/null 2>&1; then
    run_probe wpa_cli status
else
    printf 'wpa_cli: not found\n'
fi

section "rfkill"
if command -v rfkill >/dev/null 2>&1; then
    run_probe rfkill list
else
    printf 'rfkill: not found\n'
fi

section "IP addresses and routes"
if command -v ip >/dev/null 2>&1; then
    run_probe ip address show
    run_probe ip route show
    run_probe ip -6 route show
else
    printf 'ip: not found\n'
fi

exit 0
"""

# This function is appended only after a successful argument-level --connect
# decision.  State commands run even if nmcli rejects the connection attempt,
# and the nmcli status remains the SSH command's exit status.
STATE_SCRIPT = r"""
printf '\n===== Post-connection state =====\n'
nmcli -t -f IN-USE,SSID,BSSID device wifi list ifname "$ifname" --rescan no | sed -n '/^\*:/p'
nmcli -f GENERAL.STATE,GENERAL.REASON,GENERAL.CONNECTION,IP4.ADDRESS,IP4.GATEWAY,IP4.DNS device show "$ifname" 2>&1
"""


def _ipv4(value: str) -> str:
    try:
        return str(ipaddress.IPv4Address(value))
    except ipaddress.AddressValueError as exc:
        raise argparse.ArgumentTypeError("must be a literal IPv4 address") from exc


def _port(value: str) -> int:
    port = int(value)
    if not 1 <= port <= 65535:
        raise argparse.ArgumentTypeError("must be in 1..65535")
    return port


def _positive_float(value: str) -> float:
    number = float(value)
    if number <= 0:
        raise argparse.ArgumentTypeError("must be positive")
    return number


def _non_negative_int(value: str) -> int:
    number = int(value)
    if number < 0:
        raise argparse.ArgumentTypeError("must be non-negative")
    return number


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    action = parser.add_mutually_exclusive_group()
    action.add_argument(
        "--probe",
        action="store_true",
        help="read-only Wi-Fi/network probe; this is the default action",
    )
    action.add_argument(
        "--connect",
        action="store_true",
        help="interactively authorize a rescan and connect to a specified Wi-Fi",
    )
    action.add_argument(
        "--watch-wifi",
        action="store_true",
        help="watch read-only nmcli terse Wi-Fi snapshots at a bounded 10-second interval",
    )
    action.add_argument(
        "--set-ipv4", action="store_true",
        help="set IPv4 on the currently active Wi-Fi profile (default interface wlan0)",
    )
    parser.add_argument("--static-ip", help="fixed Wi-Fi IPv4 address, optionally with /prefix")
    parser.add_argument("--netmask", help="subnet mask, for example 255.255.255.0 or 24")
    parser.add_argument("--gateway", type=_ipv4, help="optional IPv4 gateway")
    parser.add_argument("--dns", nargs="+", type=_ipv4, help="optional IPv4 DNS server(s)")
    parser.add_argument("--dhcp", action="store_true", help="restore automatic IPv4 with --set-ipv4")
    parser.add_argument("--ssid", help="target SSID; omit for scanned Wi-Fi selection")
    parser.add_argument("--show-aps", action="store_true", help="watch: show each BSSID instead of grouping same-name Wi-Fi networks")
    parser.add_argument("--ifname", help="optional remote Wi-Fi interface passed to nmcli as ifname")
    parser.add_argument(
        "--wifi-rescan", choices=("auto", "no", "yes"), default="auto",
        help="watch list mode: auto matches normal nmcli, no reads cache, yes forces rescan",
    )
    parser.add_argument(
        "--sudo-rescan", action="store_true",
        help="watch: validate sudo interactively, then rescan with sudo and read all cached APs",
    )
    parser.add_argument(
        "--serial-port",
        "--port",
        dest="serial_port",
        default=DEFAULT_SERIAL_PORT,
        help="local E22 CH340 serial port (default: %(default)s)",
    )
    parser.add_argument("--baud", type=int, default=SERIAL_BAUD, help=argparse.SUPPRESS)
    parser.add_argument("--target-ip", type=_ipv4, default=DEFAULT_TARGET_IP, help="G1 IPv4 address (default: %(default)s)")
    parser.add_argument("--target-port", type=_port, default=DEFAULT_TARGET_PORT, help="G1 SSH TCP port (default: %(default)s)")
    parser.add_argument("--user", default=DEFAULT_SSH_USER, help="SSH user (default: %(default)s)")
    parser.add_argument("--ssh", default="ssh", help="system OpenSSH executable (default: %(default)s)")
    parser.add_argument("--rto", type=_positive_float, default=DEFAULT_RTO, help="LoRa RTO in seconds (default: %(default)s)")
    parser.add_argument("--retries", type=_non_negative_int, default=DEFAULT_MAX_RETRIES, help="LoRa retransmission count (default: %(default)s)")
    add_link_profile_arguments(parser)
    parser.set_defaults(fast_link=DEFAULT_FAST_LINK, ssh_password=DEFAULT_SSH_PASSWORD)
    parser.add_argument("--verbose", action="store_true", help="show LoRa proxy handshake, CH32, and error logs")
    parser.add_argument(
        "--system-ssh-algorithms", action="store_true",
        help="use system algorithm lists instead of the compact G1 LoRa proposal",
    )
    parser.add_argument(
        "--password-auth", action="store_true",
        help="request interactive password authentication without trying local public keys",
    )
    backend = parser.add_mutually_exclusive_group()
    backend.add_argument(
        "--single-password", action="store_true",
        default=DEFAULT_SINGLE_PASSWORD,
        help="reuse SSH password for sudo (default; Paramiko)",
    )
    backend.add_argument("--system-ssh", dest="single_password", action="store_false",
                         help="use system OpenSSH instead of the default single-password backend")
    parser.add_argument(
        "--no-ssh-compression", action="store_true",
        help="disable SSH compression for compatibility or timing comparison",
    )
    parser.add_argument(
        "--known-hosts", default=str(Path.home() / ".ssh" / "known_hosts"),
        help="verified OpenSSH host keys used by --single-password",
    )
    parser.add_argument(
        "--ssh-debug",
        action="store_true",
        help="pass -vvv to OpenSSH for protocol-level diagnostics",
    )
    parser.add_argument(
        "--trace-io",
        action="store_true",
        help="explicitly forward binary chunk tracing to the LoRa proxy",
    )
    return parser


def validate_args(parser: argparse.ArgumentParser, args: argparse.Namespace) -> None:
    if args.connect:
        if args.ssid == "" or (args.ssid is None and not args.single_password):
            parser.error("system SSH --connect requires a non-empty --ssid")
    else:
        if args.ssid is not None:
            parser.error("--ssid is allowed only with explicit --connect")
        if args.ifname is not None and not (args.set_ipv4 or args.watch_wifi):
            parser.error("--ifname is allowed only with --connect, --watch-wifi or --set-ipv4")
    if args.connect or args.watch_wifi or args.set_ipv4:
        args.ifname = args.ifname or DEFAULT_WIFI_IFNAME
    args.ipv4_config = None
    has_ipv4 = any((args.static_ip, args.netmask, args.gateway, args.dns, args.dhcp))
    if has_ipv4 and not args.set_ipv4:
        parser.error("IPv4 settings require --set-ipv4")
    if args.set_ipv4:
        args.ifname = args.ifname or DEFAULT_WIFI_IFNAME
        if args.dhcp:
            if any((args.static_ip, args.netmask, args.gateway, args.dns)):
                parser.error("--dhcp cannot be combined with static IPv4 settings")
            args.ipv4_config = IPv4Config("auto")
        else:
            try:
                args.ipv4_config = parse_static_ipv4(
                    args.static_ip, args.netmask, args.gateway, args.dns or [])
            except ValueError as exc:
                parser.error(str(exc))
    if not args.user:
        parser.error("--user must not be empty")
    if not args.watch_wifi and args.wifi_rescan != "auto":
        parser.error("--wifi-rescan is allowed only with --watch-wifi")
    if args.sudo_rescan and not args.watch_wifi:
        parser.error("--sudo-rescan is allowed only with --watch-wifi")
    if args.sudo_rescan and args.wifi_rescan != "auto":
        parser.error("--sudo-rescan selects its own rescan/list sequence; omit --wifi-rescan")


def probe_input_bytes() -> bytes:
    """Return the remote shell script as UTF-8 with Unix LF line endings."""
    return PROBE_SCRIPT.replace("\r\n", "\n").replace("\r", "\n").encode("utf-8")


@dataclass(frozen=True)
class IPv4Config:
    method: str
    address: str = ""
    gateway: str = ""
    dns: Tuple[str, ...] = ()


def parse_static_ipv4(address, netmask, gateway, dns) -> IPv4Config:
    if not address:
        raise ValueError("--static-ip is required unless --dhcp is selected")
    if "/" in address and netmask:
        raise ValueError("use either address/prefix or --netmask, not both")
    if "/" not in address:
        if not netmask:
            raise ValueError("a plain --static-ip requires --netmask")
        address += "/" + netmask
    mask = address.split("/", 1)[1]
    if "." in mask:
        bits = format(int(ipaddress.IPv4Address(mask)), "032b")
        if "01" in bits:
            raise ValueError("subnet mask must contain contiguous leading ones")
    interface = ipaddress.IPv4Interface(address)
    network, ip = interface.network, interface.ip
    if ip.is_multicast or ip.is_loopback or ip.is_unspecified or ip.is_reserved:
        raise ValueError("the fixed address must be a unicast LAN address")
    if network.prefixlen < 31 and ip in (network.network_address, network.broadcast_address):
        raise ValueError("the fixed address cannot be the network or broadcast address")
    if network.overlaps(ipaddress.IPv4Network("192.168.123.0/24")):
        raise ValueError("Wi-Fi subnet overlaps the CH32/G1 wired management subnet 192.168.123.0/24")
    if gateway:
        gw = ipaddress.IPv4Address(gateway)
        if gw not in network or gw == ip or (network.prefixlen < 31 and gw in (
                network.network_address, network.broadcast_address)):
            raise ValueError("gateway must be another usable address in the same Wi-Fi subnet")
    servers = tuple(dict.fromkeys(str(ipaddress.IPv4Address(value)) for value in dns))
    return IPv4Config("manual", str(interface), gateway or "", servers)


def split_nmcli_terse(line: str) -> List[str]:
    """Split nmcli terse fields, honoring its backslash-escaped colon/slash."""
    fields: List[str] = []
    field: List[str] = []
    escaped = False
    for character in line:
        if escaped:
            field.append(character)
            escaped = False
        elif character == "\\":
            escaped = True
        elif character == ":":
            fields.append("".join(field))
            field = []
        else:
            field.append(character)
    if escaped:
        # Preserve malformed trailing escapes instead of silently dropping data.
        field.append("\\")
    fields.append("".join(field))
    return fields


@dataclass(frozen=True)
class WifiRecord:
    ifname: str
    in_use: bool
    ssid: str
    bssid: str
    channel: str
    signal: str
    security: str
    frequency: str = ""

    @property
    def key(self) -> Tuple[str, str]:
        return self.ifname, self.bssid


def parse_wifi_record(line: str, ifname: Optional[str] = None) -> WifiRecord:
    fields = split_nmcli_terse(line)
    if len(fields) != 7:
        raise ValueError("expected seven nmcli Wi-Fi fields")
    frequency = ""
    if ifname is None:
        # Compatibility with older DEVICE-first snapshots.
        ifname, in_use, ssid, bssid, channel, signal, security = fields
    else:
        in_use, ssid, bssid, channel, frequency, signal, security = fields
    return WifiRecord(
        ifname=ifname,
        in_use=in_use.strip() == "*",
        ssid=ssid,
        bssid=bssid,
        channel=channel,
        signal=signal,
        security=security,
        frequency=frequency,
    )


@dataclass(frozen=True)
class WifiSnapshot:
    records: Tuple[WifiRecord, ...]
    status: int
    malformed_records: int
    complete: bool = True
    expected_records: Optional[int] = None


class WatchOutputParser:
    """Incrementally parse complete snapshots from OpenSSH stdout bytes.

    This parser is deliberately used on the SSH client's decrypted nmcli
    output only.  The independent ProxyCommand binary stream is never wrapped
    in a text stream or passed here.
    """

    def __init__(self) -> None:
        self._buffer = b""
        self._collecting = False
        self._records: List[WifiRecord] = []
        self._status = 1
        self._malformed_records = 0
        self._ifname = None
        self._expected = None

    def _begin(self) -> None:
        # A new BEGIN abandons an incomplete old snapshot rather than merging it.
        self._collecting = True
        self._records = []
        self._status = 1
        self._malformed_records = 0
        self._ifname = None
        self._expected = None

    def _snapshot(self, complete: bool = False) -> WifiSnapshot:
        return WifiSnapshot(tuple(self._records), self._status,
                            self._malformed_records, complete, self._expected)

    def _line(self, raw_line: bytes) -> List[WifiSnapshot]:
        if raw_line.endswith(b"\r"):
            raw_line = raw_line[:-1]
        if raw_line == WATCH_BEGIN_MARKER.encode("ascii"):
            self._begin()
            return [self._snapshot()]
        if raw_line == WATCH_END_MARKER.encode("ascii"):
            if not self._collecting:
                return []
            if self._status == 0 and self._expected is not None and self._expected != len(self._records):
                self._malformed_records += 1
            snapshot = self._snapshot(complete=True)
            self._collecting = False
            self._records = []
            return [snapshot]
        if not self._collecting:
            return []
        if raw_line.startswith(WATCH_INTERFACE_PREFIX.encode("ascii")):
            self._ifname = raw_line[len(WATCH_INTERFACE_PREFIX):].decode("utf-8", "replace")
            return []
        if raw_line.startswith(WATCH_TOTAL_PREFIX.encode("ascii")):
            try:
                self._expected = int(raw_line[len(WATCH_TOTAL_PREFIX):])
                if self._expected < 0:
                    raise ValueError("negative record count")
            except ValueError:
                self._expected = None
                self._malformed_records += 1
            return [self._snapshot()]
        if raw_line.startswith(WATCH_STATUS_PREFIX.encode("ascii")):
            raw_status = raw_line[len(WATCH_STATUS_PREFIX) :]
            try:
                self._status = int(raw_status.decode("ascii"))
            except (UnicodeDecodeError, ValueError):
                self._status = 1
            return []
        if not raw_line:
            return []
        # Replacement makes malformed/non-UTF-8 remote bytes safe to display.
        line = raw_line.decode("utf-8", errors="replace")
        try:
            self._records.append(parse_wifi_record(line, self._ifname))
        except ValueError:
            self._malformed_records += 1
        return [self._snapshot()]

    def feed(self, data: bytes) -> List[WifiSnapshot]:
        """Return only completed snapshots; arbitrary byte fragmentation is safe."""
        return [snapshot for snapshot in self.feed_updates(data) if snapshot.complete]

    def feed_updates(self, data: bytes) -> List[WifiSnapshot]:
        """Also expose completed rows before a slow radio finishes the scan."""
        lines = (self._buffer + bytes(data)).split(b"\n")
        self._buffer = lines.pop()
        snapshots: List[WifiSnapshot] = []
        for raw_line in lines:
            snapshots.extend(self._line(raw_line))
        return snapshots


class WifiTable:
    """Current complete snapshot, keyed by (interface, BSSID)."""

    def __init__(self) -> None:
        self._records: Dict[Tuple[str, str], WifiRecord] = {}

    @property
    def records(self) -> Dict[Tuple[str, str], WifiRecord]:
        return dict(self._records)

    def replace_snapshot(self, records: Iterable[WifiRecord]) -> None:
        # Assignment of a newly built mapping updates changed entries and
        # removes every entry absent from a shorter/new complete snapshot.
        self._records = {record.key: record for record in records}

    def update_records(self, records: Iterable[WifiRecord]) -> None:
        # Missing APs must only be removed after a successful complete scan.
        self._records.update((record.key, record) for record in records)

    def ordered_records(self) -> List[WifiRecord]:
        return sorted(
            self._records.values(),
            key=wifi_sort_key,
        )


def wifi_sort_key(record: WifiRecord) -> tuple:
    try:
        signal = int(record.signal)
    except ValueError:
        signal = -1
    return (-signal, record.ssid.casefold(), record.ifname, record.bssid)


def wifi_network_rows(records: Iterable[WifiRecord], grouped: bool = True):
    """Group display rows only. Keep the underlying BSSID snapshot intact."""
    unique = {record.key: record for record in records}
    groups = {}
    for record in unique.values():
        security = " ".join(record.security.split()) or "OPEN"
        anonymous = not record.ssid or "\ufffd" in record.ssid or set(record.ssid) == {"?"}
        key = ((record.ifname, record.ssid, security) if grouped and not anonymous
               else (record.ifname, record.bssid))
        groups.setdefault(key, []).append(record)
    rows = []
    for candidates in groups.values():
        # Keep all displayed fields true to the associated BSSID. For an
        # unconnected network choose its strongest AP deterministically.
        representative = min(candidates, key=lambda record: (not record.in_use, wifi_sort_key(record)))
        rows.append((representative, len(candidates)))
    return sorted(rows, key=lambda row: wifi_sort_key(row[0])), len(unique)


def terminal_safe_text(value: str) -> str:
    """Preserve Unicode while making control bytes/ANSI escapes visible text."""
    return "".join(
        character.encode("unicode_escape").decode("ascii")
        if unicodedata.category(character) == "Cc"
        else character
        for character in value
    )


def fit_terminal_text(value: str, width: int, pad: bool = False) -> str:
    """Fit text to terminal cells, including Chinese and combining marks."""
    result = []
    used = 0
    for character in value:
        cells = 0 if unicodedata.combining(character) else (
            2 if unicodedata.east_asian_width(character) in ("W", "F") else 1
        )
        if used + cells > width:
            break
        result.append(character)
        used += cells
    return "".join(result) + (" " * (width - used) if pad else "")


class WifiSelectionCancelled(Exception):
    pass


class WifiConnectionPicker:
    """Consume one validated scan, show numbered networks and reply over SSH."""
    def __init__(self, send, stream=None, input_fn=None):
        self.send = send
        self.stream = stream if stream is not None else sys.stdout
        self.input_fn = input_fn if input_fn is not None else input
        self.parser = WatchOutputParser()
        self.pending = b""
        self.collecting = False
        self.snapshot = None
        self.selected = False

    def choose(self):
        rows, ap_count = wifi_network_rows(self.snapshot.records)
        choices = [(record, count) for record, count in rows
                   if record.ssid and "\ufffd" not in record.ssid]
        print("\n可选 Wi-Fi：{} 个网络 / {} 个接入点，按信号排序".format(
            len(choices), ap_count), file=self.stream)
        print(" 编号   信号  SSID                              加密方式       AP", file=self.stream)
        for index, (record, count) in enumerate(choices, 1):
            print("{}{:>4}  {:>4}%  {}  {} {:>3}".format(
                "*" if record.in_use else " ", index, record.signal,
                fit_terminal_text(terminal_safe_text(record.ssid), 32, pad=True),
                fit_terminal_text(terminal_safe_text(record.security or "OPEN"), 14, pad=True),
                count), file=self.stream)
        print("* 表示当前已连接；隐藏或无法解码的名称不提供编号。", file=self.stream, flush=True)
        while True:
            choice = self.input_fn("输入 Wi-Fi 编号，m 手动输入名称，q 取消：").strip()
            if choice.lower() == "q":
                raise WifiSelectionCancelled()
            if choice.lower() == "m":
                ssid = self.input_fn("目标 Wi-Fi 名称（精确 SSID）：")
                if not ssid or any(c in ssid for c in "\r\n\x00"):
                    print("SSID 不能为空或包含换行。", file=self.stream)
                    continue
                return ssid, ""
            if choice.isdecimal() and 1 <= int(choice) <= len(choices):
                record = choices[int(choice) - 1][0]
                print("已选择：" + terminal_safe_text(record.ssid), file=self.stream, flush=True)
                return record.ssid, record.bssid
            print("请输入有效编号，或 m / q。", file=self.stream, flush=True)

    def feed(self, data):
        if self.selected:
            return data
        self.pending += data
        output = bytearray()
        while b"\n" in self.pending:
            line, self.pending = self.pending.split(b"\n", 1)
            raw = line.rstrip(b"\r")
            if raw == WATCH_BEGIN_MARKER.encode():
                self.collecting = True
            if self.collecting:
                snapshots = self.parser.feed(line + b"\n")
                if raw == WATCH_END_MARKER.encode():
                    self.collecting = False
                    self.snapshot = snapshots[-1] if snapshots else None
                    if (self.snapshot is None or self.snapshot.status != 0 or
                            self.snapshot.malformed_records or self.snapshot.expected_records is None):
                        raise ValueError("Incomplete/invalid Wi-Fi scan; no connection was selected")
                continue
            if raw == WIFI_SELECT_MARKER.encode():
                if self.snapshot is None:
                    raise ValueError("Wi-Fi selection requested without a complete scan")
                ssid, bssid = self.choose()
                self.send((ssid + "\n" + bssid + "\n").encode("utf-8"))
                self.selected = True
                output.extend(self.pending)
                self.pending = b""
                break
            output.extend(line + b"\n")
        return bytes(output)

    def finish(self):
        if self.collecting or (self.snapshot is not None and not self.selected):
            raise ValueError("Wi-Fi selection stream ended before completion")
        tail, self.pending = self.pending, b""
        return tail


class WifiRenderer:
    """Keep a fixed terminal page and write only rows whose content changed."""

    def __init__(self, stream, tty: Optional[bool] = None, group_networks: bool = True) -> None:
        self.stream = stream
        self.tty = bool(stream.isatty()) if tty is None else tty
        self._previous_lines: List[str] = []
        self._screen_size = None
        self._active = False
        self._printed = False
        self.page = 0
        self.page_count = 1
        self.group_networks = group_networks
        if self.tty and os.name == "nt" and stream.isatty():
            # Enable ANSI cursor control in a Windows console. A redirected
            # stream never enters this path; no global shell settings change.
            import ctypes
            import msvcrt
            mode = ctypes.c_ulong()
            handle = ctypes.c_void_p(msvcrt.get_osfhandle(stream.fileno()))
            kernel = ctypes.windll.kernel32
            if kernel.GetConsoleMode(handle, ctypes.byref(mode)):
                kernel.SetConsoleMode(handle, mode.value | 0x0004)

    def move_page(self, delta: int) -> None:
        self.page = max(0, min(self.page + delta, self.page_count - 1))

    def close(self) -> None:
        if self._active:
            self.stream.write("\x1b[?25h\x1b[?1049l")
            self.stream.flush()
            self._active = False
            self._previous_lines = []

    def render(
        self,
        records: Iterable[WifiRecord],
        status: int = 0,
        malformed_records: int = 0,
        receiving: bool = False,
        rows_received: Optional[int] = None,
        completed_scans: Optional[int] = None,
        last_update: Optional[str] = None,
        silence_seconds: Optional[int] = None,
        expected_records: Optional[int] = None,
    ) -> None:
        ordered, ap_count = wifi_network_rows(records, self.group_networks)
        size = shutil.get_terminal_size(fallback=(120, 30))
        if self.tty and self.stream.isatty():
            try:
                # Prefer the actual console viewport over stale LINES/COLUMNS.
                size = os.get_terminal_size(self.stream.fileno())
            except (OSError, ValueError):
                pass
        width = max(1, size.columns - 1)  # Avoid terminal automatic wrapping.
        capacity = max(0, size.lines - 4)
        self.page_count = max(1, (len(ordered) + max(1, capacity) - 1) // max(1, capacity))
        self.page = min(self.page, self.page_count - 1)
        start = self.page * capacity if self.tty else 0
        visible = ordered[start:start + capacity] if self.tty else ordered
        label = "network(s)" if self.group_networks else "access point(s)"
        lines = ["G1 Wi-Fi snapshot: {} {} | {} AP(s)".format(len(ordered), label, ap_count),
                 "    SIGNAL  SSID                          SECURITY      AP  CH   DEVICE / BSSID"]
        if completed_scans is not None:
            lines[0] = "Wi-Fi: {} {} / {} AP | {}-{}/{} | done={} | last={}".format(
                len(ordered), "nets" if self.group_networks else "rows", ap_count,
                start + 1 if visible else 0, start + len(visible), len(ordered),
                completed_scans, last_update or "waiting")
        for record, count in visible:
            lines.append(
                "{}   {:>3}%  {}  {}  {:>2} {:>3}  {} / {}".format(
                    "*" if record.in_use else " ",
                    terminal_safe_text(record.signal),
                    fit_terminal_text(terminal_safe_text(record.ssid or "<hidden>"), 28, pad=True),
                    fit_terminal_text(terminal_safe_text(record.security or "OPEN"), 12, pad=True),
                    count,
                    terminal_safe_text(record.channel),
                    terminal_safe_text(record.ifname),
                    terminal_safe_text(record.bssid),
                )
            )
        if not ordered:
            lines.append("  (no Wi-Fi access points reported)")
        parts = []
        if (status and not receiving) or malformed_records:
            parts.append("SCAN ERROR status={} invalid={}; keeping last good list".format(status, malformed_records))
        if rows_received is not None:
            progress = str(rows_received) if expected_records is None else "{}/{}".format(rows_received, expected_records)
            parts.append("{}: {} rows".format(
                "receiving scan" if receiving else "scan complete", progress))
        if silence_seconds is not None:
            parts.append("{} {}s".format("NO NEW DATA" if silence_seconds >= 30 else "idle", silence_seconds))
        if self.tty and len(visible) < len(ordered):
            parts.append("showing {}/{} page {}/{}".format(len(visible), len(ordered), self.page + 1, self.page_count))
        parts.append("N/P: page | Q/Esc: exit | * connected")
        lines.append(" | ".join(parts))

        if self.tty:
            lines = [fit_terminal_text(line, width) for line in lines[:max(1, size.lines - 1)]]
            if not self._active:
                self.stream.write("\x1b[?1049h\x1b[?25l\x1b[2J")
                self._active = True
            elif self._screen_size != size:
                self.stream.write("\x1b[2J")
                self._previous_lines = []
            for index in range(max(len(lines), len(self._previous_lines))):
                line = lines[index] if index < len(lines) else ""
                old = self._previous_lines[index] if index < len(self._previous_lines) else None
                if line != old:
                    self.stream.write("\x1b[{};1H\x1b[2K{}".format(index + 1, line))
            self._previous_lines = lines
            self._screen_size = size
        else:
            if self._printed:
                self.stream.write("\n")
            self.stream.write("\n".join(lines) + "\n")
            self._printed = True
        self.stream.flush()


def _quote_command(arguments: List[str]) -> str:
    # OpenSSH receives ProxyCommand as one -o value and invokes the local
    # platform command processor.  Use the native list quoting convention.
    if os.name == "nt":
        return subprocess.list2cmdline(arguments)
    return shlex.join(arguments)


def build_proxy_command(args: argparse.Namespace) -> str:
    proxy_script = Path(__file__).resolve().with_name("lora_ssh_proxy.py")
    arguments = [
        sys.executable or "python",
        str(proxy_script),
        "--serial-port",
        args.serial_port,
        "--baud",
        str(args.baud),
        "--target-ip",
        args.target_ip,
        "--target-port",
        str(args.target_port),
        "--rto",
        str(args.rto),
        "--retries",
        str(args.retries),
    ]
    if args.verbose:
        arguments.append("--verbose")
    arguments.append("--fast-link" if args.fast_link else "--legacy-link")
    if args.trace_io:
        # Never implied by --verbose or --watch-wifi; this is an explicit opt-in.
        arguments.append("--trace-io")
    return _quote_command(arguments)


def build_ssh_arguments(args: argparse.Namespace, remote_command: str) -> List[str]:
    command = [
        args.ssh,
        "-o",
        "TCPKeepAlive=yes",
        "-o",
        "ServerAliveInterval=30",
        "-o",
        "ServerAliveCountMax=6",
        "-o",
        "ProxyCommand=" + build_proxy_command(args),
        "-p",
        str(args.target_port),
    ]
    if args.ssh_debug:
        command.append("-vvv")
    command.extend(["-o", "Compression=" + ("no" if args.no_ssh_compression else "yes")])
    if not args.system_ssh_algorithms:
        for option in LORA_SSH_ALGORITHMS:
            command.extend(["-o", option])
    if args.password_auth:
        command.extend(["-o", "PreferredAuthentications=password",
                        "-o", "PubkeyAuthentication=no"])
    if args.connect or args.set_ipv4 or (args.watch_wifi and args.sudo_rescan):
        # A remote TTY lets sudo/nmcli prompt securely with terminal echo off.
        command.append("-tt")
    else:
        command.append("-T")
    command.extend(["--", "{}@{}".format(args.user, args.target_ip), remote_command])
    return command


def build_connect_remote_command(ssid: Optional[str], ifname: Optional[str]) -> str:
    # shlex.quote targets the remote POSIX shell.  There is deliberately no
    # password=..., PSK environment variable, or secret on this command line.
    parts = [
        "sudo -n nmcli --colors no --wait 90 --ask device wifi connect",
        shlex.quote(ssid) if ssid is not None else '"$target_ssid"',
    ]
    ifname = ifname or DEFAULT_WIFI_IFNAME
    parts.extend(["ifname", shlex.quote(ifname)])
    # A scan request alone is not a fresh list. Use the forced-list operation
    # proven by the physical G1 test before nmcli looks up the target SSID.
    scan = ("sudo -n nmcli -t -f SSID device wifi list ifname " + shlex.quote(ifname) +
            " --rescan yes >/dev/null")
    selection = ""
    connection = " ".join(parts)
    if ssid is None:
        # The PC receives one complete snapshot, then sends only SSID/BSSID.
        # Both reads use stdin; the selected values never become shell code.
        scan = ('scan=$(sudo -n nmcli --colors no --escape yes -t -f IN-USE,SSID,BSSID,CHAN,FREQ,SIGNAL,SECURITY '
                'device wifi list ifname "$ifname" --rescan yes)')
        selection = (
            "if [ -t 0 ]; then stty -echo || exit $?; fi\n"
            "printf '%s\\n' '" + WATCH_BEGIN_MARKER + "'\n"
            "printf '%s%s\\n' '" + WATCH_INTERFACE_PREFIX + "' \"$ifname\"\n"
            "total=$(printf '%s\\n' \"$scan\" | awk 'NF {n++} END {print n+0}')\n"
            "printf '%s%s\\n' '" + WATCH_TOTAL_PREFIX + "' \"$total\"\n"
            "[ -z \"$scan\" ] || printf '%s\\n' \"$scan\"\n"
            "printf '%s\\n' '" + WATCH_STATUS_PREFIX + "0' '" + WATCH_END_MARKER + "'\n"
            "printf '%s\\n' '" + WIFI_SELECT_MARKER + "'\n"
            "IFS= read -r target_ssid || exit 130\n"
            "IFS= read -r target_bssid || exit 130\n"
            "[ -n \"$target_ssid\" ] || exit 130\n"
            "if [ -t 0 ]; then stty echo || exit $?; fi\n")
        connection = ('set -- ' + connection + '\n'
                      '[ -z "$target_bssid" ] || set -- "$@" bssid "$target_bssid"\n'
                      '"$@"')
    # Same privileged forced-list sequence used by the live Wi-Fi page. The
    # subsequent --ask prompt travels over the existing SSH TTY, with echo off.
    # Disable paging on this TTY so state output cannot stop at a less prompt.
    return (
        "export LC_ALL=C TERM=dumb PAGER=\n"
        "ifname=" + shlex.quote(ifname) + "\n"
        "sudo -v || exit $?\necho '[G1] Scan'\n" + scan + " || exit $?\n" +
        selection + "echo '[G1] Connect (NetworkManager wait: 90s; saved credentials may be reused)'\n" +
        connection + "\nnmcli_rc=$?" + STATE_SCRIPT +
        'printf "\\nWi-Fi connection command status: %s\\n" "$nmcli_rc"\n' +
        'exit "$nmcli_rc"\n'
    )


def build_watch_remote_command(rescan: str = "auto", sudo_rescan: bool = False, ifname: str = "wlan0", wait_for_ack: bool = False) -> str:
    # No default-probe input or TTY is reused; watch has its own bounded loop.
    if rescan not in ("auto", "no", "yes"):
        raise ValueError("unsupported Wi-Fi rescan mode")
    script = 'ifname=' + shlex.quote(ifname) + '\n' + WATCH_REMOTE_SCRIPT.replace("--rescan auto", "--rescan " + rescan)
    if sudo_rescan:
        # Authenticate before emitting BEGIN so the PC can display the sudo
        # prompt before opening the fixed page. No password enters the parser.
        script = script.replace("while :; do", "printf 'Authorize Wi-Fi scanning with sudo.\\n'\n"
                                "sudo -v || exit $?\nwhile :; do")
        # Use the same explicit-interface, forced-scan list that was verified
        # on the robot, rather than requesting a scan then reading stale cache.
        script = script.replace("LC_ALL=C nmcli", "LC_ALL=C sudo -n nmcli")
        script = script.replace("--rescan " + rescan, "--rescan yes")
    if wait_for_ack:
        script = script.replace("while :; do", "while :; do\n"
                                "    read scan_started _ </proc/uptime\n"
                                "    scan_started=${scan_started%.*}")
        script = script.replace("    sleep 10", '    IFS= read -r next_scan || exit 0\n'
                                '    [ "$next_scan" = "' + WATCH_NEXT_MARKER + '" ] || exit 2\n'
                                '    read scan_now _ </proc/uptime\n'
                                '    scan_delay=$((10 - ${scan_now%.*} + scan_started))\n'
                                '    if [ "$scan_delay" -gt 0 ]; then sleep "$scan_delay"; fi')
    return "sh -c " + shlex.quote(script)


def build_ipv4_remote_command(ifname: str, config: IPv4Config) -> str:
    # Resolve the active profile through its device, then address it by UUID.
    # SSIDs/profile names are not unique and must not select an Ethernet profile.
    script = "export LC_ALL=C TERM=dumb PAGER=\nifname=" + shlex.quote(ifname) + r'''
kind=$(nmcli -g GENERAL.TYPE device show "$ifname") || exit $?
case "$kind" in wifi|802-11-wireless) ;; *) echo 'Refusing IPv4 change: target device is not Wi-Fi.' >&2; exit 2;; esac
uuid=$(nmcli -t -f UUID,DEVICE connection show --active | awk -F: -v dev="$ifname" '$2 == dev {print $1}')
case "$uuid" in ''|*[!0-9a-fA-F-]*) echo 'No unique active Wi-Fi profile; connect the target Wi-Fi first.' >&2; exit 2;; esac
kind=$(nmcli -g connection.type connection show uuid "$uuid") || exit $?
[ "$kind" = '802-11-wireless' ] || { echo 'Refusing to modify a non-Wi-Fi profile.' >&2; exit 2; }
sudo -v || exit $?
'''
    properties = ["ipv4.method", config.method, "ipv4.addresses", config.address,
                  "ipv4.gateway", config.gateway, "ipv4.dns", ",".join(config.dns),
                  "ipv4.ignore-auto-dns", "yes" if config.method == "manual" else "no"]
    script += ('sudo -n nmcli connection modify uuid "$uuid" ' +
               " ".join(shlex.quote(value) for value in properties) + " || exit $?\n")
    script += 'sudo -n nmcli --ask connection up uuid "$uuid" ifname "$ifname"\nipv4_rc=$?\n'
    if config.method == "manual":
        script += ('if [ "$ipv4_rc" -eq 0 ]; then\n'
                   '    ip -4 -o address show dev "$ifname" | awk \'{print $4}\' | grep -Fxq ' +
                   shlex.quote(config.address) + ' || ipv4_rc=1\nfi\n')
    else:
        script += ('if [ "$ipv4_rc" -eq 0 ]; then\n'
                   '    ip -4 -o address show dev "$ifname" | grep -q " inet " || ipv4_rc=1\nfi\n')
    script += r'''
printf '\n===== Saved Wi-Fi IPv4 configuration =====\n'
nmcli -f ipv4.method,ipv4.addresses,ipv4.gateway,ipv4.dns connection show uuid "$uuid"
printf '\n===== Applied Wi-Fi IPv4 configuration =====\n'
nmcli -f GENERAL.DEVICE,GENERAL.STATE,GENERAL.CONNECTION,IP4.ADDRESS,IP4.GATEWAY,IP4.DNS device show "$ifname"
printf '\nWi-Fi IPv4 configuration status: %s\n' "$ipv4_rc"
exit "$ipv4_rc"
'''
    return script


class WatchPreamble:
    """Forward remote sudo prompts immediately, even without a newline."""

    def __init__(self, stream) -> None:
        self.stream = stream
        self.pending = b""
        self.started = False

    def _write(self, data: bytes) -> None:
        if data:
            if hasattr(self.stream, "buffer"):
                self.stream.buffer.write(data)
                self.stream.buffer.flush()
            else:
                self.stream.write(data.decode("utf-8", errors="replace"))
                self.stream.flush()

    def feed(self, data: bytes) -> bytes:
        if self.started:
            return data
        data = self.pending + data
        marker = WATCH_BEGIN_MARKER.encode("ascii")
        index = data.find(marker)
        if index >= 0:
            self._write(data[:index])
            self.pending = b""
            self.started = True
            return data[index:]
        # Keep only a possible fragmented BEGIN marker; prompts are unbuffered.
        keep = 0
        for length in range(1, min(len(data), len(marker) - 1) + 1):
            if data.endswith(marker[:length]):
                keep = length
        self.pending = data[-keep:] if keep else b""
        self._write(data[:-keep] if keep else data)
        return b""

    def close(self) -> None:
        self._write(self.pending)
        self.pending = b""


def report_ssh_exit(returncode: int) -> None:
    """Report transport/remote failures without calling them a local timeout."""
    if returncode == 0:
        return
    if returncode == 255:
        message = "OpenSSH disconnected or failed abnormally (status=255)"
    else:
        message = "OpenSSH or the remote command exited with status={}".format(
            returncode
        )
    print(
        message + "; no local password/input timeout was imposed.",
        file=sys.stderr,
    )


class WatchReader:
    """Read a blocking SSH stream off-thread so the page can show idle time."""
    def __init__(self, read):
        self.read = read
        self.events = queue.Queue(maxsize=32)
        self.stop = threading.Event()
        self.thread = threading.Thread(target=self._run, name="wifi-watch-reader", daemon=True)
        self.thread.start()

    def _put(self, event):
        while not self.stop.is_set():
            try:
                self.events.put(event, timeout=0.1)
                return
            except queue.Full:
                pass

    def _run(self):
        try:
            while not self.stop.is_set():
                chunk = self.read()
                self._put((chunk, None))
                if not chunk:
                    return
        except Exception as exc:
            self._put((None, exc))

    def next(self, timeout=1.0):
        try:
            chunk, error = self.events.get(timeout=timeout)
        except queue.Empty:
            return None
        if error is not None:
            raise error
        return chunk


class WatchKeys:
    """Read exit keys only after authentication and the first scan marker."""
    def __init__(self, stream):
        self.stream = stream
        self.active = False
        self.saved = None
        self.page_delta = 0

    def start(self):
        if self.active or not self.stream.isatty():
            return
        if os.name != "nt":
            import termios
            import tty
            self.saved = termios.tcgetattr(self.stream.fileno())
            tty.setcbreak(self.stream.fileno())
        self.active = True

    def quit_requested(self):
        if not self.active:
            return False
        if os.name == "nt":
            import msvcrt
            while msvcrt.kbhit():
                key = msvcrt.getwch()
                if key in ("\x00", "\xe0"):
                    msvcrt.getwch()
                elif key in ("q", "Q", "\x1b", "\x03"):
                    return True
                elif key.lower() == "n":
                    self.page_delta += 1
                elif key.lower() == "p":
                    self.page_delta -= 1
        else:
            import select
            while select.select([self.stream], [], [], 0)[0]:
                key = os.read(self.stream.fileno(), 1)
                if key in (b"q", b"Q", b"\x1b", b"\x03"):
                    return True
                elif key.lower() == b"n":
                    self.page_delta += 1
                elif key.lower() == b"p":
                    self.page_delta -= 1
        return False

    def close(self):
        if self.saved is not None:
            import termios
            termios.tcsetattr(self.stream.fileno(), termios.TCSANOW, self.saved)
        self.active = False


def stop_watch_process(process):
    """Stop only this watch's SSH process and its owned proxy child."""
    if process.poll() is not None:
        return
    if os.name == "nt" and isinstance(getattr(process, "pid", None), int):
        try:
            subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                           check=False, timeout=3)
        except (OSError, subprocess.TimeoutExpired):
            pass
    if process.poll() is None:
        process.terminate()
    try:
        process.wait(timeout=3)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=3)


def run_watch(command: List[str], process=None, read_chunk=None, show_aps=False) -> int:
    """Stream decrypted nmcli snapshots from OpenSSH, never from the proxy."""
    process = process if process is not None else subprocess.Popen(
        command,
        stdin=None,
        stdout=subprocess.PIPE,
        stderr=None,
    )
    parser = WatchOutputParser()
    table = WifiTable()
    last_good_records: List[WifiRecord] = []
    renderer = WifiRenderer(sys.stdout, group_networks=not show_aps)
    preamble = WatchPreamble(sys.stderr)
    received_bytes = 0
    completed_scans = 0
    latest_snapshot: Optional[WifiSnapshot] = None
    reader = None
    last_received = time.monotonic()
    last_update = None
    keys = WatchKeys(sys.stdin)
    user_quit = False

    def render_state():
        if latest_snapshot is not None:
            renderer.render(
                table.ordered_records(), status=latest_snapshot.status,
                malformed_records=latest_snapshot.malformed_records,
                receiving=not latest_snapshot.complete,
                rows_received=len(latest_snapshot.records) + latest_snapshot.malformed_records,
                completed_scans=completed_scans, last_update=last_update,
                expected_records=latest_snapshot.expected_records,
                silence_seconds=int(time.monotonic() - last_received))

    try:
        assert process.stdout is not None
        reader = WatchReader(read_chunk or (lambda: os.read(process.stdout.fileno(), 4096)))
        while True:
            if latest_snapshot is not None:
                keys.start()
                if keys.quit_requested():
                    user_quit = True
                    stop_watch_process(process)
                    break
                if isinstance(keys.page_delta, int) and keys.page_delta:
                    renderer.move_page(keys.page_delta)
                    keys.page_delta = 0
                    render_state()
            # read(4096) on a BufferedReader can wait for a full buffer; os.read
            # returns each currently available chunk so snapshots stay live.
            chunk = reader.next(timeout=0.1)
            if chunk is None:
                # Only the idle indicator ticks. Completed scans and their
                # timestamp advance exclusively on received END markers.
                if renderer.tty:
                    render_state()
                continue
            if not chunk:
                break
            last_received = time.monotonic()
            received_bytes += len(chunk)
            updates = parser.feed_updates(preamble.feed(chunk))
            # Coalesce rows arriving in one OS read into one display update,
            # but expose each received batch without waiting for the END marker.
            for snapshot in updates:
                latest_snapshot = snapshot
                if snapshot.complete:
                    completed_scans += 1
                    last_update = datetime.now(timezone(timedelta(hours=8))).strftime("%H:%M:%S")
                    request_next = getattr(process, "request_next_scan", None)
                    if request_next is not None:
                        request_next()
                if not snapshot.complete:
                    table.replace_snapshot(last_good_records)
                    table.update_records(snapshot.records)
                elif snapshot.status == 0 and snapshot.malformed_records == 0:
                    last_good_records = list(snapshot.records)
                    table.replace_snapshot(snapshot.records)
                else:
                    table.replace_snapshot(last_good_records)
            if updates:
                render_state()
        returncode = 0 if user_quit else process.wait()
    except BaseException:
        # Only an actual local exception/interrupt stops a running SSH client.
        # Password prompts and remote keepalive waits have no local deadline.
        if process.poll() is None:
            stop_watch_process(process)
        raise
    finally:
        if reader is not None:
            reader.stop.set()
        renderer.close()
        keys.close()
        preamble.close()
        if latest_snapshot is not None:
            print("Wi-Fi watch stopped: latest scan {} row(s), {} AP(s) in list, "
                  "{} complete scan(s), {} received byte(s), {} invalid row(s).".format(
                      len(latest_snapshot.records) + latest_snapshot.malformed_records,
                      len(table.records), completed_scans, received_bytes,
                      latest_snapshot.malformed_records), file=sys.stderr)
        if process.stdout is not None:
            process.stdout.close()
        if reader is not None:
            reader.thread.join(timeout=0.2)
    report_ssh_exit(returncode)
    return returncode


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.connect and args.ssid is None and not args.single_password:
        try:
            print("Target Wi-Fi SSID: ", end="", file=sys.stderr, flush=True)
            args.ssid = input()
        except (EOFError, KeyboardInterrupt):
            print("\nWi-Fi connection cancelled.", file=sys.stderr)
            return 130
    if args.set_ipv4 and not args.dhcp and args.static_ip is None:
        try:
            args.static_ip = input("Fixed Wi-Fi IPv4 address (or address/prefix): ")
            if "/" not in args.static_ip:
                args.netmask = args.netmask or input("Subnet mask (e.g. 255.255.255.0): ")
            if args.gateway is None:
                args.gateway = input("Gateway (Enter for none): ") or None
            if args.dns is None:
                args.dns = input("DNS servers, space-separated (Enter for none): ").replace(",", " ").split()
        except (EOFError, KeyboardInterrupt):
            print("\nIPv4 configuration cancelled.", file=sys.stderr)
            return 130
    validate_args(parser, args)

    if args.connect:
        remote_command = build_connect_remote_command(args.ssid, args.ifname)
        command = build_ssh_arguments(args, remote_command)
        print(
            "Starting explicit interactive nmcli setup on {}@{}; "
            "enter the requested credentials in this terminal.".format(
                args.user, args.target_ip
            ),
            file=sys.stderr,
        )
        input_script = None
        if not args.fast_link:
            print("LoRa mode: LEGACY explicitly requested with --legacy-link.",
                  file=sys.stderr)
    elif args.set_ipv4:
        remote_command = build_ipv4_remote_command(args.ifname, args.ipv4_config)
        command = build_ssh_arguments(args, remote_command)
        print("Configuring current Wi-Fi profile on {}: method={}, address={}, gateway={}, DNS={}".format(
            args.ifname, args.ipv4_config.method, args.ipv4_config.address or "DHCP",
            args.ipv4_config.gateway or ("automatic" if args.dhcp else "none"),
            ",".join(args.ipv4_config.dns) or ("automatic" if args.dhcp else "none")),
            file=sys.stderr)
        input_script = None
    elif args.watch_wifi:
        command = build_ssh_arguments(args, build_watch_remote_command(
            args.wifi_rescan, args.sudo_rescan, args.ifname or DEFAULT_WIFI_IFNAME, wait_for_ack=args.single_password))
        print(
            "Starting G1 Wi-Fi watch; list mode={}, remote loop delay={} seconds.".format(
                "sudo forced scan list" if args.sudo_rescan else args.wifi_rescan,
                WATCH_INTERVAL_SECONDS
            ),
            file=sys.stderr,
        )
        input_script = None
    else:
        command = build_ssh_arguments(args, "sh -s")
        print("Starting read-only G1 network probe; no configuration will be changed.", file=sys.stderr)
        input_script = probe_input_bytes()

    try:
        # Never use shell=True locally.  No AutoAddPolicy or host-key bypass is
        # installed: normal system OpenSSH verification and prompting applies.
        if args.single_password:
            from g1_single_password import run
            return run(args, command[-1], input_script, run_watch)
        if args.watch_wifi:
            return run_watch(command, show_aps=args.show_aps)
        # Deliberately no timeout: OpenSSH/sudo/nmcli password prompts may wait
        # for input indefinitely.  SSH keepalives detect an unresponsive peer.
        completed = subprocess.run(
            command,
            input=input_script,
            check=False,
        )
        report_ssh_exit(completed.returncode)
        return completed.returncode
    except FileNotFoundError:
        print("System OpenSSH executable not found: {}".format(args.ssh), file=sys.stderr)
        return 127
    except KeyboardInterrupt:
        print("Interrupted", file=sys.stderr)
        return 130
    except OSError as exc:
        print("Could not start system OpenSSH: {}".format(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
