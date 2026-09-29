/**
 * Agent Integration (MCP & Skills) feature module.
 */
(function initializeAgentFeature() {
  function getOrigin() {
    return window.location.origin;
  }

  function renderMcpConfig(token = 'YOUR_TOKEN_HERE') {
    const config = {
      mcpServers: {
        'canvas-dashboard': {
          command: 'python',
          args: ['canvas_mcp.py'],
          env: {
            CANVAS_DASHBOARD_URL: getOrigin(),
            CANVAS_DASHBOARD_TOKEN: token,
          },
        },
      },
    };
    const codeElem = document.getElementById('agent-mcp-config-code');
    if (codeElem) {
      codeElem.textContent = JSON.stringify(config, null, 2);
    }
  }

  function renderSkillPrompt(token = '', hasToken = false) {
    const origin = getOrigin();
    const promptElem = document.getElementById('agent-skill-prompt-code');
    const updatePromptElem = document.getElementById('agent-skill-update-prompt-code');
    const copyPromptBtn = document.getElementById('agent-skill-copy-prompt');

    let tokenDisplay = '<YOUR_TOKEN>';
    if (token) {
      tokenDisplay = token;
    } else if (hasToken) {
      tokenDisplay = '<已激活的Token>';
    }

    if (promptElem) {
      promptElem.textContent = `请安装 Canvas Dashboard Skill：${origin}/skill/README.md\n装完告诉我是否需要开启新会话。\n安装器支持时请追加：--server ${origin} --token ${tokenDisplay}`;
    }

    if (updatePromptElem) {
      updatePromptElem.textContent = `请把我已安装的 Canvas Dashboard Skill 更新到最新版：${origin}/skill/README.md\n先告诉我它现在装在哪个目录、是否存在重复副本，再替换同一目录。\n更新后开启新会话，用“我今天有什么课？”验证。`;
    }

    if (copyPromptBtn) {
      if (token) {
        copyPromptBtn.textContent = '复制安装提示词';
      } else if (hasToken) {
        copyPromptBtn.textContent = '复制安装提示词 (需填入Token)';
      } else {
        copyPromptBtn.textContent = '请先生成 Token';
      }
    }
  }

  let hasExistingToken = false;

  function setAgentStatus(text, type = 'info') {
    const statusElem = document.getElementById('agent-token-status');
    if (!statusElem) return;
    statusElem.textContent = text;
    statusElem.className = `ui-feedback ui-feedback--${type} calendar-subscription-status`;
  }

  window.clearAgentTokenPlaintext = function clearAgentTokenPlaintext() {
    const tokenInput = document.getElementById('agent-token-input');
    if (tokenInput && tokenInput.value) {
      tokenInput.value = '';
      if (hasExistingToken) {
        tokenInput.placeholder = '•••••••••••••••••••••••••••••••• (已生成)';
      }
      const copyBtn = document.getElementById('agent-token-copy');
      if (copyBtn) copyBtn.disabled = true;
      renderMcpConfig('YOUR_TOKEN_HERE');
      renderSkillPrompt('', hasExistingToken);
    }
  };

  function escapeHtml(str) {
    return String(str || '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
  }

  function formatScopeBadge(scopes) {
    if (!scopes || !scopes.length) return '<span class="ui-tag">无</span>';
    if (scopes.includes('delete')) return '<span class="ui-tag ui-tag--danger">完整 (delete)</span>';
    if (scopes.includes('write')) return '<span class="ui-tag ui-tag--accent">读写 (write)</span>';
    return '<span class="ui-tag ui-tag--neutral">只读 (read)</span>';
  }

  function renderTokensList(tokens) {
    const container = document.getElementById('agent-tokens-list-container');
    const listElem = document.getElementById('agent-tokens-list');
    if (!container || !listElem) return;

    if (!tokens || tokens.length === 0) {
      container.classList.add('hidden');
      listElem.innerHTML = '';
      return;
    }

    container.classList.remove('hidden');
    listElem.innerHTML = tokens.map(t => {
      const createdStr = t.created_at ? new Date(t.created_at).toLocaleString() : '-';
      const expiresStr = t.expires_at ? new Date(t.expires_at).toLocaleString() : '永不过期';
      const lastUsedStr = t.last_used_at ? new Date(t.last_used_at).toLocaleString() : '未使用';
      const isExpired = t.expires_at && new Date(t.expires_at).getTime() < Date.now();
      const nameEscaped = escapeHtml(t.name || '未命名 Token');
      const idEscaped = escapeHtml(t.id || '');

      return `
        <div class="agent-token-item">
          <div class="agent-token-item-content">
            <div class="agent-token-item-header">
              <strong>${nameEscaped}</strong>
              ${formatScopeBadge(t.scopes)}
              ${isExpired ? '<span class="ui-tag ui-tag--danger">已过期</span>' : ''}
            </div>
            <div class="agent-token-item-meta">
              <span>创建: ${createdStr}</span> · <span>到期: ${expiresStr}</span> · <span>最后调用: ${lastUsedStr}</span>
            </div>
          </div>
          <button type="button" class="ui-button ui-button--secondary console-stateful-button agent-token-revoke-btn" onclick="revokeAgentToken('${idEscaped}')">撤销</button>
        </div>
      `;
    }).join('');
  }

  window.loadAgentSettings = async function loadAgentSettings() {
    const tokenInput = document.getElementById('agent-token-input');
    const copyBtn = document.getElementById('agent-token-copy');
    const revokeBtn = document.getElementById('agent-token-revoke');
    const createBtn = document.getElementById('agent-token-create');
    if (!tokenInput || !createBtn) return;

    renderMcpConfig(tokenInput.value || 'YOUR_TOKEN_HERE');
    renderSkillPrompt(tokenInput.value || '', hasExistingToken || tokenInput.placeholder.includes('已生成'));

    try {
      const data = await dashboardApi.requestJson('/api/agent/token');
      if (data.has_token) {
        hasExistingToken = true;
        const count = (data.tokens || []).filter(t => !t.is_expired).length || 1;
        if (!tokenInput.value) {
          tokenInput.placeholder = `•••••••••••••••••••••••••••••••• (已激活 ${count} 个 Token)`;
        }
        if (copyBtn) copyBtn.disabled = !tokenInput.value;
        if (revokeBtn) revokeBtn.disabled = false;
        createBtn.textContent = '新增 / 重新生成 Token';
        renderSkillPrompt(tokenInput.value || '', true);
        renderTokensList(data.tokens || []);
        const dateStr = data.created_at ? new Date(data.created_at).toLocaleString() : '';
        setAgentStatus(`Agent Token 已激活${dateStr ? '（创建于 ' + dateStr + '）' : ''}，共 ${count} 个有效凭据。离开页面后将隐藏明文。`, 'success');
      } else {
        hasExistingToken = false;
        tokenInput.value = '';
        tokenInput.placeholder = '尚未生成 Agent Token';
        if (copyBtn) copyBtn.disabled = true;
        if (revokeBtn) revokeBtn.disabled = true;
        createBtn.textContent = '生成 Agent Token';
        renderSkillPrompt('', false);
        renderTokensList(data.tokens || []);
        setAgentStatus('尚未生成 Token。生成后可直接用于 MCP 客户端或 Agent Skill。', 'info');
      }
    } catch (err) {
      setAgentStatus('获取 Token 状态失败，请稍后重试。', 'danger');
    }
  };

  window.createAgentToken = async function createAgentToken() {
    const tokenInput = document.getElementById('agent-token-input');
    const createBtn = document.getElementById('agent-token-create');
    const copyBtn = document.getElementById('agent-token-copy');
    const revokeBtn = document.getElementById('agent-token-revoke');
    const nameInput = document.getElementById('agent-token-name-input');
    const expirySelect = document.getElementById('agent-token-expiry-select');
    if (!tokenInput || !createBtn) return;

    createBtn.disabled = true;
    createBtn.setAttribute('aria-busy', 'true');
    createBtn.textContent = '正在生成…';

    const name = nameInput && nameInput.value ? nameInput.value.trim() : '';
    let scopes = ['read'];
    const selectedScope = document.querySelector('input[name="agent-token-scope"]:checked');
    if (selectedScope) {
      if (selectedScope.value === 'write') {
        scopes = ['read', 'write'];
      } else if (selectedScope.value === 'all') {
        scopes = ['read', 'write', 'delete'];
      }
    }
    let expiresInDays = null;
    if (expirySelect && expirySelect.value && expirySelect.value !== 'never') {
      const parsed = parseInt(expirySelect.value, 10);
      if (!isNaN(parsed) && parsed > 0) {
        expiresInDays = parsed;
      }
    }

    try {
      const data = await dashboardApi.requestJson('/api/agent/token', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          name: name || undefined,
          scopes: scopes,
          expires_in_days: expiresInDays
        })
      });
      if (!data.token) throw new Error('token missing');

      hasExistingToken = true;
      tokenInput.value = data.token;
      tokenInput.placeholder = '•••••••••••••••••••••••••••••••• (已生成)';
      if (copyBtn) copyBtn.disabled = false;
      if (revokeBtn) revokeBtn.disabled = false;
      createBtn.textContent = '新增 / 重新生成 Token';
      if (nameInput) nameInput.value = '';

      renderMcpConfig(data.token);
      renderSkillPrompt(data.token, true);
      setAgentStatus('🎉 Token 已生成！请立即复制并妥善保管，离开本页面后出于安全将隐藏完整密钥。', 'success');
      await loadAgentSettings();
      // Keep newly created token visible in input and copyable
      tokenInput.value = data.token;
      if (copyBtn) copyBtn.disabled = false;
    } catch (err) {
      setAgentStatus('生成 Token 失败，请稍后重试。', 'danger');
    } finally {
      createBtn.disabled = false;
      createBtn.setAttribute('aria-busy', 'false');
    }
  };

  window.revokeAgentToken = async function revokeAgentToken(tokenId) {
    const isSingle = Boolean(tokenId);
    const confirmMsg = isSingle
      ? '确定要撤销此 Token 吗？撤销后该 Token 将立即失效。'
      : '确定要撤销全部 Agent Token 吗？撤销后，所有已生成的凭据将立即失效。';
    if (!confirm(confirmMsg)) {
      return;
    }

    const tokenInput = document.getElementById('agent-token-input');
    const createBtn = document.getElementById('agent-token-create');
    const copyBtn = document.getElementById('agent-token-copy');
    const revokeBtn = document.getElementById('agent-token-revoke');

    if (revokeBtn && !isSingle) {
      revokeBtn.disabled = true;
      revokeBtn.setAttribute('aria-busy', 'true');
    }

    try {
      const body = isSingle ? { token_id: tokenId } : {};
      await dashboardApi.requestJson('/api/agent/token', {
        method: 'DELETE',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body)
      });

      if (!isSingle) {
        hasExistingToken = false;
        if (tokenInput) {
          tokenInput.value = '';
          tokenInput.placeholder = '尚未生成 Agent Token';
        }
        if (copyBtn) copyBtn.disabled = true;
        if (revokeBtn) revokeBtn.disabled = true;
        if (createBtn) createBtn.textContent = '生成 Agent Token';
        renderMcpConfig('YOUR_TOKEN_HERE');
        renderSkillPrompt('', false);
        renderTokensList([]);
        setAgentStatus('Token 已成功撤销，旧凭据已失效。', 'info');
      } else {
        await loadAgentSettings();
        setAgentStatus('指定 Token 已成功撤销。', 'info');
      }
    } catch (err) {
      setAgentStatus('撤销 Token 失败，请稍后重试。', 'danger');
      if (revokeBtn && !isSingle) revokeBtn.disabled = false;
    } finally {
      if (revokeBtn && !isSingle) revokeBtn.setAttribute('aria-busy', 'false');
    }
  };

  window.copyAgentToken = async function copyAgentToken() {
    const tokenInput = document.getElementById('agent-token-input');
    if (!tokenInput || !tokenInput.value) return;

    try {
      await navigator.clipboard.writeText(tokenInput.value);
      setAgentStatus('Token 已成功复制到剪贴板。', 'success');
    } catch (err) {
      tokenInput.select();
      document.execCommand('copy');
      setAgentStatus('Token 已成功复制。', 'success');
    }
  };

  window.copySkillPrompt = async function copySkillPrompt() {
    const tokenInput = document.getElementById('agent-token-input');
    const promptElem = document.getElementById('agent-skill-prompt-code');
    if (!promptElem) return;

    const hasActiveToken = tokenInput && (tokenInput.value || tokenInput.placeholder.includes('已生成'));
    if (!hasActiveToken) {
      setAgentStatus('请先在上方点击“生成 Agent Token”，即可自动填入专属安装提示词。', 'danger');
      return;
    }

    try {
      await navigator.clipboard.writeText(promptElem.textContent);
      if (tokenInput.value) {
        setAgentStatus('🎉 安装提示词已成功复制到剪贴板！直接粘贴发给你的 AI Agent 即可自动安装。', 'success');
      } else {
        setAgentStatus('提示词已复制！若使用的是历史生成的 Token，请将 <已激活的Token> 替换为你保存的 Token，或在上方重新生成。', 'info');
      }
    } catch (err) {
      const range = document.createRange();
      range.selectNodeContents(promptElem);
      const sel = window.getSelection();
      sel.removeAllRanges();
      sel.addRange(range);
      document.execCommand('copy');
      setAgentStatus('🎉 安装提示词已成功复制！', 'success');
    }
  };

  window.copySkillUpdatePrompt = async function copySkillUpdatePrompt() {
    const updatePromptElem = document.getElementById('agent-skill-update-prompt-code');
    if (!updatePromptElem) return;

    try {
      await navigator.clipboard.writeText(updatePromptElem.textContent);
      setAgentStatus('🎉 更新提示词已成功复制到剪贴板！直接发送给已安装 Skill 的 Agent 即可。', 'success');
    } catch (err) {
      setAgentStatus('无法自动复制更新提示词，请手动框选复制。', 'danger');
    }
  };

  window.copyAgentMcpConfig = async function copyAgentMcpConfig() {
    const codeElem = document.getElementById('agent-mcp-config-code');
    if (!codeElem) return;

    try {
      await navigator.clipboard.writeText(codeElem.textContent);
      setAgentStatus('MCP 配置代码已成功复制到剪贴板！', 'success');
    } catch (err) {
      setAgentStatus('无法自动复制配置代码，请手动框选复制。', 'danger');
    }
  };
})();
