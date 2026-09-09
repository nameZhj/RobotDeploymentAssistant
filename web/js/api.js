/**
 * VSISLAB 部署助手 前端 API 通信模块
 */
const API = {
  baseUrl: '',

  async request(endpoint, options = {}) {
    const url = `${this.baseUrl}${endpoint}`;
    try {
      const headers = { ...(options.headers || {}) };
      if (options.body && !headers['Content-Type'] && typeof options.body === 'string') {
        headers['Content-Type'] = 'application/json';
      }

      const resp = await fetch(url, {
        headers,
        ...options
      });
      if (!resp.ok) {
        throw new Error(`HTTP ${resp.status}: ${resp.statusText}`);
      }
      return await resp.json();
    } catch (err) {
      console.error(`API Error on ${endpoint}:`, err);
      throw err;
    }
  },

  // 1. 连接状态与启动自检
  getStatus() {
    return this.request('/api/status');
  },

  startupCheck() {
    return this.request('/api/startup_check');
  },

  connect(credentials) {
    return this.request('/api/connect', {
      method: 'POST',
      body: JSON.stringify(credentials)
    });
  },

  disconnect() {
    return this.request('/api/disconnect', { method: 'POST' });
  },

  // 2. 网络扫描与网卡配置
  getInterfaces() {
    return this.request('/api/network/interfaces');
  },

  autoConnect(forceNic = true) {
    return this.request('/api/network/auto_connect', {
      method: 'POST',
      body: JSON.stringify({ force_nic: forceNic })
    });
  },

  getAutoNetworkStatus() {
    return this.request('/api/network/auto_status');
  },

  configureNic(nicName, ip = '192.168.123.200') {
    return this.request('/api/network/configure_nic', {
      method: 'POST',
      body: JSON.stringify({ nic_name: nicName, ip })
    });
  },

  restoreDhcp(nicName) {
    return this.request('/api/network/restore_dhcp', {
      method: 'POST',
      body: JSON.stringify({ nic_name: nicName })
    });
  },

  scanNetwork(subnet = '192.168.123.') {
    return this.request('/api/network/scan', {
      method: 'POST',
      body: JSON.stringify({ subnet })
    });
  },

  // 3. 环境预检与修复
  getPrecheck() {
    return this.request('/api/precheck');
  },

  fixCh341() {
    return this.request('/api/fix/ch341', { method: 'POST' });
  },

  fixDocker() {
    return this.request('/api/fix/docker', { method: 'POST' });
  },

  // 4. 镜像管理与容器启动
  listImages() {
    return this.request('/api/images/list');
  },

  listContainers() {
    return this.request('/api/containers/list');
  },

  uploadImage(data) {
    if (data instanceof FormData) {
      return fetch('/api/images/upload', {
        method: 'POST',
        body: data
      }).then(res => res.json());
    } else {
      return this.request('/api/images/upload', {
        method: 'POST',
        body: JSON.stringify(data)
      });
    }
  },

  selectFile() {
    return this.request('/api/system/select_file', { method: 'POST' });
  },

  selectFolder() {
    return this.request('/api/system/select_folder', { method: 'POST' });
  },


  cancelUpload() {
    return this.request('/api/images/cancel_upload', { method: 'POST' });
  },

  getUploadProgress() {
    return this.request('/api/images/upload_progress');
  },

  loadImage(remoteTarPath) {
    return this.request('/api/images/load', {
      method: 'POST',
      body: JSON.stringify({ remote_tar_path: remoteTarPath })
    });
  },

  getContainerStatus() {
    return this.request('/api/container/status');
  },

  startContainer(imageName) {
    return this.request('/api/container/start', {
      method: 'POST',
      body: JSON.stringify({ image_name: imageName })
    });
  },

  stopContainer(containerName) {
    return this.request('/api/container/stop', {
      method: 'POST',
      body: JSON.stringify({ container_name: containerName })
    });
  },

  restartContainer(containerName = 'vsis_g1') {
    return this.request('/api/container/restart', {
      method: 'POST',
      body: JSON.stringify({ container_name: containerName })
    });
  },

  configAutostart(robotId = 'A') {
    return this.request('/api/container/autostart', {
      method: 'POST',
      body: JSON.stringify({ robot_id: robotId })
    });
  },

  checkRobotEnv() {
    return this.request('/api/robot/check_env', {
      method: 'POST'
    });
  },


  // 5. 机器码与 License
  getLicenseStatus() {
    return this.request('/api/license/status');
  },

  getMachineId() {
    return this.request('/api/machine_id');
  },

  verifyLicense(content, currentMachineId = '') {
    return this.request('/api/license/parse_and_verify', {
      method: 'POST',
      body: JSON.stringify({ content, current_machine_id: currentMachineId })
    });
  },

  deployLicense(content) {
    return this.request('/api/license/deploy', {
      method: 'POST',
      body: JSON.stringify({ content })
    });
  },

  // 6. 舞蹈更新与热重启
  updateDance(formData) {
    return fetch('/api/dance/update', {
      method: 'POST',
      body: formData
    }).then(res => res.json());
  },

  restartDanceProcesses() {
    return this.request('/api/robot/start_processes', { method: 'POST' });
  },

  getRobotProcessStatus() {
    return this.request('/api/robot/process_status');
  },

  startRobotProcesses() {
    return this.request('/api/robot/start_processes', { method: 'POST' });
  },

  stopRobotProcesses() {
    return this.request('/api/robot/stop_processes', { method: 'POST' });
  },

  // 7. 3D 舞蹈回放
  list3dDances() {
    return this.request('/api/dance/list_3d');
  },

  get3dDance(danceId) {
    return this.request(`/api/dance/get_3d/${danceId}`);
  },

  uploadNpz(formData) {
    return fetch('/api/dance/upload_npz', {
      method: 'POST',
      body: formData
    }).then(res => res.json());
  },

  delete3dDance(danceId) {
    return this.request(`/api/dance/delete_3d/${danceId}`, {
      method: 'POST'
    });
  },

  // 8. 日志与诊断
  getLogs(type = 'container', lines = 200, container = '') {
    const params = new URLSearchParams({ type, lines });
    if (container) params.append('container', container);
    return this.request(`/api/logs?${params.toString()}`);
  },

  // 9. 手动模式执行
  executeManual(command, sudo = false) {
    return this.request('/api/manual/execute', {
      method: 'POST',
      body: JSON.stringify({ command, sudo })
    });
  },

  // 9.1 Windows 本机 CH341 驱动
  checkWindowsCh341() {
    return this.request('/api/system/check_windows_ch341');
  },

  installWindowsCh341() {
    return this.request('/api/system/install_windows_ch341', {
      method: 'POST'
    });
  },

  // 11. LoRa 广播串口与群控 API
  getSerialPorts() {
    return this.request('/api/serial/ports');
  },

  autoConnectSerial(baudrate = 9600) {
    return this.request('/api/serial/auto_connect', {
      method: 'POST',
      body: JSON.stringify({ baudrate })
    });
  },

  connectSerial(portName, baudrate = 9600) {
    return this.request('/api/serial/connect', {
      method: 'POST',
      body: JSON.stringify({ port: portName, baudrate })
    });
  },

  sendSerialCmd(target, command) {
    return this.request('/api/serial/send', {
      method: 'POST',
      body: JSON.stringify({ target, command })
    });
  },

  disconnectSerial(safetyStop = true) {
    return this.request('/api/serial/disconnect', {
      method: 'POST',
      body: JSON.stringify({ safety_stop: safetyStop })
    });
  },

  getSerialStatus() {
    return this.request('/api/serial/status');
  },

  getSerialMessages(since = 0) {
    return this.request(`/api/serial/messages?since=${since}`);
  },

  getSerialDanceList(forceRefresh = false) {
    const url = forceRefresh ? '/api/serial/dance_list?refresh=1' : '/api/serial/dance_list';
    return this.request(url);
  },

  refreshSerialDanceList(timeout = 2.5) {
    return this.request('/api/serial/refresh_dance_list', {
      method: 'POST',
      body: JSON.stringify({ timeout })
    });
  },

  parseSerialDances(yamlContent) {
    return this.request('/api/serial/parse_dances', {
      method: 'POST',
      body: JSON.stringify({ content: yamlContent })
    });
  },

  // 10. SSE 任务日志流监听
  listenStream(taskId, onMessage, onComplete, onError) {
    const es = new EventSource(`/api/stream/${taskId}`);
    es.onmessage = (e) => {
      try {
        const data = JSON.parse(e.data);
        if (data.ping) return;
        if (data.text) {
          if (data.text.includes('__TASK_DONE__')) {
            const isOk = data.text.includes('__TASK_DONE__:True') || data.text.includes('__TASK_DONE__:true');
            es.close();
            if (onComplete) onComplete(isOk);
            return;
          }
          if (onMessage) onMessage(data.text, data.is_err);
        }
      } catch (err) {
        console.error('SSE JSON parse error:', err);
      }
    };
    es.onerror = (err) => {
      console.error('SSE Error:', err);
      es.close();
      if (onError) onError(err);
    };
    return es;
  }
};

