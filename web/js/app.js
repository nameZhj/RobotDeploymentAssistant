/**
 * VSISLAB 机器人助手 主应用控制器
 */
const App = {
  activeTab: 'tab-robot-control',
  statusInterval: null,

  async init() {
    this.bindTabEvents();
    this.bindConnectionEvents();
    this.bindDanceUpdateEvents();
    this.bindSettingsMenuEvents();
    this.bindOpsModalEvents();
    this.init3dPlayer();
    this.startStatusMonitor();
    this.initGlobalCopyEnhancers();

    // 初始化子模块
    if (typeof RobotControl !== 'undefined') {
      RobotControl.init();
    }
    Wizard.init();
    LogViewer.init();

    // 运行开机自检与主动 License 校验逻辑
    await this.runStartupCheck();
  },

  initGlobalCopyEnhancers() {
    // 1. 为终端控制台挂载浮动复制按钮 (跳过 #log-console-content，避免破坏其 Flex 滚动容器)
    document.querySelectorAll('.terminal-console').forEach(consoleEl => {
      if (consoleEl.id === 'log-console-content') return;
      if (consoleEl.parentElement && consoleEl.parentElement.classList.contains('console-wrapper')) return;

      const wrapper = document.createElement('div');
      wrapper.className = 'console-wrapper';
      consoleEl.parentNode.insertBefore(wrapper, consoleEl);
      wrapper.appendChild(consoleEl);

      const copyBtn = document.createElement('button');
      copyBtn.className = 'console-copy-btn';
      copyBtn.innerHTML = '📋 复制控制台输出';
      copyBtn.title = '复制当前控制台中的所有日志与错误输出';
      copyBtn.addEventListener('click', (e) => {
        e.preventDefault();
        e.stopPropagation();
        const text = consoleEl.innerText || consoleEl.textContent;
        copyToClipboard(text, '控制台输出内容已复制');
        const origHtml = copyBtn.innerHTML;
        copyBtn.innerHTML = '✅ 已复制';
        copyBtn.style.borderColor = '#10b981';
        copyBtn.style.color = '#10b981';
        copyBtn.style.opacity = '1';
        setTimeout(() => {
          copyBtn.innerHTML = origHtml;
          copyBtn.style.borderColor = '';
          copyBtn.style.color = '';
          copyBtn.style.opacity = '';
        }, 1500);
      });
      wrapper.appendChild(copyBtn);
    });

    // 2. 全局选中文本快捷复制增强
    document.addEventListener('keydown', (e) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'c') {
        const selection = window.getSelection()?.toString();
        if (selection && selection.length > 0) {
          try {
            navigator.clipboard.writeText(selection);
          } catch (_) { }
        }
      }
    });
  },

  bindSettingsMenuEvents() {
    const btn = document.getElementById('btn-settings-menu');
    const content = document.getElementById('settings-menu-content');
    if (btn && content) {
      btn.addEventListener('click', (e) => {
        e.stopPropagation();
        const isHidden = content.style.display === 'none';
        content.style.display = isHidden ? 'block' : 'none';
        if (isHidden) {
          this.refreshLicenseStatus();
        }
      });
      document.addEventListener('click', (e) => {
        if (!content.contains(e.target) && e.target !== btn) {
          content.style.display = 'none';
        }
      });
    }
  },

  async runStartupCheck() {
    try {
      const res = await API.startupCheck();
      this.updateStatusDisplay(res);

      if (res.connected) {
        // 主动校验 License 与部署全流程状态
        if (!res.first_time && res.has_license && res.license_valid && res.is_container_running && res.is_ctrl_running) {
          // 全套就绪且 License 校验通过：静默关闭向导，进入首页群控控制台
          Wizard.closeModal();
          this.switchTab('tab-robot-control');
        } else {
          // 未完成授权部署或 License 校验未通过：智能定位并调出向导对应步骤
          let targetStep = 1;
          let reason = '';

          if (!res.is_container_running) {
            reason = 'Docker 容器尚未部署运行';
            targetStep = 3;
          } else if (!res.has_license) {
            reason = '未检测到 License 授权文件';
            targetStep = 5;
          } else if (!res.license_valid) {
            reason = 'License 机器码不匹配或包含未授权舞蹈';
            targetStep = 5;
          } else if (!res.is_ctrl_running || !res.is_lora_running) {
            reason = '机载运控与通信程序尚未就绪';
            targetStep = 5;
          } else {
            reason = '首次向导配置未完成';
            targetStep = 1;
          }

          showToast(`⚠️ ${reason}，正在进入部署向导 (步骤 ${targetStep})...`, 'warning', 4000);
          Wizard.openModal(targetStep);
        }
      } else {
        // 机器人离线时保持在主界面，不弹窗（状态指示灯已体现）
        Wizard.closeModal();
      }
    } catch (err) {
      console.warn('Startup check failed:', err);
    }
  },

  bindTabEvents() {
    document.querySelectorAll('.tab-btn').forEach(btn => {
      btn.addEventListener('click', (e) => {
        const targetTab = btn.dataset.tab;
        this.switchTab(targetTab);
      });
    });
  },

  bindOpsModalEvents() {
    const btnOpen = document.getElementById('btn-open-ops-modal');
    const btnClose = document.getElementById('btn-close-ops-modal');
    const modal = document.getElementById('ops-modal');

    if (btnOpen) {
      btnOpen.addEventListener('click', (e) => {
        e.stopPropagation();
        this.openOpsModal('tab-3d-player');
      });
    }

    if (btnClose) {
      btnClose.addEventListener('click', () => {
        this.closeOpsModal();
      });
    }

    if (modal) {
      modal.addEventListener('click', (e) => {
        if (e.target === modal) {
          this.closeOpsModal();
        }
      });
    }

    document.addEventListener('keydown', (e) => {
      if (e.key === 'Escape' && modal && modal.style.display !== 'none') {
        this.closeOpsModal();
      }
    });
  },

  openOpsModal(tabId = 'tab-3d-player') {
    const modal = document.getElementById('ops-modal');
    const settingsContent = document.getElementById('settings-menu-content');
    if (settingsContent) settingsContent.style.display = 'none';

    if (modal) {
      modal.style.display = 'flex';
    }
    this.switchTab(tabId);
  },

  closeOpsModal() {
    const modal = document.getElementById('ops-modal');
    if (modal) {
      modal.style.display = 'none';
    }
    this.switchTab('tab-robot-control');
  },

  switchTab(tabId) {
    if (tabId === 'tab-dance-update') {
      tabId = 'tab-image';
    }
    if (tabId === 'tab-license') {
      tabId = 'tab-network';
    }
    this.activeTab = tabId;

    // 自动收起设置菜单下拉框
    const settingsContent = document.getElementById('settings-menu-content');
    if (settingsContent) {
      settingsContent.style.display = 'none';
    }

    // 若切入的是运维与调试子页面，确保 ops-modal 打开；若切回群控控制台，关闭 ops-modal
    const opsModal = document.getElementById('ops-modal');
    if (tabId !== 'tab-robot-control' && opsModal && opsModal.style.display === 'none') {
      opsModal.style.display = 'flex';
    } else if (tabId === 'tab-robot-control' && opsModal && opsModal.style.display !== 'none') {
      opsModal.style.display = 'none';
    }

    // 切换按钮高亮
    document.querySelectorAll('.tab-btn').forEach(btn => {
      btn.classList.toggle('active', btn.dataset.tab === tabId);
    });

    // 切换面板显示
    document.querySelectorAll('.tab-content-panel').forEach(panel => {
      panel.classList.toggle('active', panel.id === tabId);
    });

    // 如果切入 3D 播放器，触发 resize 保持视口正确
    if (tabId === 'tab-3d-player' && dancePlayer) {
      setTimeout(() => dancePlayer.onResize(), 60);
    } else if (tabId === 'tab-logs' && window.LogViewer) {
      LogViewer.fetchCurrentLogs();
    } else if (tabId === 'tab-network') {
      if (window.TabNetwork) TabNetwork.init();
      if (window.TabLicense) TabLicense.init();
    } else if (tabId === 'tab-precheck' && window.TabPrecheck) {
      TabPrecheck.run();
    } else if (tabId === 'tab-image' && window.TabImage) {
      TabImage.init();
    }
  },

  bindConnectionEvents() {
    const btnConnect = document.getElementById('btn-global-connect');
    const btnDisconnect = document.getElementById('btn-global-disconnect');

    if (btnConnect) {
      btnConnect.addEventListener('click', () => this.connect());
    }

    if (btnDisconnect) {
      btnDisconnect.addEventListener('click', () => this.disconnect());
    }
  },

  async connect() {
    const host = document.getElementById('input-host').value.trim();
    const port = document.getElementById('input-port').value.trim();
    const username = document.getElementById('input-username').value.trim();
    const password = document.getElementById('input-password').value;

    const dot = document.getElementById('status-dot');
    const text = document.getElementById('status-text');
    if (dot) dot.className = 'status-dot connecting';
    if (text) text.textContent = '连接中...';

    showToast(`正在连接 ${username}@${host}:${port} ...`, 'info');

    try {
      const res = await API.connect({ host, port, username, password });
      if (res.success) {
        showToast(res.msg, 'success');
        // 连接成功后，立即主动校验 License 与自启状态
        await this.runStartupCheck();
      } else {
        showToast(`连接失败: ${res.msg}`, 'error');
        this.updateStatus();
      }
    } catch (err) {
      showToast(`连接异常: ${err.message}`, 'error');
      this.updateStatus();
    }
  },

  async disconnect() {
    try {
      await API.disconnect();
      showToast('已断开连接', 'info');
      this.updateStatus();
    } catch (err) {
      showToast(`断开异常: ${err.message}`, 'error');
    }
  },

  startStatusMonitor() {
    if (this.statusInterval) {
      clearInterval(this.statusInterval);
      this.statusInterval = null;
    }
    this.updateStatus();
    this.statusInterval = setInterval(() => this.updateStatus(), 4000);
  },

  updateStatusDisplay(res) {
    const dot = document.getElementById('status-dot');
    const text = document.getElementById('status-text');
    const info = document.getElementById('conn-info-display');

    const isConnected = !!(res && res.connected);

    if (isConnected) {
      if (dot) dot.className = 'status-dot online';
      if (text) text.textContent = res.first_time ? '在线 (待部署)' : '在线 (已就绪)';
      if (info) {
        info.textContent = `${res.host || '192.168.123.164'}:${res.port || 22}`;
      }
      if (this.lastConnectedState === false) {
        showToast(`🎉 成功连接机器人 (${res.host || '192.168.123.164'})`, 'success', 3500);
      }
    } else {
      const isAuto = res?.auto_detecting || res?.auto_connect_enabled;
      if (dot) {
        dot.className = isAuto ? 'status-dot detecting' : 'status-dot';
      }
      if (text) {
        text.textContent = isAuto ? '探测中...' : '未连接';
      }
      if (info) {
        info.textContent = `${res?.host || '192.168.123.164'}:${res?.port || 22}`;
      }
    }

    if (isConnected && this.lastConnectedState === false) {
      // 刚连接成功时，自动触发一次 License 状态拉取
      this.refreshLicenseStatus();
    }

    this.lastConnectedState = isConnected;

    // 若当前响应中包含授权信息，同步更新设置菜单
    if (res && 'has_license' in res) {
      this.updateLicenseDisplay(res);
    }
  },

  async refreshLicenseStatus() {
    const licStatusEl = document.getElementById('settings-license-status');
    if (!licStatusEl) return;

    if (!this.lastConnectedState) {
      licStatusEl.innerHTML = `
        <div style="color: var(--text-muted); font-size: 0.78rem; padding: 4px 0;">
          ⚪ 机器人离线 (请先在顶部连接)
        </div>
      `;
      return;
    }

    try {
      const res = await API.getLicenseStatus();
      this.updateLicenseDisplay(res);
    } catch (err) {
      console.warn('获取 License 状态失败:', err);
    }
  },

  updateLicenseDisplay(res) {
    const licStatusEl = document.getElementById('settings-license-status');
    if (!licStatusEl) return;

    if (!res || !res.connected) {
      licStatusEl.innerHTML = `
        <div style="color: var(--text-muted); font-size: 0.78rem; padding: 4px 0;">
          ⚪ 机器人离线 (请先在顶部连接)
        </div>
      `;
      return;
    }

    if (res.has_license) {
      const p = res.license_data || {};
      const exp = p.expire_date || '永久授权';
      const dances = p.dance_count !== undefined ? p.dance_count : (p.dances?.length || 0);
      const customer = p.customer || '商业客户';
      const model = p.model || 'Unitree G1';

      if (res.license_valid) {
        licStatusEl.innerHTML = `
          <div style="background: rgba(16, 185, 129, 0.12); border: 1px solid rgba(16, 185, 129, 0.35); border-radius: 6px; padding: 8px 10px; margin-bottom: 6px;">
            <div style="color: #34d399; font-weight: 700; font-size: 0.84rem; display: flex; align-items: center; justify-content: space-between; margin-bottom: 4px;">
              <span>✅ 授权已生效</span>
              <span class="card-badge" style="font-size: 0.65rem; padding: 1px 5px;">${model}</span>
            </div>
            <div style="font-size: 0.75rem; color: #a7f3d0; line-height: 1.5;">
              <div><b>授权客户:</b> ${customer}</div>
              <div><b>有效期限:</b> <span style="color: #6ee7b7; font-weight: 600;">${exp}</span></div>
              <div><b>包含舞蹈:</b> <span style="color: #6ee7b7; font-weight: 600;">${dances}</span> 首动作</div>
            </div>
          </div>
        `;
      } else {
        licStatusEl.innerHTML = `
          <div style="background: rgba(239, 68, 68, 0.12); border: 1px solid rgba(239, 68, 68, 0.35); border-radius: 6px; padding: 8px 10px; margin-bottom: 6px;">
            <div style="color: #f87171; font-weight: 700; font-size: 0.84rem; margin-bottom: 4px;">❌ 授权校验未通过</div>
            <div style="font-size: 0.75rem; color: #fca5a5; line-height: 1.4;">
              <div>日志检测到 <code>[SKIP] not licensed</code></div>
              <div style="color: #f87171; margin-top: 2px;">可能由于机器码不匹配，请重新导入</div>
            </div>
          </div>
        `;
      }
    } else {
      licStatusEl.innerHTML = `
        <div style="background: rgba(245, 158, 11, 0.12); border: 1px solid rgba(245, 158, 11, 0.35); border-radius: 6px; padding: 8px 10px; margin-bottom: 6px;">
          <div style="color: #fbbf24; font-weight: 700; font-size: 0.84rem; margin-bottom: 2px;">⚠️ 未检测到 License 文件</div>
          <div style="font-size: 0.75rem; color: #fde68a;">机器人机载缺少 license.json 授权文件</div>
        </div>
      `;
    }
  },

  async updateStatus() {
    try {
      const res = await API.getStatus();
      this.updateStatusDisplay(res);
    } catch (err) {
      // ignore
    }
  },

  bindDanceUpdateEvents() {
    const folderInput = document.getElementById('input-update-folder');
    const zipInput = document.getElementById('input-update-zip');
    const dropzone = document.getElementById('dropzone-update-zip');
    const textFilename = document.getElementById('text-zip-filename');
    const textFilesize = document.getElementById('text-zip-filesize');
    const btnBrowse = document.getElementById('btn-browse-dance-folder');
    const btnSubmitUpdate = document.getElementById('btn-submit-dance-update');

    // 状态存储当前选中的单个项（单 zip 或单文件夹）
    let currentSelectedTarget = null;

    function updateSelectionDisplay(target) {
      currentSelectedTarget = target;
      if (!target) {
        if (textFilename) textFilename.textContent = '点击选择动作文件夹 / 拖拽动作包至此处';
        if (textFilesize) textFilesize.textContent = '支持点击选择文件夹，或拖拽单个动作文件夹 / .zip 压缩包导入';
        if (dropzone) {
          dropzone.style.borderColor = 'rgba(56, 189, 248, 0.35)';
          dropzone.style.background = 'rgba(14, 165, 233, 0.04)';
        }
        return;
      }
      if (target.type === 'zip') {
        const sizeMb = (target.file.size / (1024 * 1024)).toFixed(2);
        if (textFilename) textFilename.textContent = `📦 ${target.file.name}`;
        if (textFilesize) textFilesize.textContent = `文件大小: ${sizeMb} MB | 格式: .zip 压缩包`;
      } else if (target.type === 'local_folder') {
        if (textFilename) textFilename.textContent = `📁 动作文件夹: ${target.name} (共 ${target.files_count} 个文件)`;
        if (textFilesize) textFilesize.textContent = `路径: ${target.path} | 大小: ${target.size_mb} MB | 将自动覆盖至 /secure/config_vsis`;
      } else if (target.type === 'folder') {
        const sizeMb = (target.totalSize / (1024 * 1024)).toFixed(2);
        if (textFilename) textFilename.textContent = `📁 动作文件夹: ${target.name} (共 ${target.files.length} 个文件)`;
        if (textFilesize) textFilesize.textContent = `总大小: ${sizeMb} MB | 将自动打包并覆盖至 /secure/config_vsis`;
      }
      if (dropzone) {
        dropzone.style.borderColor = 'var(--accent-cyan)';
        dropzone.style.background = 'rgba(14, 165, 233, 0.12)';
      }
    }

    // 打开文件夹选择对话框（优先 Windows 原生目录选择器，兼容回退 input）
    async function triggerFolderPicker() {
      try {
        const res = await API.selectFolder();
        if (res && res.success && res.folder_path) {
          updateSelectionDisplay({
            type: 'local_folder',
            path: res.folder_path,
            name: res.folder_name,
            files_count: res.files_count,
            size_mb: res.size_mb
          });
          showToast(`已选择动作文件夹: ${res.folder_name} (包含 ${res.files_count} 个文件)`, 'success');
          return;
        } else if (res && res.msg && !res.msg.includes('取消')) {
          showToast(res.msg, 'warning');
        }
      } catch (_) {
        if (folderInput) folderInput.click();
      }
    }

    if (btnBrowse) {
      btnBrowse.addEventListener('click', (e) => {
        e.stopPropagation();
        triggerFolderPicker();
      });
    }

    if (dropzone) {
      dropzone.addEventListener('click', () => {
        triggerFolderPicker();
      });
    }

    // input 回退监听
    if (folderInput) {
      folderInput.addEventListener('change', (e) => {
        const files = Array.from(e.target.files || []);
        if (files.length > 0) {
          let folderName = '动作文件夹';
          if (files[0].webkitRelativePath) {
            folderName = files[0].webkitRelativePath.split('/')[0] || folderName;
          }
          const totalSize = files.reduce((acc, f) => acc + f.size, 0);
          updateSelectionDisplay({ type: 'folder', files: files, name: folderName, totalSize: totalSize });
        }
      });
    }

    if (zipInput) {
      zipInput.addEventListener('change', (e) => {
        const file = e.target.files?.[0];
        if (file) {
          updateSelectionDisplay({ type: 'zip', file: file });
        }
      });
    }

    // 递归遍历拖拽目录树
    async function traverseFileTree(item, path = '') {
      if (item.isFile) {
        return new Promise((resolve) => {
          item.file((file) => {
            file.relativePath = path + file.name;
            resolve([file]);
          }, () => resolve([]));
        });
      } else if (item.isDirectory) {
        const dirReader = item.createReader();
        const entries = await new Promise((resolve) => {
          dirReader.readEntries((entries) => resolve(entries || []), () => resolve([]));
        });
        const promises = entries.map((entry) => traverseFileTree(entry, path + item.name + '/'));
        const nested = await Promise.all(promises);
        return nested.flat();
      }
      return [];
    }

    // 拖拽支持 (支持单个 zip 压缩包或单个动作文件夹)
    if (dropzone) {
      dropzone.addEventListener('dragover', (e) => {
        e.preventDefault();
        e.stopPropagation();
        dropzone.style.borderColor = 'var(--accent-cyan)';
        dropzone.style.background = 'rgba(14, 165, 233, 0.18)';
      });
      dropzone.addEventListener('dragleave', (e) => {
        e.preventDefault();
        e.stopPropagation();
        if (!currentSelectedTarget) {
          dropzone.style.borderColor = 'rgba(56, 189, 248, 0.35)';
          dropzone.style.background = 'rgba(14, 165, 233, 0.04)';
        }
      });
      dropzone.addEventListener('drop', async (e) => {
        e.preventDefault();
        e.stopPropagation();

        const items = e.dataTransfer.items;
        if (items && items.length > 0) {
          const entries = [];
          for (let i = 0; i < items.length; i++) {
            const entry = items[i].webkitGetAsEntry ? items[i].webkitGetAsEntry() : null;
            if (entry) entries.push(entry);
          }

          if (entries.length === 1 && entries[0].isFile && entries[0].name.toLowerCase().endsWith('.zip')) {
            const file = e.dataTransfer.files[0];
            updateSelectionDisplay({ type: 'zip', file: file });
            return;
          }

          if (entries.length > 0) {
            const promises = entries.map((entry) => traverseFileTree(entry, ''));
            const filesArrays = await Promise.all(promises);
            const allFiles = filesArrays.flat();
            if (allFiles.length > 0) {
              const folderName = entries[0].name || '动作文件夹';
              const totalSize = allFiles.reduce((acc, f) => acc + f.size, 0);
              updateSelectionDisplay({ type: 'folder', files: allFiles, name: folderName, totalSize: totalSize });
              return;
            }
          }
        }

        if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
          const files = Array.from(e.dataTransfer.files);
          if (files.length === 1 && files[0].name.toLowerCase().endsWith('.zip')) {
            updateSelectionDisplay({ type: 'zip', file: files[0] });
          } else {
            const totalSize = files.reduce((acc, f) => acc + f.size, 0);
            updateSelectionDisplay({ type: 'folder', files: files, name: files[0].name, totalSize: totalSize });
          }
        }
      });
    }

    // 提交上传与自动重启
    if (btnSubmitUpdate) {
      btnSubmitUpdate.addEventListener('click', async () => {
        const destPath = document.getElementById('input-update-dest-path')?.value.trim() || '/secure/config_vsis';
        const legacyConsole = document.getElementById('dance-update-result');

        const logLine = (msg, isErr = false) => {
          if (window.TabImage && typeof TabImage.appendLog === 'function') {
            TabImage.appendLog(msg, isErr, '💃');
          } else {
            const consoleEl = document.getElementById('tp-unified-console');
            if (consoleEl) {
              const div = document.createElement('div');
              div.className = isErr ? 'log-error' : (String(msg).includes('SUCCESS') || String(msg).includes('🎉') || String(msg).includes('完成') ? 'log-success' : 'log-info');
              div.textContent = `[${new Date().toTimeString().split(' ')[0]}] [💃] ${msg}`;
              consoleEl.appendChild(div);
              consoleEl.scrollTop = consoleEl.scrollHeight;
            }
          }
          if (legacyConsole) {
            const div = document.createElement('div');
            div.className = isErr ? 'log-error' : 'log-info';
            div.textContent = msg;
            legacyConsole.appendChild(div);
          }
        };

        if (!currentSelectedTarget) {
          showToast('请先选择动作文件夹或拖拽动作包 (.zip / 文件夹)', 'warning');
          return;
        }

        const formData = new FormData();
        formData.append('dest_path', destPath);

        let displayTargetName = '';
        if (currentSelectedTarget.type === 'local_folder') {
          displayTargetName = `${currentSelectedTarget.name} (${currentSelectedTarget.files_count} 个文件)`;
          formData.append('local_path', currentSelectedTarget.path);
        } else if (currentSelectedTarget.type === 'zip') {
          displayTargetName = currentSelectedTarget.file.name;
          formData.append('zip_file', currentSelectedTarget.file);
        } else if (currentSelectedTarget.type === 'folder') {
          displayTargetName = `${currentSelectedTarget.name} (${currentSelectedTarget.files.length} 个文件)`;
          currentSelectedTarget.files.forEach((file) => {
            formData.append('files', file);
            formData.append('paths', file.relativePath || file.webkitRelativePath || file.name);
          });
        }

        logLine(`⏳ 正在准备上传动作包 [${displayTargetName}] ...`);

        btnSubmitUpdate.disabled = true;
        btnSubmitUpdate.textContent = '⏳ 正在上传并解压覆盖中...';

        showToast(`正在上传动作包 [${displayTargetName}] 并解压至 ${destPath} ...`, 'info');
        try {
          const res = await API.updateDance(formData);
          if (res.success && res.task_id) {
            API.listenStream(res.task_id, (line, isErr) => {
              logLine(line, isErr);
            }, (ok) => {
              btnSubmitUpdate.disabled = false;
              btnSubmitUpdate.textContent = '🚀 一键上传并导入舞蹈动作包';
              if (ok) {
                logLine(`🎉 动作包 [${displayTargetName}] 导入、解压覆盖至 ${destPath} 与跳舞程序自动热重启已完成！`, false);
                showToast(`🎉 动作包 [${displayTargetName}] 导入、解压覆盖与跳舞程序自动热重启已完成！`, 'success', 5000);
                if (window.TabImage && typeof TabImage.checkProcessStatus === 'function') {
                  TabImage.checkProcessStatus();
                }
              } else {
                logLine('舞蹈动作包导入遇到异常，请查看统一执行日志', true);
                showToast('舞蹈动作包导入遇到异常，请查看右侧执行日志', 'error');
              }
            });
          } else {
            btnSubmitUpdate.disabled = false;
            btnSubmitUpdate.textContent = '🚀 一键上传并导入舞蹈动作包';
            showToast(`更新失败: ${res.msg || '未知错误'}`, 'error');
            logLine(`❌ 更新失败: ${res.msg || '未知错误'}`, true);
          }
        } catch (err) {
          btnSubmitUpdate.disabled = false;
          btnSubmitUpdate.textContent = '🚀 一键上传并导入舞蹈动作包';
          showToast(`更新异常: ${err.message}`, 'error');
          logLine(`❌ 异常: ${err.message}`, true);
        }
      });
    }
  },




  async init3dPlayer() {
    try {
      if (typeof DancePlayer3D !== 'undefined') {
        dancePlayer = new DancePlayer3D('dance3d-viewport');
      } else {
        console.warn('DancePlayer3D 类尚未就绪');
      }
    } catch (err) {
      console.error('初始化 3D 舞蹈播放器失败:', err);
    }

    // 绑定播放控制条
    const btnPlay = document.getElementById('btn-dance-play');
    const scrubber = document.getElementById('dance-scrubber');
    const selectSpeed = document.getElementById('select-dance-speed');
    const chkLoop = document.getElementById('chk-dance-loop');
    const btnResetCam = document.getElementById('btn-reset-cam');

    if (btnPlay) {
      btnPlay.addEventListener('click', () => { if (dancePlayer) dancePlayer.togglePlay(); });
    }

    if (scrubber) {
      scrubber.addEventListener('input', (e) => { if (dancePlayer) dancePlayer.seek(e.target.value); });
    }

    if (selectSpeed) {
      selectSpeed.addEventListener('change', (e) => {
        if (dancePlayer) dancePlayer.playbackSpeed = parseFloat(e.target.value);
      });
    }

    if (chkLoop) {
      chkLoop.addEventListener('change', (e) => {
        if (dancePlayer) dancePlayer.isLoop = e.target.checked;
      });
    }

    if (btnResetCam) {
      btnResetCam.addEventListener('click', () => { if (dancePlayer) dancePlayer.resetCamera(); });
    }

    // 自定义动作/模型导入与拖拽上传 (合并 NPZ 与 ZIP，自动识别)
    const inputCustomDanceFile = document.getElementById('input-custom-dance-file');
    const btnBrowseZip = document.getElementById('btn-browse-dance-zip');
    const btnSubmitZip = document.getElementById('btn-submit-zip-path');
    const inputZipPath = document.getElementById('input-dance-zip-path');

    // ZIP 模型与动作包上传处理
    const handleZipFile = async (file) => {
      if (!file || !file.name || !file.name.toLowerCase().endsWith('.zip')) {
        showToast('请选择有效的 .zip 格式机器人模型或动作压缩包', 'warning');
        return;
      }
      showToast(`正在上传并解压解析 [${file.name}] 至 preview 目录...`, 'info', 3500);
      const formData = new FormData();
      formData.append('file', file);
      try {
        const res = await API.importDanceZip(formData);
        if (res && res.success) {
          showToast(res.msg || `✓ 成功导入并解析: ${res.dance_name || file.name}`, 'success');
          await this.refresh3dDanceList(res.dance_name);
          if (res.frames && res.frames.length > 0) {
            dancePlayer.loadDance(res);
          }
        } else {
          showToast(`导入失败: ${res?.msg || '未知错误'}`, 'error');
        }
      } catch (err) {
        showToast(`导入异常: ${err.message}`, 'error');
      }
    };

    // NPZ 动捕动作批量上传处理
    const handleNpzFiles = async (fileList) => {
      const files = Array.from(fileList || []).filter(f => f && f.name && f.name.toLowerCase().endsWith('.npz'));
      if (files.length === 0) {
        showToast('未检测到有效的 .npz 格式动捕文件', 'warning');
        return;
      }

      showToast(`正在批量导入 ${files.length} 个动作文件，请稍候...`, 'info', 2500);

      const uploadTasks = files.map(async (file) => {
        const formData = new FormData();
        formData.append('file', file);
        try {
          const res = await API.uploadNpz(formData);
          return { file, success: res.success, data: res, msg: res.msg };
        } catch (err) {
          return { file, success: false, data: null, msg: err.message };
        }
      });

      const results = await Promise.all(uploadTasks);
      const succeeded = results.filter(r => r.success);
      const failed = results.filter(r => !r.success);

      if (failed.length > 0) {
        for (const f of failed) {
          showToast(`导入 [${f.file.name}] 失败: ${f.msg}`, 'error');
        }
      }

      if (succeeded.length > 0) {
        showToast(`✓ 成功导入 ${succeeded.length} 个动捕动作文件！`, 'success');
        const lastSuccess = succeeded[succeeded.length - 1];
        if (lastSuccess && lastSuccess.data) {
          dancePlayer.loadDance(lastSuccess.data);
        }
        await this.refresh3dDanceList(lastSuccess ? (lastSuccess.data.dance_name || lastSuccess.file.name.replace('.npz', '')) : null);
      }
    };

    // 统一处理任意文件列表 (自动识别 .zip 和 .npz)
    const handleUnifiedFiles = async (fileList) => {
      const files = Array.from(fileList || []);
      const zipFiles = files.filter(f => f && f.name && f.name.toLowerCase().endsWith('.zip'));
      const npzFiles = files.filter(f => f && f.name && f.name.toLowerCase().endsWith('.npz'));

      if (zipFiles.length === 0 && npzFiles.length === 0) {
        showToast('请选择或拖入有效的 .zip (机器人模型) 或 .npz (动捕动作) 文件', 'warning');
        return;
      }

      for (const zf of zipFiles) {
        await handleZipFile(zf);
      }
      if (npzFiles.length > 0) {
        await handleNpzFiles(npzFiles);
      }
    };

    // 本地文件绝对路径导入处理 (自动识别 .zip 和 .npz)
    const handleFilePath = async (pathStr) => {
      const p = String(pathStr || '').trim().replace(/^["']|["']$/g, '');
      if (!p) {
        showToast('请输入有效的本地文件绝对路径 (.zip 或 .npz)', 'warning');
        return;
      }
      if (btnSubmitZip) {
        btnSubmitZip.disabled = true;
        btnSubmitZip.textContent = '⏳ 解析中...';
      }
      showToast(`正在从本地路径读取并解析文件至 preview 目录...`, 'info', 3000);
      try {
        const res = await API.importDanceZip({ path: p });
        if (res && res.success) {
          showToast(res.msg || `✓ 成功导入并解析: ${res.dance_name || '模型动作'}`, 'success');
          await this.refresh3dDanceList(res.dance_name);
          if (res.frames && res.frames.length > 0) {
            dancePlayer.loadDance(res);
          }
        } else {
          showToast(`解析导入失败: ${res?.msg || '未知错误'}`, 'error');
        }
      } catch (err) {
        showToast(`请求异常: ${err.message}`, 'error');
      } finally {
        if (btnSubmitZip) {
          btnSubmitZip.disabled = false;
          btnSubmitZip.textContent = '🚀 解析播放';
        }
      }
    };

    // 绑定统一导入动作/模型按钮事件 (.zip / .npz)
    if (inputCustomDanceFile) {
      inputCustomDanceFile.addEventListener('change', async (e) => {
        const selected = Array.from(e.target.files || []);
        e.target.value = '';
        await handleUnifiedFiles(selected);
      });
    }

    if (btnBrowseZip) {
      btnBrowseZip.addEventListener('click', async () => {
        try {
          const res = await API.browseDanceZip();
          if (res && res.success && res.file_path) {
            if (inputZipPath) inputZipPath.value = res.file_path;
            showToast(`已选择文件: ${res.filename}，点击【🚀 解析播放】立即加载运行`, 'info', 3000);
          } else if (res && res.msg && !res.msg.includes('取消')) {
            showToast(res.msg, 'warning');
          }
        } catch (e) {
          showToast(`浏览异常: ${e.message}`, 'error');
        }
      });
    }

    if (btnSubmitZip) {
      btnSubmitZip.addEventListener('click', async () => {
        const p = inputZipPath ? inputZipPath.value : '';
        await handleFilePath(p);
      });
    }

    if (inputZipPath) {
      inputZipPath.addEventListener('keydown', async (e) => {
        if (e.key === 'Enter') {
          e.preventDefault();
          const p = inputZipPath.value;
          await handleFilePath(p);
        }
      });
    }

    // 全局防默认打开文件，并在用户拖入任意窗口区域时智能分发至 3D 动作导入
    window.addEventListener('dragover', (e) => {
      e.preventDefault();
      if (e.dataTransfer) e.dataTransfer.dropEffect = 'copy';
    });

    window.addEventListener('drop', async (e) => {
      e.preventDefault();
      const files = e.dataTransfer ? Array.from(e.dataTransfer.files) : [];
      if (files && files.length > 0) {
        const hasDance = files.some(f => {
          const n = (f && f.name) ? f.name.toLowerCase() : '';
          return n.endsWith('.zip') || n.endsWith('.npz');
        });
        if (hasDance) {
          if (typeof App !== 'undefined' && typeof App.openOpsModal === 'function') {
            App.openOpsModal('tab-3d-player');
          }
          await handleUnifiedFiles(files);
        }
      }
    });

    // 拖拽多区域高亮与监听（支持拖入 3D 面板、侧边栏列表或 3D 视口，同时支持 .zip 与 .npz）
    const dropZones = [
      document.getElementById('tab-3d-player'),
      document.querySelector('.player3d-sidebar'),
      document.getElementById('dance-3d-list'),
      document.querySelector('.player3d-container'),
      document.getElementById('dance3d-viewport')
    ].filter(Boolean);

    let dragCounter = 0;
    const setDragState = (isOver) => {
      const sb = document.querySelector('.player3d-sidebar');
      const container = document.querySelector('.player3d-container');
      if (sb) {
        sb.style.borderColor = isOver ? 'var(--accent-cyan)' : '';
        sb.style.boxShadow = isOver ? 'inset 0 0 20px rgba(0, 240, 255, 0.25)' : '';
      }
      if (container) {
        container.style.borderColor = isOver ? 'var(--accent-cyan)' : '';
      }
    };

    dropZones.forEach(zone => {
      zone.addEventListener('dragenter', (e) => {
        e.preventDefault();
        e.stopPropagation();
        dragCounter++;
        setDragState(true);
        if (e.dataTransfer) e.dataTransfer.dropEffect = 'copy';
      });

      zone.addEventListener('dragover', (e) => {
        e.preventDefault();
        e.stopPropagation();
        if (e.dataTransfer) e.dataTransfer.dropEffect = 'copy';
      });

      zone.addEventListener('dragleave', (e) => {
        e.preventDefault();
        e.stopPropagation();
        dragCounter--;
        if (dragCounter <= 0) {
          dragCounter = 0;
          setDragState(false);
        }
      });

      zone.addEventListener('drop', async (e) => {
        e.preventDefault();
        e.stopPropagation();
        dragCounter = 0;
        setDragState(false);
        const files = e.dataTransfer ? Array.from(e.dataTransfer.files) : [];
        if (files && files.length > 0) {
          await handleUnifiedFiles(files);
        }
      });
    });

    // 加载舞蹈列表
    this.refresh3dDanceList();
  },

  async refresh3dDanceList(preferredActiveName = null) {
    const listContainer = document.getElementById('dance-3d-list');
    if (!listContainer) return;

    try {
      const res = await API.list3dDances();
      if (!res.success) return;

      listContainer.innerHTML = '';

      if (!res.dances || res.dances.length === 0) {
        listContainer.innerHTML = `
          <div style="text-align: center; color: var(--text-muted); font-size: 0.8rem; padding: 25px 10px; line-height: 1.6;">
            📭 暂无舞蹈动作或模型<br>
          </div>
        `;
        if (dancePlayer) {
          dancePlayer.clear();
        }
        return;
      }

      let matchedBtn = null;

      for (const d of res.dances) {
        const item = document.createElement('div');
        item.className = 'dance-item-btn';
        item.dataset.id = d.id;

        const modelBadge = d.has_robot_model
          ? `<span style="font-size: 0.65rem; background: rgba(14, 165, 233, 0.22); color: #38bdf8; border: 1px solid rgba(14, 165, 233, 0.45); border-radius: 4px; padding: 1px 5px; font-weight: 700; white-space: nowrap;">🤖 3D实体</span>`
          : `<span style="font-size: 0.65rem; background: rgba(168, 85, 247, 0.2); color: #c084fc; border: 1px solid rgba(168, 85, 247, 0.4); border-radius: 4px; padding: 1px 5px; font-weight: 600; white-space: nowrap;">💃 动捕</span>`;

        item.innerHTML = `
          <div style="flex: 1; min-width: 0; padding-right: 6px;">
            <div style="font-weight: 600; font-size: 0.84rem; display: flex; align-items: center; gap: 5px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;" title="${d.name}">
              <span style="overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">🎵 ${d.name}</span>
              ${modelBadge}
            </div>
            <div style="font-size: 0.72rem; color: var(--text-muted); margin-top: 2px;">${d.duration}s | ${d.frames} 帧 (50fps)</div>
          </div>
          <div style="display: flex; align-items: center; gap: 6px;">
            <button class="btn-delete-dance" title="彻底删除此动作" style="background: none; border: none; cursor: pointer; color: #ef4444; padding: 2px 4px; font-size: 0.85rem; border-radius: 4px; opacity: 0.6; transition: all 0.2s;">🗑️</button>
            <span style="color: var(--accent-cyan); font-size: 0.8rem;">▶</span>
          </div>
        `;

        // 绑定删除按钮
        const delBtn = item.querySelector('.btn-delete-dance');
        if (delBtn) {
          delBtn.addEventListener('mouseenter', () => { delBtn.style.opacity = '1.0'; });
          delBtn.addEventListener('mouseleave', () => { delBtn.style.opacity = '0.6'; });
          delBtn.addEventListener('click', async (e) => {
            e.stopPropagation();
            if (confirm(`确定要彻底删除动作【${d.name}】吗？`)) {
              try {
                const delRes = await API.delete3dDance(d.id);
                if (delRes.success) {
                  showToast(`✓ 已删除动作: ${d.name}`, 'warning');
                  // 若删除的是当前正在播放的动作，立即清空舞台
                  if (dancePlayer && dancePlayer.currentDanceData &&
                    (dancePlayer.currentDanceData.dance_name === d.name || dancePlayer.currentDanceData.dance_id === d.id)) {
                    dancePlayer.clear();
                  }
                  await this.refresh3dDanceList();
                } else {
                  showToast(`删除失败: ${delRes.msg}`, 'error');
                }
              } catch (err) {
                showToast(`删除异常: ${err.message}`, 'error');
              }
            }
          });
        }

        // 绑定动作切换播放
        item.addEventListener('click', async () => {
          document.querySelectorAll('.dance-item-btn').forEach(b => b.classList.remove('active'));
          item.classList.add('active');
          const danceData = await API.get3dDance(d.id);
          if (danceData.success) {
            dancePlayer.loadDance(danceData);
          }
        });

        listContainer.appendChild(item);

        if (preferredActiveName && (d.name === preferredActiveName || d.id === preferredActiveName)) {
          matchedBtn = item;
        }
      }

      // 激活选中项
      if (matchedBtn) {
        document.querySelectorAll('.dance-item-btn').forEach(b => b.classList.remove('active'));
        matchedBtn.classList.add('active');
      } else if (!dancePlayer.currentDanceData && res.dances.length > 0) {
        const first = res.dances[0];
        const firstData = await API.get3dDance(first.id);
        if (firstData.success) {
          dancePlayer.loadDance(firstData);
          const firstBtn = listContainer.querySelector('.dance-item-btn');
          if (firstBtn) firstBtn.classList.add('active');
        }
      }
    } catch (err) {
      console.error('加载 3D 舞蹈列表失败:', err);
    }
  }
};

window.addEventListener('DOMContentLoaded', () => {
  App.init();
});
