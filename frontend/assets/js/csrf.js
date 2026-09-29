(function () {
  const token = window.CSRF_TOKEN;
  const originalFetch = window.fetch;
  const unsafeMethods = new Set(['POST', 'PUT', 'PATCH', 'DELETE']);

  function isSameOrigin(targetUrl) {
    if (!targetUrl) return true;
    try {
      const parsed = new URL(targetUrl, window.location.origin);
      return parsed.origin === window.location.origin;
    } catch (_) {
      return false;
    }
  }

  async function resolveOperation(response, signal) {
    if (response.status !== 202) return response;
    const task = await response.clone().json();
    if (!task.async_task || !task.status_url) return response;
    const statusUrl = new URL(task.status_url, window.location.origin);
    if (statusUrl.origin !== window.location.origin || !statusUrl.pathname.startsWith('/api/operations/')) return response;
    const deadline = Date.now() + 10 * 60 * 1000;
    while (Date.now() < deadline) {
      await new Promise((resolve) => setTimeout(resolve, 1000));
      const statusResponse = await originalFetch(statusUrl.href, {signal, credentials: 'same-origin'});
      if (!statusResponse.ok) return statusResponse;
      const status = await statusResponse.json();
      if (status.state === 'done') {
        return new Response(JSON.stringify(status.result), {
          status: status.result_status || 200, headers: {'Content-Type': 'application/json', ...status.result_headers},
        });
      }
    }
    return new Response(JSON.stringify({ok: false, error: '操作仍在后台执行，请稍后查看状态'}), {
      status: 504, headers: {'Content-Type': 'application/json'},
    });
  }

  window.fetch = function (input, init) {
    let url = '';
    let method = 'GET';

    if (typeof input === 'string') {
      url = input;
      method = (init?.method || 'GET').toUpperCase();
    } else if (input instanceof URL) {
      url = input.href;
      method = (init?.method || 'GET').toUpperCase();
    } else if (input && typeof input === 'object' && 'url' in input) {
      url = input.url;
      method = (init?.method || input.method || 'GET').toUpperCase();
    }

    const needsCsrf = Boolean(token && unsafeMethods.has(method) && isSameOrigin(url));

    if (needsCsrf) {
      if (typeof Request !== 'undefined' && input instanceof Request) {
        const headers = new Headers(input.headers);
        if (init?.headers) {
          new Headers(init.headers).forEach((v, k) => headers.set(k, v));
        }
        if (!headers.has('X-CSRF-Token')) {
          headers.set('X-CSRF-Token', token);
        }
        const options = Object.assign({}, init, { headers });
        return originalFetch(input, options).then(response => resolveOperation(response, options.signal));
      } else {
        const options = init ? Object.assign({}, init) : {};
        const headers = new Headers(options.headers || {});
        if (!headers.has('X-CSRF-Token')) {
          headers.set('X-CSRF-Token', token);
        }
        options.headers = headers;
        return originalFetch(input, options).then(response => resolveOperation(response, options.signal));
      }
    }

    return originalFetch(input, init).then(response => resolveOperation(response, init?.signal));
  };
})();
