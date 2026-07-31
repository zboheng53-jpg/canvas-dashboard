(function initializeConnectionsFeature() {
  const bindSubmit = (id, handler) => {
    document.getElementById(id)?.addEventListener('submit', handler);
  };

  bindSubmit('canvas-setup-form-inline', saveCanvasFeedUrlInline);
  bindSubmit('haoke-setup-form-inline', saveHaokeCredentialsInline);
  bindSubmit('zxm-pwd-form-inline', doZhixuemengPasswordLoginInline);
  document.getElementById('zxm-course-select-inline')?.addEventListener('change', changeZhixuemengCourseInline);
})();
