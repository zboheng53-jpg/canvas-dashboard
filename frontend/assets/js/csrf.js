(function () {
  const token = window.CSRF_TOKEN;
  const originalFetch = window.fetch;
  const unsafeMethods = new Set(['POST', 'PUT', 'PATCH', 'DELETE']);

  window.fetch = function (input, init) {
    const options = init ? Object.assign({}, init) : {};
    const method = (options.method || 'GET').toUpperCase();
    if (token && unsafeMethods.has(method)) {
      const headers = new Headers(options.headers || {});
      if (!headers.has('X-CSRF-Token')) {
        headers.set('X-CSRF-Token', token);
      }
      options.headers = headers;
    }
    return originalFetch(input, options);
  };
})();
