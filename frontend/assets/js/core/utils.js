/* Dashboard: core/utils.js; loaded in index.html order. */
const HTML_ESCAPE_MAP = {
  '&': '&amp;',
  '<': '&lt;',
  '>': '&gt;',
  '"': '&quot;',
  "'": '&#39;',
};

function escapeHtml(str) {
  if (str === null || str === undefined) return '';
  return String(str).replace(/[&<>"']/g, (ch) => HTML_ESCAPE_MAP[ch]);
}

function getShanghaiTodayISO() {
  if (typeof window.customToday === 'string' && /^\d{4}-\d{2}-\d{2}$/.test(window.customToday.trim())) {
    return window.customToday.trim();
  }
  try {
    const formatter = new Intl.DateTimeFormat('en-CA', {
      timeZone: 'Asia/Shanghai',
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
    });
    const parts = formatter.formatToParts(new Date());
    const byType = Object.fromEntries(parts.map((part) => [part.type, part.value]));
    if (byType.year && byType.month && byType.day) {
      return `${byType.year}-${byType.month}-${byType.day}`;
    }
  } catch (_) { /* Fallback below if Intl fails. */ }
  const shanghaiNow = new Date(Date.now() + 8 * 60 * 60 * 1000);
  return shanghaiNow.toISOString().slice(0, 10);
}

window.getShanghaiTodayISO = getShanghaiTodayISO;

function sanitizeExternalUrl(value) {
  if (typeof value !== 'string' || !value.trim()) return '';
  try {
    const url = new URL(value);
    return ['https:', 'http:'].includes(url.protocol) ? url.href : '';
  } catch (e) {
    return '';
  }
}

function populateZhixuemengCourseSelect(select, courses, selectedCourse) {
  select.replaceChildren(new Option('全部课程', ''));
  (Array.isArray(courses) ? courses : []).forEach((course) => {
    const option = document.createElement('option');
    option.value = String(course.courseCode || '');
    option.textContent = `${course.courseCode || ''} - ${course.courseName || ''}`;
    select.append(option);
  });
  select.value = selectedCourse || '';
}
