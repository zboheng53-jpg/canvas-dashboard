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
        return originalFetch(input, options);
      } else {
        const options = init ? Object.assign({}, init) : {};
        const headers = new Headers(options.headers || {});
        if (!headers.has('X-CSRF-Token')) {
          headers.set('X-CSRF-Token', token);
        }
        options.headers = headers;
        return originalFetch(input, options);
      }
    }

    return originalFetch(input, init);
  };
})();
