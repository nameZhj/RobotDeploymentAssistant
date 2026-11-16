"""
@file: backend/g1_wifi_parser.py
@brief: 适配 docs/g1_wifi_setup(1).py 的 G1 Wi-Fi nmcli 解析、IPv4 网段冲突校验与远端命令构建器
@exports: IPv4Config, WifiRecord, PROBE_SCRIPT, parse_static_ipv4, split_nmcli_terse, parse_wifi_record, wifi_network_rows, parse_scan_output, parse_device_state, build_scan_cmd, build_connect_cmd, build_ipv4_cmd
"""
import ipaddress
import shlex
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

WIRED_MGMT_SUBNET = "192.168.123.0/24"
DEFAULT_WIFI_IFNAME = "wlan0"

PROBE_SCRIPT = r"""#!/bin/sh
export LC_ALL=C TERM=dumb PAGER=
section() { printf '\n===== %s =====\n' "$1"; }
run_probe() {
    printf '\n$'
    printf ' %s' "$@"
    printf '\n'
    "$@" 2>&1
    rc=$?
    [ "$rc" -eq 0 ] || printf '[probe] unavailable or failed (status=%s)\n' "$rc"
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
section "IP addresses and routes"
if command -v ip >/dev/null 2>&1; then
    run_probe ip address show
    run_probe ip route show
else
    printf 'ip: not found\n'
fi
exit 0
"""

_STATE_SNIPPET = r"""
printf '\n===== Post-connection state =====\n'
nmcli -t -f IN-USE,SSID,BSSID device wifi list ifname "$ifname" --rescan no | sed -n '/^\*:/p'
nmcli -f GENERAL.STATE,GENERAL.REASON,GENERAL.CONNECTION,IP4.ADDRESS,IP4.GATEWAY,IP4.DNS device show "$ifname" 2>&1
"""


@dataclass(frozen=True)
class IPv4Config:
    method: str
    address: str = ""
    gateway: str = ""
    dns: Tuple[str, ...] = ()


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


def parse_static_ipv4(
    address: str,
    netmask: str = "",
    gateway: str = "",
    dns: Sequence[str] = (),
) -> IPv4Config:
    """校验静态 IPv4 配置并阻断与有线管理网段 192.168.123.0/24 的冲突"""
    addr = (address or "").strip()
    mask_in = (netmask or "").strip()
    if not addr:
        raise ValueError("静态 IP 地址不能为空")
    if "/" in addr and mask_in:
        raise ValueError("请勿同时填写 CIDR 前缀（如 /24）与子网掩码")
    if "/" not in addr:
        if not mask_in:
            raise ValueError("未包含 /前缀 时必须填写子网掩码（如 255.255.255.0）")
        addr += "/" + mask_in
    mask = addr.split("/", 1)[1]
    if "." in mask:
        bits = format(int(ipaddress.IPv4Address(mask)), "032b")
        if "01" in bits:
            raise ValueError("子网掩码必须是连续的高位 1")
    iface = ipaddress.IPv4Interface(addr)
    network, ip = iface.network, iface.ip
    if ip.is_multicast or ip.is_loopback or ip.is_unspecified or ip.is_reserved:
        raise ValueError("静态 IP 必须是有效的单播局域网地址")
    if network.prefixlen < 31 and ip in (network.network_address, network.broadcast_address):
        raise ValueError("静态 IP 不能为网络地址或广播地址")
    if network.overlaps(ipaddress.IPv4Network(WIRED_MGMT_SUBNET)):
        raise ValueError("Wi-Fi 网段不可与 G1 有线管理网段 192.168.123.0/24 重叠")
    gw_str = (gateway or "").strip()
    if gw_str:
        gw = ipaddress.IPv4Address(gw_str)
        if gw not in network or gw == ip or (network.prefixlen < 31 and gw in (network.network_address, network.broadcast_address)):
            raise ValueError("默认网关必须位于同一 Wi-Fi 子网且不同于本机 IP")
    dns_list = [d.strip() for d in dns if d and d.strip()]
    servers = tuple(dict.fromkeys(str(ipaddress.IPv4Address(v)) for v in dns_list))
    return IPv4Config("manual", str(iface), gw_str, servers)


