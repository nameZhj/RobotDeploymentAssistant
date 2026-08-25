/**
 * 日志监控与智能诊断故障分析前端逻辑
 */
const LogViewer = {
  currentLogType: 'container',
  autoRefreshInterval: null,
  isAutoRefresh: true,

  init() {
    this.bindEvents();
    this.fetchCurrentLogs();
    this.startAutoRefresh();
  },

  bindEvents() {
    // 日志类型切换
    document.querySelectorAll('.log-type-btn').forEach(btn => {
      btn.addEventListener('click', (e) => {
        document.querySelectorAll('.log-type-btn').forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
        this.currentLogType = btn.dataset.type;
        this.fetchCurrentLogs();
      });
    });

    // 自动刷新开关
    const chkAuto = document.getElementById('chk-log-autorefresh');
    if (chkAuto) {
      chkAuto.addEventListener('change', (e) => {
        this.isAutoRefresh = e.target.checked;
        if (this.isAutoRefresh) this.startAutoRefresh();
        else this.stopAutoRefresh();
      });
    }

    // 搜索过滤
    const filterInput = document.getElementById('input-log-filter');
    if (filterInput) {
      filterInput.addEventListener('input', () => {
        this.applyFilter();
      });
    }
  },

  startAutoRefresh() {
    this.stopAutoRefresh();
    this.autoRefreshInterval = setInterval(() => {
      const activeTab = document.querySelector('.tab-content-panel.active');
      if (activeTab && activeTab.id === 'tab-logs') {
        this.fetchCurrentLogs(true);
      }
    }, 3000);
  },

  stopAutoRefresh() {
    if (this.autoRefreshInterval) {
      clearInterval(this.autoRefreshInterval);
      this.autoRefreshInterval = null;
    }
  },

  async fetchCurrentLogs(isBackground = false) {
    try {
      const res = await API.getLogs(this.currentLogType, 200);
      if (res.success) {
        this.renderLogs(res.raw_text);
        this.renderDiagnostics(res.diagnostics);
      } else {
        this.renderLogs(res.raw_text || res.msg || '拉取日志失败，请检查连接');
        this.renderDiagnostics([]);
      }
    } catch (err) {
      this.renderLogs(`HTTP 请求失败: ${err.message}`);
      if (!isBackground) {
        showToast(`拉取日志失败: ${err.message}`, 'error');
      }
    }
  },

  renderLogs(rawText) {
    const consoleEl = document.getElementById('log-console-content');
    if (!consoleEl) return;

    const filterVal = (document.getElementById('input-log-filter')?.value || '').toLowerCase();
    const lines = rawText.split('\n');
    let formattedHtml = '';

    for (const line of lines) {
      if (!line.trim()) continue;
      if (filterVal && !line.toLowerCase().includes(filterVal)) continue;

      let cls = '';
      if (line.includes('[ERROR]') || line.includes('error') || line.includes('failed') || line.includes('mismatch')) {
        cls = 'log-error';
      } else if (line.includes('[WARNING]') || line.includes('warn') || line.includes('[SKIP]')) {
        cls = 'log-warn';
      } else if (line.includes('[SUCCESS]') || line.includes('[READY]')) {
        cls = 'log-success';
      } else if (line.includes('[INFO]') || line.includes('[STEP]')) {
        cls = 'log-info';
      }

      formattedHtml += `<div class="${cls}">${this.escapeHtml(line)}</div>`;
    }

    consoleEl.innerHTML = formattedHtml || '<div class="text-muted">（无匹配日志内容）</div>';

    const chkAutoScroll = document.getElementById('chk-log-autoscroll');
    if (!chkAutoScroll || chkAutoScroll.checked) {
      consoleEl.scrollTop = consoleEl.scrollHeight;
    }
  },

  renderDiagnostics(diagnostics) {
    const diagContainer = document.getElementById('log-diag-alerts');
    if (!diagContainer) return;

    if (!diagnostics || diagnostics.length === 0) {
      diagContainer.innerHTML = `
        <div style="padding: 12px 16px; background: rgba(16, 185, 129, 0.1); border: 1px solid rgba(16, 185, 129, 0.3); border-radius: 6px; color: #34d399; font-size: 0.85rem; display: flex; align-items: center; gap: 8px;">
          <span>✅</span>
          <span>智能诊断：未发现异常故障，各组件运行指标正常。</span>
        </div>
      `;
      return;
    }

    let html = '';
    for (const diag of diagnostics) {
      const isDanger = diag.severity === 'danger';
      const diagCopyText = `【${diag.title}】\n描述: ${diag.description}\n特征: ${diag.matched_text}\n建议: ${diag.fix_title}`;
      html += `
        <div class="diag-alert ${isDanger ? '' : 'warning'}">
          <div style="flex: 1;">
            <div class="diag-title">⚠️ ${diag.title}</div>
            <div class="diag-desc">${diag.description}</div>
            <div style="margin-top: 6px; font-family: monospace; font-size: 0.75rem; color: #9ca3af; background: rgba(0,0,0,0.3); padding: 4px 8px; border-radius: 4px; user-select: text;">
              匹配特征: ${this.escapeHtml(diag.matched_text)}
            </div>
          </div>
          <div style="display: flex; flex-direction: column; gap: 6px; align-items: flex-end;">
            <button class="btn ${isDanger ? 'btn-danger' : 'btn-primary'} btn-sm" onclick="LogViewer.triggerFix('${diag.fix_action}')">
              🛠️ ${diag.fix_title}
            </button>
            <button class="btn-copy-mini" onclick="copyToClipboard(${JSON.stringify(diagCopyText)}, '诊断故障信息已复制')">
              📋 复制诊断
            </button>
          </div>
        </div>
      `;
    }
    diagContainer.innerHTML = html;
  },

  triggerFix(action) {
    if (action === 'fix_ch341') {
      showToast('正在触发 CH341 驱动一键修复...', 'info');
      App.switchTab('tab-precheck');
      TabPrecheck.fixCh341();
    } else if (action === 'goto_license') {
      App.switchTab('tab-license');
    } else if (action === 'restart_processes') {
      showToast('正在重启控制进程...', 'info');
      Wizard.restartProcesses();
    } else if (action === 'goto_precheck') {
      App.switchTab('tab-precheck');
    } else if (action === 'fix_robot_id') {
      API.configAutostart('A').then(res => {
        showToast(res.msg, res.success ? 'success' : 'error');
        this.fetchCurrentLogs();
      });
    } else if (action === 'fix_port_conflict') {
      showToast('正在释放 400/4001/4002 端口并重启容器...', 'info');
      App.switchTab('tab-image');
      TabImage.startContainer();
    }
  },

  applyFilter() {
    this.fetchCurrentLogs();
  },

  clearLogs() {
    const consoleEl = document.getElementById('log-console-content');
    if (consoleEl) consoleEl.innerHTML = '<div class="text-muted">（日志已清空）</div>';
  },

  copyLogs() {
    const consoleEl = document.getElementById('log-console-content');
    if (consoleEl) {
      copyToClipboard(consoleEl.innerText, '控制台日志已全部复制');
    }
  },

  escapeHtml(str) {
    return (str || '')
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;');
  }
};
