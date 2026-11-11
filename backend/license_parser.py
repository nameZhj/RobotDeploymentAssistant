import base64
import json
import logging
from typing import Any, Dict, Optional

logger = logging.getLogger("LicenseParser")


class LicenseParser:
    """负责 License 内容的 JSON/Base64 解析与机器码校验比对"""

    @staticmethod
    def parse_license_content(content_str: str) -> Dict[str, Any]:
        if not content_str or not content_str.strip():
            return {"success": False, "msg": "License 文件内容为空"}

        try:
            data = json.loads(content_str.strip())
            payload_b64 = data.get("payload_b64")
            if payload_b64:
                try:
                    payload = json.loads(base64.b64decode(payload_b64).decode('utf-8'))
                    for k, v in payload.items():
                        if k not in data or not data[k]:
                            data[k] = v
                except Exception as ex:
                    logger.warning(f"解析 payload_b64 失败: {ex}")

            machine_id = str(data.get("machine_id") or data.get("machine_code") or data.get("hardware_id", "")).strip().lower()
            expire_date = data.get("expire_at") or data.get("expire_date") or data.get("valid_until") or data.get("expiration", "永久授权 (Permanent)")
            
            dances_raw = data.get("features") or data.get("authorized_dances") or data.get("dances") or data.get("dance_list") or []
            if isinstance(dances_raw, dict):
                dance_list = list(dances_raw.keys())
            elif isinstance(dances_raw, list):
                dance_list = [str(d).strip() for d in dances_raw]
            else:
                dance_list = []

            customer = data.get("customer_id") or data.get("customer") or data.get("client") or "商业客户"
            model = data.get("product") or data.get("robot_model") or data.get("model") or "Unitree G1"
            signature = data.get("signature") or data.get("sign") or ""

            return {
                "success": True,
                "data": {
                    "machine_id": machine_id,
                    "expire_date": str(expire_date),
                    "dances": dance_list,
                    "dance_count": len(dance_list),
                    "customer": customer,
                    "model": model,
                    "signature": signature,
                    "raw_json": data
                }
            }
        except Exception as e:
            return {
                "success": False,
                "msg": f"License 解析失败: {str(e)}",
                "data": {
                    "machine_id": "",
                    "expire_date": "未知",
                    "dances": [],
                    "dance_count": 0,
                    "customer": "自定义文件",
                    "model": "Unitree G1",
                    "signature": "",
                    "raw_json": {}
                }
            }

    @staticmethod
    def verify_license(license_data: Dict[str, Any], current_machine_id: Optional[str] = None) -> Dict[str, Any]:
        lic_mid = str(license_data.get("machine_id", "")).strip().lower()
        curr_mid = str(current_machine_id or "").strip().lower()
        customer = license_data.get("customer", "商业客户")
        expire_date = license_data.get("expire_date", "永久授权")
        dances = license_data.get("dances", [])
        is_match = bool(lic_mid and curr_mid and lic_mid == curr_mid)

        return {
            "is_match": is_match,
            "msg": "License 机器码与当前机器人完全匹配" if is_match else f"机器码不匹配: License 授权目标为 [{lic_mid[:8]}...]，本机指纹为 [{curr_mid[:8]}...]",
            "current_machine_id": curr_mid,
            "license_machine_id": lic_mid,
            "dances": dances,
            "dance_count": len(dances),
            "expire_date": expire_date,
            "customer": customer
        }


license_parser = LicenseParser()