def split_nmcli_terse(line: str) -> List[str]:
    """按 nmcli --terse 转义规则拆分字段"""
    fields: List[str] = []
    buf: List[str] = []
    escaped = False
    for ch in line:
        if escaped:
            buf.append(ch)
            escaped = False
        elif ch == "\\":
            escaped = True
        elif ch == ":":
            fields.append("".join(buf))
            buf = []
        else:
            buf.append(ch)
    if escaped:
        buf.append("\\")
    fields.append("".join(buf))
    return fields


def parse_wifi_record(line: str, ifname: Optional[str] = DEFAULT_WIFI_IFNAME) -> WifiRecord:
    fields = split_nmcli_terse(line)
    if len(fields) != 7:
        raise ValueError("nmcli Wi-Fi 记录应包含 7 个字段")
    frequency = ""
    if ifname is None:
        ifname, in_use, ssid, bssid, channel, signal, security = fields
    else:
        in_use, ssid, bssid, channel, frequency, signal, security = fields
    return WifiRecord(
        ifname=ifname, in_use=in_use.strip() == "*", ssid=ssid, bssid=bssid,
        channel=channel, signal=signal, security=security, frequency=frequency,
    )


def _sort_key(r: WifiRecord) -> tuple:
    try:
        sig = int(r.signal)
    except ValueError:
        sig = -1
    return (-sig, r.ssid.casefold(), r.ifname, r.bssid)


def wifi_network_rows(records: Iterable[WifiRecord], grouped: bool = True) -> Tuple[List[Tuple[WifiRecord, int]], int]:
    """按 (ifname, ssid, security) 聚合多 AP 热点，保留信号最强/已连接代表项"""
    unique = {r.key: r for r in records}
    groups: Dict[tuple, List[WifiRecord]] = {}
    for rec in unique.values():
        sec = " ".join(rec.security.split()) or "OPEN"
        anon = not rec.ssid or "\ufffd" in rec.ssid or set(rec.ssid) == {"?"}
        key = (rec.ifname, rec.ssid, sec) if (grouped and not anon) else (rec.ifname, rec.bssid)
        groups.setdefault(key, []).append(rec)
    rows = [(min(cands, key=lambda r: (not r.in_use, _sort_key(r))), len(cands)) for cands in groups.values()]
    return sorted(rows, key=lambda row: _sort_key(row[0])), len(unique)


def parse_scan_output(stdout: str, ifname: str = DEFAULT_WIFI_IFNAME) -> Dict[str, Any]:
    records: List[WifiRecord] = []
    malformed = 0
    for raw in (stdout or "").splitlines():
        line = raw.strip("\r")
        if not line:
            continue
        try:
            records.append(parse_wifi_record(line, ifname=ifname))
        except ValueError:
            malformed += 1
    rows, ap_count = wifi_network_rows(records, grouped=True)
    networks = [{
        "ifname": rec.ifname,
        "in_use": rec.in_use,
        "ssid": rec.ssid,
        "bssid": rec.bssid,
        "channel": rec.channel,
        "frequency": rec.frequency,
        "signal": rec.signal,
        "security": rec.security or "OPEN",
        "ap_count": count,
    } for rec, count in rows if rec.ssid and "\ufffd" not in rec.ssid]
    return {"networks": networks, "ap_count": ap_count, "malformed": malformed}


def parse_device_state(stdout: str) -> Dict[str, Any]:
    info: Dict[str, Any] = {"connection": "", "state": "", "ip_cidr": "", "ip_address": "", "gateway": "", "dns": ""}
    for raw in (stdout or "").splitlines():
        line = raw.strip()
        if ":" not in line:
            continue
        key, val = [p.strip() for p in line.split(":", 1)]
        if val in ("--", ""):
            continue
        if key == "GENERAL.CONNECTION":
            info["connection"] = val
        elif key == "GENERAL.STATE":
            info["state"] = val
        elif key.startswith("IP4.ADDRESS") and not info["ip_cidr"]:
            info["ip_cidr"] = val
            info["ip_address"] = val.split("/", 1)[0]
        elif key.startswith("IP4.GATEWAY") and not info["gateway"]:
            info["gateway"] = val
        elif key.startswith("IP4.DNS"):
            info["dns"] = f"{info['dns']},{val}".strip(",")
    return info


