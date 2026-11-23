import time
import logging
import threading
import re
from typing import List, Dict, Any, Optional, Tuple

try:
    import serial
    import serial.tools.list_ports as list_ports
except ImportError:
    serial = None
    list_ports = None

logger = logging.getLogger("SerialManager")


def parse_dance_map_yaml(raw_text: str) -> List[Dict[str, Any]]:
    """
    解析从串口接收到的 dance_map YAML 文本
    规则：
    1. 动态提取所有动作组（如 # Group 1: select key L1 -> G1 动作组 (L1)）
    2. 每项提取 alias, keys, short_code, cmd 等
    3. 命名规则：注释中存在中文则用中文命名，不存在中文则使用英文命名
    4. 健壮容错：支持乱序分组识别与重复别名去重
    """
    if not raw_text or not raw_text.strip():
        return []

    lines = raw_text.strip().splitlines()
    pattern = re.compile(r'^\s*([A-Za-z0-9_]+)\s*:\s*\[([^\]]+)\](?:\s*#\s*(.*))?$')
    group_pattern = re.compile(r'^\s*#\s*(?:Group\s*(\d+)|\bGroup\b|\b组\b)[\s:]*([^\n\r]*)', re.IGNORECASE)

    groups_dict: Dict[str, Dict[str, Any]] = {}
    group_order: List[str] = []
    current_gid = None

    KEY_GROUP_MAP = {
        "L1": ("G1", "G1 动作组 (L1)"),
        "R1": ("G2", "G2 动作组 (R1)"),
        "L2": ("G3", "G3 动作组 (L2)"),
        "DOWN": ("G4", "G4 动作组 (DOWN)"),
        "UP": ("G0", "基础动作组 (UP)"),
    }

    seen_aliases = set()

    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("dance_map:"):
            continue

        # 检查是否为分组注释行
        g_match = group_pattern.match(stripped)
        if g_match and not pattern.match(stripped):
            g_num = g_match.group(1) or ""
            g_desc = g_match.group(2).strip()
            g_id = f"G{g_num}" if g_num else f"G{len(group_order) + 1}"
            title = f"{g_id} 动作组"
            if "select key" in g_desc.lower():
                k_name = g_desc.split("key")[-1].strip(": \t")
                title += f" ({k_name})"
            elif g_desc:
                title += f" ({g_desc})"

            current_gid = g_id
            if current_gid not in groups_dict:
                groups_dict[current_gid] = {"group_id": g_id, "title": title, "items": []}
                group_order.append(current_gid)
            else:
                groups_dict[current_gid]["title"] = title
            continue

        match = pattern.match(line)
        if match:
            alias = match.group(1).strip()
            if alias in seen_aliases:
                continue
            seen_aliases.add(alias)

            keys_raw = match.group(2).strip()
            comment_raw = (match.group(3) or "").strip()

            keys = [k.strip() for k in keys_raw.split(",") if k.strip()]
            select_key = keys[0] if len(keys) > 0 else ""
            action_key = keys[1] if len(keys) > 1 else ""

            # 提取动作名称与模型名称
            name_candidate = comment_raw
            model_name = ""
            if " RL_" in comment_raw or " rl_" in comment_raw:
                parts = re.split(r'\s+(?=RL_|\brl_)', comment_raw, flags=re.IGNORECASE)
                name_candidate = parts[0].strip()
                if len(parts) > 1:
                    model_name = parts[1].strip()
            elif " " in comment_raw:
                tokens = comment_raw.split()
                if len(tokens) >= 2 and any(tokens[-1].startswith(p) for p in ["RL", "Mimic", "CMU", "soma", "cmu", "dance"]):
                    name_candidate = " ".join(tokens[:-1]).strip()
                    model_name = tokens[-1].strip()

            has_chinese = bool(re.search(r'[\u4e00-\u9fa5]', comment_raw))
            final_name = name_candidate if name_candidate else alias

            short_code = alias
            if "_" in alias:
                parts = alias.split("_", 1)
                if parts[0].upper().startswith("G") and parts[0][1:].isdigit():
                    short_code = parts[1]

            item = {
                "alias": alias,
                "name": final_name,
                "short_code": short_code,
                "keys": keys,
                "select_key": select_key,
                "action_key": action_key,
                "model_name": model_name,
                "comment": comment_raw,
                "cmd": f"DANCE,{alias}",
                "has_chinese": has_chinese
            }

            # 确定所属分组 (优先使用当前注释组，其次使用按键特征映射)
            target_gid = current_gid
            if not target_gid:
                if select_key.upper() in KEY_GROUP_MAP:
                    target_gid, default_title = KEY_GROUP_MAP[select_key.upper()]
                elif alias.startswith("G1_"):
                    target_gid, default_title = ("G1", "G1 动作组 (L1)")
                elif alias.startswith("G2_"):
                    target_gid, default_title = ("G2", "G2 动作组 (R1)")
                elif alias.startswith("G3_"):
                    target_gid, default_title = ("G3", "G3 动作组 (L2)")
                else:
                    target_gid, default_title = ("G1", "G1 动作组")
            else:
                default_title = f"{target_gid} 动作组"

            if target_gid not in groups_dict:
                groups_dict[target_gid] = {"group_id": target_gid, "title": default_title, "items": []}
                group_order.append(target_gid)

            groups_dict[target_gid]["items"].append(item)

    return [groups_dict[gid] for gid in group_order if groups_dict[gid]["items"]]


