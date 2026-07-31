(function initializeScheduleFeature() {
  const form = document.getElementById('schedule-modal-form');
  form?.addEventListener('submit', handleScheduleFormSubmit);
  form?.querySelectorAll('input[name="kind"]').forEach((input) => {
    input.addEventListener('change', toggleScheduleKindFields);
  });
  document.getElementById('schedule-file-input')?.addEventListener('change', (event) => importCourseSchedule(event.target));
})();
