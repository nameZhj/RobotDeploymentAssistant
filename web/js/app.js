/**
 * VSISLAB 机器人部署助手 主应用控制器
 */
const App = {
  activeTab: 'tab-3d-player',
  statusInterval: null,

  async init() {
    this.bindTabEvents();
    this.bindConnectionEvents();
    this.bindDanceUpdateEvents();
    this.bindSettingsMenuEvents();
    this.init3dPlayer();
    this.startStatusMonitor();
    this.initGlobalCopyEnhancers();

    // 初始化子模块
    Wizard.init();
    LogViewer.init();
    ManualMode.init();

    // 运行开机自检与主动 License 校验逻辑
    await this.runStartupCheck();
  },

  initGlobalCopyEnhancers() {
    // 1. 为所有终端控制台容器挂载浮动复制按钮
    document.querySelectorAll('.terminal-console').forEach(consoleEl => {
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
          } catch (_) {}
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
        // 主动校验 License 与部署状态
        if (!res.first_time) {
          // License 校验通过且无 [SKIP] not licensed，容器运行中：静默关闭向导，切换主界面
          Wizard.closeModal();
          this.switchTab('tab-3d-player');
          // 不显示成功通知，静默完成
        } else {
          // License 校验错误或不存在 License 或 容器未启动：弹出向导
          const reason = !res.has_license ? '未检测到 License 授权文件'
            : (!res.license_valid ? 'License 校验未通过（存在 [SKIP] not licensed）'
            : '容器尚未部署启动');
          showToast(`⚠️ ${reason}，正在调出部署向导...`, 'warning', 4000);
          Wizard.openModal(1);
        }
      } else {
        // 机器人离线时保持在主界面，不提示（状态指示灯已体现）
        Wizard.closeModal();
      }
    } catch (err) {
      // 静默处理网络异常，不打扰用户
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

  switchTab(tabId) {
    this.activeTab = tabId;

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
      setTimeout(() => dancePlayer.onResize(), 50);
    } else if (tabId === 'tab-logs' && window.LogViewer) {
      LogViewer.fetchCurrentLogs();
    } else if (tabId === 'tab-network' && window.TabNetwork) {
      TabNetwork.init();
    } else if (tabId === 'tab-precheck' && window.TabPrecheck) {
      TabPrecheck.run();
    } else if (tabId === 'tab-image' && window.TabImage) {
      TabImage.init();
    } else if (tabId === 'tab-license' && window.TabLicense) {
      TabLicense.init();
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

    if (res && res.connected) {
      if (dot) dot.className = 'status-dot online';
      if (text) text.textContent = res.first_time ? '在线 (未部署)' : '在线 (已就绪)';
      if (info) {
        const lat = res.latency_ms >= 0 ? `${res.latency_ms}ms` : '--';
        info.textContent = `${res.username || 'unitree'}@${res.host || '192.168.123.164'}:${res.port || 22} [${lat}]`;
      }
    } else {
      if (dot) dot.className = 'status-dot';
      if (text) text.textContent = '离线 (Offline)';
      if (info) info.textContent = `${res?.host || '192.168.123.164'}:${res?.port || 22} (未连接)`;
    }

    // 更新设置菜单中的 License 状态（仅当接口返回了授权数据时才更新，防止每 4s 的 status 轮询覆盖它）
    const licStatusEl = document.getElementById('settings-license-status');
    if (licStatusEl && res && 'has_license' in res) {
      if (res.connected) {
        if (res.license_valid) {
          const exp = res.license_data?.expire_date || '永久授权';
          const dances = res.license_data?.dance_count || 0;
          licStatusEl.innerHTML = `<span style="color: var(--accent-cyan);">✅ 已授权</span><br>有效期: ${exp}<br>授权舞蹈: ${dances} 首`;
        } else if (res.has_license) {
          licStatusEl.innerHTML = `<span style="color: var(--accent-red);">❌ 校验失败</span><br>可能因机器码不匹配`;
        } else {
          licStatusEl.innerHTML = `<span style="color: var(--accent-red);">⚠️ 未授权</span><br>缺少 License 文件`;
        }
      } else {
        licStatusEl.innerHTML = `未检测到授权信息`;
      }
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
    const btnSubmitUpdate = document.getElementById('btn-submit-dance-update');
    if (btnSubmitUpdate) {
      btnSubmitUpdate.addEventListener('click', async () => {
        const alias = document.getElementById('input-update-alias')?.value.trim();
        const group = document.getElementById('select-update-group')?.value || 'R1';
        const action = document.getElementById('select-update-action')?.value || 'SELECT';
        const vsisFile = document.getElementById('input-update-vsis')?.files[0];
        const licFile = document.getElementById('input-update-license')?.files[0];
        const resultConsole = document.getElementById('dance-update-result');

        if (!alias) {
          showToast('请填写新舞蹈的别名 (如 G2_NEW_DANCE)', 'warning');
          return;
        }

        if (resultConsole) {
          resultConsole.innerHTML = `<div class="log-info">⏳ 正在上传并部署舞蹈 [${alias}] ...</div>`;
        }

        const formData = new FormData();
        formData.append('dance_alias', alias);
        formData.append('button_group', group);
        formData.append('button_action', action);
        if (vsisFile) formData.append('vsis_file', vsisFile);
        if (licFile) formData.append('license_file', licFile);

        showToast(`正在上传并部署舞蹈 [${alias}] ...`, 'info');
        try {
          const res = await API.updateDance(formData);
          if (res.success) {
            showToast(res.msg, 'success');
            if (resultConsole) {
              resultConsole.innerHTML += `<div class="log-success">✅ ${res.msg}</div>
                <div class="log-info">💡 提示：点击【立即重启控制进程】使新舞蹈生效。</div>`;
            }
          } else {
            showToast(`更新失败: ${res.msg}`, 'error');
            if (resultConsole) {
              resultConsole.innerHTML += `<div class="log-error">❌ 更新失败: ${res.msg}</div>`;
            }
          }
        } catch (err) {
          showToast(`更新异常: ${err.message}`, 'error');
          if (resultConsole) {
            resultConsole.innerHTML += `<div class="log-error">❌ 异常: ${err.message}</div>`;
          }
        }
      });
    }
  },

  async init3dPlayer() {
    dancePlayer = new DancePlayer3D('dance3d-viewport');

    // 绑定播放控制条
    const btnPlay = document.getElementById('btn-dance-play');
    const scrubber = document.getElementById('dance-scrubber');
    const selectSpeed = document.getElementById('select-dance-speed');
    const chkLoop = document.getElementById('chk-dance-loop');
    const btnResetCam = document.getElementById('btn-reset-cam');

    if (btnPlay) {
      btnPlay.addEventListener('click', () => dancePlayer.togglePlay());
    }

    if (scrubber) {
      scrubber.addEventListener('input', (e) => dancePlayer.seek(e.target.value));
    }

    if (selectSpeed) {
      selectSpeed.addEventListener('change', (e) => {
        dancePlayer.playbackSpeed = parseFloat(e.target.value);
      });
    }

    if (chkLoop) {
      chkLoop.addEventListener('change', (e) => {
        dancePlayer.isLoop = e.target.checked;
      });
    }

    if (btnResetCam) {
      btnResetCam.addEventListener('click', () => dancePlayer.resetCamera());
    }

    // 自定义 NPZ 动作导入与拖拽上传
    const inputCustomNpz = document.getElementById('input-custom-npz');

    const handleNpzFiles = async (fileList) => {
      const files = Array.from(fileList || []).filter(f => f && f.name && f.name.toLowerCase().endsWith('.npz'));
      if (files.length === 0) {
        showToast('未检测到有效的 .npz 格式动作文件', 'warning');
        return;
      }

      showToast(`正在批量导入 ${files.length} 个动作文件，请稍候...`, 'warning');

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
        showToast(`✓ 成功导入 ${succeeded.length} 个动作文件！`, 'warning');
        const lastSuccess = succeeded[succeeded.length - 1];
        if (lastSuccess && lastSuccess.data) {
          dancePlayer.loadDance(lastSuccess.data);
        }
        await this.refresh3dDanceList(lastSuccess ? lastSuccess.data.dance_name : null);
      }
    };

    if (inputCustomNpz) {
      inputCustomNpz.addEventListener('change', async (e) => {
        const selectedFiles = Array.from(e.target.files || []);
        e.target.value = ''; // 安全清空 input value，不影响已克隆的数组
        await handleNpzFiles(selectedFiles);
      });
    }

    // 全局防默认打开文件
    window.addEventListener('dragover', (e) => e.preventDefault());
    window.addEventListener('drop', (e) => e.preventDefault());

    // 拖拽多区域监听（支持拖入侧边栏列表或 3D 视口）
    const dropZones = [
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

      zone.addEventListener('drop', (e) => {
        e.preventDefault();
        e.stopPropagation();
        dragCounter = 0;
        setDragState(false);
        const files = e.dataTransfer ? e.dataTransfer.files : [];
        if (files && files.length > 0) {
          handleNpzFiles(files);
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
      if (!res.success || !res.dances) return;

      listContainer.innerHTML = '';
      let matchedBtn = null;

      for (const d of res.dances) {
        const item = document.createElement('div');
        item.className = 'dance-item-btn';
        item.dataset.id = d.id;
        item.innerHTML = `
          <div style="flex: 1; min-width: 0; padding-right: 6px;">
            <div style="font-weight: 600; font-size: 0.85rem; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;" title="${d.name}">🎵 ${d.name}</div>
            <div style="font-size: 0.72rem; color: var(--text-muted);">${d.duration}s | ${d.frames} 帧 (50fps)</div>
          </div>
          <div style="display: flex; align-items: center; gap: 6px;">
            <button class="btn-delete-dance" title="删除此动作" style="background: none; border: none; cursor: pointer; color: #ef4444; padding: 2px 4px; font-size: 0.85rem; border-radius: 4px; opacity: 0.6; transition: all 0.2s;">🗑️</button>
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
            if (confirm(`确定要删除动作【${d.name}】吗？`)) {
              try {
                const delRes = await API.delete3dDance(d.id);
                if (delRes.success) {
                  showToast(`✓ 已删除动作: ${d.name}`, 'warning');
                  this.refresh3dDanceList();
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

        if (preferredActiveName && d.name === preferredActiveName) {
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