def merge_dance_groups(existing_groups: List[Dict[str, Any]], new_groups: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """合并两个舞蹈动作组列表，保留唯一动作并合并增量组（多包/跨通道无缝合并）"""
    if not existing_groups:
        return new_groups or []
    if not new_groups:
        return existing_groups

    groups_map = {g["group_id"]: dict(g, items=list(g.get("items", []))) for g in existing_groups}
    order = [g["group_id"] for g in existing_groups]

    for ng in new_groups:
        gid = ng["group_id"]
        if gid not in groups_map:
            groups_map[gid] = dict(ng, items=list(ng.get("items", [])))
            order.append(gid)
        else:
            existing_items = groups_map[gid]["items"]
            item_map = {it["alias"]: it for it in existing_items}
            for nit in ng.get("items", []):
                alias = nit["alias"]
                if alias in item_map:
                    item_map[alias].update(nit)
                else:
                    existing_items.append(nit)
                    item_map[alias] = nit
            if ng.get("title") and ("(" in ng["title"] or not groups_map[gid].get("title")):
                groups_map[gid]["title"] = ng["title"]

    return [groups_map[gid] for gid in order]


class SerialManager:
    """Windows LoRa 广播发射串口管理器 (支持自动检测、自动识别 CH340/CH341、指令下发、ALL|GETDANCELIST 舞蹈列表获取与解析)"""

    def __init__(self):
        self.ser: Optional[Any] = None
        self.current_port: str = ""
        self.current_baudrate: int = 9600
        self.current_description: str = ""
        self._lock = threading.Lock()

        # 串口数据接收与舞蹈列表缓存
        self._reader_thread: Optional[threading.Thread] = None
        self._stop_reader = threading.Event()
        self._rx_buffer = ""
        self.latest_dance_list_raw: str = ""
        self.latest_dance_list_parsed: List[Dict[str, Any]] = []
        self._dance_list_event = threading.Event()

        # 实时串口交互消息历史 (供控制台及前端 UI 实时显示)
        self.message_history: List[Dict[str, Any]] = []
        self._history_lock = threading.Lock()

    def _append_message(self, msg_type: str, text: str):
        """记录并存储一条串口 TX/RX 消息"""
        clean_text = text.strip()
        if not clean_text:
            return
        with self._history_lock:
            self.message_history.append({
                "type": msg_type,
                "text": clean_text,
                "timestamp": time.time(),
                "time_str": time.strftime("%H:%M:%S")
            })
            if len(self.message_history) > 300:
                self.message_history = self.message_history[-150:]

    def get_recent_messages(self, since_ts: float = 0.0) -> List[Dict[str, Any]]:
        """获取指定时间戳之后产生的所有串口消息"""
        with self._history_lock:
            if since_ts <= 0:
                return list(self.message_history)
            return [m for m in self.message_history if m["timestamp"] > since_ts]

    def list_ports(self) -> List[Dict[str, Any]]:
        """列出所有可用串口并标记是否为 CH340/CH341/USB-Serial"""
        if list_ports is None:
            return []

        results = []
        try:
            com_ports = list_ports.comports()
            for p in com_ports:
                desc = p.description or ""
                hwid = p.hwid or ""
                name = p.device or ""

                # 检测是否为常用 USB 转串口芯片（宇树 LoRa 模块多用 CH340/CH341/CP210x/FTDI）
                is_ch341 = any(k in desc.lower() or k in hwid.lower() for k in ["ch34", "usb-serial", "cp210", "ftdi", "uart"])
                is_current = (self.ser is not None and self.ser.is_open and self.current_port == name)

                results.append({
                    "port": name,
                    "description": desc,
                    "hwid": hwid,
                    "is_ch341": is_ch341,
                    "is_active": is_current
                })

            # 排序：优先排 CH340/CH341 设备
            results.sort(key=lambda x: (not x["is_ch341"], x["port"]))
        except Exception as e:
            logger.error(f"扫描串口失败: {e}")

        return results

    def _start_reader_thread(self):
        """启动后台串口监听线程"""
        self._stop_reader.clear()
        self._line_buffer = ""
        self._accumulated_dance_lines = []
        self._last_dance_rx_time = 0.0
        self._reader_thread = threading.Thread(target=self._reader_loop, daemon=True)
        self._reader_thread.start()

    def _stop_reader_thread(self):
        """停止后台串口监听线程"""
        self._stop_reader.set()
        if self._reader_thread and self._reader_thread.is_alive():
            self._reader_thread.join(timeout=0.5)
        self._reader_thread = None

    def _reader_loop(self):
        """后台串口数据读取与协议响应处理循环（实时监听机器人串口回传字符串并在控制台打印）"""
        self._line_buffer = ""
        self._accumulated_dance_lines = []
        self._last_dance_rx_time = 0.0

        dance_line_regex = re.compile(r'^\s*([A-Za-z0-9_]+)\s*:\s*\[([^\]]+)\](?:\s*#\s*(.*))?$')
        group_header_regex = re.compile(r'^\s*#\s*(?:Group\s*(\d+)|\bGroup\b|\b组\b)[\s:]*([^\n\r]*)', re.IGNORECASE)

        while not self._stop_reader.is_set():
            try:
                ser_obj = None
                with self._lock:
                    if self.ser is not None and self.ser.is_open:
                        ser_obj = self.ser

                if not ser_obj:
                    time.sleep(0.05)
                    continue

                # 读取串口底层接收缓冲区中的所有字节
                if ser_obj.in_waiting > 0:
                    raw_bytes = ser_obj.read(ser_obj.in_waiting)
                    if raw_bytes:
                        try:
                            decoded = raw_bytes.decode("utf-8", errors="ignore")
                        except Exception:
                            decoded = raw_bytes.decode("latin1", errors="ignore")
                        self._line_buffer += decoded

                        # 提取所有由换行符分隔的完整行（彻底避免跨数据包截断）
                        while "\n" in self._line_buffer:
                            line, self._line_buffer = self._line_buffer.split("\n", 1)
                            line_s = line.strip("\r").rstrip()
                            if not line_s:
                                continue

                            # 1. 实时在控制台打印并加入历史消息
                            logger.info(f"[RX] {line_s}")
                            self._append_message("rx", line_s)

                            # 2. 判断是否属于舞蹈列表内容
                            is_dance_line = bool(dance_line_regex.match(line_s))
                            is_group_header = bool(group_header_regex.match(line_s))
                            is_yaml_header = line_s.strip().startswith("dance_map:")

                            if is_dance_line or is_group_header or is_yaml_header:
                                self._accumulated_dance_lines.append(line_s)
                                self._last_dance_rx_time = time.time()

                                # 增量实时解析当前已累积的所有完整舞蹈行并与已有动作无缝合并
                                parsed = parse_dance_map_yaml("\n".join(self._accumulated_dance_lines))
                                if parsed and any(g.get("items") for g in parsed):
                                    self.latest_dance_list_parsed = merge_dance_groups(self.latest_dance_list_parsed, parsed)
                                    self.latest_dance_list_raw = "\n".join(self._accumulated_dance_lines)
                                    self._dance_list_event.set()

                # 如果收到过舞蹈行且静默超过 1.8 秒，进行最终完整汇总确认
                if self._accumulated_dance_lines and self._last_dance_rx_time > 0 and (time.time() - self._last_dance_rx_time) > 1.8:
                    parsed = parse_dance_map_yaml("\n".join(self._accumulated_dance_lines))
                    if parsed and any(g.get("items") for g in parsed):
                        self.latest_dance_list_parsed = merge_dance_groups(self.latest_dance_list_parsed, parsed)
                        self.latest_dance_list_raw = "\n".join(self._accumulated_dance_lines)
                        total_items = sum(len(g.get("items", [])) for g in self.latest_dance_list_parsed)
                        logger.info(f"成功从串口接收并完整解析全部舞蹈列表: 共 {len(self.latest_dance_list_parsed)} 个动作组，{total_items} 支舞蹈")
                        self._dance_list_event.set()
                    self._last_dance_rx_time = 0.0

                time.sleep(0.02)
            except Exception as e:
                logger.debug(f"串口读取循环异常: {e}")
                time.sleep(0.05)

    def auto_connect_best_port(self, baudrate: int = 9600) -> Dict[str, Any]:
        """
        自动检测并连接最佳串口：
        1. 若已连接且正常，直接返回，绝不重复触发 ALL|GETDANCELIST
        2. 扫描所有可用串口，优先连接识别为 CH340/CH341 或 USB-Serial 的端口
        3. 首次连接成功后自动向机器人发送且仅发送一次 ALL|GETDANCELIST
        """
        if serial is None:
            return {"success": False, "msg": "pyserial 模块未安装"}

        with self._lock:
            if self.ser is not None and self.ser.is_open:
                return {
                    "success": True,
                    "connected": True,
                    "port": self.current_port,
                    "description": self.current_description,
                    "baudrate": self.current_baudrate,
                    "msg": f"串口 [{self.current_port}] 已处于连接状态"
                }

            ports = self.list_ports()
            if not ports:
                return {
                    "success": False,
                    "connected": False,
                    "msg": "未检测到已插入的串口设备，请插入 USB LoRa 发射器"
                }

            # 寻找最佳候选（CH340/CH341 优先）
            best_candidate = None
            for p in ports:
                if p.get("is_ch341"):
                    best_candidate = p
                    break

            if not best_candidate:
                best_candidate = ports[0]

            target_port = best_candidate["port"]
            desc = best_candidate["description"]

            try:
                self.ser = serial.Serial(
                    port=target_port,
                    baudrate=baudrate,
                    bytesize=serial.EIGHTBITS,
                    parity=serial.PARITY_NONE,
                    stopbits=serial.STOPBITS_ONE,
                    timeout=0.2,
                    write_timeout=1.0
                )
                try:
                    self.ser.dtr = False
                    self.ser.rts = False
                except Exception:
                    pass

                self.current_port = target_port
                self.current_baudrate = baudrate
                self.current_description = desc
                time.sleep(0.15)
                logger.info(f"自动连接串口成功: {target_port} ({desc}) @ {baudrate} Baud (DTR=0, RTS=0)")

                # 启动监听线程并仅在首次连接成功时异步发送一次 ALL|GETDANCELIST (单次执行，绝不轮询)
                self._start_reader_thread()
                if not getattr(self, '_has_synced_dance_list', False):
                    self._has_synced_dance_list = True
                    threading.Thread(target=self.request_dance_list, args=(6.0, True), daemon=True).start()

                return {
                    "success": True,
                    "connected": True,
                    "port": target_port,
                    "description": desc,
                    "baudrate": baudrate,
                    "msg": f"已自动连接串口 [{target_port}] ({desc})，已发送 ALL|GETDANCELIST 获取舞蹈列表"
                }
            except Exception as e:
                logger.error(f"连接串口 {target_port} 失败: {e}")
                return {
                    "success": False,
                    "connected": False,
                    "port": target_port,
                    "msg": f"打开串口 [{target_port}] 失败: {str(e)}"
                }

    def connect_port(self, port_name: str, baudrate: int = 9600) -> Dict[str, Any]:
        """手动连接指定串口并在首次连接时单次下发 ALL|GETDANCELIST"""
        if serial is None:
            return {"success": False, "msg": "pyserial 模块未安装"}

        with self._lock:
            # 若已连接其他串口，先关闭
            self._stop_reader_thread()
            if self.ser is not None:
                try:
                    self.ser.close()
                except Exception:
                    pass
                self.ser = None

            try:
                self.ser = serial.Serial(
                    port=port_name,
                    baudrate=baudrate,
                    bytesize=serial.EIGHTBITS,
                    parity=serial.PARITY_NONE,
                    stopbits=serial.STOPBITS_ONE,
                    timeout=0.2,
                    write_timeout=1.0
                )
                try:
                    self.ser.dtr = False
                    self.ser.rts = False
                except Exception:
                    pass

                self.current_port = port_name
                self.current_baudrate = baudrate
                self.current_description = f"{port_name} 串口"
                time.sleep(0.15)

                # 启动后台监听并仅在首次连接时发送一次 ALL|GETDANCELIST
                self._start_reader_thread()
                self._has_synced_dance_list = True
                threading.Thread(target=self.request_dance_list, args=(6.0, True), daemon=True).start()

                return {
                    "success": True,
                    "connected": True,
                    "port": port_name,
                    "baudrate": baudrate,
                    "msg": f"成功连接串口 [{port_name}]，已发送 ALL|GETDANCELIST 同步舞蹈列表"
                }
            except Exception as e:
                return {
                    "success": False,
                    "connected": False,
                    "port": port_name,
                    "msg": f"打开串口 [{port_name}] 失败: {str(e)}"
                }

    def send_command(self, target: str, command: str) -> Dict[str, Any]:
        """向串口发送 TARGET|COMMAND\\n 数据包"""
        target = target.strip().upper()
        command = command.strip().upper()

        if not target or not command:
            return {"success": False, "msg": "目标或指令不能为空"}

        packet = f"{target}|{command}\n".encode("ascii", errors="ignore")

        with self._lock:
            if self.ser is None or not self.ser.is_open:
                return {"success": False, "msg": "串口未连接，无法发送指令"}

            try:
                try:
                    if self.ser.dtr:
                        self.ser.dtr = False
                    if self.ser.rts:
                        self.ser.rts = False
                except Exception:
                    pass

                self.ser.write(packet)
                self.ser.flush()
                logger.info(f"[TX] {target}|{command} @ {time.time():.6f}")
                self._append_message("tx", f"{target}|{command}")
                return {
                    "success": True,
                    "target": target,
                    "command": command,
                    "packet": f"{target}|{command}",
                    "msg": "指令已下发至串口发射缓冲区"
                }
            except Exception as e:
                logger.error(f"串口发送异常: {e}")
                return {"success": False, "msg": f"串口发送失败: {str(e)}"}

    def send_raw(self, raw_str: str) -> Dict[str, Any]:
        """向串口直接发送原始字符串"""
        if not raw_str:
            return {"success": False, "msg": "数据为空"}

        if not raw_str.endswith("\n"):
            raw_str += "\n"

        packet = raw_str.encode("ascii", errors="ignore")

        with self._lock:
            if self.ser is None or not self.ser.is_open:
                return {"success": False, "msg": "串口未连接"}

            try:
                self.ser.write(packet)
                self.ser.flush()
                self._append_message("tx", raw_str.strip())
                return {"success": True, "msg": "原始数据已发送"}
            except Exception as e:
                return {"success": False, "msg": str(e)}

    def is_connected(self) -> bool:
        """检查当前串口是否处于连接就绪状态"""
        with self._lock:
            return self.ser is not None and self.ser.is_open

    def get_status(self) -> Dict[str, Any]:
        """获取串口连接状态及当前活跃配置"""
        with self._lock:
            connected = self.ser is not None and self.ser.is_open
            return {
                "connected": connected,
                "port": self.current_port if connected else "",
                "description": self.current_description if connected else "",
                "baudrate": self.current_baudrate if connected else 9600
            }

    def request_dance_list(self, timeout: float = 6.0, force: bool = False) -> Dict[str, Any]:
        """
        向机器人发送 ALL|GETDANCELIST 并等待接收与解析舞蹈列表：
        - 仅在首次连接或用户点击刷新时执行 (force=True)
        - 内部防抖保护，避免连续高频发送打满机载端串口缓冲区
        - 多包与增量动作智能合并，若串口空中丢包则自动无缝由 SSH 补齐
        """
        last_req = getattr(self, '_last_dance_request_time', 0.0)
        now = time.time()
        if not force and (now - last_req < 2.5) and self.latest_dance_list_parsed:
            total_count = sum(len(g.get("items", [])) for g in self.latest_dance_list_parsed)
            return {
                "success": True,
                "received": True,
                "groups": self.latest_dance_list_parsed,
                "total_count": total_count,
                "raw": self.latest_dance_list_raw,
                "msg": f"使用已同步舞蹈列表 ({total_count} 首)"
            }

        self._last_dance_request_time = now
        self._dance_list_event.clear()
        self._last_dance_rx_time = 0.0

        tx_res = self.send_command("ALL", "GETDANCELIST")
        if not tx_res.get("success"):
            return {
                "success": False,
                "msg": f"发送 GETDANCELIST 指令失败: {tx_res.get('msg')}",
                "groups": self.latest_dance_list_parsed,
                "raw": self.latest_dance_list_raw
            }

        # 等待后台 reader 捕获并解析数据 (LoRa 传输约 4-6 秒)
        got = self._dance_list_event.wait(timeout=timeout)
        self._try_ssh_dance_sync_fallback()
        total_count = sum(len(g.get("items", [])) for g in self.latest_dance_list_parsed)

        return {
            "success": True,
            "received": got or total_count > 0,
            "groups": self.latest_dance_list_parsed,
            "total_count": total_count,
            "raw": self.latest_dance_list_raw,
            "msg": f"成功同步舞蹈列表 ({total_count} 首)" if total_count > 0 else "已发送获取指令，等待机器人响应"
        }

    def _try_ssh_dance_sync_fallback(self):
        """当串口空口传输分包受限时，自动通过 SSH 读取机器人容器内部的 lora_recv_group.yaml 补全全部 33 支动作"""
        total_count = sum(len(g.get("items", [])) for g in self.latest_dance_list_parsed)
        if total_count >= 33:
            return

        try:
            from backend.ssh_client import ssh_manager
            if ssh_manager.is_connected():
                code, out, _ = ssh_manager.execute_command(
                    "docker exec vsis_g1 cat /home/ubuntu/vsis_mimic_deploy/group/lora_recv_group.yaml 2>/dev/null "
                    "|| cat /home/ubuntu/vsis_mimic_deploy/group/lora_recv_group.yaml 2>/dev/null",
                    sudo=True
                )
                if code == 0 and out.strip():
                    parsed = parse_dance_map_yaml(out)
                    if parsed:
                        self.latest_dance_list_parsed = merge_dance_groups(self.latest_dance_list_parsed, parsed)
                        if not self.latest_dance_list_raw:
                            self.latest_dance_list_raw = out
        except Exception as e:
            logger.debug(f"SSH 自动补全动作列表异常: {e}")

    def get_dance_list(self) -> Dict[str, Any]:
        """获取当前已缓存的舞蹈列表与原始数据（若动作数量不足自动由 SSH 补齐）"""
        self._try_ssh_dance_sync_fallback()
        total_count = sum(len(g.get("items", [])) for g in self.latest_dance_list_parsed)
        return {
            "success": True,
            "groups": self.latest_dance_list_parsed,
            "total_count": total_count,
            "raw": self.latest_dance_list_raw,
            "has_data": len(self.latest_dance_list_parsed) > 0
        }

    def set_dance_list_raw(self, raw_yaml_text: str) -> Dict[str, Any]:
        """手动设置并解析舞蹈列表 YAML 字符串 (用于测试或调试)"""
        parsed = parse_dance_map_yaml(raw_yaml_text)
        self.latest_dance_list_raw = raw_yaml_text
        self.latest_dance_list_parsed = merge_dance_groups(self.latest_dance_list_parsed, parsed)
        total_count = sum(len(g.get("items", [])) for g in self.latest_dance_list_parsed)
        return {
            "success": True,
            "groups": self.latest_dance_list_parsed,
            "total_count": total_count,
            "raw": raw_yaml_text
        }

    def sync_dance_list_from_robot(self, timeout: float = 3.0) -> Tuple[bool, List[Dict[str, Any]], str]:
        """从机器人实时同步最新动作列表并更新本地缓存"""
        res = self.request_dance_list(timeout=timeout, force=True)
        return res.get("success", False), res.get("groups", []), res.get("msg", "")

    def disconnect(self, safety_stop: bool = True) -> Dict[str, Any]:
        """断开连接，并在断开前安全广播 ALL|STOP"""
        self._stop_reader_thread()
        with self._lock:
            if self.ser is not None and self.ser.is_open:
                if safety_stop:
                    try:
                        self.ser.write(b"ALL|STOP\n")
                        self.ser.flush()
                        time.sleep(0.1)
                    except Exception:
                        pass
                try:
                    self.ser.close()
                except Exception:
                    pass

            self.ser = None
            old_port = self.current_port
            self.current_port = ""
            self.current_description = ""
            return {"success": True, "msg": f"已断开串口连接 ({old_port})"}

    def get_status(self) -> Dict[str, Any]:
        """获取当前串口状态"""
        is_conn = (self.ser is not None and self.ser.is_open)
        return {
            "connected": is_conn,
            "port": self.current_port if is_conn else "",
            "description": self.current_description if is_conn else "",
            "baudrate": self.current_baudrate if is_conn else 9600
        }


serial_manager = SerialManager()