def build_scan_cmd(ifname: str = DEFAULT_WIFI_IFNAME, rescan: str = "auto") -> str:
    mode = rescan if rescan in ("auto", "no", "yes") else "auto"
    q_if = shlex.quote(ifname or DEFAULT_WIFI_IFNAME)
    return (
        "export LC_ALL=C TERM=dumb PAGER= && "
        f"nmcli --mode tabular --colors no --terse --escape yes "
        f"--fields IN-USE,SSID,BSSID,CHAN,FREQ,SIGNAL,SECURITY "
        f"device wifi list ifname {q_if} --rescan {mode}"
    )


def build_connect_cmd(ssid: str, password: str = "", ifname: str = DEFAULT_WIFI_IFNAME) -> str:
    q_if = shlex.quote(ifname or DEFAULT_WIFI_IFNAME)
    q_ssid = shlex.quote(ssid)
    pwd_part = f" password {shlex.quote(password)}" if password else ""
    return (
        "export LC_ALL=C TERM=dumb PAGER=\n"
        f"ifname={q_if}\n"
        f"nmcli -t -f SSID device wifi list ifname {q_if} --rescan yes >/dev/null 2>&1 || true\n"
        f"nmcli --colors no --wait 60 device wifi connect {q_ssid}{pwd_part} ifname {q_if}\n"
        "nmcli_rc=$?\n"
        + _STATE_SNIPPET
        + 'printf "\\nWi-Fi connection command status: %s\\n" "$nmcli_rc"\n'
        + 'exit "$nmcli_rc"\n'
    )


def build_ipv4_cmd(ifname: str, config: IPv4Config) -> str:
    q_if = shlex.quote(ifname or DEFAULT_WIFI_IFNAME)
    props = [
        "ipv4.method", config.method,
        "ipv4.addresses", config.address,
        "ipv4.gateway", config.gateway,
        "ipv4.dns", ",".join(config.dns),
        "ipv4.ignore-auto-dns", "yes" if config.method == "manual" else "no",
    ]
    mod_args = " ".join(shlex.quote(v) for v in props)
    verify = (
        f"ip -4 -o address show dev {q_if} | awk '{{print $4}}' | grep -Fxq {shlex.quote(config.address)} || ipv4_rc=1"
        if config.method == "manual"
        else f"ip -4 -o address show dev {q_if} | grep -q ' inet ' || ipv4_rc=1"
    )
    return (
        "export LC_ALL=C TERM=dumb PAGER=\n"
        f"ifname={q_if}\n"
        'kind=$(nmcli -g GENERAL.TYPE device show "$ifname") || exit $?\n'
        'case "$kind" in wifi|802-11-wireless) ;; *) echo "Refusing IPv4 change: target device is not Wi-Fi." >&2; exit 2;; esac\n'
        'uuid=$(nmcli -t -f UUID,DEVICE connection show --active | awk -F: -v dev="$ifname" \'$2 == dev {print $1}\')\n'
        'case "$uuid" in ""|*[!0-9a-fA-F-]*) echo "No unique active Wi-Fi profile; connect the target Wi-Fi first." >&2; exit 2;; esac\n'
        'kind=$(nmcli -g connection.type connection show uuid "$uuid") || exit $?\n'
        '[ "$kind" = "802-11-wireless" ] || { echo "Refusing to modify a non-Wi-Fi profile." >&2; exit 2; }\n'
        f'nmcli connection modify uuid "$uuid" {mod_args} || exit $?\n'
        'nmcli connection up uuid "$uuid" ifname "$ifname"\n'
        'ipv4_rc=$?\n'
        f'if [ "$ipv4_rc" -eq 0 ]; then {verify}; fi\n'
        'nmcli -f GENERAL.DEVICE,GENERAL.STATE,GENERAL.CONNECTION,IP4.ADDRESS,IP4.GATEWAY,IP4.DNS device show "$ifname"\n'
        'exit "$ipv4_rc"\n'
    )
