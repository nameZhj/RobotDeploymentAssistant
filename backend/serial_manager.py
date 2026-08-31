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
    """
    if not raw_text or not raw_text.strip():
        return []

    lines = raw_text.strip().splitlines()
    groups: List[Dict[str, Any]] = []
    current_group: Dict[str, Any] = {
        "group_id": "G1",
        "title": "G1 动作组 (L1)",
        "items": []
    }

    # 匹配动作映射行，如: G1_TURN_JUMP:    [L1, DOWN]     # 转身跳跃 RL_Mimic_CMU_83_58
    pattern = re.compile(r'^\s*([A-Za-z0-9_]+)\s*:\s*\[([^\]]+)\](?:\s*#\s*(.*))?$')
    group_pattern = re.compile(r'^\s*#\s*(?:Group\s*(\d+)|\bGroup\b|\b组\b)[\s:]*([^\n\r]*)', re.IGNORECASE)

    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("dance_map:"):
            continue

        # 检查是否为分组注释行
        g_match = group_pattern.match(stripped)
        if g_match and not pattern.match(stripped):
            g_num = g_match.group(1) or ""
            g_desc = g_match.group(2).strip()
            g_id = f"G{g_num}" if g_num else f"G{len(groups) + 1}"
            title = f"{g_id} 动作组"
            if "select key" in g_desc.lower():
                key_name = g_desc.split("key")[-1].strip(": \t")
                title += f" ({key_name})"
            elif g_desc:
                title += f" ({g_desc})"

            # 如果当前分组已有内容，保存并开辟新分组
            if current_group["items"]:
                groups.append(current_group)
                current_group = {
                    "group_id": g_id,
                    "title": title,
                    "items": []
                }
            else:
                current_group["group_id"] = g_id
                current_group["title"] = title
            continue

        match = pattern.match(line)
        if match:
            alias = match.group(1).strip()
            keys_raw = match.group(2).strip()
            comment_raw = (match.group(3) or "").strip()

            keys = [k.strip() for k in keys_raw.split(",") if k.strip()]
            select_key = keys[0] if len(keys) > 0 else ""
            action_key = keys[1] if len(keys) > 1 else ""

            # 提取动作名称与模型名称
            # 常见注释格式: <动作名称> <模型名(如 RL_Mimic_...)>
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

            # 命名规则：注释中存在中文则用中文命名，不存在中文则使用英文命名
            has_chinese = bool(re.search(r'[\u4e00-\u9fa5]', comment_raw))
            final_name = name_candidate if name_candidate else alias

            # 动作代码简写展示 (如 FRONT_FLIP / TIKTOK / D1S1)
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

            # 自动根据别名前缀 G1_, G2_, G3_ 等归类分组
            if alias.startswith("G1_") and current_group["group_id"] != "G1" and not current_group["items"]:
                current_group["group_id"] = "G1"
                current_group["title"] = "G1 动作组 (L1)"
            elif alias.startswith("G2_") and current_group["group_id"] == "G1" and current_group["items"]:
                groups.append(current_group)
                current_group = {"group_id": "G2", "title": "G2 动作组 (R1)", "items": []}
            elif alias.startswith("G3_") and current_group["group_id"] in ["G1", "G2"] and current_group["items"]:
                groups.append(current_group)
                current_group = {"group_id": "G3", "title": "G3 动作组 (L2)", "items": []}

            current_group["items"].append(item)

    if current_group["items"]:
        groups.append(current_group)

    return groups


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
        self._rx_buffer = ""
        self._reader_thread = threading.Thread(target=self._reader_loop, daemon=True)
        self._reader_thread.start()

    def _stop_reader_thread(self):
        """停止后台串口监听线程"""
        self._stop_reader.set()
        if self._reader_thread and self._reader_thread.is_alive():
            self._reader_thread.join(timeout=0.5)
        self._reader_thread = None

    def _reader_loop(self):
        """后台串口数据读取与协议响应处理循环"""
        accumulated_text = ""
        last_rx_time = time.time()
        in_dance_map_block = False

        while not self._stop_reader.is_set():
            try:
                ser_obj = None
                with self._lock:
                    if self.ser is not None and self.ser.is_open:
                        ser_obj = self.ser

                if not ser_obj:
                    time.sleep(0.1)
                    continue

                # 读取可用字节
                if ser_obj.in_waiting > 0:
                    raw_bytes = ser_obj.read(ser_obj.in_waiting)
                    if raw_bytes:
                        try:
                            decoded = raw_bytes.decode("utf-8", errors="ignore")
                        except Exception:
                            decoded = raw_bytes.decode("latin1", errors="ignore")

                        accumulated_text += decoded
                        last_rx_time = time.time()

                        if "dance_map:" in accumulated_text:
                            in_dance_map_block = True

                # 若处于舞蹈数据接收中，且超过 400ms 无新数据到来，判定为接收完毕并进行解析
                if in_dance_map_block and accumulated_text:
                    if (time.time() - last_rx_time) > 0.4:
                        # 提取 dance_map: 起始到末尾的内容
                        start_idx = accumulated_text.find("dance_map:")
                        if start_idx != -1:
                            yaml_content = accumulated_text[start_idx:].strip()
                            self.latest_dance_list_raw = yaml_content
                            self.latest_dance_list_parsed = parse_dance_map_yaml(yaml_content)
                            total_items = sum(len(g.get("items", [])) for g in self.latest_dance_list_parsed)
                            logger.info(f"成功从串口接收并解析舞蹈列表: 共 {len(self.latest_dance_list_parsed)} 个动作组，{total_items} 支舞蹈")
                            self._dance_list_event.set()

                        # 重置缓冲区
                        accumulated_text = ""
                        in_dance_map_block = False

                # 避免累积过多无用数据
                if len(accumulated_text) > 65536:
                    accumulated_text = accumulated_text[-16384:]

                time.sleep(0.05)
            except Exception as e:
                logger.debug(f"串口读取循环异常: {e}")
                time.sleep(0.1)

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
                self.current_port = target_port
                self.current_baudrate = baudrate
                self.current_description = desc
                time.sleep(0.15)
                logger.info(f"自动连接串口成功: {target_port} ({desc}) @ {baudrate} Baud")

                # 启动监听线程并仅在首次连接成功时异步发送一次 ALL|GETDANCELIST
                self._start_reader_thread()
                if not getattr(self, '_has_synced_dance_list', False):
                    self._has_synced_dance_list = True
                    threading.Thread(target=self.request_dance_list, args=(2.5, True), daemon=True).start()

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
        """手动连接指定串口并在首次连接时下发 ALL|GETDANCELIST"""
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
                self.current_port = port_name
                self.current_baudrate = baudrate
                self.current_description = f"{port_name} 串口"
                time.sleep(0.15)

                # 启动后台监听并仅在首次连接时发送一次 ALL|GETDANCELIST
                self._start_reader_thread()
                self._has_synced_dance_list = True
                threading.Thread(target=self.request_dance_list, args=(2.5, True), daemon=True).start()

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

        packet = f"{target}|{command}\n"

        with self._lock:
            if self.ser is None or not self.ser.is_open:
                # 尝试一次自动重连 (不再触发 GETDANCELIST)
                auto_res = self.auto_connect_best_port(self.current_baudrate or 9600)
                if not auto_res.get("success"):
                    return {
                        "success": False,
                        "msg": f"串口未连接且自动连接失败: {auto_res.get('msg')}",
                        "packet": packet.strip()
                    }

            try:
                self.ser.write(packet.encode("ascii"))
                self.ser.flush()
                ts = time.time()
                logger.info(f"[TX] {packet.strip()} @ {ts:.6f}")
                return {
                    "success": True,
                    "packet": packet.strip(),
                    "timestamp": ts,
                    "port": self.current_port
                }
            except Exception as e:
                logger.error(f"串口发送失败: {e}")
                try:
                    self.ser.close()
                except Exception:
                    pass
                self.ser = None
                self._has_synced_dance_list = False
                return {
                    "success": False,
                    "msg": f"串口发送异常: {str(e)}",
                    "packet": packet.strip()
                }

    def disconnect(self, safety_stop: bool = True) -> Dict[str, Any]:
        """断开当前串口连接并释放资源"""
        self._stop_reader_thread()
        self._has_synced_dance_list = False
        with self._lock:
            if self.ser is not None:
                try:
                    if safety_stop and self.ser.is_open:
                        try:
                            self.ser.write(b"ALL|GAIT\n")
                            self.ser.flush()
                        except Exception:
                            pass
                    self.ser.close()
                except Exception as e:
                    logger.warn(f"关闭串口异常: {e}")
                self.ser = None

            old_port = self.current_port
            self.current_port = ""
            return {
                "success": True,
                "msg": f"已断开串口 [{old_port}]" if old_port else "串口未处于连接状态"
            }

    def request_dance_list(self, timeout: float = 2.5, force: bool = False) -> Dict[str, Any]:
        """
        向机器人发送 ALL|GETDANCELIST 并等待接收与解析舞蹈列表：
        - 仅在首次连接或用户点击刷新时执行 (force=True)
        - 内部防抖保护，避免连续高频发送打满机载端串口缓冲区
        """
        last_req = getattr(self, '_last_dance_request_time', 0.0)
        now = time.time()
        if not force and (now - last_req < 2.0):
            # 2秒内若已请求过且非强制刷新，直接返回当前最新缓存
            total_count = sum(len(g.get("items", [])) for g in self.latest_dance_list_parsed)
            return {
                "success": True,
                "received": True,
                "groups": self.latest_dance_list_parsed,
                "total_count": total_count,
                "raw": self.latest_dance_list_raw,
                "msg": f"使用已缓存舞蹈列表 ({total_count} 首)"
            }

        self._last_dance_request_time = now
        self._dance_list_event.clear()
        tx_res = self.send_command("ALL", "GETDANCELIST")
        if not tx_res.get("success"):
            return {
                "success": False,
                "msg": f"发送 GETDANCELIST 指令失败: {tx_res.get('msg')}",
                "groups": self.latest_dance_list_parsed,
                "raw": self.latest_dance_list_raw
            }

        # 等待后台 reader 捕获并解析数据
        got = self._dance_list_event.wait(timeout=timeout)
        total_count = sum(len(g.get("items", [])) for g in self.latest_dance_list_parsed)

        return {
            "success": True,
            "received": got,
            "groups": self.latest_dance_list_parsed,
            "total_count": total_count,
            "raw": self.latest_dance_list_raw,
            "msg": f"成功同步舞蹈列表 ({total_count} 首)" if got else "已发送获取指令，等待机器人响应"
        }


    def get_dance_list(self) -> Dict[str, Any]:
        """获取当前已缓存的舞蹈列表与原始数据"""
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
        self.latest_dance_list_parsed = parsed
        total_count = sum(len(g.get("items", [])) for g in parsed)
        return {
            "success": True,
            "groups": parsed,
            "total_count": total_count,
            "raw": raw_yaml_text
        }

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