// 全局通用安全剪贴板复制工具
function copyToClipboard(text, notifyText = '已复制到剪贴板！') {
  if (!text && text !== 0) return;
  const str = String(text);
  
  if (navigator.clipboard && window.isSecureContext) {
    navigator.clipboard.writeText(str).then(() => {
      showToast(`✓ ${notifyText}`, 'success', 2000, false);
    }).catch(() => fallbackCopy(str, notifyText));
  } else {
    fallbackCopy(str, notifyText);
  }

  function fallbackCopy(val, notice) {
    const ta = document.createElement('textarea');
    ta.value = val;
    ta.style.position = 'fixed';
    ta.style.top = '-9999px';
    ta.style.left = '-9999px';
    document.body.appendChild(ta);
    ta.focus();
    ta.select();
    try {
      document.execCommand('copy');
      showToast(`✓ ${notice}`, 'success', 2000, false);
    } catch (e) {
      showToast('复制失败，请手动选择复制', 'error');
    }
    document.body.removeChild(ta);
  }
}

// UI 弹窗通知 (支持一键复制错误与日志信息)
function showToast(msg, type = 'info', duration = 3500, showCopyBtn = true) {
  // 仅显示失败/警告类的提示，屏蔽成功与常规信息提示（保留复制成功的特定提示避免复制无反馈，如果不需要也可全屏蔽）
  if ((type === 'success' || type === 'info') && !msg.includes('复制')) {
    return;
  }

  const container = document.getElementById('toast-container');
  if (!container) return;

  const toast = document.createElement('div');
  toast.className = `toast ${type}`;
  let icon = 'ℹ️';
  if (type === 'success') icon = '✅';
  if (type === 'error') icon = '❌';
  if (type === 'warning') icon = '⚠️';

  const copyBtnHtml = (showCopyBtn && (type === 'error' || type === 'warning' || (typeof msg === 'string' && msg.length > 25)))
    ? `<button class="toast-copy-btn" title="复制此消息" onclick="event.stopPropagation(); copyToClipboard(${JSON.stringify(String(msg))}, '消息内容已复制')">📋 复制</button>`
    : '';

  toast.innerHTML = `
    <div class="toast-msg-body">
      <span>${icon}</span>
      <span>${msg}</span>
    </div>
    ${copyBtnHtml}
  `;
  container.appendChild(toast);

  setTimeout(() => {
    toast.style.opacity = '0';
    toast.style.transform = 'translateX(100%)';
    toast.style.transition = 'all 0.3s';
    setTimeout(() => toast.remove(), 300);
  }, duration);
}

