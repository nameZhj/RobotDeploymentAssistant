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
            targetStep = 4;
          } else if (!res.license_valid) {
            reason = 'License 机器码不匹配或包含未授权舞蹈';
            targetStep = 4;
          } else if (!res.is_ctrl_running || !res.is_lora_running) {
            reason = '机载运控与通信程序尚未就绪';
            targetStep = 4;
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
        this.openOpsModal('tab-network');
      });
    }

    const btnStudioWindow = document.getElementById('btn-open-studio-window');
    if (btnStudioWindow) {
      btnStudioWindow.addEventListener('click', (e) => {
        e.stopPropagation();
        fetch('/api/system/open-studio', { method: 'POST' })
          .then(res => res.json())
          .then(data => {
            if (typeof showToast === 'function') {
              showToast(data.msg || '正在启动舞台编导控制台...', data.success ? 'success' : 'warning');
            }
          })
          .catch(err => {
            console.error('Launch studio error:', err);
            if (typeof showToast === 'function') {
              showToast('启动舞台编导服务通信异常', 'error');
            }
          });
      });
    }

    const btnNetworkMgr = document.getElementById('btn-open-network-mgr');
    if (btnNetworkMgr) {
      btnNetworkMgr.addEventListener('click', (e) => {
        e.stopPropagation();
        this.openOpsModal('tab-network');
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

    this.bindOpsConsoleToggles();
  },

  // 运维中心底部控制台条：展开 / 收起切换，展开状态记忆在 localStorage
  bindOpsConsoleToggles() {
    const strips = document.querySelectorAll('.ops-console-strip');
    if (!strips.length) return;
    const STORAGE_KEY = 'opsConsoleExpanded';
    let expanded = false;
    try { expanded = localStorage.getItem(STORAGE_KEY) === '1'; } catch (_) {}

    const apply = (strip, isExpanded) => {
      strip.classList.toggle('expanded', isExpanded);
      const btn = strip.querySelector('.ops-console-toggle');
      if (btn) {
        btn.textContent = isExpanded ? '⤡ 收起' : '⤢ 展开';
        btn.setAttribute('aria-expanded', isExpanded ? 'true' : 'false');
      }
    };

    strips.forEach(strip => {
      apply(strip, expanded);
      const btn = strip.querySelector('.ops-console-toggle');
      if (btn && !btn.dataset.bound) {
        btn.dataset.bound = '1';
        btn.addEventListener('click', () => {
          expanded = !strip.classList.contains('expanded');
          strips.forEach(s => apply(s, expanded));
          try { localStorage.setItem(STORAGE_KEY, expanded ? '1' : '0'); } catch (_) {}
        });
      }
    });
  },

  openOpsModal(tabId = 'tab-network') {
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
    if (tabId === 'tab-license' || tabId === 'tab-3d-player') {
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

    if (tabId === 'tab-logs' && window.LogViewer) {
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
    const hasSsh = !!(res && res.ssh_connected);

    if (isConnected) {
      if (dot) dot.className = 'status-dot online';
      if (text) text.textContent = res.first_time ? 'HTTP在线 (待部署)' : 'HTTP在线 (已就绪)';
      if (info) {
        info.textContent = res.host ? `${res.host}:${res.port || 8090}` : 'HTTP已连接';
      }
      if (this.lastConnectedState === false) {
        showToast(`🎉 成功连接机器人 (${res.host || 'HTTP'})`, 'success', 3500);
      }
    } else {
      const isAuto = res?.auto_detecting || res?.auto_connect_enabled;
      if (dot) {
        dot.className = hasSsh ? 'status-dot detecting' : (isAuto ? 'status-dot detecting' : 'status-dot');
      }
      if (text) {
        text.textContent = hasSsh ? '仅SSH维护已连' : (isAuto ? '探测中...' : '未绑定');
      }
      if (info) {
        info.textContent = res?.host ? `${res.host}:${res.port || 8090}` : '未绑定';
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
      const model = p.model || 'G1';

      if (res.license_valid) {
        licStatusEl.innerHTML = `
          <div style="background: rgba(16, 185, 129, 0.12); border: 1px solid rgba(16, 185, 129, 0.35); border-radius: 6px; padding: 8px 10px; margin-bottom: 6px;">
            <div style="color: #34d399; font-weight: 700; font-size: 0.84rem; display: flex; align-items: center; justify-content: space-between; margin-bottom: 4px;">
              <span>✅ 授权已生效</span>
              <span class="card-badge" style="font-size: 0.65rem; padding: 1px 5px;">${escapeHtml(model)}</span>
            </div>
            <div style="font-size: 0.75rem; color: #a7f3d0; line-height: 1.5;">
              <div><b>授权客户:</b> ${escapeHtml(customer)}</div>
              <div><b>有效期限:</b> <span style="color: #6ee7b7; font-weight: 600;">${escapeHtml(exp)}</span></div>
              <div><b>包含舞蹈:</b> <span style="color: #6ee7b7; font-weight: 600;">${escapeHtml(dances)}</span> 首动作</div>
            </div>
          </div>
        `;
      } else {
        const failReason = res.msg ? escapeHtml(res.msg) : '日志检测到 <code>[SKIP] not licensed</code>';
        licStatusEl.innerHTML = `
          <div style="background: rgba(239, 68, 68, 0.12); border: 1px solid rgba(239, 68, 68, 0.35); border-radius: 6px; padding: 8px 10px; margin-bottom: 6px;">
            <div style="color: #f87171; font-weight: 700; font-size: 0.84rem; margin-bottom: 4px;">❌ 授权校验未通过</div>
            <div style="font-size: 0.75rem; color: #fca5a5; line-height: 1.4;">
              <div>${failReason}</div>
              <div style="color: #f87171; margin-top: 2px;">请核对机器码或重新导入授权文件</div>
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
            }, () => {
              // W-5: SSE 断流兜底——复位按钮避免永久 disabled
              btnSubmitUpdate.disabled = false;
              btnSubmitUpdate.textContent = '🚀 一键上传并导入舞蹈动作包';
              logLine('上传任务日志流中断，请检查连接后重试', true);
              showToast('上传任务日志流中断，请重试', 'error');
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
  }
};

window.addEventListener('DOMContentLoaded', () => {
  App.init();
});
