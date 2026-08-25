/**
 * Tab Panel 独立功能处理器
 * 每个 Tab 独立调用 API 并操作自己专属的 DOM 元素，
 * 与向导弹窗 (Wizard) 共用 API 但不共用 DOM 元素 ID。
 */

// ===========================================
// Tab 网络扫描与网卡配置
// ===========================================
const TabNetwork = {
  async init() {
    await this.loadNics();
  },

  async loadNics() {
    const select = document.getElementById('tp-nic-select');
    if (!select) return;
    try {
      const res = await API.getInterfaces();
      select.innerHTML = '';
      if (!res.interfaces || res.interfaces.length === 0) {
        select.innerHTML = '<option value="">未找到可用网卡</option>';
        return;
      }
      for (const nic of res.interfaces) {
        if (nic.is_loopback) continue;
        const opt = document.createElement('option');
        opt.value = nic.name;
        opt.textContent = `${nic.name}  (${nic.ip || '未分配IP'} / ${nic.is_up ? '已连接' : '未连接'})`;
        if (nic.is_unitree_subnet) opt.selected = true;
        select.appendChild(opt);
      }
    } catch (err) {
      console.error('获取网卡列表失败:', err);
    }
  },

  async scan() {
    const btn = document.getElementById('tp-btn-scan');
    const listEl = document.getElementById('tp-scan-results');
    if (btn) btn.disabled = true;
    if (listEl) listEl.innerHTML = '<div style="padding: 12px; color: var(--accent-cyan);">🔍 正在扫描局域网 (192.168.123.1~254) ...</div>';

    try {
      const res = await API.scanNetwork('192.168.123.');
      if (btn) btn.disabled = false;
      if (!res.devices || res.devices.length === 0) {
        if (listEl) listEl.innerHTML = `
          <div style="padding: 12px; color: var(--accent-yellow);">
            ⚠️ 未发现活跃设备。请确认：网线已连接、电脑网卡已配置为 192.168.123.x 网段、机器人电源已开启。
          </div>
        `;
        return;
      }
      let html = '';
      for (const dev of res.devices) {
        html += `
          <div class="card" style="margin-bottom: 8px; padding: 12px; display: flex; align-items: center; justify-content: space-between;">
            <div>
              <div style="font-weight: 700; color: #ffffff; font-family: monospace; font-size: 1rem;">${dev.ip}:${dev.port}</div>
              <div style="font-size: 0.78rem; color: #9ca3af;">${dev.device_type} - ${dev.default_hint}</div>
            </div>
            <button class="btn btn-primary btn-sm" onclick="TabNetwork.connectDevice('${dev.ip}', ${dev.port})">🔗 连接此设备</button>
          </div>
        `;
      }
      if (listEl) listEl.innerHTML = html;
    } catch (err) {
      if (btn) btn.disabled = false;
      if (listEl) listEl.innerHTML = `<div style="padding: 12px; color: var(--accent-red);">扫描失败: ${err.message}</div>`;
    }
  },

  connectDevice(ip, port) {
    const hostInput = document.getElementById('input-host');
    const portInput = document.getElementById('input-port');
    if (hostInput) hostInput.value = ip;
    if (portInput) portInput.value = port;
    App.connect();
  },

  async setStatic() {
    const select = document.getElementById('tp-nic-select');
    const nicName = select ? select.value : '';
    if (!nicName) {
      showToast('请先选择需要配置的以太网卡', 'warning');
      return;
    }
    showToast(`正在将网卡 [${nicName}] 设为 192.168.123.200 ...`, 'info');
    try {
      const res = await API.configureNic(nicName, '192.168.123.200');
      if (res.success) {
        showToast(res.msg, 'success');
        await this.loadNics();
      } else {
        showToast(`配置失败: ${res.msg}`, 'error');
      }
    } catch (err) {
      showToast(`网卡配置异常: ${err.message}`, 'error');
    }
  },

  async setDhcp() {
    const select = document.getElementById('tp-nic-select');
    const nicName = select ? select.value : '';
    if (!nicName) return;
    showToast(`正在将网卡 [${nicName}] 恢复为 DHCP ...`, 'info');
    try {
      const res = await API.restoreDhcp(nicName);
      showToast(res.success ? res.msg : `恢复失败: ${res.msg}`, res.success ? 'success' : 'error');
      if (res.success) await this.loadNics();
    } catch (err) {
      showToast(`恢复异常: ${err.message}`, 'error');
    }
  }
};


