/**
 * 日志监控与智能诊断故障分析前端逻辑
 */
const LogViewer = {
  currentLogType: 'container',
  currentContainer: '',
  currentLines: 500,
  lastRawText: '',
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

        // 控制容器选择下拉框的显示/隐藏
        const containerWrap = document.getElementById('log-container-select-wrapper');
        if (containerWrap) {
          containerWrap.style.display = (this.currentLogType === 'container') ? 'inline-flex' : 'none';
        }

        this.fetchCurrentLogs();
      });
    });

    // 容器下拉选择切换
    const containerSelect = document.getElementById('select-log-container');
    if (containerSelect) {
      containerSelect.addEventListener('change', (e) => {
        this.currentContainer = e.target.value;
        this.fetchCurrentLogs();
      });
    }

    // 行数选择切换
    const linesSelect = document.getElementById('select-log-lines');
    if (linesSelect) {
      linesSelect.addEventListener('change', (e) => {
        this.currentLines = parseInt(e.target.value, 10) || 500;
        this.fetchCurrentLogs();
      });
    }

    // 自动换行开关
    const chkWordwrap = document.getElementById('chk-log-wordwrap');
    if (chkWordwrap) {
      chkWordwrap.addEventListener('change', (e) => {
        const consoleEl = document.getElementById('log-console-content');
        if (consoleEl) {
          if (e.target.checked) {
            consoleEl.classList.add('log-wordwrap');
          } else {
            consoleEl.classList.remove('log-wordwrap');
          }
        }
      });
    }

    // 时间戳开关
    const chkTimestamp = document.getElementById('chk-log-timestamp');
    if (chkTimestamp) {
      chkTimestamp.addEventListener('change', (e) => {
        const consoleEl = document.getElementById('log-console-content');
        if (consoleEl) {
          if (e.target.checked) {
            consoleEl.classList.remove('hide-timestamps');
          } else {
            consoleEl.classList.add('hide-timestamps');
          }
        }
      });
    }

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
        this.renderLogs(this.lastRawText);
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

  updateContainerDropdown(containers, targetContainer) {
    const select = document.getElementById('select-log-container');
    if (!select || !containers || containers.length === 0) return;

    const currentVal = this.currentContainer || targetContainer || select.value;
    select.innerHTML = '';
    for (const c of containers) {
      const opt = document.createElement('option');
      opt.value = c.name;
      opt.textContent = `📦 ${c.name} (${c.status})`;
      if (c.name === currentVal) {
        opt.selected = true;
      }
      select.appendChild(opt);
    }
    if (select.value) {
      this.currentContainer = select.value;
    }
  },

  async fetchCurrentLogs(isBackground = false) {
    try {
      const lines = this.currentLines || 500;
      const res = await API.getLogs(this.currentLogType, lines, this.currentContainer);
      if (res.available_containers) {
        this.updateContainerDropdown(res.available_containers, res.target_container);
      }
      if (res.success) {
        this.lastRawText = res.raw_text || '';
        this.renderLogs(this.lastRawText);
        this.renderDiagnostics(res.diagnostics);
      } else {
        this.lastRawText = res.raw_text || res.msg || '拉取日志失败，请检查连接';
        this.renderLogs(this.lastRawText);
        this.renderDiagnostics([]);
      }
    } catch (err) {
      this.lastRawText = `HTTP 请求失败: ${err.message}`;
      this.renderLogs(this.lastRawText);
      if (!isBackground) {
        showToast(`拉取日志失败: ${err.message}`, 'error');
      }
    }
  },

  parseTimestamp(line, fallbackTimeStr, fallbackFullDate) {
    // 1. Docker ISO-8601 (如 2026-09-09T01:32:15.123456789Z)
    const isoMatch = line.match(/^(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:?\d{2})?)\s+(.*)$/);
    if (isoMatch) {
      try {
        const d = new Date(isoMatch[1]);
        if (!isNaN(d.getTime())) {
          const pad = n => String(n).padStart(2, '0');
          const timeStr = `${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`;
          const fullDate = `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`;
          return {
            timeStr,
            fullDate,
            cleanLine: isoMatch[2]
          };
        }
      } catch (_) {}
    }

    // 2. 标准日期时间 (如 2026-09-09 09:32:15,123 或 [2026-09-09 09:32:15])
    const dtMatch = line.match(/^\[?(\d{4}-\d{2}-\d{2}[ T](\d{2}:\d{2}:\d{2})(?:[,\.]\d{1,6})?)\]?\s*(.*)$/);
    if (dtMatch) {
      return {
        timeStr: dtMatch[2],
        fullDate: dtMatch[1],
        cleanLine: dtMatch[3]
      };
    }

    // 3. dmesg -T (如 [Wed Sep  9 09:32:15 2026])
    const dmesgMatch = line.match(/^\[([A-Za-z]{3}\s+[A-Za-z]{3}\s+\d+\s+(\d{2}:\d{2}:\d{2})\s+\d{4})\]\s*(.*)$/);
    if (dmesgMatch) {
      return {
        timeStr: dmesgMatch[2],
        fullDate: dmesgMatch[1],
        cleanLine: dmesgMatch[3]
      };
    }

    // 4. 仅时间格式 (如 [09:32:15] 或 09:32:15)
    const timeMatch = line.match(/^\[?(\d{2}:\d{2}:\d{2}(?:[,\.]\d{1,3})?)\]?\s+(.*)$/);
    if (timeMatch) {
      const timeStr = timeMatch[1].split(/[,\.]/)[0];
      return {
        timeStr,
        fullDate: fallbackFullDate ? `${fallbackFullDate.split(' ')[0]} ${timeStr}` : timeStr,
        cleanLine: timeMatch[2]
      };
    }

    // 5. 无嵌入时间戳普通行 -> 使用批次拉取/接收时间戳
    return {
      timeStr: fallbackTimeStr,
      fullDate: fallbackFullDate,
      cleanLine: line
    };
  },

  renderLogs(rawText) {
    const consoleEl = document.getElementById('log-console-content');
    if (!consoleEl) return;

    // 清理 ANSI 控制字符
    const cleanText = (rawText || '').replace(/\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])/g, '');
    const filterVal = (document.getElementById('input-log-filter')?.value || '').toLowerCase();
    const lines = cleanText.split('\n');
    let formattedHtml = '';

    const now = new Date();
    const pad = n => String(n).padStart(2, '0');
    const fallbackTimeStr = `${pad(now.getHours())}:${pad(now.getMinutes())}:${pad(now.getSeconds())}`;
    const fallbackFullDate = `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())} ${fallbackTimeStr}`;

    for (const line of lines) {
      if (!line.trim()) {
        formattedHtml += '<div>&nbsp;</div>';
        continue;
      }
      if (filterVal && !line.toLowerCase().includes(filterVal)) continue;

      // 进程状态 section 标题行或长分隔线单独作为横条展示，不加时间戳
      if ((line.startsWith('===') && line.endsWith('===')) || line.startsWith('=========================================') || /^[🤖📋📡⚡🆔🔌]\s*\[/.test(line)) {
        formattedHtml += `<div class="log-section-header">${this.escapeHtml(line)}</div>`;
        continue;
      }

      const parsed = this.parseTimestamp(line, fallbackTimeStr, fallbackFullDate);
      const l = parsed.cleanLine.toLowerCase();
      let cls = '';

      // 进程离线
      if (l.includes('[offline]') || l.includes('未运行') || l.includes('not running')) {
        cls = 'log-error';
      }
      // 关键成功/就绪状态
      else if (l.includes('[ready]') || l.includes('加载完成') || l.includes('[success]') || l.includes('[ok]') || l.includes('signature verify success')) {
        cls = 'log-success';
      }
      // 错误
      else if (l.includes('[error]') || l.includes('error') || l.includes('failed') || l.includes('mismatch') || l.includes('segmentation fault')) {
        cls = 'log-error';
      }
      // 警告
      else if (l.includes('[warning]') || l.includes('warn') || l.includes('[skip]')) {
        cls = 'log-warn';
      }
      // 信息
      else if (l.includes('[info]') || l.includes('[step]') || l.includes('[tx]') || l.includes('[rx]') || l.includes('[config]') || l.includes('[dds]')) {
        cls = 'log-info';
      }
      // 日志文件不存在提示
      else if (l.includes('[日志文件不存在]') || l.includes('no such file')) {
        cls = 'log-warn';
      }

      formattedHtml += `
        <div class="log-row ${cls}">
          <span class="log-timestamp" title="${this.escapeHtml(parsed.fullDate)}">[${parsed.timeStr}]</span>
          <span class="log-content">${this.escapeHtml(parsed.cleanLine)}</span>
        </div>
      `;
    }

    consoleEl.innerHTML = formattedHtml || '<div class="text-muted">（无匹配日志内容）</div>';

    // 确保与时间戳开关状态同步
    const chkTimestamp = document.getElementById('chk-log-timestamp');
    if (chkTimestamp && !chkTimestamp.checked) {
      consoleEl.classList.add('hide-timestamps');
    } else {
      consoleEl.classList.remove('hide-timestamps');
    }

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
        <div style="padding: 10px 14px; background: rgba(16, 185, 129, 0.1); border: 1px solid rgba(16, 185, 129, 0.3); border-radius: 6px; color: #34d399; font-size: 0.82rem; display: flex; align-items: center; gap: 8px;">
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

  toggleFullscreen() {
    const card = document.getElementById('log-viewer-main-card');
    const btn = document.getElementById('btn-log-fullscreen');
    if (!card) return;

    if (card.classList.contains('fullscreen-console')) {
      card.classList.remove('fullscreen-console');
      if (btn) btn.textContent = '⛶ 全屏';
    } else {
      card.classList.add('fullscreen-console');
      if (btn) btn.textContent = '🗗 还原';
    }
  },

  copyAllLogs() {
    const consoleEl = document.getElementById('log-console-content');
    const textToCopy = this.lastRawText || (consoleEl ? consoleEl.innerText : '');
    if (!textToCopy.trim()) {
      showToast('当前无可用日志内容', 'warning');
      return;
    }
    copyToClipboard(textToCopy, '全部日志内容已复制到剪贴板');
  },

  downloadLogs() {
    const consoleEl = document.getElementById('log-console-content');
    const text = this.lastRawText || (consoleEl ? consoleEl.innerText : '');
    if (!text.trim()) {
      showToast('当前无可用日志内容可供导出', 'warning');
      return;
    }

    const now = new Date();
    const timestamp = `${now.getFullYear()}${String(now.getMonth() + 1).padStart(2, '0')}${String(now.getDate()).padStart(2, '0')}_${String(now.getHours()).padStart(2, '0')}${String(now.getMinutes()).padStart(2, '0')}`;
    const filename = `robot_log_${this.currentLogType}_${timestamp}.txt`;

    const blob = new Blob([text], { type: 'text/plain;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
    showToast(`日志已导出为 ${filename}`, 'success');
  },

  clearLogs() {
    this.lastRawText = '';
    const consoleEl = document.getElementById('log-console-content');
    if (consoleEl) consoleEl.innerHTML = '<div class="text-muted">（日志已清空）</div>';
  },

  escapeHtml(str) {
    return (str || '')
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;');
  }
};
