from typing import Any, Dict, Optional, Tuple
from src.core.logger import get_logger
from src.domain.fleet.robot_entity import validate_robot_id
from src.infrastructure.ssh.remote_ssh_channel import ssh_channel

logger = get_logger("DeploymentService")


class DeploymentService:
    """
    Coordinates remote robot deployment, environment self-healing, and container supervision.
    Strictly forbids tampering with the original onboard run_bg.sh file.
    """

    def check_remote_environment(self) -> Dict[str, Any]:
        if not ssh_channel.is_connected:
            return {"connected": False, "msg": "SSH channel not connected"}

        code_docker, out_docker, _ = ssh_channel.execute_command("docker --version")
        code_gpu, out_gpu, _ = ssh_channel.execute_command("nvidia-smi -L 2>/dev/null || echo 'NO_GPU'")
        code_ps, out_ps, _ = ssh_channel.execute_command(
            "docker ps --filter name=vsis_g1 --format '{{.Names}}|{{.Status}}'"
        )

        return {
            "connected": True,
            "has_docker": code_docker == 0,
            "docker_version": out_docker.strip(),
            "has_gpu": "NO_GPU" not in out_gpu,
            "container_status": out_ps.strip(),
        }

    def configure_autostart_hook(self, robot_id: str) -> Tuple[bool, str]:
        ok, clean_id, err = validate_robot_id(robot_id)
        if not ok:
            return False, err

        if not ssh_channel.is_connected:
            return False, "Not connected"

        startup_hook = (
            "#!/bin/bash\n"
            "sleep 8\n"
            "/home/ubuntu/vsis_mimic_deploy/run_bg.sh\n"
        )
        ssh_channel.execute_command("mkdir -p /docker_config")
        cmd_hook = f"echo '{startup_hook}' > /docker_config/custom_startup.sh && chmod +x /docker_config/custom_startup.sh"
        code, _, err = ssh_channel.execute_command(cmd_hook)
        if code != 0:
            return False, f"Failed to write startup hook: {err}"

        cmd_id = f"mkdir -p /home/ubuntu/vsis_mimic_deploy/group && echo '{clean_id}' > /home/ubuntu/vsis_mimic_deploy/group/lora_robot_id.txt"
        ssh_channel.execute_command(cmd_id)

        return True, f"Startup hook and robot ID {clean_id} configured"


deployment_service = DeploymentService()