// ===========================================
// Tab 环境预检与修复
// ===========================================
const TabPrecheck = {
  async run() {
    const container = document.getElementById('tp-precheck-items');
    if (!container) return;
    container.innerHTML = '<div style="padding: 20px; color: var(--accent-cyan);">⏳ 正在执行环境预检，请稍候...</div>';

    try {
      const res = await API.getPrecheck();
      if (!res.success || !res.data) {
        container.innerHTML = `<div style="padding: 20px; color: var(--accent-red);">预检失败: ${res.msg || '未知错误'}</div>`;
        return;
      }
      const items = res.data.items;
      let html = '';
      for (const key in items) {
        const item = items[key];
        let statusIcon = '✅';
        if (item.status === 'error') statusIcon = '❌';
        else if (item.status === 'warning') statusIcon = '⚠️';

        const copyText = `【${item.name}】状态: ${item.status}\n指标/版本: ${item.version}\n说明: ${item.msg}`;
        html += `
          <div class="card" style="margin-bottom: 12px;">
            <div class="card-header">
              <div class="card-title">
                <span>${statusIcon}</span>
                <span>${item.name}</span>
              </div>
              <div style="display: flex; gap: 8px; align-items: center;">
                <button class="btn-copy-mini" onclick="copyToClipboard(${JSON.stringify(copyText)}, '指标信息已复制')">📋 复制</button>
                ${item.can_fix ? `<button class="btn btn-primary btn-sm" onclick="TabPrecheck.fixItem('${key}')">🛠️ 一键修复</button>` : ''}
              </div>
            </div>
            <div style="font-size: 0.85rem; color: #ffffff; font-family: monospace; margin-bottom: 4px; user-select: text;">${item.version}</div>
            <div style="font-size: 0.8rem; color: var(--text-secondary); user-select: text;">${item.msg}</div>
          </div>
        `;
      }
      container.innerHTML = html || '<div style="color: var(--text-muted); padding: 20px;">没有预检数据</div>';

      if (res.data.all_passed) {
        // 静默通过，仅在 UI 上显示绿勾，不再弹出 toast
      } else {
        showToast('⚠️ 检测到部分环境指标异常，请使用【一键修复】按钮解决', 'warning', 4000);
      }
    } catch (err) {
      container.innerHTML = `<div style="padding: 20px; color: var(--accent-red);">预检异常: ${err.message}</div>`;
    }
  },

  async fixItem(key) {
    if (key === 'serial_ch341') {
      this.fixCh341();
    } else if (key === 'docker') {
      this.fixDocker();
    }
  },

  async fixCh341() {
    showToast('正在启动 CH341 串口驱动编译与安装任务...', 'info');
    const modal = document.getElementById('fix-stream-modal');
    const consoleEl = document.getElementById('fix-stream-console');
    if (modal) modal.style.display = 'flex';
    if (consoleEl) consoleEl.innerHTML = '<div class="log-info">开始编译安装 CH341 驱动...</div>';
    try {
      const res = await API.fixCh341();
      if (res.success && res.task_id) {
        API.listenStream(res.task_id, (line, isErr) => {
          if (consoleEl) {
            const div = document.createElement('div');
            div.className = isErr ? 'log-error' : 'log-info';
            div.textContent = line;
            consoleEl.appendChild(div);
            consoleEl.scrollTop = consoleEl.scrollHeight;
          }
        }, (ok) => {
          showToast(ok ? 'CH341 驱动安装完成！' : '驱动安装遇到问题，请检查日志', ok ? 'success' : 'error');
          TabPrecheck.run();
        });
      }
    } catch (err) {
      showToast(`修复触发异常: ${err.message}`, 'error');
    }
  },

  async fixDocker() {
    showToast('正在修复 Docker 环境...', 'info');
    const modal = document.getElementById('fix-stream-modal');
    const consoleEl = document.getElementById('fix-stream-console');
    if (modal) modal.style.display = 'flex';
    if (consoleEl) consoleEl.innerHTML = '<div class="log-info">正在修复 Docker...</div>';
    try {
      const res = await API.fixDocker();
      if (res.success && res.task_id) {
        API.listenStream(res.task_id, (line, isErr) => {
          if (consoleEl) {
            const div = document.createElement('div');
            div.className = isErr ? 'log-error' : 'log-info';
            div.textContent = line;
            consoleEl.appendChild(div);
            consoleEl.scrollTop = consoleEl.scrollHeight;
          }
        }, (ok) => {
          showToast(ok ? 'Docker 修复完成' : 'Docker 修复遇到问题', ok ? 'success' : 'error');
          TabPrecheck.run();
        });
      }
    } catch (err) {
      showToast(`修复异常: ${err.message}`, 'error');
    }
  }
};


