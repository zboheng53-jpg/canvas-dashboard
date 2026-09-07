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

  function setAgentStatus(text, type = 'info') {
    const statusElem = document.getElementById('agent-token-status');
    if (!statusElem) return;
    statusElem.textContent = text;
    statusElem.className = `ui-feedback ui-feedback--${type} calendar-subscription-status`;
  }

  window.loadAgentSettings = async function loadAgentSettings() {
    const tokenInput = document.getElementById('agent-token-input');
    const copyBtn = document.getElementById('agent-token-copy');
    const revokeBtn = document.getElementById('agent-token-revoke');
    const createBtn = document.getElementById('agent-token-create');
    if (!tokenInput || !createBtn) return;

    renderMcpConfig(tokenInput.value || 'YOUR_TOKEN_HERE');

    try {
      const data = await dashboardApi.requestJson('/api/agent/token');
      if (data.has_token) {
        if (!tokenInput.value) {
          tokenInput.placeholder = '•••••••••••••••••••••••••••••••• (已生成)';
        }
        if (copyBtn) copyBtn.disabled = !tokenInput.value;
        if (revokeBtn) revokeBtn.disabled = false;
        createBtn.textContent = '重新生成 Token';
        const dateStr = data.created_at ? new Date(data.created_at).toLocaleString() : '';
        setAgentStatus(`Agent Token 已激活${dateStr ? '（创建于 ' + dateStr + '）' : ''}。重新生成会使旧 Token 立即失效。`, 'success');
      } else {
        tokenInput.value = '';
        tokenInput.placeholder = '尚未生成 Agent Token';
        if (copyBtn) copyBtn.disabled = true;
        if (revokeBtn) revokeBtn.disabled = true;
        createBtn.textContent = '生成 Agent Token';
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
    if (!tokenInput || !createBtn) return;

    if (tokenInput.placeholder.includes('已生成') && !confirm('重新生成将使旧 Token 立即失效，外部正在运行的 Agent 需要更新配置。是否继续？')) {
      return;
    }

    createBtn.disabled = true;
    createBtn.setAttribute('aria-busy', 'true');
    createBtn.textContent = '正在生成…';

    try {
      const data = await dashboardApi.requestJson('/api/agent/token', { method: 'POST' });
      if (!data.token) throw new Error('token missing');

      tokenInput.value = data.token;
      if (copyBtn) copyBtn.disabled = false;
      if (revokeBtn) revokeBtn.disabled = false;
      createBtn.textContent = '重新生成 Token';

      renderMcpConfig(data.token);
      setAgentStatus('🎉 Token 已生成！请立即复制并妥善保管，离开本页面后出于安全将隐藏完整密钥。', 'success');
    } catch (err) {
      setAgentStatus('生成 Token 失败，请稍后重试。', 'danger');
    } finally {
      createBtn.disabled = false;
      createBtn.setAttribute('aria-busy', 'false');
    }
  };

  window.revokeAgentToken = async function revokeAgentToken() {
    if (!confirm('确定要撤销当前 Agent Token 吗？撤销后，所有使用该 Token 的外部 Agent 将立即失去访问权限。')) {
      return;
    }

    const tokenInput = document.getElementById('agent-token-input');
    const createBtn = document.getElementById('agent-token-create');
    const copyBtn = document.getElementById('agent-token-copy');
    const revokeBtn = document.getElementById('agent-token-revoke');
    if (!revokeBtn) return;

    revokeBtn.disabled = true;
    revokeBtn.setAttribute('aria-busy', 'true');

    try {
      await dashboardApi.requestJson('/api/agent/token', { method: 'DELETE' });
      tokenInput.value = '';
      tokenInput.placeholder = '尚未生成 Agent Token';
      if (copyBtn) copyBtn.disabled = true;
      if (revokeBtn) revokeBtn.disabled = true;
      if (createBtn) createBtn.textContent = '生成 Agent Token';
      renderMcpConfig('YOUR_TOKEN_HERE');
      setAgentStatus('Token 已成功撤销，旧凭据已失效。', 'info');
    } catch (err) {
      setAgentStatus('撤销 Token 失败，请稍后重试。', 'danger');
      revokeBtn.disabled = false;
    } finally {
      revokeBtn.setAttribute('aria-busy', 'false');
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
