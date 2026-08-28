import time
import logging
import threading
from typing import List, Dict, Any, Optional

try:
    import serial
    import serial.tools.list_ports as list_ports
except ImportError:
    serial = None
    list_ports = None

logger = logging.getLogger("SerialManager")


class SerialManager:
    """Windows LoRa 广播发射串口管理器 (支持自动检测、自动识别 CH340/CH341、指令下发与安全停机)"""

    def __init__(self):
        self.ser: Optional[Any] = None
        self.current_port: str = ""
        self.current_baudrate: int = 9600
        self.current_description: str = ""
        self._lock = threading.Lock()

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

    def auto_connect_best_port(self, baudrate: int = 9600) -> Dict[str, Any]:
        """
        自动检测并连接最佳串口：
        1. 若已连接且正常，直接返回
        2. 扫描所有可用串口，优先连接识别为 CH340/CH341 或 USB-Serial 的端口
        3. 若只有一个串口，直接尝试连接
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
                    timeout=1.0,
                    write_timeout=1.0
                )
                self.current_port = target_port
                self.current_baudrate = baudrate
                self.current_description = desc
                time.sleep(0.15)
                logger.info(f"自动连接串口成功: {target_port} ({desc}) @ {baudrate} Baud")
                return {
                    "success": True,
                    "connected": True,
                    "port": target_port,
                    "description": desc,
                    "baudrate": baudrate,
                    "msg": f"已自动连接串口 [{target_port}] ({desc})"
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
        """手动连接指定串口"""
        if serial is None:
            return {"success": False, "msg": "pyserial 模块未安装"}

        with self._lock:
            # 若已连接其他串口，先关闭
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
                    timeout=1.0,
                    write_timeout=1.0
                )
                self.current_port = port_name
                self.current_baudrate = baudrate
                self.current_description = f"{port_name} 串口"
                time.sleep(0.15)
                return {
                    "success": True,
                    "connected": True,
                    "port": port_name,
                    "baudrate": baudrate,
                    "msg": f"成功连接串口 [{port_name}]"
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
                # 尝试一次自动重连
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
                return {
                    "success": False,
                    "msg": f"串口发送异常: {str(e)}",
                    "packet": packet.strip()
                }

    def disconnect(self, safety_stop: bool = True) -> Dict[str, Any]:
        """断开连接，并在断开前安全广播 ALL|STOP"""
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