// ===========================================
// Tab 镜像与容器管理
// ===========================================
const TabImage = {
  uploadInterval: null,

  async init() {
    await this.loadImages();
    this.bindEvents();
  },

  bindEvents() {
    // 文件选择回显文件名
    const fileInput = document.getElementById('tp-image-file-input');
    if (fileInput) {
      fileInput.addEventListener('change', (e) => {
        if (e.target.files.length > 0) {
          const file = e.target.files[0];
          const label = document.getElementById('tp-image-file-label');
          if (label) label.textContent = `${file.name} (${(file.size / (1024*1024*1024)).toFixed(2)} GB)`;
        }
      });
    }
  },

  async loadImages() {
    const select = document.getElementById('tp-docker-image-select');
    if (!select) return;
    try {
      const res = await API.listImages();
      select.innerHTML = '';
      if (!res.images || res.images.length === 0) {
        select.innerHTML = '<option value="vsis_dancer:gpu-0.1">vsis_dancer:gpu-0.1 (默认)</option>';
        return;
      }
      for (const img of res.images) {
        const opt = document.createElement('option');
        const tag = `${img.repository}:${img.tag}`;
        opt.value = tag;
        opt.textContent = `${tag} (${img.size})`;
        select.appendChild(opt);
      }
    } catch (err) {
      console.error('获取镜像列表失败:', err);
    }
  },

  async uploadImage() {
    const fileInput = document.getElementById('tp-image-file-input');
    const pathInput = document.getElementById('tp-remote-path-input');
    let localPath = '';

    const formData = new FormData();
    if (fileInput && fileInput.files.length > 0) {
      formData.append('file', fileInput.files[0]);
    } else {
      showToast('请选取本地镜像包 (.tar.gz)', 'warning');
      return;
    }

    showToast('开始 SFTP 上传镜像至机器人 /tmp 目录...', 'info');
    const progressBox = document.getElementById('tp-upload-progress-box');
    const consoleEl = document.getElementById('tp-load-console');
    if (progressBox) progressBox.style.display = 'block';
    if (consoleEl) consoleEl.innerHTML = '<div class="log-info">正在建立 SFTP 连接...</div>';

    try {
      const res = await API.uploadImage(formData);
      if (!res.success) {
        showToast(`上传失败: ${res.msg}`, 'error');
        return;
      }
      if (pathInput) pathInput.value = res.remote_path;

      if (this.uploadInterval) clearInterval(this.uploadInterval);
      this.uploadInterval = setInterval(async () => {
        const prog = await API.getUploadProgress();
        this._updateProgress(prog);
        if (prog.status === 'completed') {
          clearInterval(this.uploadInterval);
          showToast('镜像上传成功！可执行 docker load ...', 'success');
        } else if (prog.status === 'error') {
          clearInterval(this.uploadInterval);
          showToast(`上传出错: ${prog.error_msg}`, 'error');
        }
      }, 500);
    } catch (err) {
      showToast(`上传请求异常: ${err.message}`, 'error');
    }
  },

  _updateProgress(p) {
    const bar = document.getElementById('tp-upload-bar');
    const pctText = document.getElementById('tp-upload-pct');
    const infoText = document.getElementById('tp-upload-info');
    if (bar) bar.style.width = `${p.percent || 0}%`;
    if (pctText) pctText.textContent = `${p.percent || 0}%`;
    if (infoText) {
      const mbTrans = ((p.transferred_bytes || 0) / (1024*1024)).toFixed(1);
      const mbTotal = ((p.total_bytes || 0) / (1024*1024)).toFixed(1);
      infoText.textContent = `${mbTrans} MB / ${mbTotal} MB | 速率: ${p.speed_mbps || 0} MB/s | 剩余: ${p.eta_seconds || '--'}s`;
    }
  },

  async dockerLoad() {
    const pathInput = document.getElementById('tp-remote-path-input');
    const remotePath = pathInput ? pathInput.value.trim() : '/tmp/vsis_dancer_gpu.tar.gz';
    if (!remotePath) {
      showToast('请填写远端镜像文件路径', 'warning');
      return;
    }

    const consoleEl = document.getElementById('tp-load-console');
    if (consoleEl) consoleEl.innerHTML = '<div class="log-info">正在执行 docker load -i ...</div>';

    try {
      const res = await API.loadImage(remotePath);
      if (res.success && res.task_id) {
        API.listenStream(res.task_id, (line, isErr) => {
          if (consoleEl) {
            const div = document.createElement('div');
            div.className = isErr ? 'log-error' : 'log-info';
            div.textContent = line;
            consoleEl.appendChild(div);
            consoleEl.scrollTop = consoleEl.scrollHeight;
          }
        }, async (ok) => {
          if (ok) {
            showToast('Docker 镜像导入完成！', 'success');
            await this.loadImages();
          } else {
            showToast('镜像导入异常，请查看日志', 'error');
          }
        });
      }
    } catch (err) {
      showToast(`执行异常: ${err.message}`, 'error');
    }
  },

  async startContainer() {
    const select = document.getElementById('tp-docker-image-select');
    const imgName = select && select.value ? select.value : 'vsis_dancer:gpu-0.1';
    const consoleEl = document.getElementById('tp-container-console');
    if (consoleEl) consoleEl.innerHTML = '<div class="log-info">正在执行固化容器启动命令...</div>';

    try {
      const res = await API.startContainer(imgName);
      if (res.success && res.task_id) {
        API.listenStream(res.task_id, (line, isErr) => {
          if (consoleEl) {
            const div = document.createElement('div');
            div.className = isErr ? 'log-error' : 'log-info';
            div.textContent = line;
            consoleEl.appendChild(div);
            consoleEl.scrollTop = consoleEl.scrollHeight;
          }
        }, async (ok) => {
          if (ok) {
            showToast('✓ 容器 vsis_g1 已启动！', 'success');
          } else {
            showToast('容器启动失败，请查看上方日志', 'error');
          }
        });
      }
    } catch (err) {
      showToast(`启动异常: ${err.message}`, 'error');
    }
  },

  async writeAutostart() {
    const select = document.getElementById('tp-robot-id-select');
    const robotId = select ? select.value : 'A';
    showToast(`正在配置开机自启并写入 Robot ID [${robotId}] ...`, 'info');
    try {
      const res = await API.configAutostart(robotId);
      showToast(res.success ? res.msg : `写入失败: ${res.msg}`, res.success ? 'success' : 'error');
    } catch (err) {
      showToast(`写入失败: ${err.message}`, 'error');
    }
  }
};


