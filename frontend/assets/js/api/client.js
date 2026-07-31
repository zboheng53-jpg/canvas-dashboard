(function attachDashboardApi(global) {
  class DashboardRequestError extends Error {
    constructor(message, { response, data, cause } = {}) {
      super(message, { cause });
      this.name = 'DashboardRequestError';
      this.response = response;
      this.data = data;
    }
  }

  async function requestJson(url, options = {}) {
    let response;
    try {
      response = await fetch(url, options);
    } catch (cause) {
      throw new DashboardRequestError('网络连接失败，请稍后重试。', { cause });
    }

    let data;
    try {
      data = await response.json();
    } catch (cause) {
      throw new DashboardRequestError('服务返回了无法识别的数据。', { response, cause });
    }

    if (!response.ok || data?.ok === false) {
      throw new DashboardRequestError(data?.error || `请求失败（${response.status}）`, { response, data });
    }
    return data;
  }

  global.dashboardApi = Object.freeze({ requestJson, DashboardRequestError });
})(window);
