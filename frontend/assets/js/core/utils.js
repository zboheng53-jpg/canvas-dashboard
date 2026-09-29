/* Dashboard: core/utils.js; loaded in index.html order. */
    function escapeHtml(str) {
      const div = document.createElement('div');
      div.textContent = str;
      return div.innerHTML;
    }

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

