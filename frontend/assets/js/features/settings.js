(function initializeSettingsFeature() {
  const form = document.getElementById('account-delete-form');
  form?.addEventListener('submit', (event) => {
    event.preventDefault();
    deleteCurrentAccount();
  });
  document.getElementById('account-delete-password')?.addEventListener('input', syncDeleteAccountForm);
  document.getElementById('account-delete-confirmation')?.addEventListener('input', syncDeleteAccountForm);
})();
