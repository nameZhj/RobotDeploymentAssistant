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
        this.goToStep(step);
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

    // 镜像文件选择
    const inputImageFile = document.getElementById('input-image-file');
    if (inputImageFile) {
      inputImageFile.addEventListener('change', (e) => {
        if (e.target.files.length > 0) {
          const file = e.target.files[0];
          document.getElementById('image-selected-name').textContent = `${file.name} (${(file.size / (1024*1024*1024)).toFixed(2)} GB)`;
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
      licDropzone.addEventListener('click', () => licFileInput.click());
      licDropzone.addEventListener('dragover', (e) => {
        e.preventDefault();
        licDropzone.classList.add('dragover');
      });
      licDropzone.addEventListener('dragleave', () => licDropzone.classList.remove('dragover'));
      licDropzone.addEventListener('drop', (e) => {
        e.preventDefault();
        licDropzone.classList.remove('dragover');
        if (e.dataTransfer.files.length > 0) {
          this.handleLicenseFile(e.dataTransfer.files[0]);
        }
      });
      licFileInput.addEventListener('change', (e) => {
        if (e.target.files.length > 0) {
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
      if (autoTrigger) this.autoCheckStep1();
    } else if (this.currentStep === 2) {
      this.runPrecheck(autoTrigger);
    } else if (this.currentStep === 3) {
      if (autoTrigger) this.autoCheckStep3();
    } else if (this.currentStep === 4) {
      this.refreshImagesList();
      if (autoTrigger) this.autoCheckStep4();
    } else if (this.currentStep === 5) {
      this.fetchMachineId();
    }
  },

  // ==========================
  // 自动化智能判定与跳步引擎
  // ==========================
  async autoCheckStep1() {
    try {
      const status = await API.getStatus();
      if (status.connected) {
        showToast('✓ 机器人已连接 (192.168.123.164:22)，自动进入环境预检...', 'success', 2000);
        setTimeout(() => this.goToStep(2, true), 800);
        return;
      }

      // 尝试自动连接一次默认预置参数
      const res = await API.connect({ host: '192.168.123.164', port: 22, username: 'unitree', password: '123' });
      if (res.success) {
        showToast('✓ 成功自动连接机器人 192.168.123.164，自动进入环境预检...', 'success', 2000);
        App.updateStatus();
        setTimeout(() => this.goToStep(2, true), 800);
      } else {
        showToast('⚠️ 未能直连 192.168.123.164，请配置网卡或全网扫描', 'info');
      }
    } catch (err) {
      console.warn('Step 1 auto check failed:', err);
    }
  },

  async autoCheckStep3() {
    try {
      const res = await API.listImages();
      if (res.success && res.images && res.images.length > 0) {
        const found = res.images[0];
        const tag = `${found.repository}:${found.tag}`;
        showToast(`✓ 检测到机器人已存在镜像 [${tag}]，自动跳过导入步骤...`, 'success', 2000);

        // 检查第4步：如果 400 端口容器也已经存在并运行，直接连跳至第 5 步！
        try {
          const cRes = await API.getContainerStatus();
          if (cRes.success && cRes.data && (cRes.data.has_port_400 || cRes.data.running)) {
            const cName = cRes.data.container_name || 'vsis_g1';
            showToast(`✓ 检测到 400 端口容器 [${cName}] 运行中（已设置自启并正常启动），自动跳过第4步，进入第5步...`, 'success', 3000);
            setTimeout(() => this.goToStep(5, true), 800);
            return;
          }
        } catch (_) {}

        setTimeout(() => this.goToStep(4, true), 800);
      }
    } catch (err) {
      console.warn('Step 3 auto check failed:', err);
    }
  },

  async autoCheckStep4() {
    try {
      const res = await API.getContainerStatus();
      if (res.success && res.data) {
        const d = res.data;
        // 如果设备中存在一个 400 端口的容器，则说明程序已经设置好了自启并且已经正常启动，此时应该跳过第四步启动与自启
        if (d.has_port_400 || d.running) {
          const cName = d.container_name || 'vsis_g1';
          showToast(`✓ 检测到 400 端口容器 [${cName}] 运行中（已设置自启并正常启动），自动跳过此步骤...`, 'success', 3000);
          setTimeout(() => this.goToStep(5, true), 600);
          return;
        }

        // 未检测到 400 端口容器：自动执行容器拉起与自启写入
        showToast('⚙️ 未检测到 400 端口容器，正在自动拉起 vsis_g1 并配置开机自启...', 'info', 3000);
        this.startContainer(true); // 传入 true 表示自动化模式
      }
    } catch (err) {
      console.warn('Step 4 auto check failed:', err);
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

      // 智能判定：如果全部指标通过且为自动化模式，自动跳入第3步
      if (res.data.all_passed) {
        if (autoAdvance) {
          showToast('✓ 运行环境预检全部通过 (Docker/GPU/CH341/磁盘/架构)，自动进入镜像检测...', 'success', 2500);
          setTimeout(() => this.goToStep(3, true), 1000);
        }
      } else {
        showToast('⚠️ 检测到部分环境指标异常，请使用【一键修复】按钮解决', 'warning', 4000);
      }
    } catch (err) {
      container.innerHTML = `<div style="padding: 20px; color: var(--accent-red);">预检异常: ${err.message}</div>`;
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
          this.runPrecheck(true);
        });
      }
    } catch (err) {
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
  async startImageUpload() {
    const fileInput = document.getElementById('input-image-file');
    const pathInput = document.getElementById('input-local-tar-path');
    let localPath = pathInput ? pathInput.value.trim() : '';

    const formData = new FormData();
    if (fileInput && fileInput.files.length > 0) {
      formData.append('file', fileInput.files[0]);
    } else if (localPath) {
      formData.append('local_path', localPath);
    } else {
      showToast('请选取本地镜像包或填写镜像文件完整路径', 'warning');
      return;
    }

    showToast('开始 SFTP 上传镜像至机器人 /tmp 目录...', 'info');
    const uploadBox = document.getElementById('upload-progress-box');
    if (uploadBox) uploadBox.style.display = 'block';

    try {
      const res = await API.uploadImage(formData);
      if (!res.success) {
        showToast(`上传失败: ${res.msg}`, 'error');
        return;
      }

      // 启动轮询进度
      if (this.uploadInterval) clearInterval(this.uploadInterval);
      this.uploadInterval = setInterval(async () => {
        const prog = await API.getUploadProgress();
        this.updateUploadUI(prog);
        if (prog.status === 'completed') {
          clearInterval(this.uploadInterval);
          showToast('镜像上传成功！正在自动执行 docker load ...', 'success');
          document.getElementById('input-remote-load-path').value = res.remote_path;
          this.startDockerLoad(true); // 自动执行 docker load
        } else if (prog.status === 'error') {
          clearInterval(this.uploadInterval);
          showToast(`上传出错: ${prog.error_msg}`, 'error');
        }
      }, 500);

    } catch (err) {
      showToast(`上传请求异常: ${err.message}`, 'error');
    }
  },

  updateUploadUI(p) {
    const bar = document.getElementById('image-upload-bar');
    const pctText = document.getElementById('image-upload-pct');
    const infoText = document.getElementById('image-upload-info');
    if (bar) bar.style.width = `${p.percent}%`;
    if (pctText) pctText.textContent = `${p.percent}%`;
    if (infoText) {
      const mbTrans = (p.transferred_bytes / (1024*1024)).toFixed(1);
      const mbTotal = (p.total_bytes / (1024*1024)).toFixed(1);
      infoText.textContent = `${mbTrans} MB / ${mbTotal} MB | 速率: ${p.speed_mbps} MB/s | 剩余: ${p.eta_seconds}s`;
    }
  },

  async startDockerLoad(autoAdvance = false) {
    const pathInput = document.getElementById('input-remote-load-path');
    const remotePath = pathInput ? pathInput.value.trim() : '/tmp/rl_cu118_v2.tar.gz';

    showToast('正在远端执行 docker load -i ... (请稍候 1~3 分钟)', 'info');
    const consoleEl = document.getElementById('image-load-console');
    if (consoleEl) consoleEl.innerHTML = '<div class="log-info">正在执行 docker load ...</div>';

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
        }, (ok) => {
          if (ok) {
            showToast('Docker 镜像导入完成！自动进入容器启动...', 'success');
            this.refreshImagesList();
            if (autoAdvance) {
              setTimeout(() => this.goToStep(4, true), 1000);
            }
          } else {
            showToast('镜像导入异常，请查看日志', 'error');
          }
        });
      }
    } catch (err) {
      showToast(`执行异常: ${err.message}`, 'error');
    }
  },

  // ==========================
  // Step 4: 固化容器启动与自启动
  // ==========================
  async refreshImagesList() {
    try {
      const res = await API.listImages();
      const select = document.getElementById('select-docker-image');
      if (!select) return;

      select.innerHTML = '';
      if (!res.images || res.images.length === 0) {
        select.innerHTML = '<option value="rl_cu118:2.0">rl_cu118:2.0 (推荐默认)</option>';
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

  async startContainer(autoAdvance = false) {
    const select = document.getElementById('select-docker-image');
    const imgName = select && select.value ? select.value : 'rl_cu118:2.0';

    showToast(`正在启动固化容器 vsis_g1 (镜像: ${imgName}) ...`, 'info');
    const consoleEl = document.getElementById('container-start-console');
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
            showToast('✓ 容器 vsis_g1 已启动！正在写入开机自启动与 Robot ID...', 'success');
            await this.writeAutostartAndId();
            if (autoAdvance) {
              setTimeout(() => this.goToStep(5, true), 1000);
            }
          } else {
            showToast('容器启动失败，请检查上方日志', 'error');
          }
        });
      }
    } catch (err) {
      showToast(`启动异常: ${err.message}`, 'error');
    }
  },

  async writeAutostartAndId() {
    const robotId = document.getElementById('select-robot-id')?.value || 'A';
    showToast(`正在配置开机自启并写入 Robot ID [${robotId}] ...`, 'info');

    try {
      const res = await API.configAutostart(robotId);
      if (res.success) {
        showToast(res.msg, 'success');
      } else {
        showToast(res.msg, 'error');
      }
    } catch (err) {
      showToast(`写入失败: ${err.message}`, 'error');
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

  async handleLicenseFile(file) {
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

  async deployLicense(autoAdvance = false) {
    if (!this.lastLicenseContent) {
      showToast('请先选择或拖入 license.json 文件', 'warning');
      return;
    }

    const btn = document.getElementById('btn-deploy-license');
    if (btn) {
      btn.disabled = true;
      btn.textContent = '⏳ 正在部署并重启验证...';
    }

    showToast('正在写入 License 并重启运控进程校验日志...', 'info');
    try {
      const res = await API.deployLicense(this.lastLicenseContent);
      const resBox = document.getElementById('license-verify-result');
      if (res.success) {
        showToast('✓ License 部署成功！日志确认无 [SKIP] not licensed，即将进入下一步...', 'success', 2500);
        if (resBox && res.log_snippet) {
          const logCard = document.createElement('div');
          logCard.className = 'diag-alert success';
          logCard.style.marginTop = '12px';
          logCard.innerHTML = `
            <div style="flex: 1;">
              <div><b>✅ 部署与校验成功！</b> ${res.msg}</div>
              <div style="font-size: 0.76rem; color: #a7f3d0; margin-top: 4px; font-family: monospace; white-space: pre-wrap; max-height: 100px; overflow-y: auto;">${res.log_snippet}</div>
            </div>
            <button class="btn-copy-mini" onclick="copyToClipboard(${JSON.stringify(res.log_snippet)}, '主控验证日志已复制')">📋 复制日志</button>
          `;
          resBox.appendChild(logCard);
        }
        // 校验通过后直接自动进入第 6 步
        setTimeout(() => {
          this.goToStep(6, true);
        }, 1000);
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
      }
    } catch (err) {
      showToast(`部署 License 异常: ${err.message}`, 'error');
    } finally {
      if (btn) {
        btn.disabled = false;
        btn.textContent = '🚀 部署 License 至机器人';
      }
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
      this.goToStep(step);
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
