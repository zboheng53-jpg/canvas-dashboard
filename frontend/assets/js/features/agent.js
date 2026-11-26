/**
 * Agent Integration (MCP & Skills) feature module.
 */
(function initializeAgentFeature() {
  const AGENT_PLAINTEXT_TTL_MS = 5 * 60 * 1000;
  let hasExistingToken = false;
  let plaintextToken = '';
  let plaintextTokenId = null;
  let plaintextExpiresAt = 0;
  let plaintextHideTimer = null;
  let activeConnectTab = 'skill';

  function getOrigin() {
    return window.location.origin;
  }

  function formatScopeBadge(scopes) {
    if (!scopes || !scopes.length) return '<span class="ui-tag">无</span>';
    if (scopes.includes('delete')) return '<span class="ui-tag ui-tag--danger">完全控制</span>';
    if (scopes.includes('write')) return '<span class="ui-tag ui-tag--accent">读写</span>';
    return '<span class="ui-tag ui-tag--neutral">只读</span>';
  }

  function setAgentStatus(text, type = 'info') {
    const statusElem = document.getElementById('agent-token-status');
    if (!statusElem) return;
    statusElem.textContent = text;
    if (typeof applyFeedbackSemantic === 'function') {
      applyFeedbackSemantic(statusElem, type);
    } else {
      statusElem.className = `ui-feedback ui-feedback--${type} calendar-subscription-status`;
    }
  }

  function renderMcpConfig(token = 'YOUR_TOKEN_HERE') {
    const config = {
      mcpServers: {
        'canvas-dashboard': {
          command: 'python',
          args: ['canvas_mcp.py'],
          env: {
            CANVAS_DASHBOARD_URL: getOrigin(),
            CANVAS_DASHBOARD_TOKEN: token || 'YOUR_TOKEN_HERE',
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
        copyPromptBtn.textContent = '复制安装提示词（需填入 Token）';
      } else {
        copyPromptBtn.textContent = '一键生成只读 Token 并复制提示词';
      }
    }
  }

  function syncTokenControls() {
    const card = document.getElementById('agent-token-plaintext-card');
    const tokenInput = document.getElementById('agent-token-input');
    const copyBtn = document.getElementById('agent-token-copy');
    const revokeBtn = document.getElementById('agent-token-revoke');
    const createBtn = document.getElementById('agent-token-create');

    const hasPlaintext = Boolean(plaintextToken);
    if (card) card.classList.toggle('hidden', !hasPlaintext);
    if (tokenInput) {
      tokenInput.value = plaintextToken || '';
      tokenInput.placeholder = hasExistingToken
        ? '•••••••••••••••••••••••••••••••• (已隐藏明文)'
        : '尚未生成 Agent Token';
    }
    if (copyBtn) copyBtn.disabled = !hasPlaintext;
    if (revokeBtn) {
      revokeBtn.classList.toggle('hidden', !hasExistingToken);
      revokeBtn.disabled = !hasExistingToken;
    }
    if (createBtn) {
      createBtn.textContent = hasExistingToken ? '新增 Token' : '生成 Agent Token';
    }
  }

  window.clearAgentTokenPlaintext = function clearAgentTokenPlaintext(force = false, notify = force) {
    if (!force && plaintextToken && Date.now() < plaintextExpiresAt) {
      return;
    }
    if (plaintextHideTimer) {
      clearTimeout(plaintextHideTimer);
      plaintextHideTimer = null;
    }
    const hadPlaintext = Boolean(plaintextToken);
    plaintextToken = '';
    plaintextTokenId = null;
    plaintextExpiresAt = 0;
    syncTokenControls();
    renderMcpConfig('YOUR_TOKEN_HERE');
    renderSkillPrompt('', hasExistingToken);
    if (notify && hadPlaintext) {
      setAgentStatus('出于安全考虑已隐藏 Token 明文。如需再次获取完整密钥，可点击上方新增 Token。', 'info');
    }
  };

  function escapeHtml(str) {
    return String(str || '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
  }

  function renderTokensList(tokens) {
    const container = document.getElementById('agent-tokens-list-container');
    const listElem = document.getElementById('agent-tokens-list');
    if (!container || !listElem) return;

    if (!tokens || tokens.length === 0) {
      container.classList.add('hidden');
      listElem.replaceChildren();
      return;
    }

    container.classList.remove('hidden');
    listElem.innerHTML = tokens.map((t) => {
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
          <button type="button" class="ui-button ui-button--secondary ui-button--sm console-stateful-button agent-token-revoke-btn" onclick="revokeAgentToken('${idEscaped}')">撤销</button>
        </div>
      `;
    }).join('');
  }

  window.switchAgentConnectTab = function switchAgentConnectTab(tab) {
    activeConnectTab = tab === 'mcp' ? 'mcp' : 'skill';
    const useMcp = activeConnectTab === 'mcp';
    const skillPanel = document.getElementById('agent-panel-skill');
    const mcpPanel = document.getElementById('agent-panel-mcp');
    const skillTab = document.getElementById('agent-tab-btn-skill');
    const mcpTab = document.getElementById('agent-tab-btn-mcp');
    const tabsEl = document.getElementById('agent-connect-tabs');

    skillPanel?.classList.toggle('hidden', useMcp);
    mcpPanel?.classList.toggle('hidden', !useMcp);
    if (skillTab) {
      skillTab.classList.toggle('is-active', !useMcp);
      skillTab.setAttribute('aria-selected', String(!useMcp));
    }
    if (mcpTab) {
      mcpTab.classList.toggle('is-active', useMcp);
      mcpTab.setAttribute('aria-selected', String(useMcp));
    }
    const activeTabBtn = useMcp ? mcpTab : skillTab;
    if (tabsEl && activeTabBtn && window.uiMotion?.glideIndicator) {
      requestAnimationFrame(() => {
        if (!activeTabBtn.offsetWidth) return;
        window.uiMotion.glideIndicator(tabsEl, activeTabBtn);
      });
    }
  };

  window.loadAgentSettings = async function loadAgentSettings({ silentStatus = false } = {}) {
    const createBtn = document.getElementById('agent-token-create');
    if (!createBtn) return;

    if (plaintextToken && Date.now() >= plaintextExpiresAt) {
      clearAgentTokenPlaintext(false);
    }

    renderMcpConfig(plaintextToken || 'YOUR_TOKEN_HERE');
    renderSkillPrompt(plaintextToken, hasExistingToken);
    switchAgentConnectTab(activeConnectTab);

    try {
      const data = await dashboardApi.requestJson('/api/agent/token');
      hasExistingToken = Boolean(data.has_token);

      if (hasExistingToken) {
        if (plaintextTokenId && Array.isArray(data.tokens) && !data.tokens.some((t) => t.id === plaintextTokenId)) {
          plaintextToken = '';
          plaintextTokenId = null;
          plaintextExpiresAt = 0;
        }
        const activeCount = (data.tokens || []).filter((t) => !t.is_expired).length || 1;
        syncTokenControls();
        renderMcpConfig(plaintextToken || 'YOUR_TOKEN_HERE');
        renderSkillPrompt(plaintextToken, true);
        renderTokensList(data.tokens || []);
        if (!silentStatus) {
          const dateStr = data.created_at ? new Date(data.created_at).toLocaleString() : '';
          setAgentStatus(
            `Agent Token 已激活${dateStr ? `（最近创建于 ${dateStr}）` : ''}，共 ${activeCount} 个有效凭据。`,
            'success'
          );
        }
      } else {
        clearAgentTokenPlaintext(true, false);
        renderTokensList(data.tokens || []);
        if (!silentStatus) {
          setAgentStatus('尚未生成 Token。生成后即可在下方通过 Agent Skill 或 MCP 接入。', 'info');
        }
      }
    } catch (err) {
      setAgentStatus('获取 Token 状态失败，请稍后重试。', 'danger');
    }
  };

  window.createAgentToken = async function createAgentToken(overrideOptions = null) {
    const createBtn = document.getElementById('agent-token-create');
    const nameInput = document.getElementById('agent-token-name-input');
    const expirySelect = document.getElementById('agent-token-expiry-select');
    if (!createBtn) return false;

    const name = overrideOptions?.name !== undefined
      ? String(overrideOptions.name).trim()
      : (nameInput?.value || '').trim();

    let scopes = ['read'];
    if (Array.isArray(overrideOptions?.scopes)) {
      scopes = overrideOptions.scopes;
    } else {
      const selectedScope = document.querySelector('input[name="agent-token-scope"]:checked');
      if (selectedScope?.value === 'write') {
        scopes = ['read', 'write'];
      } else if (selectedScope?.value === 'all') {
        scopes = ['read', 'write', 'delete'];
      }
    }

    let expiresInDays = overrideOptions?.expiresInDays ?? null;
    if (expiresInDays === null && expirySelect && expirySelect.value && expirySelect.value !== 'never') {
      const parsed = parseInt(expirySelect.value, 10);
      if (!Number.isNaN(parsed) && parsed > 0) {
        expiresInDays = parsed;
      }
    }

    let created = false;
    const runCreate = async () => {
      try {
        const data = await dashboardApi.requestJson('/api/agent/token', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            name: name || undefined,
            scopes,
            expires_in_days: expiresInDays,
          }),
        });
        if (!data.token) throw new Error('token missing');

        hasExistingToken = true;
        plaintextToken = data.token;
        plaintextTokenId = data.tokens?.[0]?.id || null;
        plaintextExpiresAt = Date.now() + AGENT_PLAINTEXT_TTL_MS;
        if (plaintextHideTimer) clearTimeout(plaintextHideTimer);
        plaintextHideTimer = setTimeout(() => {
          clearAgentTokenPlaintext(true);
        }, AGENT_PLAINTEXT_TTL_MS);

        if (!overrideOptions && nameInput) nameInput.value = '';
        syncTokenControls();
        renderMcpConfig(plaintextToken);
        renderSkillPrompt(plaintextToken, true);
        setAgentStatus('Token 已生成，请及时复制保存；明文将在 5 分钟后或刷新页面后自动隐藏。', 'success');
        await loadAgentSettings({ silentStatus: true });
        syncTokenControls();
        renderMcpConfig(plaintextToken);
        renderSkillPrompt(plaintextToken, true);
        created = true;
      } catch (err) {
        setAgentStatus('生成 Token 失败，请稍后重试。', 'danger');
      }
    };

    if (window.withButtonBusy) {
      await window.withButtonBusy(createBtn, '正在生成…', runCreate);
    } else {
      await runCreate();
    }
    syncTokenControls();
    return created;
  };

  window.revokeAgentToken = async function revokeAgentToken(tokenId) {
    const isSingle = Boolean(tokenId);
    if (window.uiConfirm) {
      const confirmed = await window.uiConfirm(
        isSingle
          ? {
              title: '撤销此 Token',
              message: '确定撤销该 Agent Token 吗？撤销后使用此凭据的客户端将立即失去访问权限。',
              confirmLabel: '确认撤销',
              cancelLabel: '保留',
              tone: 'danger',
            }
          : {
              title: '撤销全部 Agent Token',
              message: '确定撤销全部 Agent Token 吗？所有已生成的凭据都将立即失效，且无法恢复。',
              confirmLabel: '撤销全部',
              cancelLabel: '保留',
              tone: 'danger',
            }
      );
      if (!confirmed) return;
    }

    const revokeBtn = document.getElementById('agent-token-revoke');
    const runRevoke = async () => {
      try {
        const body = isSingle ? { token_id: tokenId } : {};
        await dashboardApi.requestJson('/api/agent/token', {
          method: 'DELETE',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(body),
        });

        if (!isSingle) {
          hasExistingToken = false;
          clearAgentTokenPlaintext(true, false);
          renderTokensList([]);
          syncTokenControls();
          setAgentStatus('全部 Token 已成功撤销，旧凭据已失效。', 'info');
        } else {
          if (tokenId === plaintextTokenId) {
            clearAgentTokenPlaintext(true, false);
          }
          await loadAgentSettings({ silentStatus: true });
          setAgentStatus('指定 Token 已成功撤销。', 'info');
        }
      } catch (err) {
        setAgentStatus('撤销 Token 失败，请稍后重试。', 'danger');
      }
    };

    if (!isSingle && window.withButtonBusy && revokeBtn) {
      await window.withButtonBusy(revokeBtn, '撤销中…', runRevoke);
    } else {
      await runRevoke();
    }
    syncTokenControls();
  };

  async function copyAgentSnippet(text, button, successMessage, failMessage, fallbackNode = null) {
    if (!text) return false;
    if (window.copyWithFeedback) {
      const ok = await window.copyWithFeedback(text, button, { copiedLabel: '已复制' });
      if (ok) {
        setAgentStatus(successMessage, 'success');
        return true;
      }
    }
    try {
      await navigator.clipboard.writeText(text);
      setAgentStatus(successMessage, 'success');
      return true;
    } catch (_) {
      if (fallbackNode) {
        try {
          const range = document.createRange();
          range.selectNodeContents(fallbackNode);
          const sel = window.getSelection();
          sel?.removeAllRanges();
          sel?.addRange(range);
        } catch (_) { /* ignore */ }
      }
      setAgentStatus(failMessage, 'danger');
      return false;
    }
  }

  window.copyAgentToken = async function copyAgentToken() {
    const tokenInput = document.getElementById('agent-token-input');
    const copyBtn = document.getElementById('agent-token-copy');
    const value = plaintextToken || tokenInput?.value || '';
    if (!value) return;
    await copyAgentSnippet(
      value,
      copyBtn,
      'Token 已复制到剪贴板。',
      '无法自动复制 Token，请手动选中文本框中的密钥复制。'
    );
  };

  window.copySkillPrompt = async function copySkillPrompt() {
    const promptElem = document.getElementById('agent-skill-prompt-code');
    const copyBtn = document.getElementById('agent-skill-copy-prompt');
    if (!promptElem) return;

    if (!plaintextToken && !hasExistingToken) {
      const created = await window.createAgentToken({
        name: 'Agent Skill',
        scopes: ['read'],
        expiresInDays: null,
      });
      if (!created) return;
      const copied = await copyAgentSnippet(
        promptElem.textContent,
        copyBtn,
        '已自动生成只读 Token 并复制安装提示词！直接粘贴发给你的 AI Agent 即可安装。',
        '只读 Token 已生成并填入提示词！请再次点击“复制安装提示词”或手动复制。',
        promptElem
      );
      if (!copied && window.uiToast?.show) {
        window.uiToast.show('已生成只读 Token，点击“复制安装提示词”即可复制。', { tone: 'info' });
      }
      return;
    }

    const msg = plaintextToken
      ? '安装提示词已复制到剪贴板！直接粘贴发给你的 AI Agent 即可自动安装。'
      : '提示词已复制！由于出于安全隐藏了旧 Token 明文，请将 <已激活的Token> 替换为你保存的密钥，或在第一步新增 Token。';
    await copyAgentSnippet(
      promptElem.textContent,
      copyBtn,
      msg,
      '无法自动复制安装提示词，请手动选中复制。',
      promptElem
    );
  };

  window.copySkillUpdatePrompt = async function copySkillUpdatePrompt() {
    const updatePromptElem = document.getElementById('agent-skill-update-prompt-code');
    const copyBtn = document.getElementById('agent-skill-copy-update');
    if (!updatePromptElem) return;
    await copyAgentSnippet(
      updatePromptElem.textContent,
      copyBtn,
      '更新提示词已复制到剪贴板！直接发送给已安装 Skill 的 Agent 即可。',
      '无法自动复制更新提示词，请手动框选复制。',
      updatePromptElem
    );
  };

  window.copyAgentMcpConfig = async function copyAgentMcpConfig() {
    const codeElem = document.getElementById('agent-mcp-config-code');
    const copyBtn = document.getElementById('agent-mcp-copy-config');
    if (!codeElem) return;
    await copyAgentSnippet(
      codeElem.textContent,
      copyBtn,
      'MCP 配置 JSON 已复制到剪贴板！',
      '无法自动复制配置代码，请手动框选复制。',
      codeElem
    );
  };

  document.querySelectorAll('#dashboard-view-agent .agent-details').forEach((detailsEl) => {
    window.uiMotion?.enhanceDisclosure?.(detailsEl);
  });
})();