/**
 * 全局公共校验：验证 Robot ID 格式、安全性与有效性
 * 规范要求：
 * 1. 不能为空，去除首尾空白后转大写
 * 2. 长度 1~20 位
 * 3. 仅允许字母 (A-Z)、数字 (0-9)、下划线 (_) 和短横线 (-)
 * 4. 严禁包含逗号 ','（群控多机分隔符）或竖线 '|'（通信协议指令分隔符）
 * 5. 严禁为保留广播关键字 'ALL'
 * 6. 严禁包含空格、引号、分号、反引号等任何危险注入字符
 * @param {string} rawId
 * @returns {{ valid: boolean, cleanId: string, error: string }}
 */
function validateRobotId(rawId) {
  if (rawId === undefined || rawId === null) {
    return { valid: false, cleanId: '', error: 'Robot ID 不能为空！请输入唯一寻址标识 (如 A, B, R1, G1_02 等)' };
  }
  const cleanId = String(rawId).trim().toUpperCase();
  if (!cleanId) {
    return { valid: false, cleanId: '', error: 'Robot ID 不能为空！请输入唯一寻址标识 (如 A, B, R1, G1_02 等)' };
  }
  if (cleanId === 'ALL') {
    return { valid: false, cleanId: '', error: 'ALL 为群控广播保留关键字，不能作为单机 ID！' };
  }
  if (cleanId.includes(',')) {
    return { valid: false, cleanId: '', error: 'Robot ID 不能包含逗号 \',\'，多机群控已使用逗号作为目标分隔符！' };
  }
  if (cleanId.includes('|')) {
    return { valid: false, cleanId: '', error: 'Robot ID 不能包含竖线 \'|\'，该字符为通信协议指令分隔符！' };
  }
  // 严格字符集白名单校验：只允许字母、数字、下划线、短横线，长度 1~20 位
  const validRegex = /^[A-Z0-9_-]{1,20}$/;
  if (!validRegex.test(cleanId)) {
    return {
      valid: false,
      cleanId: '',
      error: 'Robot ID 格式不合法！仅支持 1~20 位英文字母、数字、下划线(_)或短横线(-)，严禁包含空格或特殊字符以防注入漏洞。'
    };
  }
  return { valid: true, cleanId: cleanId, error: '' };
}

window.validateRobotId = validateRobotId;
if (typeof API !== 'undefined') {
  API.validateRobotId = validateRobotId;
}