// ===========================================
// Tab 机器码与 License
// ===========================================
const TabLicense = {
  machineId: null,
  licenseContent: null,

  init() {
    this.bindDropzone();
    this.fetchMachineId();
  },

  bindDropzone() {
    const dropzone = document.getElementById('tp-license-dropzone');
    const fileInput = document.getElementById('tp-license-file-input');
    const deployBtn = document.getElementById('tp-deploy-btn');

    if (dropzone && fileInput) {
      dropzone.addEventListener('click', () => fileInput.click());
      dropzone.addEventListener('dragover', (e) => {
        e.preventDefault();
        dropzone.classList.add('dragover');
      });
      dropzone.addEventListener('dragleave', () => dropzone.classList.remove('dragover'));
      dropzone.addEventListener('drop', (e) => {
        e.preventDefault();
        dropzone.classList.remove('dragover');
        if (e.dataTransfer.files.length > 0) {
          this.handleFile(e.dataTransfer.files[0]);
        }
      });
      fileInput.addEventListener('change', (e) => {
        if (e.target.files.length > 0) {
          this.handleFile(e.target.files[0]);
        }
      });
    }

    if (deployBtn) {
      deployBtn.addEventListener('click', () => this.deploy());
    }
  },

  async fetchMachineId() {
    const midEl = document.getElementById('tp-machine-id-val');
    if (midEl) midEl.textContent = '正在读取硬件机器码...';
    try {
      const res = await API.getMachineId();
      if (res.success && res.machine_id) {
        this.machineId = res.machine_id;
        if (midEl) midEl.textContent = res.machine_id;
        // 静默更新，不弹 toast
      } else {
        if (midEl) midEl.textContent = '未能读取到机器码（请先确保容器已启动）';
        showToast(`读取失败: ${res.msg}`, 'warning');
      }
    } catch (err) {
      if (midEl) midEl.textContent = '读取机器码异常';
      showToast(`机器码接口异常: ${err.message}`, 'error');
    }
  },

  copyMachineId() {
    if (!this.machineId) {
      showToast('暂无机器码可复制', 'warning');
      return;
    }
    copyToClipboard(this.machineId, '64位机器码已复制到剪贴板！');
  },

  async handleFile(file) {
    const reader = new FileReader();
    reader.onload = async (e) => {
      this.licenseContent = e.target.result;
      const deployBtn = document.getElementById('tp-deploy-btn');
      const nameEl = document.getElementById('tp-license-filename');
      if (nameEl) nameEl.textContent = `已选择: ${file.name}`;
      if (deployBtn) deployBtn.disabled = false;

      // 简单显示文件已加载
      this._showResult(`<div style="color: var(--accent-cyan); padding: 12px; background: rgba(56,189,248,0.08); border-radius: 8px; border: 1px solid rgba(56,189,248,0.3);">
        📄 <b>${file.name}</b> 已加载，点击【部署 License】写入机器人并重启校验。
      </div>`);

      showToast('License 文件已读取，点击【部署 License】开始校验', 'info');
    };
    reader.readAsText(file);
  },

  _showResult(html) {
    const resEl = document.getElementById('tp-license-result');
    if (resEl) resEl.innerHTML = html;
  },

  async deploy() {
    if (!this.licenseContent) {
      showToast('请先选择或拖入 license.json 文件', 'warning');
      return;
    }
    const btn = document.getElementById('tp-deploy-btn');
    if (btn) { btn.disabled = true; btn.textContent = '⏳ 正在部署并重启验证...'; }

    showToast('正在写入 License 并重启运控进程校验日志...', 'info');
    try {
      const res = await API.deployLicense(this.licenseContent);
      if (res.success) {
        showToast('✓ License 部署并校验成功！日志无 [SKIP] not licensed', 'success', 3500);
        let html = `<div style="background: rgba(16,185,129,0.1); border: 1px solid rgba(16,185,129,0.3); border-radius: 8px; padding: 16px;">
          <div style="color: #34d399; font-weight: 700; margin-bottom: 8px;">✅ 部署与校验成功！</div>
          <div style="font-size: 0.85rem; color: #a7f3d0;">${res.msg}</div>`;
        if (res.log_snippet) {
          html += `<div style="margin-top: 8px; font-family: monospace; font-size: 0.75rem; color: #a7f3d0; background: rgba(0,0,0,0.3); padding: 8px; border-radius: 4px; white-space: pre-wrap; max-height: 120px; overflow-y: auto;">${res.log_snippet}</div>`;
        }
        html += '</div>';
        this._showResult(html);
      } else {
        showToast(`❌ 机器端校验失败: ${res.msg}`, 'error');
        let html = `<div style="background: rgba(239,68,68,0.1); border: 1px solid rgba(239,68,68,0.3); border-radius: 8px; padding: 16px;">
          <div style="color: #f87171; font-weight: 700; margin-bottom: 8px;">❌ 校验失败: ${res.msg}</div>`;
        if (res.log_snippet) {
          html += `<div style="margin-top: 8px; font-family: monospace; font-size: 0.75rem; color: #fca5a5; background: rgba(0,0,0,0.3); padding: 8px; border-radius: 4px; white-space: pre-wrap; max-height: 120px; overflow-y: auto;">${res.log_snippet}</div>`;
        }
        html += '</div>';
        this._showResult(html);
      }
    } catch (err) {
      showToast(`部署 License 异常: ${err.message}`, 'error');
    } finally {
      if (btn) { btn.disabled = false; btn.textContent = '🚀 部署 License 至机器人'; }
    }
  }
};


// ===========================================
// Tab 切换时懒加载初始化
// ===========================================
(function initTabLazyLoad() {
  document.addEventListener('DOMContentLoaded', () => {
    // 绑定 tab 切换时的懒初始化
    document.querySelectorAll('.tab-btn').forEach(btn => {
      btn.addEventListener('click', () => {
        const tabId = btn.dataset.tab;
        if (tabId === 'tab-network') {
          TabNetwork.init();
        } else if (tabId === 'tab-precheck') {
          TabPrecheck.run();
        } else if (tabId === 'tab-image') {
          TabImage.init();
        } else if (tabId === 'tab-license') {
          TabLicense.init();
        }
      });
    });
  });
})();
