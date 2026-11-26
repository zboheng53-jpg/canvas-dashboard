(function initializeConnectionsFeature() {
  const bindSubmit = (id, handler) => {
    document.getElementById(id)?.addEventListener('submit', handler);
  };

  bindSubmit('canvas-setup-form-inline', saveCanvasFeedUrlInline);
  bindSubmit('haoke-setup-form-inline', saveHaokeCredentialsInline);
  bindSubmit('zxm-pwd-form-inline', doZhixuemengPasswordLoginInline);
  document.getElementById('zxm-course-select-inline')?.addEventListener('change', changeZhixuemengCourseInline);
  bindSubmit('ktp-pwd-form-inline', doKetangpaiPasswordLoginInline);
  document.getElementById('ktp-course-select-inline')?.addEventListener('change', changeKetangpaiCourseInline);
  bindSubmit('tjoj-iam-form-inline', doTongjiojIamLoginInline);
  bindSubmit('tjoj-local-form-inline', doTongjiojLocalLoginInline);
  document.getElementById('tjoj-course-select-inline')?.addEventListener('change', changeTongjiojCourseInline);
  bindSubmit('ktp-figure-form', submitKetangpaiFigureCode);

  [
    {
      id: 'platform-data-confirm-modal',
      close: () => closePlatformDataConfirm?.(),
      resetState: () => { platformPendingClear = null; },
    },
    {
      id: 'ktp-figure-modal',
      close: () => closeKetangpaiFigureModal?.(),
      resetState: () => {
        const input = document.getElementById('ktp-figure-input');
        if (input) input.value = '';
        const err = document.getElementById('ktp-figure-error');
        if (err) { err.textContent = ''; err.classList.add('hidden'); }
      },
    },
  ].forEach(({ id, close, resetState }) => {
    const modal = document.getElementById(id);
    if (!modal) return;
    if (window.uiDialog?.bindDialog) {
      window.uiDialog.bindDialog(modal, { onClose: resetState });
    } else {
      modal.addEventListener('click', (event) => {
        if (event.target === modal) close();
      });
    }
  });
})();
