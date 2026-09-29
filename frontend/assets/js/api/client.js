(function attachDashboardApi(global) {
  class DashboardRequestError extends Error {
    constructor(message, { response, data, cause, code, isTimeout, retryAfter } = {}) {
      super(message, { cause });
      this.name = 'DashboardRequestError';
      this.response = response;
      this.data = data;
      this.code = code || data?.code || (response ? `http_${response.status}` : 'network_error');
      this.status = response?.status;
      this.isTimeout = Boolean(isTimeout);
      this.retryAfter = retryAfter;
    }
  }

  async function requestJson(url, options = {}) {
    const timeoutMs = typeof options.timeout === 'number' ? options.timeout : 25000;
    const controller = new AbortController();
    const externalSignal = options.signal;

    let abortListener = null;
    if (externalSignal) {
      if (externalSignal.aborted) {
        controller.abort();
      } else {
        abortListener = () => controller.abort();
        externalSignal.addEventListener('abort', abortListener);
      }
    }

    const timer = timeoutMs > 0 ? setTimeout(() => controller.abort(), timeoutMs) : null;
    const fetchOptions = Object.assign({}, options, { signal: controller.signal });
    delete fetchOptions.timeout;

    let response;
    let data;
    try {
      response = await fetch(url, fetchOptions);
      try {
        data = await response.json();
      } catch (cause) {
        if (cause?.name === 'AbortError') throw cause;
        if (!response.ok) {
          throw new DashboardRequestError(`服务暂时不可用（HTTP ${response.status}）`, { response, cause });
        }
        throw new DashboardRequestError('服务返回了无法识别的数据格式。', { response, cause });
      }
    } catch (cause) {
      if (cause instanceof DashboardRequestError) throw cause;
      if (cause?.name === 'AbortError') {
        if (externalSignal?.aborted) {
          throw new DashboardRequestError('请求已取消。', { cause, code: 'cancelled' });
        }
        throw new DashboardRequestError('网络请求超时，已自动取消，请稍后重试。', { cause, isTimeout: true, code: 'timeout' });
      }
      throw new DashboardRequestError('网络连接失败，请检查网络设置后重试。', { cause, code: 'network_error' });
    } finally {
      if (timer) clearTimeout(timer);
      if (abortListener && externalSignal) externalSignal.removeEventListener('abort', abortListener);
    }

    if (!response.ok || data?.ok === false) {
      let msg = data?.error;
      const status = response.status;
      const retryAfter = response.headers ? response.headers.get('Retry-After') : null;

      if (status === 401) {
        msg = msg || '登录会话已失效，请重新登录。';
      } else if (status === 409) {
        msg = msg || '数据在其他页面已修改，请刷新获取最新内容后再提交。';
      } else if (status === 429) {
        const waitNotice = retryAfter ? `，请在 ${retryAfter} 秒后再试` : '，请稍后重试';
        msg = msg || `请求过于频繁${waitNotice}。`;
      } else if (!msg) {
        msg = `请求失败（HTTP ${status}）`;
      }

      throw new DashboardRequestError(msg, {
        response,
        data,
        code: data?.code,
        retryAfter,
      });
    }

    return data;
  }

  global.dashboardApi = Object.freeze({ requestJson, DashboardRequestError });
})(window);
