/**
 * 一键部署向导全流程状态机与交互控制器
 */
const Wizard = {
  currentStep: 1,
  totalSteps: 6,
  detectedMachineId: '',
  uploadInterval: null,

  init() {
    this.bindEvents();
    this.renderStep();
  },

  bindEvents() {
    // 模态弹窗唤起与关闭
    const btnOpenWizard = document.getElementById('btn-open-wizard');
    if (btnOpenWizard) {
      btnOpenWizard.addEventListener('click', () => this.openModal(1));
    }

    const btnCloseWizard = document.getElementById('btn-close-wizard');
    if (btnCloseWizard) {
      btnCloseWizard.addEventListener('click', () => this.closeModal());
    }

    // 点击遮罩外部关闭
    const modalOverlay = document.getElementById('wizard-modal');
    if (modalOverlay) {
      modalOverlay.addEventListener('click', (e) => {
        if (e.target === modalOverlay) {
          this.closeModal();
        }
      });
    }

    // ESC 键退出向导
    document.addEventListener('keydown', (e) => {
      if (e.key === 'Escape') {
        this.closeModal();
      }
    });

    // 步骤节点点击
    document.querySelectorAll('.step-node').forEach(node => {
      node.addEventListener('click', () => {
        const step = parseInt(node.dataset.step);
        this.goToStep(step, false);
      });
    });

    // 直连网卡刷新与配置
    const btnRefreshNics = document.getElementById('btn-refresh-nics');
    if (btnRefreshNics) {
      btnRefreshNics.addEventListener('click', () => this.refreshInterfaces());
    }

    const btnConfigNic = document.getElementById('btn-config-nic-static');
    if (btnConfigNic) {
      btnConfigNic.addEventListener('click', () => this.configNicStatic());
    }

    const btnRestoreDhcp = document.getElementById('btn-config-nic-dhcp');
    if (btnRestoreDhcp) {
      btnRestoreDhcp.addEventListener('click', () => this.restoreNicDhcp());
    }

    // 扫描网络
    const btnScan = document.getElementById('btn-scan-network');
    if (btnScan) {
      btnScan.addEventListener('click', () => this.runNetworkScan());
    }

    // 重新预检
    const btnRecheck = document.getElementById('btn-run-precheck');
    if (btnRecheck) {
      btnRecheck.addEventListener('click', () => this.runPrecheck());
    }

    // 监听本地镜像文件路径输入变动回显
    const pathInput = document.getElementById('input-local-tar-path');
    if (pathInput) {
      pathInput.addEventListener('input', (e) => {
        const val = e.target.value.trim();
        const nameEl = document.getElementById('image-selected-name');
        if (nameEl) {
          nameEl.textContent = val ? `已指定文件: ${val}` : '';
        }
      });
    }

    // 启动上传
    const btnStartUpload = document.getElementById('btn-start-upload');
    if (btnStartUpload) {
      btnStartUpload.addEventListener('click', () => this.startImageUpload());
    }

    // 加载镜像
    const btnLoadImage = document.getElementById('btn-docker-load');
    if (btnLoadImage) {
      btnLoadImage.addEventListener('click', () => this.startDockerLoad());
    }

    // 固化启动容器
    const btnStartContainer = document.getElementById('btn-start-container');
    if (btnStartContainer) {
      btnStartContainer.addEventListener('click', () => this.startContainer());
    }

    // 写入自启动与 ID
    const btnWriteAutostart = document.getElementById('btn-write-autostart');
    if (btnWriteAutostart) {
      btnWriteAutostart.addEventListener('click', () => this.writeAutostartAndId());
    }

    // 读取机器码
    const btnReadMid = document.getElementById('btn-read-machine-id');
    if (btnReadMid) {
      btnReadMid.addEventListener('click', () => this.fetchMachineId());
    }

    // License 拖拽上传区
    const licDropzone = document.getElementById('license-dropzone');
    const licFileInput = document.getElementById('license-file-input');
    if (licDropzone && licFileInput) {
      licDropzone.addEventListener('click', (e) => {
        if (e.target !== licFileInput) {
          licFileInput.click();
        }
      });

      ['dragenter', 'dragover'].forEach(eventName => {
        licDropzone.addEventListener(eventName, (e) => {
          e.preventDefault();
          e.stopPropagation();
          licDropzone.classList.add('dragover');
          if (e.dataTransfer) e.dataTransfer.dropEffect = 'copy';
        });
      });

      ['dragleave', 'dragend'].forEach(eventName => {
        licDropzone.addEventListener(eventName, (e) => {
          e.preventDefault();
          e.stopPropagation();
          licDropzone.classList.remove('dragover');
        });
      });

      licDropzone.addEventListener('drop', (e) => {
        e.preventDefault();
        e.stopPropagation();
        licDropzone.classList.remove('dragover');
        const files = e.dataTransfer ? e.dataTransfer.files : null;
        if (files && files.length > 0) {
          this.handleLicenseFile(files[0]);
        }
      });

      licFileInput.addEventListener('change', (e) => {
        if (e.target.files && e.target.files.length > 0) {
          this.handleLicenseFile(e.target.files[0]);
        }
      });
    }

    // 部署 License
    const btnDeployLic = document.getElementById('btn-deploy-license');
    if (btnDeployLic) {
      btnDeployLic.addEventListener('click', () => this.deployLicense());
    }
  },

  goToStep(step, autoTrigger = true) {
    if (step < 1 || step > this.totalSteps) return;
    this.currentStep = step;
    this.renderStep(autoTrigger);
  },

  nextStep() {
    this.goToStep(this.currentStep + 1, true);
  },

  prevStep() {
    this.goToStep(this.currentStep - 1, false);
  },

  renderStep(autoTrigger = true) {
    // 更新步骤节点样式
    document.querySelectorAll('.step-node').forEach(node => {
      const s = parseInt(node.dataset.step);
      node.classList.remove('active', 'completed');
      if (s === this.currentStep) {
        node.classList.add('active');
      } else if (s < this.currentStep) {
        node.classList.add('completed');
      }
    });

    // 显示对应的卡片
    document.querySelectorAll('.wizard-step-pane').forEach(pane => {
      pane.style.display = 'none';
    });
    const curPane = document.getElementById(`wizard-step-${this.currentStep}`);
    if (curPane) curPane.style.display = 'block';

    // 步骤初始化与自动化流转触发动作
    if (this.currentStep === 1) {
      this.refreshInterfaces();
      this.loadWindowsCh341();
      if (autoTrigger) this.autoCheckStep1();
    } else if (this.currentStep === 2) {
      this.runPrecheck(autoTrigger);
    } else if (this.currentStep === 3) {
      this.autoCheckStep3(autoTrigger);
    } else if (this.currentStep === 4) {
      this.refreshImagesList();
      this.updateStep4ButtonStatus();
      this.checkProcessStatus();
      if (autoTrigger) this.autoCheckStep4(autoTrigger);
    } else if (this.currentStep === 5) {
      this.fetchMachineId();
    }
  },

  async updateStep4ButtonStatus() {
    try {
      const res = await API.getContainerStatus();
      if (res.success && res.data) {
        const d = res.data;
        const btnStart = document.getElementById('btn-start-container');
        const btnAuto = document.getElementById('btn-write-autostart');
        const consoleEl = document.getElementById('container-start-console');

        if (btnStart) {
          btnStart.disabled = false;
          btnStart.classList.add('btn-primary');
          btnStart.classList.remove('btn-secondary');
          if (d.running) {
            btnStart.textContent = `🔄 重新固化启动 / 更新 vsis_g1 容器 (当前运行中)`;
            if (consoleEl && (consoleEl.innerHTML.includes('等待执行') || consoleEl.innerHTML.includes('正在执行固化容器启动命令'))) {
              consoleEl.innerHTML = `<div class="log-success">[就绪] 容器 vsis_g1 正在正常运行中。如需更换镜像或重新启动，可选择上方镜像后点击此按钮。</div>`;
            }
          } else {
            btnStart.textContent = `⚡ 固化启动容器 vsis_g1`;
          }
        }

        const inputRobotId = document.getElementById('select-robot-id');
        if (inputRobotId && d.robot_id) {
          inputRobotId.value = d.robot_id;
        }

        this.isIdConfigured = !!d.autostart_configured;
        this.updateWriteIdButtonText();
      }
    } catch (e) {
      console.warn(e);
    }
  },

  setRobotId(id) {
    const inputEl = document.getElementById('select-robot-id');
    if (inputEl) {
      inputEl.value = id;
    }
    this.updateWriteIdButtonText();
  },

  updateWriteIdButtonText() {
    const inputEl = document.getElementById('select-robot-id');
    const val = inputEl ? inputEl.value.trim().toUpperCase() : '';
    const btn = document.getElementById('btn-write-autostart');
    if (!btn) return;
    const idLabel = val ? ` [${val}]` : '';
    btn.disabled = false;
    btn.classList.remove('btn-secondary');
    btn.classList.add('btn-success');
    if (this.isIdConfigured) {
      btn.textContent = `⚙️ 重新写入 ID${idLabel}`;
    } else {
      btn.textContent = `💾 写入 ID${idLabel}`;
    }
  },

  async autoCheckStep1() {
    try {
      const status = await API.getStatus();
      if (status && status.connected) {
        showToast('✓ 机器人已连接 (192.168.123.164:22)，自动进入环境预检...', 'success', 2000);
        setTimeout(() => this.goToStep(2, true), 800);
        return;
      }

      // 启动断网自愈与自动探测连接
      const res = await API.autoConnect(true);
      if (res && res.connected) {
        showToast(res.msg || '✓ 成功自动连接机器人，自动进入环境预检...', 'success', 2500);
        App.updateStatus();
        setTimeout(() => this.goToStep(2, true), 800);
      }
    } catch (err) {
      console.warn('Step 1 auto check failed:', err);
    }
  },

  async autoCheckStep3() {
    const hintEl = document.getElementById('wizard-step3-image-hint');
    try {
      const res = await API.listImages();
      const allImgs = res.all_images || res.available_images || res.images || [];
      
      // 仅判断 vsis_dancer 名称类似的镜像是否存在，不考虑其它镜像
      const vsisImg = allImgs.find(img => {
        const repo = (img.repository || '').toLowerCase();
        const tag = (img.tag || '').toLowerCase();
        const full = `${repo}:${tag}`;
        return full.includes('vsis_dancer') || (full.includes('vsis') && full.includes('dancer'));
      });

      if (vsisImg) {
        const tag = `${vsisImg.repository}:${vsisImg.tag}`;
        if (hintEl) {
          hintEl.style.display = 'block';
          hintEl.innerHTML = `
            <div style="background: rgba(16, 185, 129, 0.12); border: 1px solid rgba(16, 185, 129, 0.35); border-radius: 6px; padding: 6px 12px; margin-bottom: 8px; display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 8px;">
              <div>
                <span style="font-weight: 700; color: #34d399; font-size: 0.82rem;">✅ 宿主机已检测到运控跳舞镜像 (vsis_dancer)：</span>
                <span style="font-size: 0.78rem; color: #a7f3d0;"><b style="font-family: monospace;">${tag}</b> (${vsisImg.size || ''})，可直接点击下一步继续。</span>
              </div>
              <button class="btn btn-success btn-xs" onclick="Wizard.nextStep()" style="white-space: nowrap; font-weight: 700; padding: 3px 10px;">
                👉 下一步：固化启动容器 ➔
              </button>
            </div>
          `;
        }
      } else {
        if (hintEl) {
          hintEl.style.display = 'block';
          hintEl.innerHTML = `
            <div style="background: rgba(56, 189, 248, 0.08); border: 1px solid rgba(56, 189, 248, 0.25); border-radius: 6px; padding: 6px 12px; margin-bottom: 8px; font-size: 0.78rem; color: var(--text-secondary); display: flex; align-items: center; gap: 6px;">
              <span>ℹ️ 机器人宿主机尚未检测到运控/舞蹈镜像 (vsis_dancer)，请在下方选择本地 <code>.tar / .tar.gz</code> 文件并执行上传与导入。</span>
            </div>
          `;
        }
      }
    } catch (err) {
      console.warn('Step 3 auto check failed:', err);
    }
  },

  async autoCheckStep4(autoAdvance = false) {
    try {
      await this.updateStep4ButtonStatus();
      await this.checkProcessStatus();
      const res = await API.getContainerStatus();
      if (res.success && res.data) {
        const d = res.data;
        if (d.running && d.autostart_configured) {
          if (autoAdvance) {
            showToast(`✓ 检测到 vsis_g1 运行中且自启已配置，自动进入授权校验...`, 'success', 2000);
            setTimeout(() => this.goToStep(5, true), 1000);
          }
        }
      }
    } catch (err) {
      console.warn('Step 4 auto check failed:', err);
    }
  },

  // ==========================
  // 自动化智能判定与跳步引擎
  // ==========================
  async autoDetectAndConnect() {
    showToast('⚡ 正在自愈直连网卡并并发探测连接机器人 (192.168.123.x)...', 'info', 3000);
    const btn = document.getElementById('btn-wizard-auto-connect');
    if (btn) {
      btn.disabled = true;
      btn.textContent = '⏳ 探测连接中...';
    }
    try {
      const res = await API.autoConnect(true);
      if (res.connected) {
        showToast(res.msg, 'success', 3500);
        App.updateStatus();
        setTimeout(() => this.goToStep(2, true), 800);
      } else {
        showToast(res.msg || '未探测到在线机器人', 'warning', 3500);
      }
    } catch (err) {
      showToast(`自愈连接异常: ${err.message}`, 'error');
    } finally {
      if (btn) {
        btn.disabled = false;
        btn.textContent = '⚡ 立即执行自愈连接';
      }
    }
  },

  // ==========================
  // Step 1: 网络与网卡
  // ==========================
  async refreshInterfaces() {
    try {
      const res = await API.getInterfaces();
      const select = document.getElementById('select-nic-list');
      if (!select) return;

      select.innerHTML = '';
      if (!res.interfaces || res.interfaces.length === 0) {
        select.innerHTML = '<option value="">未找到可用网卡</option>';
        return;
      }

      for (const nic of res.interfaces) {
        if (nic.is_loopback) continue;
        const opt = document.createElement('option');
        opt.value = nic.name;
        opt.textContent = `${nic.name} (${nic.ip || '未分配IP'} / ${nic.is_up ? '已连接' : '未连接'})`;
        if (nic.is_unitree_subnet) opt.selected = true;
        select.appendChild(opt);
      }
    } catch (err) {
      console.error('获取网卡列表失败:', err);
    }
  },

  async configNicStatic() {
    const select = document.getElementById('select-nic-list');
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
        this.refreshInterfaces();
      } else {
        showToast(`配置失败: ${res.msg}`, 'error');
      }
    } catch (err) {
      showToast(`网卡配置异常: ${err.message}`, 'error');
    }
  },

  async restoreNicDhcp() {
    const select = document.getElementById('select-nic-list');
    const nicName = select ? select.value : '';
    if (!nicName) return;

    showToast(`正在将网卡 [${nicName}] 恢复为 DHCP ...`, 'info');
    try {
      const res = await API.restoreDhcp(nicName);
      if (res.success) {
        showToast(res.msg, 'success');
        this.refreshInterfaces();
      } else {
        showToast(res.msg, 'error');
      }
    } catch (err) {
      showToast(`恢复异常: ${err.message}`, 'error');
    }
  },

  async runNetworkScan() {
    const btn = document.getElementById('btn-scan-network');
    const listEl = document.getElementById('scan-results-list');
    if (btn) btn.disabled = true;
    if (listEl) listEl.innerHTML = '<div style="padding: 12px; color: var(--accent-cyan);">🔍 正在扫描局域网 (192.168.123.1~254) ...</div>';

    try {
      const res = await API.scanNetwork('192.168.123.');
      if (btn) btn.disabled = false;
      if (!res.devices || res.devices.length === 0) {
        listEl.innerHTML = `
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
            <button class="btn btn-primary btn-sm" onclick="Wizard.selectScannedDevice('${dev.ip}', ${dev.port})">🔗 连接此设备</button>
          </div>
        `;
      }
      listEl.innerHTML = html;
    } catch (err) {
      if (btn) btn.disabled = false;
      if (listEl) listEl.innerHTML = `<div style="padding: 12px; color: var(--accent-red);">扫描失败: ${err.message}</div>`;
    }
  },

  selectScannedDevice(ip, port) {
    document.getElementById('input-host').value = ip;
    document.getElementById('input-port').value = port;
    App.connect();
  },

  async loadWindowsCh341() {
    const statusEl = document.getElementById('wizard-win-ch341-status');
    if (statusEl) statusEl.innerHTML = '<span style="color: var(--text-muted);">正在检测 Windows 本机串口状态...</span>';
    try {
      const res = await API.checkWindowsCh341();
      if (statusEl) {
        if (res.driver_installed) {
          statusEl.innerHTML = `<span style="color: #34d399; font-weight: 600;">✓ 本机驱动已就绪</span> | 端口: <span style="font-family: monospace; color: var(--accent-cyan);">${res.ports_found && res.ports_found.length > 0 ? res.ports_found.join(', ') : '未插设备'}</span>`;
        } else {
          statusEl.innerHTML = `<span style="color: #f87171; font-weight: 600;">❌ 未检测到驱动</span> | <span style="color: var(--text-secondary);">${res.msg || '若插有 LoRa 发射器，请点击右侧按钮安装'}</span>`;
        }
      }
    } catch (e) {
      if (statusEl) statusEl.innerHTML = `<span style="color: #f87171;">检测异常: ${e.message}</span>`;
    }
  },

  // ==========================
  // Step 2: 环境预检与修复
  // ==========================
  async runPrecheck(autoAdvance = true) {
    const container = document.getElementById('precheck-items-list');
    if (!container) return;

    container.innerHTML = '<div style="padding: 20px; color: var(--accent-cyan);">⏳ 正在执行环境预检，请稍候...</div>';

    try {
      const res = await API.getPrecheck();
      if (!res.success || !res.data) {
        container.innerHTML = `<div style="padding: 20px; color: var(--accent-red);">预检失败: ${res.msg}</div>`;
        return;
      }

      const items = res.data.items;
      let html = '';
      for (const key in items) {
        const item = items[key];
        let statusIcon = '✅';
        if (item.status === 'error') {
          statusIcon = '❌';
        } else if (item.status === 'warning') {
          statusIcon = '⚠️';
        }

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
                ${item.can_fix ? `<button class="btn btn-primary btn-sm" onclick="Wizard.runFixItem('${key}')">🛠️ 一键修复</button>` : ''}
              </div>
            </div>
            <div style="font-size: 0.85rem; color: #ffffff; font-family: monospace; margin-bottom: 4px; user-select: text;">${item.version}</div>
            <div style="font-size: 0.8rem; color: var(--text-secondary); user-select: text;">${item.msg}</div>
          </div>
        `;
      }
      container.innerHTML = html;

      // 智能判定：如果全部指标通过且为自动化模式，自动流转至第3步（若已有舞蹈镜像则自动进第4步）
      if (res.data.all_passed) {
        if (autoAdvance) {
          showToast('✓ 运行环境预检全部通过，进入第 3 步镜像检测...', 'success', 2000);
          setTimeout(() => this.goToStep(3, true), 1000);
        }
      } else {
        showToast('⚠️ 检测到部分环境指标异常，请使用【一键修复】按钮解决', 'warning', 4000);
      }
    } catch (err) {
      container.innerHTML = `<div style="padding: 20px; color: var(--accent-red);">预检异常: ${err.message}</div>`;
    }
  },

  async installWindowsCh341() {
    try {
      showToast('正在启动 Windows 本机 CH341 驱动安装程序...', 'info');
      const res = await API.installWindowsCh341();
      if (res.success) {
        showToast(res.msg || 'Windows CH341 驱动安装程序已启动，请在弹出的窗口中点击【安装】。', 'success', 5000);
      } else {
        showToast(`启动驱动安装程序失败: ${res.msg}`, 'error', 4000);
      }
    } catch (err) {
      showToast(`安装驱动异常: ${err.message}`, 'error');
    }
  },

  async runFixItem(key) {
    if (key === 'serial_ch341') {
      this.runFixCh341();
    } else if (key === 'docker') {
      this.runFixDocker();
    }
  },

  async runFixCh341() {
    const allFixBtns = document.querySelectorAll('#btn-wizard-fix-ch341, #btn-tp-fix-ch341, .btn-fix-ch341-item');
    allFixBtns.forEach(btn => {
      btn.disabled = true;
      if (!btn.dataset.origText) btn.dataset.origText = btn.innerHTML;
      btn.innerHTML = '⏳ 正在编译安装驱动中...';
      btn.classList.add('loading');
    });

    showToast('正在执行 CH341 串口驱动编译与安装任务，请稍候...', 'info', 4000);
    const modal = document.getElementById('fix-stream-modal');
    const consoleEl = document.getElementById('fix-stream-console');
    const progressBar = document.getElementById('fix-step-progress-bar');
    const progressPct = document.getElementById('fix-step-percent');
    const progressTxt = document.getElementById('fix-step-status-text');
    const modalTitle = document.getElementById('fix-modal-title');
    const modalIcon = document.getElementById('fix-modal-icon');

    if (modalTitle) modalTitle.textContent = '正在执行 LoRa 串口驱动与群控通信环境深度自愈修复';
    if (modalIcon) modalIcon.textContent = '🛠️';
    if (progressBar) progressBar.style.width = '10%';
    if (progressPct) progressPct.textContent = '10%';
    if (progressTxt) progressTxt.textContent = '⏳ 正在连接机器人并初始化修复环境...';

    if (modal) modal.style.display = 'flex';
    if (consoleEl) consoleEl.innerHTML = '<div class="log-info">[INFO] 准备开始 LoRa 通信自愈修复，下发指令并监听输出...</div>';

    const updateProgress = (line) => {
      if (!progressBar || !progressPct || !progressTxt) return;
      const l = line.toLowerCase();
      if (l.includes('step 1') || l.includes('检查 ch341 内核驱动')) {
        progressBar.style.width = '20%';
        progressPct.textContent = '20%';
        progressTxt.textContent = '🔍 [1/6] 检查与加载 CH341 Linux 内核驱动模块...';
      } else if (l.includes('step 2') || l.includes('配置 udev') || l.includes('权限')) {
        progressBar.style.width = '35%';
        progressPct.textContent = '35%';
        progressTxt.textContent = '🛡️ [2/6] 配置 udev 规则并放行 0666 设备读写权限...';
      } else if (l.includes('step 3') || l.includes('lora_recv_group.yaml')) {
        progressBar.style.width = '50%';
        progressPct.textContent = '50%';
        progressTxt.textContent = '⚙️ [3/6] 优化 lora_recv_group.yaml 串口稳定参数...';
      } else if (l.includes('step 4') || l.includes('热补丁') || l.includes('make.sh')) {
        progressBar.style.width = '70%';
        progressPct.textContent = '70%';
        progressTxt.textContent = '🔧 [4/6] 注入多端口自适应热补丁并编译 lora_recv_group...';
      } else if (l.includes('step 5') || l.includes('run_bg.sh')) {
        progressBar.style.width = '85%';
        progressPct.textContent = '85%';
        progressTxt.textContent = '📝 [5/6] 写入自适应多节点扫描 run_bg.sh 启动与守护脚本...';
      } else if (l.includes('step 6') || l.includes('拉起 lora')) {
        progressBar.style.width = '95%';
        progressPct.textContent = '95%';
        progressTxt.textContent = '🚀 [6/6] 校验并守护拉起机载 LoRa 接收程序...';
      }
    };

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
          updateProgress(line);
        }, (ok) => {
          allFixBtns.forEach(btn => {
            btn.disabled = false;
            btn.innerHTML = btn.dataset.origText || '🛠️ 一键修复 LoRa 通信';
            btn.classList.remove('loading');
          });

          if (ok) {
            if (progressBar) progressBar.style.width = '100%';
            if (progressPct) progressPct.textContent = '100%';
            if (progressTxt) progressTxt.textContent = '✅ LoRa 串口与群控通信环境自愈修复成功！';
            if (consoleEl) {
              const banner = document.createElement('div');
              banner.style.cssText = 'margin-top: 10px; padding: 10px; background: rgba(16, 185, 129, 0.2); border: 1px solid #10b981; border-radius: 6px; color: #10b981; font-weight: bold;';
              banner.textContent = '✅ LoRa 串口驱动与群控通信环境已全部修复并就绪！';
              consoleEl.appendChild(banner);
              consoleEl.scrollTop = consoleEl.scrollHeight;
            }
            showToast('✅ LoRa 通信环境修复完成！', 'success', 3000);
            setTimeout(() => {
              this.closeFixModal();
              this.runPrecheck(true);
            }, 1200);
          } else {
            if (progressTxt) progressTxt.textContent = '❌ 修复遇到问题，请检查日志输出';
            showToast('❌ 修复遇到问题，请检查终端日志', 'error', 4000);
            this.runPrecheck(false);
          }
        });
      } else {
        allFixBtns.forEach(btn => {
          btn.disabled = false;
          btn.innerHTML = btn.dataset.origText || '🛠️ 一键修复 LoRa 通信';
          btn.classList.remove('loading');
        });
        showToast(`启动修复失败: ${res.msg || '未知错误'}`, 'error');
      }
    } catch (err) {
      allFixBtns.forEach(btn => {
        btn.disabled = false;
        btn.innerHTML = btn.dataset.origText || '🛠️ 一键修复 LoRa 通信';
        btn.classList.remove('loading');
      });
      showToast(`修复触发异常: ${err.message}`, 'error');
    }
  },

  async runFixDocker() {
    showToast('正在修复 Docker 环境...', 'info');
    try {
      const res = await API.fixDocker();
      if (res.success && res.task_id) {
        API.listenStream(res.task_id, (line) => console.log(line), () => {
          showToast('Docker 修复流程结束', 'success');
          this.runPrecheck(true);
        });
      }
    } catch (err) {
      showToast(`修复异常: ${err.message}`, 'error');
    }
  },

  closeFixModal() {
    const modal = document.getElementById('fix-stream-modal');
    if (modal) modal.style.display = 'none';
  },

  // ==========================
  // Step 3: 镜像上传与导入
  // ==========================
  async browseTarFile() {
    try {
      showToast('正在打开文件选择器...', 'info');
      const res = await API.selectFile();
      if (res.success && res.file_path) {
        const pathInput = document.getElementById('input-local-tar-path');
        const remoteInput = document.getElementById('input-remote-load-path');
        const nameEl = document.getElementById('image-selected-name');
        if (pathInput) pathInput.value = res.file_path;
        if (nameEl) nameEl.textContent = `已选: ${res.filename} (${res.size_gb} GB)`;
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
      showToast('已取消上传任务', 'info');
    } catch (err) {
      showToast(`取消上传失败: ${err.message}`, 'error');
    }
  },

  _resetUploadButtons() {
    const btnStart = document.getElementById('btn-start-upload');
    const btnCancel = document.getElementById('btn-cancel-upload-wizard');
    if (btnStart) {
      btnStart.disabled = false;
      btnStart.style.display = 'block';
    }
    if (btnCancel) {
      btnCancel.style.display = 'none';
    }
  },

  async startImageUpload() {
    const pathInput = document.getElementById('input-local-tar-path');
    const remoteInput = document.getElementById('input-remote-load-path');
    let localPath = pathInput ? pathInput.value.trim() : '';
    let remotePath = remoteInput ? remoteInput.value.trim() : '';

    if (!localPath) {
      showToast('请点击【📁 浏览本地镜像文件】选取镜像，或输入本机文件完整绝对路径', 'warning');
      return;
    }

    const reqData = { local_path: localPath, remote_path: remotePath };

    showToast('正在检查远端镜像并准备传输...', 'info');
    const uploadBox = document.getElementById('upload-progress-box');
    const btnStart = document.getElementById('btn-start-upload');
    const btnCancel = document.getElementById('btn-cancel-upload-wizard');
    const consoleEl = document.getElementById('image-load-console');

    if (uploadBox) uploadBox.style.display = 'block';
    if (btnStart) btnStart.disabled = true;
    if (btnCancel) btnCancel.style.display = 'block';
    if (consoleEl) {
      consoleEl.innerHTML = `<div class="log-info">[INFO] 准备通过独立 SFTP 会话传输镜像: ${localPath} -> ${remotePath || '/home/ubuntu/'} ...</div>`;
    }

    try {
      const res = await API.uploadImage(reqData);
      if (!res.success) {
        showToast(`上传失败: ${res.msg}`, 'error');
        if (consoleEl) {
          const div = document.createElement('div');
          div.className = 'log-error';
          div.textContent = `[ERROR] 上传任务启动失败: ${res.msg}`;
          consoleEl.appendChild(div);
        }
        this._resetUploadButtons();
        return;
      }
      if (res.remote_path && remoteInput) {
        remoteInput.value = res.remote_path;
      }

      if (res.skipped) {
        // 远端已存在完全同名同大小镜像，直接跳过并自动执行安装
        this._resetUploadButtons();
        this.updateUploadUI({ percent: 100, transferred_bytes: 1, total_bytes: 1, speed_mbps: 0, eta_seconds: 0 });
        showToast('远端已存在同名同大小镜像包，正在自动执行 Docker 镜像安装...', 'success');
        if (consoleEl) {
          const div = document.createElement('div');
          div.className = 'log-info';
          div.textContent = `[INFO] ✅ 检测到远端已存在完全一致的镜像文件 (${res.remote_path})，无需重复上传，立即自动加载镜像！`;
          consoleEl.appendChild(div);
        }
        setTimeout(() => this.startDockerLoad(true), 500);
        return;
      }

      // 启动轮询进度
      if (this.uploadInterval) clearInterval(this.uploadInterval);
      this.uploadInterval = setInterval(async () => {
        try {
          const prog = await API.getUploadProgress();
          this.updateUploadUI(prog);
          if (prog.status === 'completed') {
            clearInterval(this.uploadInterval);
            this.uploadInterval = null;
            this._resetUploadButtons();
            showToast('镜像上传成功！正在自动执行 Docker 镜像安装 ...', 'success');
            if (consoleEl) {
              const div = document.createElement('div');
              div.className = 'log-info';
              div.textContent = `[SUCCESS] ✅ 镜像文件传输完成 (${res.remote_path})，立即自动执行 docker load 安装镜像...`;
              consoleEl.appendChild(div);
            }
            if (res.remote_path && remoteInput) {
              remoteInput.value = res.remote_path;
            }
            this.startDockerLoad(true); // 自动执行 docker load
          } else if (prog.status === 'error' || prog.status === 'canceled') {
            clearInterval(this.uploadInterval);
            this.uploadInterval = null;
            this._resetUploadButtons();
            showToast(`上传异常: ${prog.error_msg || '任务中断'}`, 'error');
            if (consoleEl) {
              const div = document.createElement('div');
              div.className = 'log-error';
              div.textContent = `[ERROR] 传输终止: ${prog.error_msg || '任务中断'}`;
              consoleEl.appendChild(div);
            }
          }
        } catch (pollErr) {
          console.warn('获取上传进度异常:', pollErr);
        }
      }, 500);

    } catch (err) {
      this._resetUploadButtons();
      showToast(`上传请求异常: ${err.message}`, 'error');
      if (consoleEl) {
        const div = document.createElement('div');
        div.className = 'log-error';
        div.textContent = `[ERROR] 请求异常: ${err.message}`;
        consoleEl.appendChild(div);
      }
    }
  },

  updateUploadUI(p) {
    const bar = document.getElementById('image-upload-bar');
    const pctText = document.getElementById('image-upload-pct');
    const infoText = document.getElementById('image-upload-info');
    const pct = typeof p.percent === 'number' ? p.percent : (parseFloat(p.percent) || 0);
    if (bar) bar.style.width = `${pct}%`;
    if (pctText) pctText.textContent = `${pct}%`;
    if (infoText) {
      const mbTrans = (((p.transferred_bytes || 0)) / (1024*1024)).toFixed(1);
      const mbTotal = (((p.total_bytes || 0)) / (1024*1024)).toFixed(1);
      const speed = p.speed_mbps !== undefined && p.speed_mbps !== null ? p.speed_mbps : 0;
      const eta = p.eta_seconds !== undefined && p.eta_seconds !== null ? `${p.eta_seconds}s` : '--';
      infoText.textContent = `${mbTrans} MB / ${mbTotal} MB | 速率: ${speed} MB/s | 剩余: ${eta}`;
    }
  },

  async startDockerLoad(autoAdvance = false) {
    const pathInput = document.getElementById('input-remote-load-path');
    const remotePath = pathInput ? pathInput.value.trim() : '/home/ubuntu/vsis_dancer_cpu_1.0.tar.gz';
    const btnLoad = document.getElementById('btn-docker-load');

    if (btnLoad && btnLoad.disabled) return;
    if (btnLoad) {
      btnLoad.disabled = true;
      btnLoad.classList.add('loading');
      btnLoad.textContent = '⏳ 正在安装镜像中... (约需 1~3 分钟)';
    }

    const pBox = document.getElementById('docker-load-progress-box');
    const pBar = document.getElementById('docker-load-progress-bar');
    const pPct = document.getElementById('docker-load-pct');
    const pText = document.getElementById('docker-load-stage-text');
    const pSub = document.getElementById('docker-load-subtext');
    if (pBox) pBox.style.display = 'block';

    let currentPct = 15;
    const setProgress = (pct, stage, sub) => {
      currentPct = Math.max(currentPct, pct);
      if (pBar) {
        pBar.style.width = `${currentPct}%`;
        pBar.style.background = currentPct >= 100 ? '#10b981' : 'linear-gradient(90deg, #0ea5e9, #10b981)';
      }
      if (pPct) pPct.textContent = `${Math.round(currentPct)}%`;
      if (pText && stage) pText.textContent = stage;
      if (pSub && sub) pSub.textContent = sub;
    };
    setProgress(15, '⏳ 检查镜像包压缩状态与磁盘空间...', '准备文件解压与 Docker 归档导入...');

    // 平滑递增定时器，防止长时间执行造成卡顿感 (最高自然增长至 92%)
    let ticker = setInterval(() => {
      if (currentPct < 92) {
        currentPct += 0.6;
        setProgress(currentPct);
      }
    }, 800);

    showToast('正在远端执行 docker load -i ... (请稍候 1~3 分钟)', 'info');
    const consoleEl = document.getElementById('image-load-console');
    if (consoleEl) consoleEl.innerHTML = '<div class="log-info">正在执行 docker load 安装镜像...</div>';

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

          // 根据输出流关键字动态推进阶段进度
          const text = String(line || '');
          if (text.includes('[STEP 1/3]')) {
            setProgress(20, '🔍 步骤 1/3: 检查镜像包格式与磁盘...', '检测 GZIP / TAR 压缩状态与 NVMe 剩余空间');
          } else if (text.includes('[STEP 2/3]') || text.includes('解压') || text.includes('pigz') || text.includes('gzip')) {
            setProgress(45, '📦 步骤 2/3: 正在物理完整解压镜像 TAR 归档...', '利用多核 pigz/gzip 高速解压缩 (预计 30~60 秒)');
          } else if (text.includes('解压完成')) {
            setProgress(65, '✅ TAR 归档解压完成，准备导入 Docker 引擎...', '已落盘，正在调用 docker load 引擎');
          } else if (text.includes('[STEP 3/3]') || text.includes('docker load')) {
            setProgress(75, '⚡ 步骤 3/3: 正在向 Docker 引擎加载镜像层...', '写入 Layer 分层数据与 OCI 格式元数据');
          } else if (text.includes('Loaded image') || text.includes('ctr') || text.includes('skopeo')) {
            setProgress(90, '🎉 镜像层加载成功，正在巡检环境权限...', '执行权限配置与开机环境适配');
          } else if (text.includes('[SUCCESS]') || text.includes('🎉')) {
            setProgress(100, '✅ Docker 镜像导入与环境适配全部完成！', '镜像已成功注册至 Docker，可进入下一步固化启动');
          }
        }, (ok) => {
          if (ticker) clearInterval(ticker);
          if (ok) {
            setProgress(100, '✅ Docker 镜像安装与导入成功！', '已成功加载至宿主机，请点击【下一步】继续。');
            if (consoleEl) {
              const banner = document.createElement('div');
              banner.className = 'upload-success-badge';
              banner.style.cssText = 'margin-top: 10px; padding: 10px 14px; background: rgba(16, 185, 129, 0.18); border: 1px solid #10b981; border-radius: 6px; color: #10b981; font-weight: 700; font-size: 0.9rem; display: flex; align-items: center; gap: 8px; box-shadow: 0 0 12px rgba(16, 185, 129, 0.2);';
              banner.innerHTML = '<span>✅</span> <span>Docker 镜像安装导入成功！请点击【下一步】继续。</span>';
              consoleEl.appendChild(banner);
              consoleEl.scrollTop = consoleEl.scrollHeight;
            }
            if (btnLoad) {
              btnLoad.disabled = false;
              btnLoad.classList.remove('loading');
              btnLoad.textContent = '✅ 重新执行 docker load -i';
            }
            showToast('✅ Docker 镜像安装导入成功！请点击【下一步】继续。', 'success', 3000);
            this.refreshImagesList();
            this.autoCheckStep3();
          } else {
            setProgress(currentPct, '❌ 镜像安装遇到异常', '请查看下方控制台详细错误日志');
            if (pBar) pBar.style.background = '#f87171';
            if (btnLoad) {
              btnLoad.disabled = false;
              btnLoad.classList.remove('loading');
              btnLoad.textContent = '⚡ 执行 docker load -i';
            }
            showToast('❌ 镜像导入异常，请查看下方终端输出', 'error');
          }
        });
      } else {
        if (ticker) clearInterval(ticker);
        if (btnLoad) {
          btnLoad.disabled = false;
          btnLoad.classList.remove('loading');
          btnLoad.textContent = '⚡ 执行 docker load -i';
        }
        showToast(`启动失败: ${res?.msg || '未知错误'}`, 'error');
      }
    } catch (err) {
      if (ticker) clearInterval(ticker);
      if (btnLoad) {
        btnLoad.disabled = false;
        btnLoad.classList.remove('loading');
        btnLoad.textContent = '⚡ 执行 docker load -i';
      }
      showToast(`执行异常: ${err.message}`, 'error');
    }
  },

  // ==========================
  // Step 4: 固化容器启动与自启动
  // ==========================
  renderRunningContainers(containers, targetElId = 'wizard-running-containers-list') {
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

  async refreshImagesList() {
    try {
      const res = await API.listImages();
      const select = document.getElementById('select-docker-image');
      
      // 1. 渲染当前宿主机已运行容器列表
      if (res && res.running_containers) {
        this.renderRunningContainers(res.running_containers, 'wizard-running-containers-list');
      }

      if (!select) return;

      select.innerHTML = '';
      const availableImgs = res.available_images || res.images || [];
      if (availableImgs.length === 0) {
        select.innerHTML = '<option value="">(所有可用镜像均已在容器中运行)</option>';
        return;
      }

      // 优先将 vsis_dancer 镜像排在首位
      availableImgs.sort((a, b) => {
        const aName = `${a.repository}:${a.tag}`.toLowerCase();
        const bName = `${b.repository}:${b.tag}`.toLowerCase();
        const aMatch = aName.includes('vsis_dancer') || (aName.includes('vsis') && aName.includes('dancer'));
        const bMatch = bName.includes('vsis_dancer') || (bName.includes('vsis') && bName.includes('dancer'));
        if (aMatch && !bMatch) return -1;
        if (!aMatch && bMatch) return 1;
        return 0;
      });

      for (const img of availableImgs) {
        const opt = document.createElement('option');
        const tag = `${img.repository}:${img.tag}`;
        opt.value = tag;
        opt.textContent = `${tag} (${img.size})`;
        select.appendChild(opt);
      }
    } catch (err) {
      console.error('获取镜像与容器列表失败:', err);
    }
  },

  async startContainer(autoAdvance = false) {
    return this.deployStep4Sequential(autoAdvance);
  },

  async deployStep4Sequential(autoAdvance = false) {
    if (this.isStartingContainer) return;
    this.isStartingContainer = true;

    const inputEl = document.getElementById('select-robot-id');
    const rawValue = inputEl ? inputEl.value : 'A';
    const valResult = window.validateRobotId ? window.validateRobotId(rawValue) : { valid: true, cleanId: rawValue.trim().toUpperCase(), error: '' };

    // 校验规则 (统一公共验证逻辑)
    if (!valResult.valid) {
      showToast(valResult.error, 'error');
      if (inputEl) inputEl.focus();
      this.isStartingContainer = false;
      return;
    }
    const robotId = valResult.cleanId;
    if (inputEl) inputEl.value = robotId;

    const select = document.getElementById('select-docker-image');
    const imgName = select && select.value ? select.value : 'rl_cu118:2.0';

    const consoleEl = document.getElementById('container-start-console');
    if (consoleEl) consoleEl.innerHTML = '';

    const appendLog = (msg, isErr = false) => {
      if (!consoleEl) return;
      const div = document.createElement('div');
      div.className = isErr ? 'log-error' : (msg.includes('✅') || msg.includes('SUCCESS') || msg.includes('🎉') ? 'log-success' : 'log-info');
      div.textContent = msg;
      consoleEl.appendChild(div);
      consoleEl.scrollTop = consoleEl.scrollHeight;
    };

    const btnAuto = document.getElementById('btn-write-autostart');
    const btnStart = document.getElementById('btn-start-container');

    if (btnAuto) btnAuto.disabled = true;
    if (btnStart) {
      btnStart.disabled = true;
      btnStart.classList.add('loading');
      btnStart.textContent = '⏳ 正在部署 (写入ID ➔ 启动容器 ➔ 拉起机载)...';
    }

    const resetButtons = () => {
      this.isStartingContainer = false;
      if (btnAuto) btnAuto.disabled = false;
      if (btnStart) {
        btnStart.disabled = false;
        btnStart.classList.remove('loading');
        btnStart.textContent = '⚡ 固化启动 vsis_g1 容器';
      }
    };

    try {
      // 步骤 1 (优先): 写入 Robot ID 与自启钩子
      appendLog(`[步骤 1/2 优先执行] 正在配置开机自启并写入 Robot ID [${robotId}] ...`);
      showToast(`[步骤 1/2] 优先写入 Robot ID [${robotId}] ...`, 'info');

      const autostartRes = await API.configAutostart(robotId);
      if (!autostartRes.success) {
        appendLog(`[ERROR] ❌ 写入 Robot ID 失败: ${autostartRes.msg}`, true);
        showToast(`写入失败: ${autostartRes.msg}`, 'error');
        resetButtons();
        return;
      }

      this.isIdConfigured = true;
      appendLog(`[SUCCESS] ✅ Robot ID [${robotId}] 与开机自启动钩子写入成功！`);
      showToast(`✅ Robot ID [${robotId}] 写入成功！`, 'success');

      // 步骤 2 (然后): 固化启动容器 vsis_g1 (第 4 步不再执行 run_bg.sh)
      appendLog(`[步骤 2/2 然后执行] 正在启动固化参数容器 vsis_g1 (镜像: ${imgName}) ...`);
      showToast(`[步骤 2/2] 正在启动容器 vsis_g1 ...`, 'info');

      const containerRes = await API.startContainer(imgName);
      if (containerRes.success && containerRes.task_id) {
        API.listenStream(containerRes.task_id, (line, isErr) => {
          appendLog(line, isErr);
        }, async (ok) => {
          resetButtons();
          if (ok) {
            appendLog('[SUCCESS] ✅ 容器 vsis_g1 固化启动完成！已就绪，请在第 5 步完成授权并拉起运控。');
            showToast('✓ 容器 vsis_g1 已固化启动！即将进入第 5 步机器码与 License 授权...', 'success');
            await this.refreshImagesList();
            setTimeout(() => this.goToStep(5, true), 1000);
          } else {
            appendLog('[ERROR] ❌ 容器启动失败，请检查上方日志', true);
            showToast('容器启动失败，请检查上方日志', 'error');
          }
        });
      } else {
        resetButtons();
        appendLog(`[ERROR] ❌ 启动容器请求失败: ${containerRes?.msg || '未知错误'}`, true);
        showToast(`启动容器失败: ${containerRes?.msg || '未知错误'}`, 'error');
      }
    } catch (err) {
      resetButtons();
      appendLog(`[ERROR] 部署异常: ${err.message}`, true);
      showToast(`部署异常: ${err.message}`, 'error');
    }
  },

  async writeAutostartAndId() {
    const inputEl = document.getElementById('select-robot-id');
    const rawValue = inputEl ? inputEl.value : 'A';
    const valResult = window.validateRobotId ? window.validateRobotId(rawValue) : { valid: true, cleanId: rawValue.trim().toUpperCase(), error: '' };

    // 校验规则（与群控控制台"添加机器人"一致）
    if (!valResult.valid) {
      showToast(valResult.error, 'error');
      if (inputEl) inputEl.focus();
      return;
    }
    const robotId = valResult.cleanId;

    if (inputEl) inputEl.value = robotId; // 写回大写
    this.updateWriteIdButtonText();

    const btn = document.getElementById('btn-write-autostart');
    if (btn) {
      btn.disabled = true;
      btn.textContent = `⏳ 正在写入 ID [${robotId}] ...`;
    }

    const consoleEl = document.getElementById('container-start-console');
    const appendLog = (msg, isErr = false) => {
      if (!consoleEl) return;
      const div = document.createElement('div');
      div.className = isErr ? 'log-error' : (msg.includes('✅') || msg.includes('SUCCESS') || msg.includes('🎉') ? 'log-success' : 'log-info');
      div.textContent = msg;
      consoleEl.appendChild(div);
      consoleEl.scrollTop = consoleEl.scrollHeight;
    };

    appendLog(`[INFO] 正在写入 Robot ID [${robotId}] 与配置开机自启钩子...`);
    showToast(`正在写入 Robot ID [${robotId}] ...`, 'info');

    try {
      // 1. 写入 ID 与自启钩子（此时不直接启动 run_bg，等待容器重启）
      const res = await API.configAutostart(robotId);
      if (!res.success) {
        appendLog(`[ERROR] ❌ 写入失败: ${res.msg}`, true);
        showToast(`写入失败: ${res.msg}`, 'error');
        if (btn) btn.disabled = false;
        this.updateWriteIdButtonText();
        return;
      }

      this.isIdConfigured = true;
      appendLog(`[SUCCESS] ✅ Robot ID [${robotId}] 写入成功！`);

      // 2. 检查宿主机当前容器状态，若 vsis_g1 已存在/运行，自动重启容器
      const cStatus = await API.getContainerStatus();
      const hasContainer = cStatus.success && cStatus.data && (cStatus.data.running || cStatus.data.container_exists);

      if (hasContainer) {
        appendLog(`[INFO] 检测到 vsis_g1 容器已就绪，正在自动重启容器以应用新 ID [${robotId}] ...`);
        showToast(`已写入 ID [${robotId}]，正在自动重启 vsis_g1 容器...`, 'info');
        if (btn) btn.textContent = '⏳ 正在重启容器 vsis_g1 ...';

        const restartRes = await API.restartContainer('vsis_g1');
        if (restartRes.success) {
          appendLog(`[SUCCESS] ✅ 容器 vsis_g1 已重启，新 ID [${robotId}] 已应用生效！`);
          showToast(`🎉 Robot ID [${robotId}] 已写入，容器已重启就绪！`, 'success');
        } else {
          appendLog(`[ERROR] ❌ 重启容器失败: ${restartRes.msg}`, true);
          showToast(`重启容器失败: ${restartRes.msg}`, 'error');
        }
      } else {
        appendLog(`[INFO] 容器尚未创建。Robot ID [${robotId}] 已就绪，请在下方点击【⚡ 固化启动 vsis_g1 容器】。`);
        showToast(`✅ Robot ID [${robotId}] 写入成功！请启动容器`, 'success');
      }
      if (btn) btn.disabled = false;
      this.updateWriteIdButtonText();
    } catch (err) {
      appendLog(`[ERROR] 写入异常: ${err.message}`, true);
      showToast(`写入失败: ${err.message}`, 'error');
      if (btn) btn.disabled = false;
      this.updateWriteIdButtonText();
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
        await this.refreshImagesList();
      } else {
        showToast(`关闭失败: ${res.msg}`, 'error');
      }
    } catch (err) {
      showToast(`关闭容器异常: ${err.message}`, 'error');
    }
  },

  async checkProcessStatus() {
    const badgeEl = document.getElementById('wizard-robot-process-badge');
    const dotEl = document.getElementById('wizard-process-dot');
    const textEl = document.getElementById('wizard-process-status-text');
    const ctrlSub = document.getElementById('wizard-ctrl-sub-badge');
    const loraSub = document.getElementById('wizard-lora-sub-badge');

    try {
      const res = await API.getRobotProcessStatus();
      if (!res || !res.connected) {
        if (dotEl) { dotEl.style.background = '#94a3b8'; dotEl.className = 'pulse-dot'; }
        if (textEl) textEl.textContent = '未连接';
        if (badgeEl) { badgeEl.style.borderColor = 'rgba(255,255,255,0.1)'; badgeEl.style.background = 'rgba(255,255,255,0.05)'; }
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

      if (dotEl && textEl && badgeEl) {
        if (res.all_running) {
          dotEl.style.background = '#34d399';
          dotEl.className = 'pulse-dot active';
          textEl.textContent = '运行中';
          badgeEl.style.borderColor = 'rgba(52, 211, 153, 0.4)';
          badgeEl.style.background = 'rgba(16, 185, 129, 0.12)';
        } else if (res.g1_ctrl_running && !res.lora_recv_running) {
          dotEl.style.background = '#fbbf24';
          dotEl.className = 'pulse-dot active';
          textEl.textContent = '仅运控';
          badgeEl.style.borderColor = 'rgba(251, 191, 36, 0.4)';
          badgeEl.style.background = 'rgba(245, 158, 11, 0.12)';
        } else if (!res.g1_ctrl_running && res.lora_recv_running) {
          dotEl.style.background = '#fbbf24';
          dotEl.className = 'pulse-dot active';
          textEl.textContent = '仅通信';
          badgeEl.style.borderColor = 'rgba(251, 191, 36, 0.4)';
          badgeEl.style.background = 'rgba(245, 158, 11, 0.12)';
        } else {
          dotEl.style.background = '#f87171';
          dotEl.className = 'pulse-dot';
          textEl.textContent = '未运行';
          badgeEl.style.borderColor = 'rgba(239, 68, 68, 0.3)';
          badgeEl.style.background = 'rgba(239, 68, 68, 0.08)';
        }
      }
    } catch (_) {}
  },

  // --- 一键修复与任务执行实时流式弹窗控制器 ---
  openFixModal(title = '正在执行任务', icon = '🛠️') {
    const modal = document.getElementById('fix-stream-modal');
    const titleEl = document.getElementById('fix-modal-title');
    const iconEl = document.getElementById('fix-modal-icon');
    const consoleEl = document.getElementById('fix-stream-console');
    const pBar = document.getElementById('fix-step-progress-bar');
    const pPct = document.getElementById('fix-step-percent');
    const pText = document.getElementById('fix-step-status-text');

    if (titleEl) titleEl.textContent = title;
    if (iconEl) iconEl.textContent = icon;
    if (consoleEl) consoleEl.innerHTML = '<div class="log-info">正在建立安全会话并下发启动指令...</div>';
    if (pBar) {
      pBar.style.width = '10%';
      pBar.style.background = 'linear-gradient(90deg, #00d2ff, #00ff88)';
    }
    if (pPct) pPct.textContent = '10%';
    if (pText) pText.textContent = '⏳ 正在初始化运行环境...';

    if (modal) {
      modal.style.display = 'flex';
    }
  },

  updateFixModalProgress(pct, statusText) {
    const pBar = document.getElementById('fix-step-progress-bar');
    const pPct = document.getElementById('fix-step-percent');
    const pText = document.getElementById('fix-step-status-text');
    if (pBar) {
      pBar.style.width = `${pct}%`;
      if (pct >= 100) pBar.style.background = '#10b981';
    }
    if (pPct) pPct.textContent = `${Math.round(pct)}%`;
    if (pText && statusText) pText.textContent = statusText;
  },

  appendFixModalLog(line, isErr = false) {
    const consoleEl = document.getElementById('fix-stream-console');
    if (!consoleEl) return;
    const div = document.createElement('div');
    div.className = isErr ? 'log-error' : (line.includes('✅') || line.includes('SUCCESS') || line.includes('🎉') ? 'log-success' : 'log-info');
    div.textContent = line;
    consoleEl.appendChild(div);
    consoleEl.scrollTop = consoleEl.scrollHeight;
  },

  closeFixModal() {
    const modal = document.getElementById('fix-stream-modal');
    if (modal) {
      modal.style.display = 'none';
    }
  },

  async startRobotProcesses() {
    const btnStart = document.getElementById('wizard-btn-start-process');
    this.openFixModal('正在拉起机载运控主程序与 LoRa 接收服务 (run_bg.sh)', '🚀');
    if (btnStart) {
      btnStart.disabled = true;
      btnStart.textContent = '⏳ 正在启动机载程序...';
    }

    try {
      const res = await API.startRobotProcesses();
      if (res && res.success && res.task_id) {
        API.listenStream(res.task_id, (line, isErr) => {
          this.appendFixModalLog(line, isErr);

          // 依据真实运控主程序与 LoRa 运行日志解析真实进度百分比与当前步骤
          const match = line.match(/\[PROGRESS\s+(\d+)%\]\s*(.*)/i);
          if (match) {
            const pct = parseInt(match[1], 10);
            const desc = match[2] || '';
            this.updateFixModalProgress(pct, desc);
          }
        }, async (ok) => {
          if (btnStart) {
            btnStart.disabled = false;
            btnStart.textContent = '🚀 启动机载程序 (run_bg.sh)';
          }
          if (ok) {
            this.updateFixModalProgress(100, '🎉 机载运控 (g1_ctrl_vsis) 与 LoRa 接收服务已全面就绪！');
            showToast('✅ 机载运控与 LoRa 程序已全部成功启动！', 'success', 3000);
            setTimeout(() => this.closeFixModal(), 1800);
          } else {
            this.updateFixModalProgress(100, '⚠️ 启动未在超时内就绪');
            showToast('机载程序已下发，请在日志中查看详细状态', 'warning', 4000);
          }
          await this.checkProcessStatus();
        });
      } else {
        if (btnStart) {
          btnStart.disabled = false;
          btnStart.textContent = '🚀 启动机载程序 (run_bg.sh)';
        }
        this.appendFixModalLog(`[ERROR] 启动请求失败: ${res?.msg || '未知错误'}`, true);
        showToast(`启动失败: ${res?.msg || '未知错误'}`, 'error');
      }
    } catch (err) {
      if (btnStart) {
        btnStart.disabled = false;
        btnStart.textContent = '🚀 启动机载程序 (run_bg.sh)';
      }
      this.appendFixModalLog(`[ERROR] 请求异常: ${err.message}`, true);
      showToast(`请求异常: ${err.message}`, 'error');
    }
  },

  async stopRobotProcesses() {
    if (!confirm('确定要停止机器人机载跳舞运控与 LoRa 接收进程 (pkill) 吗？')) return;
    showToast('正在停止机载运控与 LoRa 进程...', 'info');
    try {
      const res = await API.stopRobotProcesses();
      if (res && res.success) {
        showToast('⚠️ 机器人机载运控与 LoRa 接收进程已停止', 'info');
        setTimeout(() => this.checkProcessStatus(), 1000);
      } else {
        showToast(`停止失败: ${res?.msg || '未知错误'}`, 'error');
      }
    } catch (err) {
      showToast(`请求异常: ${err.message}`, 'error');
    }
  },

  async checkAndFixEnvironment() {
    showToast('正在巡检与修复机器人运行环境权限...', 'info');
    try {
      const res = await API.checkRobotEnv();
      if (res && res.success && res.task_id) {
        API.listenStream(res.task_id, (line) => console.log(line), async (ok) => {
          if (ok) {
            showToast('✅ 机器人环境巡检与权限修复已完成', 'success');
            await this.refreshImagesList();
            await this.checkProcessStatus();
          } else {
            showToast('环境巡检发现警告，请查看日志', 'warning');
          }
        });
      }
    } catch (e) {
      showToast(`环境巡检异常: ${e.message}`, 'error');
    }
  },

  // ==========================
  // Step 5: 机器码与 License
  // ==========================
  async fetchMachineId() {
    const midValEl = document.getElementById('machine-id-display');
    if (midValEl) midValEl.textContent = '正在读取硬件机器码...';

    try {
      const res = await API.getMachineId();
      if (res.success && res.machine_id) {
        this.detectedMachineId = res.machine_id;
        if (midValEl) midValEl.textContent = res.machine_id;
        showToast('机器码读取成功', 'success');
      } else {
        if (midValEl) midValEl.textContent = '未能读取到机器码 (请先确保容器已启动)';
        showToast(`读取失败: ${res.msg}`, 'warning');
      }
    } catch (err) {
      if (midValEl) midValEl.textContent = '读取机器码异常';
      showToast(`机器码接口异常: ${err.message}`, 'error');
    }
  },

  copyMachineId() {
    if (!this.detectedMachineId) {
      showToast('暂无机器码可复制', 'warning');
      return;
    }
    copyToClipboard(this.detectedMachineId, '64位机器码已复制到剪贴板！');
  },

  handleLicenseFileInput(input) {
    if (input && input.files && input.files.length > 0) {
      this.handleLicenseFile(input.files[0]);
    }
  },

  handleLicenseDrop(e) {
    e.preventDefault();
    e.stopPropagation();
    const licDropzone = document.getElementById('license-dropzone');
    if (licDropzone) licDropzone.classList.remove('dragover');
    const dt = e.dataTransfer;
    if (dt && dt.files && dt.files.length > 0) {
      this.handleLicenseFile(dt.files[0]);
    }
  },

  async handleLicenseFile(file) {
    if (!file) return;
    const reader = new FileReader();
    reader.onload = async (e) => {
      const content = e.target.result;
      this.lastLicenseContent = content;
      try {
        const res = await API.verifyLicense(content, this.detectedMachineId);
        this.renderLicenseVerification(res);
        // 上传后立即自动触发部署并重启机器端进行日志校验
        showToast('已检测到 License 文件，正在自动部署至机器人并重启校验...', 'info', 2000);
        await this.deployLicense(true);
      } catch (err) {
        showToast(`License 处理失败: ${err.message}`, 'error');
      }
    };
    reader.readAsText(file);
  },

  renderLicenseVerification(res) {
    const resBox = document.getElementById('license-verify-result');
    if (!resBox) return;

    if (!res.success) {
      resBox.innerHTML = `
        <div class="diag-alert danger" style="align-items: center;">
          <div style="flex: 1;">${res.msg}</div>
          <button class="btn-copy-mini" onclick="copyToClipboard(${JSON.stringify(res.msg)}, '错误信息已复制')">📋 复制错误</button>
        </div>
      `;
      return;
    }

    const p = res.parsed || {};
    let dancesHtml = (p.dances || []).map(d => `<span class="card-badge" style="margin: 2px;">${d}</span>`).join(' ');

    resBox.innerHTML = `
      <div style="background: rgba(56, 189, 248, 0.1); border: 1px solid rgba(56, 189, 248, 0.3); padding: 12px; border-radius: 6px; color: #38bdf8; font-weight: 600; margin-bottom: 12px; display: flex; justify-content: space-between; align-items: center;">
        <span>📄 License 文件已加载，正在自动写入机器人并重启主控程序进行生效校验...</span>
      </div>
      <div class="card" style="padding: 14px;">
        <div style="font-size: 0.85rem; margin-bottom: 6px; user-select: text;"><b>授权客户:</b> ${p.customer || '商业客户'} | <b>适用机型:</b> ${p.model || 'Unitree G1'}</div>
        <div style="font-size: 0.85rem; margin-bottom: 6px; user-select: text;"><b>有效期至:</b> <span style="color: var(--accent-cyan); font-weight: 600;">${p.expire_date || '永久授权'}</span></div>
        ${p.dance_count > 0 ? `<div style="font-size: 0.85rem; margin-bottom: 8px; user-select: text;"><b>包含舞蹈清单 (${p.dance_count} 支):</b></div>
        <div style="display: flex; flex-wrap: wrap; gap: 4px; max-height: 120px; overflow-y: auto; user-select: text;">${dancesHtml}</div>` : ''}
      </div>
    `;

    const deployBtn = document.getElementById('btn-deploy-license');
    if (deployBtn) deployBtn.disabled = false;
  },

  async deployLicense(autoAdvance = true) {
    if (!this.lastLicenseContent) {
      showToast('请先选择或拖入 license.json 文件', 'warning');
      return;
    }

    const btn = document.getElementById('btn-deploy-license');
    if (btn) {
      btn.disabled = true;
      btn.textContent = '⏳ 正在部署 License...';
    }

    showToast('正在写入 License 并校验授权...', 'info');
    try {
      const res = await API.deployLicense(this.lastLicenseContent);
      const resBox = document.getElementById('license-verify-result');
      if (res.success) {
        showToast('✓ License 部署成功！正在拉起机载程序并校验运控与 LoRa 状态...', 'success', 2500);
        if (resBox && res.log_snippet) {
          const logCard = document.createElement('div');
          logCard.className = 'diag-alert success';
          logCard.style.marginTop = '12px';
          logCard.innerHTML = `
            <div style="flex: 1;">
              <div><b>✅ License 部署与授权成功！</b> ${res.msg}</div>
              <div style="font-size: 0.76rem; color: #a7f3d0; margin-top: 4px; font-family: monospace; white-space: pre-wrap; max-height: 100px; overflow-y: auto;">${res.log_snippet}</div>
            </div>
            <button class="btn-copy-mini" onclick="copyToClipboard(${JSON.stringify(res.log_snippet)}, '主控验证日志已复制')">📋 复制日志</button>
          `;
          resBox.appendChild(logCard);
        }

        // 第 5 步授权成功后，自动执行 run_bg.sh 并展示执行进度条，等待 lora 和运控完全启动成功后再进入第 6 步
        await this.startStep5ProcessesWithProgress(autoAdvance);
      } else {
        showToast(`❌ 机器端校验失败: ${res.msg}`, 'error');
        if (resBox && res.log_snippet) {
          const logCard = document.createElement('div');
          logCard.className = 'diag-alert danger';
          logCard.style.marginTop = '12px';
          logCard.innerHTML = `
            <div style="flex: 1;">
              <div><b>❌ 校验失败:</b> ${res.msg}</div>
              <div style="font-size: 0.76rem; color: #fca5a5; margin-top: 4px; font-family: monospace; white-space: pre-wrap; max-height: 100px; overflow-y: auto;">${res.log_snippet}</div>
            </div>
            <button class="btn-copy-error" onclick="copyToClipboard(${JSON.stringify(res.log_snippet)}, '错误日志已复制')">📋 复制报错日志</button>
          `;
          resBox.appendChild(logCard);
        }
        if (btn) {
          btn.disabled = false;
          btn.textContent = '🚀 重新部署 License 至机器人';
        }
      }
    } catch (err) {
      showToast(`部署 License 异常: ${err.message}`, 'error');
      if (btn) {
        btn.disabled = false;
        btn.textContent = '🚀 重新部署 License 至机器人';
      }
    }
  },

  async startStep5ProcessesWithProgress(autoAdvance = true) {
    const pBox = document.getElementById('step5-process-progress-box');
    const pText = document.getElementById('step5-process-stage-text');
    const pPct = document.getElementById('step5-process-pct');
    const pBar = document.getElementById('step5-process-bar');
    const pSub = document.getElementById('step5-process-subtext');
    const ctrlBadge = document.getElementById('step5-ctrl-badge');
    const loraBadge = document.getElementById('step5-lora-badge');

    if (pBox) pBox.style.display = 'block';

    const setProgress = (pct, stage, sub) => {
      if (pBar && pct !== undefined) {
        pBar.style.width = `${pct}%`;
        pBar.style.background = pct >= 100 ? '#10b981' : 'linear-gradient(90deg, #0ea5e9, #10b981)';
      }
      if (pPct && pct !== undefined) pPct.textContent = `${Math.round(pct)}%`;
      if (pText && stage) pText.textContent = stage;
      if (pSub && sub) pSub.textContent = sub;
    };

    setProgress(15, '🚀 正在拉起机载运控与通信程序 (run_bg.sh)...', '正在下发启动脚本并实时监听启动日志...');

    try {
      // 1. 发起 startRobotProcesses 流式监听
      const res = await API.startRobotProcesses();
      if (res && res.success && res.task_id) {
        API.listenStream(res.task_id, (line, isErr) => {
          // 解析真实运控日志中的进度标签
          const match = line.match(/\[PROGRESS\s+(\d+)%\]\s*(.*)/i);
          if (match) {
            const pct = parseInt(match[1], 10);
            const desc = match[2] || '';
            setProgress(pct, desc, line.trim());
          } else if (line.includes('[运控日志]')) {
            const clean = line.replace('[运控日志]', '').trim();
            if (clean) setProgress(undefined, null, `[运控] ${clean}`);
          } else if (line.includes('[LoRa日志]')) {
            const clean = line.replace('[LoRa日志]', '').trim();
            if (clean) setProgress(undefined, null, `[LoRa] ${clean}`);
          }
        }, async (ok) => {
          const status = await API.getRobotProcessStatus();
          if (ctrlBadge) {
            ctrlBadge.className = status?.g1_ctrl_running ? 'container-status-badge running' : 'container-status-badge stopped';
            ctrlBadge.textContent = status?.g1_ctrl_running ? '🦾 运行中' : '🦾 未运行';
          }
          if (loraBadge) {
            loraBadge.className = status?.lora_recv_running ? 'container-status-badge running' : 'container-status-badge stopped';
            loraBadge.textContent = status?.lora_recv_running ? '📡 运行中' : '📡 未运行';
          }

          if (ok && status?.all_running) {
            setProgress(100, '🎉 机载程序启动成功！', '商业化环境全流程校验通过，即将进入测试联调...');
            showToast('🎉 机载程序已启动，自动进入第 6 步！', 'success', 3000);
            await this.checkProcessStatus();

            // 刷新全站授权与进程状态
            if (window.App) {
              if (typeof App.runStartupCheck === 'function') App.runStartupCheck();
              if (typeof App.refreshLicenseStatus === 'function') App.refreshLicenseStatus();
            }
            if (window.TabImage && typeof TabImage.checkProcessStatus === 'function') {
              TabImage.checkProcessStatus();
            }
            if (window.TabLicense && typeof TabLicense.fetchMachineId === 'function') {
              TabLicense.fetchMachineId();
            }
            if (window.TabDanceUpdate && typeof TabDanceUpdate.loadDances === 'function') {
              TabDanceUpdate.loadDances();
            }

            if (autoAdvance) {
              setTimeout(() => this.goToStep(6, true), 1200);
            }
          } else {
            setProgress(100, '⚠️ 机载服务启动指令已完成', '双进程已在后台启动，可点击下一步进入联调测试。');
            showToast('机载程序已拉起，正在后台稳定运行', 'info', 3000);
            if (autoAdvance) {
              setTimeout(() => this.goToStep(6, true), 1500);
            }
          }
        });
      } else {
        setProgress(100, '❌ 启动请求失败', res?.msg || '未知错误');
        showToast(`启动失败: ${res?.msg || '未知错误'}`, 'error');
      }
    } catch (e) {
      setProgress(100, '❌ 启动异常', e.message || e);
      showToast(`启动异常: ${e.message}`, 'error');
    }
  },

  async sendTestCmd(target, cmd) {
    showToast(`正在发送指令: [${target}|${cmd}] ...`, 'info');
    try {
      const res = await API.sendSerialCmd(target, cmd);
      if (res.success) {
        showToast(`✅ 指令发送成功: ${res.raw_command || cmd}`, 'success', 2500);
      } else {
        showToast(`发送失败: ${res.msg}`, 'warning', 3500);
      }
    } catch (err) {
      showToast(`发送异常: ${err.message}`, 'error');
    }
  },

  restartProcesses() {
    API.restartDanceProcesses().then(res => {
      showToast('已下发进程重启指令', 'info');
    });
  },

  openModal(step = 1) {
    const modal = document.getElementById('wizard-modal');
    if (modal) {
      modal.classList.add('active');
      modal.style.display = 'flex';
      this.goToStep(step, false);
    }
  },

  closeModal() {
    const modal = document.getElementById('wizard-modal');
    if (modal) {
      modal.classList.remove('active');
      modal.style.display = 'none';
    }
  }
};
