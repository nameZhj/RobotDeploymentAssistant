import json
import time
import os
import logging
from typing import Dict, Any, Tuple, Optional, List
from backend.ssh_client import ssh_manager
from backend.deployment_core import deployment_core

logger = logging.getLogger("LicenseService")


class LicenseService:
    """License 导入、解析、机器码一致性校验与部署服务"""

    def __init__(self):
        pass

    def parse_license_content(self, content_str: str) -> Dict[str, Any]:
        """解析 License JSON 内容以供前端与后端校验"""
        if not content_str or not content_str.strip():
            return {"success": False, "msg": "License 文件内容为空"}

        try:
            import base64
            data = json.loads(content_str.strip())
            
            # 若含有 payload_b64 (商业化 Ed25519 签名标准结构)，进行 Base64 解码提取
            payload_b64 = data.get("payload_b64")
            if payload_b64:
                try:
                    payload = json.loads(base64.b64decode(payload_b64).decode('utf-8'))
                    for k, v in payload.items():
                        if k not in data or not data[k]:
                            data[k] = v
                except Exception as ex:
                    logger.warning(f"解析 payload_b64 失败: {ex}")

            machine_id = data.get("machine_id") or data.get("machine_code") or data.get("hardware_id", "")
            machine_id = str(machine_id).strip().lower()

            expire_date = data.get("expire_at") or data.get("expire_date") or data.get("valid_until") or data.get("expiration", "永久授权 (Permanent)")
            
            # 提取舞蹈列表
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

    def verify_license(self, license_data: Dict[str, Any], current_machine_id: Optional[str] = None) -> Dict[str, Any]:
        """
        前端预览比对与合法性初步校验
        """
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

    def check_remote_license_status(self) -> Dict[str, Any]:
        """
        探测机器人远端部署与 License 状态：
        校验标准：
        1. 检查是否存在 /home/ubuntu/vsis_mimic_deploy/license.json
        2. 提取 license 中的 machine_id 与当前真机指纹比对
        3. 容器正在运行
        4. 机器人主控日志中各舞蹈无 [SKIP] not licensed
        5. 机载主控与 LoRa 程序处于活跃运行状态
        """
        if not ssh_manager.is_connected():
            return {
                "connected": False,
                "first_time": True,
                "has_license": False,
                "license_valid": False,
                "is_container_running": False,
                "msg": "未连接至机器人"
            }

        # 上传超大镜像期间，挂起高频后台容器与文件巡检，保障网络与 CPU 完全专注于数据上传
        if ssh_manager.upload_progress.get("is_uploading"):
            return {
                "connected": True,
                "first_time": True,
                "has_license": False,
                "license_valid": False,
                "is_container_running": False,
                "machine_id": "",
                "robot_id": "A",
                "license_data": {},
                "msg": "正在高速流式传输镜像包..."
            }

        # 1. 尝试读取远端 License 是否存在
        remote_lic_path = "/home/ubuntu/vsis_mimic_deploy/license.json"
        ok_lic, lic_content = ssh_manager.read_remote_text_file(remote_lic_path)
        if not ok_lic or not lic_content.strip():
            # 容器内部读取
            code, out, _ = ssh_manager.execute_command(f"docker exec vsis_g1 cat {remote_lic_path} 2>/dev/null", sudo=True)
            if code == 0 and out.strip():
                lic_content = out
                ok_lic = True

        has_license = bool(ok_lic and lic_content.strip())
        
        # 2. 读取当前机器码
        m_res = deployment_core.read_machine_id()
        current_mid = m_res.get("machine_id", "").strip().lower()

        parsed_license = {}
        lic_mid = ""
        if has_license:
            p = self.parse_license_content(lic_content)
            if p.get("success"):
                parsed_license = p.get("data", {})
                lic_mid = str(parsed_license.get("machine_id", "")).strip().lower()

        # 3. 机器码严格一致性比对
        is_mid_matched = False
        if has_license and lic_mid and current_mid:
            is_mid_matched = (lic_mid == current_mid)

        # 4. 检查容器运行状态 (包含 400 端口或 vsis_g1 容器)
        code_p400, p400_out, _ = ssh_manager.execute_command("docker ps --filter publish=400 --format '{{.Names}}'", sudo=True)
        code_ps, ps_out, _ = ssh_manager.execute_command("docker ps --filter name=vsis_g1 --format '{{.Names}}'", sudo=True)
        is_container_running = bool((code_p400 == 0 and p400_out.strip()) or (code_ps == 0 and "vsis_g1" in ps_out))

        # 5. 检查机载程序运行状态
        code_ctrl, out_ctrl, _ = ssh_manager.execute_command("pgrep -f g1_ctrl_vsis", sudo=True)
        is_ctrl_running = bool(code_ctrl == 0 and out_ctrl.strip())
        code_lora, out_lora, _ = ssh_manager.execute_command("pgrep -f lora_recv_group", sudo=True)
        is_lora_running = bool(code_lora == 0 and out_lora.strip())

        # 6. 读取 Robot ID
        ok_id, id_txt = ssh_manager.read_remote_text_file("/home/ubuntu/vsis_mimic_deploy/group/lora_robot_id.txt")
        robot_id = id_txt.strip() if ok_id and id_txt.strip() else "A"

        # 7. 校验日志中是否存在 [SKIP] not licensed
        has_skip = False
        if has_license and is_container_running:
            check_cmd = "cat /home/ubuntu/vsis_mimic_deploy/log/sec_run.log 2>/dev/null | tail -n 80"
            code_log, log_out, _ = ssh_manager.execute_command(check_cmd, sudo=True)
            if not log_out.strip():
                c_name = p400_out.strip().split('\n')[0] if p400_out.strip() else "vsis_g1"
                _, log_out, _ = ssh_manager.execute_command(f"docker exec {c_name} cat /home/ubuntu/vsis_mimic_deploy/log/sec_run.log 2>/dev/null | tail -n 80", sudo=True)
            has_skip = bool("[SKIP] not licensed" in log_out or "not licensed" in log_out)

        # 只有在：有 License + 机器码匹配 + 日志无跳过 时，才算 License 有效
        license_valid = bool(has_license and is_mid_matched and not has_skip)
        
        # 判定是否首次部署向导 (全套就绪才判定为 False，否则一律 True 引导进入向导)
        first_time = not (has_license and license_valid and is_container_running and is_ctrl_running and is_lora_running)

        return {
            "connected": True,
            "first_time": first_time,
            "has_license": has_license,
            "license_valid": license_valid,
            "is_mid_matched": is_mid_matched,
            "is_container_running": is_container_running,
            "is_ctrl_running": is_ctrl_running,
            "is_lora_running": is_lora_running,
            "machine_id": current_mid,
            "license_machine_id": lic_mid,
            "robot_id": robot_id,
            "license_data": parsed_license,
            "msg": "已完成部署且 License 验证通过，直接进入群控运行模式" if not first_time else "检测到未授权或未部署完成，需进入一键部署向导"
        }

    def deploy_license_to_robot(self, license_json_str: str) -> Dict[str, Any]:
        """
        按照群控商业化说明第8节第6步完整执行：
        1. license 放入 /home/ubuntu/vsis_mimic_deploy/license.json
        2. 同步拷贝至容器内部并重启进程/容器
        3. 自动读取日志确认各舞蹈无 [SKIP] not licensed
        """
        remote_path = "/home/ubuntu/vsis_mimic_deploy/license.json"

        # 0. 前置检查：若现有 License 文件与传入的内容相同且无 [SKIP] not licensed，直接返回成功
        ok_cur, cur_lic_str = ssh_manager.read_remote_text_file(remote_path)
        if ok_cur and cur_lic_str.strip():
            try:
                import json
                cur_data = json.loads(cur_lic_str.strip())
                new_data = json.loads(license_json_str.strip())
                if cur_data == new_data:
                    # 检查运行日志是否有 [SKIP] not licensed
                    check_cmd = "cat /home/ubuntu/vsis_mimic_deploy/log/sec_run.log 2>/dev/null | tail -n 80"
                    _, log_out, _ = ssh_manager.execute_command(check_cmd, sudo=True)
                    if "[SKIP] not licensed" not in log_out and "not licensed" not in log_out:
                        return {
                            "success": True,
                            "already_identical": True,
                            "has_skip": False,
                            "msg": "检测到机器人端已存在完全相同的有效 License 授权文件，且所有舞蹈均已授权就绪，无需重复导入！"
                        }
            except Exception:
                pass
        
        # 1. 写入宿主机目录
        ok, msg = ssh_manager.write_remote_text_file(license_json_str, remote_path, sudo=True)
        if not ok:
            logger.error(f"[LICENSE 部署错误] 写入宿主机 {remote_path} 失败: {msg}")
            return {"success": False, "msg": f"写入宿主机 License 失败: {msg}"}

        # 2. 动态获取运行容器名称 (例如 mimic_cpu 或 vsis_g1)
        code_p400, p400_out, _ = ssh_manager.execute_command("docker ps --filter publish=400 --format '{{.Names}}'", sudo=True)
        c_names = set(["vsis_g1"])
        if code_p400 == 0 and p400_out.strip():
            for name in p400_out.strip().split('\n'):
                if name.strip():
                    c_names.add(name.strip())

        # 同步拷贝进入容器
        for c_name in c_names:
            cmd_cp = f"docker cp {remote_path} {c_name}:{remote_path} 2>/dev/null || true"
            ssh_manager.execute_command(cmd_cp, sudo=True)

        logger.info(f"[LICENSE 部署] 已写入 {remote_path} 并同步至容器 {list(c_names)}，正在重启运控与群控进程...")

        # 3. 重启控制程序 (杀掉旧进程并重新调用 run_bg.sh)
        for c_name in c_names:
            cmd_restart = (
                f"docker exec {c_name} bash -c "
                f"\"pkill -9 -f g1_ctrl_vsis ; pkill -9 -f lora_recv_group ; nohup /home/ubuntu/vsis_mimic_deploy/run_bg.sh >/dev/null 2>&1 &\" || true"
            )
            ssh_manager.execute_command(cmd_restart, sudo=True)

        # 4. 等待 2 秒让主控程序完成模型加载与 License 初始化
        time.sleep(2.0)

        # 5. 读取主控日志并校验各舞蹈是否存在 [SKIP] not licensed
        check_cmd = "cat /home/ubuntu/vsis_mimic_deploy/log/sec_run.log 2>/dev/null | tail -n 80"
        code_log, log_out, _ = ssh_manager.execute_command(check_cmd, sudo=True)
        if not log_out.strip():
            for c_name in c_names:
                code_log, log_out, _ = ssh_manager.execute_command(f"docker exec {c_name} cat /home/ubuntu/vsis_mimic_deploy/log/sec_run.log 2>/dev/null | tail -n 80", sudo=True)
                if log_out.strip():
                    break

        has_skip = bool("[SKIP] not licensed" in log_out or "not licensed" in log_out)
        
        if has_skip:
            logger.error(f"[LICENSE 校验失败] 容器已重启，但在日志中检测到舞蹈跳过标记 [SKIP] not licensed！\n日志片段:\n{log_out[-400:]}")
            return {
                "success": False,
                "has_skip": True,
                "path": remote_path,
                "msg": "License 已导入并重启，但在日志中检测到 [SKIP] not licensed 标记，部分舞蹈未获得授权！",
                "log_snippet": log_out[-600:] if log_out else ""
            }
        else:
            logger.info(f"[LICENSE 部署与校验成功] License 成功部署生效并重启！日志确认各舞蹈无 [SKIP] not licensed 标记。")
            return {
                "success": True,
                "has_skip": False,
                "path": remote_path,
                "msg": "License 成功部署并重启生效！主控日志确认各舞蹈正常加载，无未授权跳过情况。",
                "log_snippet": log_out[-600:] if log_out else ""
            }


license_service = LicenseService()

