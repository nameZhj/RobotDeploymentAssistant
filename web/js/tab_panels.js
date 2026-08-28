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
    await this.loadWindowsCh341();
  },

  async autoConnect() {
    showToast('⚡ 正在执行断网自愈与自动连接...', 'info', 3000);
    try {
      const res = await API.autoConnect(true);
      if (res.connected) {
        showToast(res.msg, 'success', 3500);
        App.updateStatus();
        this.loadNics();
      } else {
        showToast(res.msg || '未探测到在线机器人', 'warning', 3500);
      }
    } catch (err) {
      showToast(`自愈连接异常: ${err.message}`, 'error');
    }
  },

  async loadWindowsCh341() {
    const statusEl = document.getElementById('tp-win-ch341-status');
    if (!statusEl) return;
    try {
      const res = await API.checkWindowsCh341();
      if (res.success && res.data) {
        const data = res.data;
        if (data.ports && data.ports.length > 0) {
          const portNames = data.ports.map(p => `${p.port} (${p.device.replace('\\Device\\', '')})`).join(', ');
          statusEl.innerHTML = `<span style="color: var(--accent-green); font-weight: bold;">✅ 已识别串口：${portNames}</span>`;
        } else {
          statusEl.innerHTML = `<span style="color: var(--text-muted);">未插入 USB 串口模块（若已插入但未识别，请点击右侧安装驱动）</span>`;
        }
      }
    } catch (e) {
      console.error('检测 Windows 串口失败:', e);
    }
  },

  async installWindowsCh341() {
    try {
      const res = await API.installWindowsCh341();
      if (res.success) {
        alert(res.msg || 'Windows CH341 驱动安装程序已启动，请在弹窗中点击【安装】完成驱动安装。');
        setTimeout(() => this.loadWindowsCh341(), 4000);
      } else {
        alert(`启动驱动安装程序失败: ${res.msg}`);
      }
    } catch (err) {
      alert(`安装驱动异常: ${err.message}`);
    }
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

      // 控制顶部快速修复按钮：仅在驱动缺失且可修复时显示，已就绪则隐藏
      const btnHeaderFix = document.getElementById('btn-tp-fix-ch341');
      if (btnHeaderFix) {
        if (items.serial_ch341 && items.serial_ch341.can_fix) {
          btnHeaderFix.style.display = 'inline-block';
        } else {
          btnHeaderFix.style.display = 'none';
        }
      }

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
  processPollInterval: null,

  async init() {
    await this.loadImages();
    await this.checkStatus();
    await this.checkProcessStatus();
    this.bindEvents();
    this.startProcessPolling();
  },

  async checkStatus() {
    try {
      const res = await API.getContainerStatus();
      if (res.success && res.data) {
        const d = res.data;
        const btnStart = document.getElementById('tp-btn-start-container');
        const btnAutostart = document.getElementById('tp-btn-write-autostart');
        const consoleEl = document.getElementById('tp-container-console');

        if (btnStart) {
          btnStart.disabled = false;
          btnStart.classList.add('btn-primary');
          btnStart.classList.remove('btn-secondary');
          if (d.running) {
            btnStart.textContent = `🔄 重新固化启动 / 更新 vsis_g1 (当前运行中)`;
            if (consoleEl && (consoleEl.innerHTML.includes('等待') || consoleEl.innerHTML.includes('点击上方按钮启动容器'))) {
              consoleEl.innerHTML = `<div class="log-success">[就绪] 容器 vsis_g1 正在正常运行中。如需更换镜像或重新启动，可直接选择镜像后点击上方启动按钮。</div>`;
            }
          } else {
            btnStart.textContent = `⚡ 固化启动容器 (vsis_g1)`;
          }
        }

        const inputRobotId = document.getElementById('tp-robot-id-select');
        if (inputRobotId && d.robot_id) {
          inputRobotId.value = d.robot_id;
        }

        if (btnAutostart) {
          btnAutostart.disabled = false;
          if (d.autostart_configured) {
            btnAutostart.classList.remove('btn-secondary');
            btnAutostart.classList.add('btn-success');
            btnAutostart.textContent = `⚙️ 重新写入开机自启动与 Robot ID [${d.robot_id}]`;
          } else {
            btnAutostart.classList.remove('btn-secondary');
            btnAutostart.classList.add('btn-success');
            btnAutostart.textContent = `📝 一键写入开机自启动与 Robot ID`;
          }
        }
      }
    } catch (e) {
      console.warn('Check container/autostart status failed:', e);
    }
  },

  bindEvents() {
    // 监听本地文件输入框变动回显
    const localInput = document.getElementById('tp-local-tar-path');
    if (localInput) {
      localInput.addEventListener('input', (e) => {
        const val = e.target.value.trim();
        const label = document.getElementById('tp-image-file-label');
        if (label) {
          label.textContent = val ? `已指定文件: ${val}` : '未选择文件';
        }
      });
    }
  },

  async browseTarFile() {
    try {
      showToast('正在打开文件选择器...', 'info');
      const res = await API.selectFile();
      if (res.success && res.file_path) {
        const localInput = document.getElementById('tp-local-tar-path');
        const remoteInput = document.getElementById('tp-remote-path-input');
        const label = document.getElementById('tp-image-file-label');
        if (localInput) localInput.value = res.file_path;
        if (label) label.textContent = `已选: ${res.filename} (${res.size_gb} GB)`;
        if (remoteInput) {
          const curVal = remoteInput.value.trim();
          const dir = curVal && curVal.includes('/') ? curVal.substring(0, curVal.lastIndexOf('/')) : '/home/ubuntu';
          remoteInput.value = `${dir}/${res.filename}`;
        }
        showToast(`已选择镜像文件: ${res.filename} (${res.size_gb} GB)`, 'success');
      } else if (res.msg && !res.msg.includes('取消')) {
        showToast(res.msg, 'error');
      }
    } catch (err) {
      showToast(`打开文件选择器异常: ${err.message}`, 'error');
    }
  },

  async cancelUpload() {
    try {
      showToast('正在取消上传...', 'warning');
      await API.cancelUpload();
      if (this.uploadInterval) {
        clearInterval(this.uploadInterval);
        this.uploadInterval = null;
      }
      this._resetUploadButtons();
      const consoleEl = document.getElementById('tp-load-console');
      if (consoleEl) consoleEl.innerHTML = '<div class="log-warn">上传已被用户取消。</div>';
      showToast('已取消上传任务', 'info');
    } catch (err) {
      showToast(`取消上传失败: ${err.message}`, 'error');
    }
  },

  _resetUploadButtons() {
    const btnStart = document.getElementById('tp-btn-start-upload');
    const btnCancel = document.getElementById('tp-btn-cancel-upload');
    if (btnStart) {
      btnStart.disabled = false;
      btnStart.style.display = 'block';
    }
    if (btnCancel) {
      btnCancel.style.display = 'none';
    }
  },

  renderRunningContainers(containers, targetElId = 'tp-running-containers-list') {
    const listEl = document.getElementById(targetElId);
    if (!listEl) return;
    if (!containers || containers.length === 0) {
      listEl.innerHTML = '<div style="font-size: 0.8rem; color: var(--text-muted); padding: 4px 0;">⚪ 暂无正在运行中的容器</div>';
      return;
    }
    let html = '<div style="display: flex; flex-direction: column; gap: 6px;">';
    for (const c of containers) {
      const isUp = c.is_running;
      const statusBadge = isUp 
        ? `<span class="container-status-badge running">🟢 运行中</span>`
        : `<span class="container-status-badge stopped">⚪ ${c.status || '已停止'}</span>`;
      
      const isWizard = targetElId.includes('wizard');
      const stopHandler = isWizard ? `Wizard.stopContainer('${c.name}')` : `TabImage.stopContainer('${c.name}')`;

      const stopBtn = isUp 
        ? `<button class="btn btn-danger btn-xs" style="padding: 4px 10px; font-size: 0.75rem; border-radius: 4px; display: inline-flex; align-items: center; gap: 4px; font-weight: 600; cursor: pointer; flex-shrink: 0;" onclick="${stopHandler}" title="停止并关闭该容器">⏹️ 关闭容器</button>`
        : '';

      const portInfo = c.ports ? `<div style="font-size: 0.72rem; color: var(--text-muted); font-family: monospace; word-break: break-all; margin-top: 2px;">端口: ${c.ports}</div>` : '';
      html += `
        <div style="display: flex; align-items: center; justify-content: space-between; padding: 7px 10px; background: rgba(0, 0, 0, 0.25); border-radius: 6px; border: 1px solid rgba(255, 255, 255, 0.05); gap: 12px;">
          <div style="min-width: 0; flex: 1;">
            <div style="font-weight: 700; font-size: 0.85rem; color: #ffffff; display: flex; align-items: center; gap: 8px; flex-wrap: wrap;">
              <span>📦 ${c.name}</span>
              <span style="font-size: 0.75rem; color: var(--accent-cyan); font-family: monospace; font-weight: normal; word-break: break-all;">[${c.image}]</span>
            </div>
            ${portInfo}
          </div>
          <div style="flex-shrink: 0; display: flex; align-items: center; gap: 8px; white-space: nowrap;">
            ${statusBadge}
            ${stopBtn}
          </div>
        </div>
      `;
    }
    html += '</div>';
    listEl.innerHTML = html;
  },

  async loadImages() {
    const select = document.getElementById('tp-docker-image-select');
    try {
      const res = await API.listImages();
      
      // 1. 渲染当前宿主机已运行容器列表
      if (res && res.running_containers) {
        this.renderRunningContainers(res.running_containers, 'tp-running-containers-list');
      }

      if (!select) return;

      select.innerHTML = '';
      const availableImgs = res.available_images || res.images || [];
      if (availableImgs.length === 0) {
        select.innerHTML = '<option value="">(所有可用镜像均已在容器中运行)</option>';
        return;
      }

      for (const img of availableImgs) {
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
    const localInput = document.getElementById('tp-local-tar-path');
    const remoteInput = document.getElementById('tp-remote-path-input');
    const localPath = localInput ? localInput.value.trim() : '';
    const remotePath = remoteInput ? remoteInput.value.trim() : '';

    if (!localPath) {
      showToast('请点击【📁 浏览本地镜像文件】选取镜像，或输入本机文件完整绝对路径', 'warning');
      return;
    }

    const reqData = { local_path: localPath, remote_path: remotePath };

    showToast('正在检查远端镜像并准备传输...', 'info');
    const progressBox = document.getElementById('tp-upload-progress-box');
    const consoleEl = document.getElementById('tp-load-console');
    const btnStart = document.getElementById('tp-btn-start-upload');
    const btnCancel = document.getElementById('tp-btn-cancel-upload');

    if (progressBox) progressBox.style.display = 'block';
    if (consoleEl) consoleEl.innerHTML = '<div class="log-info">正在校验远端镜像状态...</div>';
    if (btnStart) btnStart.disabled = true;
    if (btnCancel) btnCancel.style.display = 'block';

    try {
      const res = await API.uploadImage(reqData);
      if (!res.success) {
        showToast(`上传失败: ${res.msg}`, 'error');
        if (consoleEl) consoleEl.innerHTML = `<div class="log-error">上传失败: ${res.msg}</div>`;
        this._resetUploadButtons();
        return;
      }
      if (remoteInput && res.remote_path) remoteInput.value = res.remote_path;

      if (res.skipped) {
        // 远端已存在完全一致的镜像文件，直接跳过并自动执行安装！
        this._resetUploadButtons();
        this._updateProgress({ percent: 100, transferred_bytes: 1, total_bytes: 1, speed_mbps: 0, eta_seconds: 0 });
        showToast('远端已存在同名同大小镜像包，正在自动执行 Docker 镜像安装...', 'success');
        if (consoleEl) consoleEl.innerHTML = `<div class="log-success">✅ 检测到远端已存在完全一致的镜像文件 (${res.remote_path})，无需重复上传，立即自动安装镜像！</div>`;
        setTimeout(() => this.dockerLoad(), 500);
        return;
      }

      if (this.uploadInterval) clearInterval(this.uploadInterval);
      this.uploadInterval = setInterval(async () => {
        const prog = await API.getUploadProgress();
        this._updateProgress(prog);
        if (prog.status === 'completed') {
          clearInterval(this.uploadInterval);
          this.uploadInterval = null;
          this._resetUploadButtons();
          showToast('镜像上传成功！正在自动执行 Docker 镜像安装...', 'success');
          if (consoleEl) consoleEl.innerHTML = `<div class="log-success">✅ 文件上传成功 (${res.remote_path})，立即自动执行 docker load 安装镜像...</div>`;
          setTimeout(() => this.dockerLoad(), 600);
        } else if (prog.status === 'error' || prog.status === 'canceled') {
          clearInterval(this.uploadInterval);
          this.uploadInterval = null;
          this._resetUploadButtons();
          showToast(`上传异常: ${prog.error_msg}`, 'error');
          if (consoleEl) consoleEl.innerHTML = `<div class="log-error">传输已终止: ${prog.error_msg}</div>`;
        }
      }, 500);
    } catch (err) {
      this._resetUploadButtons();
      showToast(`上传请求异常: ${err.message}`, 'error');
      if (consoleEl) consoleEl.innerHTML = `<div class="log-error">请求异常: ${err.message}</div>`;
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
    const remotePath = pathInput ? pathInput.value.trim() : '/home/ubuntu/vsis_dancer_cpu_1.0.tar.gz';
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
            if (consoleEl) {
              const banner = document.createElement('div');
              banner.className = 'upload-success-badge';
              banner.style.cssText = 'margin-top: 10px; padding: 10px 14px; background: rgba(16, 185, 129, 0.18); border: 1px solid #10b981; border-radius: 6px; color: #10b981; font-weight: 700; font-size: 0.9rem; display: flex; align-items: center; gap: 8px; box-shadow: 0 0 12px rgba(16, 185, 129, 0.2);';
              banner.innerHTML = '<span>✅</span> <span>Docker 镜像导入成功！请在右侧选择镜像并点击【固化启动容器】。</span>';
              consoleEl.appendChild(banner);
              consoleEl.scrollTop = consoleEl.scrollHeight;
            }
            showToast('✅ Docker 镜像导入成功！', 'success');
            await this.loadImages();
          } else {
            showToast('❌ 镜像导入异常，请查看上方终端输出', 'error');
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
            showToast('✓ 容器 vsis_g1 已固化启动，开机自启动钩子已就绪！', 'success');
            await this.loadImages();
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
    const inputEl = document.getElementById('tp-robot-id-select');
    const rawValue = inputEl ? inputEl.value.trim() : '';
    const robotId = rawValue.toUpperCase();

    // 校验规则（与群控控制台“添加机器人”一致）
    if (!robotId) {
      showToast('Robot ID 不能为空！请输入如 A、B、R1 等唯一标识。', 'error');
      if (inputEl) inputEl.focus();
      return;
    }
    if (robotId === 'ALL') {
      showToast('ALL 为广播保留关键字，不能作为单机 ID！', 'error');
      if (inputEl) inputEl.focus();
      return;
    }

    if (inputEl) inputEl.value = robotId; // 写回大写
    showToast(`正在配置开机自启并写入 Robot ID [${robotId}] ...`, 'info');
    try {
      const res = await API.configAutostart(robotId);
      showToast(res.success ? res.msg : `写入失败: ${res.msg}`, res.success ? 'success' : 'error');
    } catch (err) {
      showToast(`写入失败: ${err.message}`, 'error');
    }
  },

  async stopContainer(containerName) {
    if (!containerName) return;
    if (!confirm(`确定要关闭/停止正在运行的容器 [${containerName}] 吗？\n停止后该容器内的运控程序将退出，且该镜像将重新在待启动镜像列表中可选。`)) {
      return;
    }
    showToast(`正在关闭容器 [${containerName}] ...`, 'info');
    try {
      const res = await API.stopContainer(containerName);
      if (res.success) {
        showToast(`✅ ${res.msg}`, 'success');
        await this.loadImages();
      } else {
        showToast(`关闭失败: ${res.msg}`, 'error');
      }
    } catch (err) {
      showToast(`关闭容器异常: ${err.message}`, 'error');
    }
  },

  startProcessPolling() {
    if (this.processPollInterval) clearInterval(this.processPollInterval);
    this.processPollInterval = setInterval(() => {
      const panel = document.getElementById('tab-image');
      if (panel && panel.classList.contains('active')) {
        this.checkProcessStatus();
      }
    }, 4000);
  },

  async checkProcessStatus() {
    const badgeEl = document.getElementById('tp-robot-process-badge');
    const dotEl = document.getElementById('tp-process-dot');
    const textEl = document.getElementById('tp-process-status-text');
    const ctrlSub = document.getElementById('tp-ctrl-sub-badge');
    const loraSub = document.getElementById('tp-lora-sub-badge');

    if (!badgeEl || !textEl || !dotEl) return;

    try {
      const res = await API.getRobotProcessStatus();
      if (!res.connected) {
        dotEl.style.background = '#94a3b8';
        dotEl.className = 'pulse-dot';
        textEl.textContent = '机器人未连接';
        badgeEl.style.borderColor = 'rgba(255,255,255,0.1)';
        badgeEl.style.background = 'rgba(255,255,255,0.05)';
        if (ctrlSub) { ctrlSub.className = 'container-status-badge stopped'; ctrlSub.textContent = '未连接'; }
        if (loraSub) { loraSub.className = 'container-status-badge stopped'; loraSub.textContent = '未连接'; }
        return;
      }

      if (ctrlSub) {
        ctrlSub.className = res.g1_ctrl_running ? 'container-status-badge running' : 'container-status-badge stopped';
        ctrlSub.textContent = res.g1_ctrl_running ? '🟢 运行中' : '⚪ 未运行';
      }
      if (loraSub) {
        loraSub.className = res.lora_recv_running ? 'container-status-badge running' : 'container-status-badge stopped';
        loraSub.textContent = res.lora_recv_running ? '🟢 运行中' : '⚪ 未运行';
      }

      if (res.all_running) {
        dotEl.style.background = '#34d399';
        dotEl.className = 'pulse-dot active';
        textEl.textContent = '运控与LoRa运行中';
        badgeEl.style.borderColor = 'rgba(52, 211, 153, 0.4)';
        badgeEl.style.background = 'rgba(16, 185, 129, 0.12)';
      } else if (res.g1_ctrl_running && !res.lora_recv_running) {
        dotEl.style.background = '#fbbf24';
        dotEl.className = 'pulse-dot active';
        textEl.textContent = '运控运行中 (LoRa未就绪)';
        badgeEl.style.borderColor = 'rgba(251, 191, 36, 0.4)';
        badgeEl.style.background = 'rgba(245, 158, 11, 0.12)';
      } else if (!res.g1_ctrl_running && res.lora_recv_running) {
        dotEl.style.background = '#fbbf24';
        dotEl.className = 'pulse-dot active';
        textEl.textContent = 'LoRa已就绪 (运控未运行)';
        badgeEl.style.borderColor = 'rgba(251, 191, 36, 0.4)';
        badgeEl.style.background = 'rgba(245, 158, 11, 0.12)';
      } else {
        dotEl.style.background = '#f87171';
        dotEl.className = 'pulse-dot';
        textEl.textContent = '运控未运行 (离线)';
        badgeEl.style.borderColor = 'rgba(239, 68, 68, 0.3)';
        badgeEl.style.background = 'rgba(239, 68, 68, 0.08)';
      }
    } catch (_) {}
  },

  async startRobotProcesses() {
    const consoleEl = document.getElementById('tp-process-console');
    const btnStart = document.getElementById('tp-btn-start-process');
    if (consoleEl) consoleEl.innerHTML = '<div class="log-info">正在远程拉起机器人机载程序 (run_bg.sh)...</div>';
    if (btnStart) btnStart.disabled = true;

    showToast('正在启动机载程序 (run_bg.sh)...', 'info');

    try {
      const res = await API.startRobotProcesses();
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
          if (btnStart) btnStart.disabled = false;
          if (ok) {
            showToast('🚀 机载程序启动指令已发送', 'success');
            if (consoleEl) {
              const div = document.createElement('div');
              div.className = 'log-success';
              div.textContent = '✅ 机载程序 (run_bg.sh) 启动完成，正在后台运行。';
              consoleEl.appendChild(div);
              consoleEl.scrollTop = consoleEl.scrollHeight;
            }
          } else {
            showToast('机载程序启动遇到异常，请检查上方日志', 'error');
          }
          await this.checkProcessStatus();
        });
      } else {
        if (btnStart) btnStart.disabled = false;
        showToast(`启动失败: ${res.msg || '未知错误'}`, 'error');
        if (consoleEl) consoleEl.innerHTML = `<div class="log-error">启动失败: ${res.msg || '未知错误'}</div>`;
      }
    } catch (err) {
      if (btnStart) btnStart.disabled = false;
      showToast(`请求异常: ${err.message}`, 'error');
      if (consoleEl) consoleEl.innerHTML = `<div class="log-error">请求异常: ${err.message}</div>`;
    }
  },

  async stopRobotProcesses() {
    if (!confirm('确定要停止机器人机载跳舞运控与 LoRa 接收进程 (pkill) 吗？')) return;
    const consoleEl = document.getElementById('tp-process-console');
    if (consoleEl) consoleEl.innerHTML = '<div class="log-info">正在发送停止机载进程指令 (pkill -f g1_ctrl_vsis ; pkill -f lora_recv_group)...</div>';

    showToast('正在停止机载进程...', 'info');

    try {
      const res = await API.stopRobotProcesses();
      if (res.success) {
        showToast('⏹️ 机载进程已停止', 'info');
        if (consoleEl) {
          const div = document.createElement('div');
          div.className = 'log-warn';
          div.textContent = '⏹️ 已向机器人发送停止指令！';
          consoleEl.appendChild(div);
          consoleEl.scrollTop = consoleEl.scrollHeight;
        }
        setTimeout(() => this.checkProcessStatus(), 1200);
      } else {
        showToast(`停止失败: ${res.msg || '未知错误'}`, 'error');
        if (consoleEl) consoleEl.innerHTML = `<div class="log-error">停止失败: ${res.msg || '未知错误'}</div>`;
      }
    } catch (err) {
      showToast(`请求异常: ${err.message}`, 'error');
      if (consoleEl) consoleEl.innerHTML = `<div class="log-error">请求异常: ${err.message}</div>`;
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
      dropzone.addEventListener('click', (e) => {
        if (e.target !== fileInput) {
          fileInput.click();
        }
      });

      ['dragenter', 'dragover'].forEach(eventName => {
        dropzone.addEventListener(eventName, (e) => {
          e.preventDefault();
          e.stopPropagation();
          dropzone.classList.add('dragover');
          if (e.dataTransfer) e.dataTransfer.dropEffect = 'copy';
        });
      });

      ['dragleave', 'dragend'].forEach(eventName => {
        dropzone.addEventListener(eventName, (e) => {
          e.preventDefault();
          e.stopPropagation();
          dropzone.classList.remove('dragover');
        });
      });

      dropzone.addEventListener('drop', (e) => {
        e.preventDefault();
        e.stopPropagation();
        dropzone.classList.remove('dragover');
        const files = e.dataTransfer ? e.dataTransfer.files : null;
        if (files && files.length > 0) {
          this.handleFile(files[0]);
        }
      });

      fileInput.addEventListener('change', (e) => {
        if (e.target.files && e.target.files.length > 0) {
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

  handleFileInput(input) {
    if (input && input.files && input.files.length > 0) {
      this.handleFile(input.files[0]);
    }
  },

  handleDrop(e) {
    e.preventDefault();
    e.stopPropagation();
    const dropzone = document.getElementById('tp-license-dropzone');
    if (dropzone) dropzone.classList.remove('dragover');
    const dt = e.dataTransfer;
    if (dt && dt.files && dt.files.length > 0) {
      this.handleFile(dt.files[0]);
    }
  },

  async handleFile(file) {
    if (!file) return;
    const reader = new FileReader();
    reader.onload = async (e) => {
      this.licenseContent = e.target.result;
      const deployBtn = document.getElementById('tp-deploy-btn');
      const nameEl = document.getElementById('tp-license-filename');
      if (nameEl) nameEl.textContent = `已选择: ${file.name}`;
      if (deployBtn) deployBtn.disabled = false;

      // 自动解析 License 并展示信息
      try {
        const res = await API.verifyLicense(this.licenseContent, this.machineId);
        if (res.success && res.parsed) {
          const p = res.parsed;
          let dancesHtml = (p.dances || []).map(d => `<span class="card-badge" style="margin: 2px;">${d}</span>`).join(' ');
          this._showResult(`
            <div style="background: rgba(56, 189, 248, 0.1); border: 1px solid rgba(56, 189, 248, 0.3); padding: 12px; border-radius: 6px; color: #38bdf8; font-weight: 600; margin-bottom: 12px;">
              📄 License 文件已加载，点击下方【部署 License 至机器人】开始写入并重启校验。
            </div>
            <div class="card" style="padding: 14px;">
              <div style="font-size: 0.85rem; margin-bottom: 6px; user-select: text;"><b>授权客户:</b> ${p.customer || '商业客户'} | <b>适用机型:</b> ${p.model || 'Unitree G1'}</div>
              <div style="font-size: 0.85rem; margin-bottom: 6px; user-select: text;"><b>有效期至:</b> <span style="color: var(--accent-cyan); font-weight: 600;">${p.expire_date || '永久授权'}</span></div>
              ${p.dance_count > 0 ? `<div style="font-size: 0.85rem; margin-bottom: 8px; user-select: text;"><b>包含舞蹈清单 (${p.dance_count} 支):</b></div>
              <div style="display: flex; flex-wrap: wrap; gap: 4px; max-height: 120px; overflow-y: auto; user-select: text;">${dancesHtml}</div>` : ''}
            </div>
          `);
        } else {
          this._showResult(`<div style="color: var(--accent-cyan); padding: 12px; background: rgba(56,189,248,0.08); border-radius: 8px; border: 1px solid rgba(56,189,248,0.3);">
            📄 <b>${file.name}</b> 已就绪，点击【部署 License 至机器人】写入并重启校验。
          </div>`);
        }
      } catch (_) {
        this._showResult(`<div style="color: var(--accent-cyan); padding: 12px; background: rgba(56,189,248,0.08); border-radius: 8px; border: 1px solid rgba(56,189,248,0.3);">
          📄 <b>${file.name}</b> 已就绪，点击【部署 License 至机器人】写入并重启校验。
        </div>`);
      }

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

// 暴露到全局 window
window.TabNetwork = TabNetwork;
window.TabPrecheck = TabPrecheck;
window.TabImage = TabImage;
window.TabManual = TabManual;
window.TabTutorials = TabTutorials;
window.TabDanceUpdate = TabDanceUpdate;
window.TabLicense = TabLicense;

// ===========================================
// DOM就绪时全局初始化
// ===========================================
document.addEventListener('DOMContentLoaded', () => {
  TabLicense.init();

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
