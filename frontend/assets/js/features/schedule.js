/* Dashboard: features/schedule.js; loaded in index.html order. */
    // ---- Schedule management and today's busy items ----
    const weekdayLabels = ['周一', '周二', '周三', '周四', '周五', '周六', '周日'];
    let scheduleData = null;
    let scheduleToday = null;

    function setScheduleStatus(message, isError = false) {
      const status = document.getElementById('schedule-manager-status');
      if (!status) return;
      status.textContent = message;
      const semantic = isError
        ? 'danger'
        : !message
          ? 'neutral'
          : message.startsWith('正在') || message.startsWith('请在')
            ? 'info'
            : message.includes('重叠')
              ? 'warning'
              : 'success';
      applyFeedbackSemantic(status, semantic);
    }

    function scheduleElement(tag, className, text) {
      const element = document.createElement(tag);
      if (className) element.className = className;
      if (text !== undefined) element.textContent = text;
      return element;
    }

    const scheduleDefaultStartMinutes = 8 * 60;
    const scheduleDefaultEndMinutes = 17 * 60;
    let currentScheduleWeekOffset = 0;
    let scheduleHourHeight = 44;
    let scheduleHasRendered = false;
    let scheduleEditingKind = null;
    let scheduleEditingItem = null;
    let scheduleEditingOccurrenceDate = null;
    let scheduleNowTimer = null;
    let scheduleResizeFrame = null;

    function getMondayOfOffset(offset = 0) {
      const now = new Date();
      const day = now.getDay();
      const diffToMon = day === 0 ? -6 : 1 - day;
      const monday = new Date(now);
      monday.setDate(now.getDate() + diffToMon + (offset * 7));
      monday.setHours(0, 0, 0, 0);
      return monday;
    }

    function getWeekDates(offset = 0) {
      const monday = getMondayOfOffset(offset);
      return Array.from({length: 7}, (_, index) => {
        const date = new Date(monday);
        date.setDate(monday.getDate() + index);
        return date;
      });
    }

    function formatDateISO(date) {
      const year = date.getFullYear();
      const month = String(date.getMonth() + 1).padStart(2, '0');
      const day = String(date.getDate()).padStart(2, '0');
      return `${year}-${month}-${day}`;
    }

    function timeToMinutes(timeStr) {
      if (!timeStr) return 0;
      const [hour, minute] = timeStr.split(':').map(Number);
      return (hour || 0) * 60 + (minute || 0);
    }

    function minutesToTime(minutes) {
      const bounded = Math.max(0, Math.min(1439, minutes));
      return `${String(Math.floor(bounded / 60)).padStart(2, '0')}:${String(bounded % 60).padStart(2, '0')}`;
    }

    function calculateWeekNumber(dateObj, semesterStartStr) {
      if (!semesterStartStr) return null;
      const parts = semesterStartStr.split('-').map(Number);
      if (parts.length !== 3 || parts.some(value => !Number.isInteger(value))) return null;
      const startDay = Date.UTC(parts[0], parts[1] - 1, parts[2]);
      const currentDay = Date.UTC(dateObj.getFullYear(), dateObj.getMonth(), dateObj.getDate());
      const diffDays = Math.floor((currentDay - startDay) / (1000 * 60 * 60 * 24));
      const weekNum = Math.floor(diffDays / 7) + 1;
      return weekNum > 0 ? weekNum : null;
    }

    function formatWeekRanges(weeks) {
      if (!weeks || !weeks.length) return '';
      const sorted = Array.from(new Set(weeks)).filter(n => typeof n === 'number' && !isNaN(n)).sort((a, b) => a - b);
      if (!sorted.length) return '';
      const ranges = [];
      let start = sorted[0], prev = start;
      for (let i = 1; i < sorted.length; i += 1) {
        if (sorted[i] === prev + 1) {
          prev = sorted[i];
        } else {
          ranges.push(start === prev ? `${start}` : `${start}-${prev}`);
          start = sorted[i];
          prev = start;
        }
      }
      ranges.push(start === prev ? `${start}` : `${start}-${prev}`);
      return `第${ranges.join(',')}周`;
    }

    function navigateScheduleWeek(offsetDelta) {
      currentScheduleWeekOffset = offsetDelta === 0 ? 0 : currentScheduleWeekOffset + offsetDelta;
      loadScheduleManager();
    }

    function scheduleEventGroups(events) {
      const sorted = [...events].sort((a, b) => timeToMinutes(a.start_time) - timeToMinutes(b.start_time) || timeToMinutes(a.end_time) - timeToMinutes(b.end_time));
      const groups = [];
      sorted.forEach((event) => {
        const start = timeToMinutes(event.start_time);
        const last = groups[groups.length - 1];
        if (!last || start >= last.end) {
          groups.push({events: [event], end: timeToMinutes(event.end_time)});
        } else {
          last.events.push(event);
          last.end = Math.max(last.end, timeToMinutes(event.end_time));
        }
      });
      return groups;
    }

    function collectScheduleEvents(data, courses, dateObj, dayIdx, semesterStart) {
      const dateISO = formatDateISO(dateObj);
      const weekNum = calculateWeekNumber(dateObj, semesterStart);
      const events = [];

      (courses.courses || []).forEach((course, courseIndex) => {
        (course.sessions || []).forEach((session, sessionIndex) => {
          if (session.weekday !== dayIdx) return;
          let valid = true;
          if (session.date_start && session.date_end) {
            valid = session.date_start <= dateISO && dateISO <= session.date_end;
          } else if (session.weeks?.length) {
            valid = Boolean(weekNum && session.weeks.includes(weekNum));
          } else if (semesterStart && !weekNum) {
            valid = false;
          }
          if (session.parity === 'odd' && (!weekNum || weekNum % 2 === 0)) valid = false;
          if (session.parity === 'even' && (!weekNum || weekNum % 2 !== 0)) valid = false;
          if (!valid) return;
          events.push({
            uid: `course-${courseIndex}-${sessionIndex}`,
            kind: 'course',
            title: course.name,
            location: session.location || course.location || '',
            start_time: session.start_time,
            end_time: session.end_time,
            session,
            courseIndex,
            raw: course
          });
        });
      });

      (data.items?.recurring || []).forEach((item) => {
        const inRange = (!item.start_date || item.start_date <= dateISO) && (!item.end_date || dateISO <= item.end_date);
        if (!item.enabled || !inRange || item.weekday !== dayIdx || item.skipped_dates?.includes(dateISO)) return;
        events.push({
          uid: `recurring-${item.id}`,
          kind: 'recurring',
          title: item.title,
          location: item.location || '',
          start_time: item.start_time,
          end_time: item.end_time,
          raw: item
        });
      });

      (data.items?.one_off || []).forEach((item) => {
        if (item.date !== dateISO) return;
        events.push({
          uid: `one-off-${item.id}`,
          kind: 'one-off',
          title: item.title,
          location: item.location || '',
          start_time: item.start_time,
          end_time: item.end_time,
          raw: item
        });
      });
      return events;
    }

    function buildScheduleCard(event, dateISO, lane = 0, laneCount = 1) {
      const duration = Math.max(1, timeToMinutes(event.end_time) - timeToMinutes(event.start_time));
      const cardKind = event.kind === 'one-off' ? 'oneoff' : event.kind;
      const card = scheduleElement('button', `schedule-card schedule-card-${cardKind}${duration <= 30 ? ' is-compact' : ''}`);
      card.type = 'button';
      card.style.top = `${timeToMinutes(event.start_time) / 60 * scheduleHourHeight}px`;
      card.style.height = `${duration / 60 * scheduleHourHeight}px`;
      if (laneCount > 1) {
        card.style.left = `calc(${lane / laneCount * 100}% + 3px)`;
        card.style.width = `calc(${100 / laneCount}% - 5px)`;
        card.style.right = 'auto';
      } else {
        card.style.left = '3px';
        card.style.right = '3px';
        card.style.width = 'calc(100% - 6px)';
      }
      const fullDescription = [event.title, `${event.start_time} - ${event.end_time}`, event.location].filter(Boolean).join('\n');
      card.title = fullDescription;
      card.setAttribute('aria-label', fullDescription.replaceAll('\n', '，'));
      card.append(scheduleElement('span', 'schedule-card-title', event.title));
      if (duration <= 30) {
        card.append(scheduleElement('span', 'schedule-card-summary', `${event.start_time} - ${event.end_time}${event.location ? ` · ${event.location}` : ''}`));
      } else {
        card.append(scheduleElement('span', 'schedule-card-time', `${event.start_time} - ${event.end_time}`));
        if (event.location) card.append(scheduleElement('span', 'schedule-card-loc', event.location));
      }
      card.addEventListener('click', (clickEvent) => {
        clickEvent.stopPropagation();
        onScheduleCardClick(event, dateISO);
      });
      return card;
    }

    function renderScheduleRangeHint(element, direction, dayEvents) {
      element.replaceChildren();
      const entries = dayEvents.filter((entry) => entry.events.length);
      element.classList.toggle('hidden', entries.length === 0);
      if (!entries.length) return;
      element.append(scheduleElement(
        'span',
        '',
        direction === 'before'
          ? `↑ ${minutesToTime(scheduleDefaultStartMinutes)} 前：`
          : `↓ ${minutesToTime(scheduleDefaultEndMinutes)} 后：`
      ));
      entries.forEach((entry, index) => {
        const button = scheduleElement('button', 'schedule-range-day', `${weekdayLabels[entry.day]} ${entry.events.length} 项`);
        button.type = 'button';
        const targetMinute = direction === 'before'
          ? Math.min(...entry.events.map(event => timeToMinutes(event.start_time)))
          : Math.max(...entry.events.map(event => timeToMinutes(event.start_time)));
        button.addEventListener('click', () => scrollScheduleToMinute(targetMinute));
        element.append(button);
        if (index < entries.length - 1) element.append(document.createTextNode(' · '));
      });
    }

    function updateScheduleScrollAffordance() {
      const viewport = document.getElementById('schedule-scroll-viewport');
      const returnButton = document.getElementById('schedule-return-default');
      if (!viewport || !returnButton) return;
      returnButton.classList.toggle('hidden', Math.abs(viewport.scrollTop - getScheduleDefaultScrollTop()) < scheduleHourHeight / 2);
    }

    function scrollScheduleToMinute(minute, behavior = 'smooth') {
      const viewport = document.getElementById('schedule-scroll-viewport');
      if (!viewport) return;
      viewport.scrollTo({top: Math.max(0, minute / 60 * scheduleHourHeight - 12), behavior});
    }

    function scrollScheduleToDefault() {
      const viewport = document.getElementById('schedule-scroll-viewport');
      if (!viewport) return;
      viewport.scrollTo({top: getScheduleDefaultScrollTop(), behavior: 'smooth'});
    }

    function getScheduleDefaultScrollTop() {
      return Math.max(0, scheduleDefaultStartMinutes / 60 * scheduleHourHeight - 6);
    }

    function renderScheduleManager(data) {
      scheduleData = data;
      const courses = data.courses || {};
      const viewport = document.getElementById('schedule-scroll-viewport');
      const grid = document.getElementById('schedule-timetable-grid');
      const header = document.getElementById('schedule-grid-header');
      if (!viewport || !grid || !header) return;
      const preservedScrollMinute = scheduleHasRendered ? viewport.scrollTop / scheduleHourHeight * 60 : null;
      const defaultVisibleHours = (scheduleDefaultEndMinutes - scheduleDefaultStartMinutes) / 60;
      scheduleHourHeight = Math.max(52, Math.min(90, (viewport.clientHeight - 12) / defaultVisibleHours || 52));
      grid.style.setProperty('--schedule-hour-height', `${scheduleHourHeight}px`);
      header.style.setProperty('--schedule-hour-height', `${scheduleHourHeight}px`);

      const meta = document.getElementById('schedule-term-meta');
      const summary = document.getElementById('schedule-management-summary');
      const metaText = courses.updated_at
        ? `${courses.term || '当前学期'} · 更新于 ${new Date(courses.updated_at).toLocaleDateString('zh-CN')}`
        : '尚未导入本学期课表';
      if (meta) meta.textContent = metaText;
      if (summary) summary.textContent = `${metaText} · 已导入 ${(courses.courses || []).length} 门课程`;

      const courseList = courses.courses || [];
      const headerClearBtn = document.getElementById('schedule-header-clear-btn');
      const coursesSection = document.getElementById('schedule-courses-section');
      const coursesListEl = document.getElementById('schedule-courses-list');
      const coursesCountEl = document.getElementById('schedule-courses-count');

      if (headerClearBtn) {
        headerClearBtn.disabled = courseList.length === 0;
        headerClearBtn.title = courseList.length === 0 ? '当前暂无已导入课程' : '清空本学期已导入课程';
      }

      if (coursesSection && coursesListEl) {
        if (courseList.length > 0) {
          coursesSection.classList.remove('hidden');
          if (coursesCountEl) coursesCountEl.textContent = `${courseList.length} 门`;
          coursesListEl.replaceChildren();
          courseList.forEach((course) => {
            const item = scheduleElement('div', 'schedule-course-manage-item');
            const info = scheduleElement('div', 'schedule-course-manage-info');
            const nameEl = scheduleElement('div', 'schedule-course-manage-name', course.name || '未命名课程');
            const sessionTimes = (course.sessions || []).map(s => {
              const weekLabel = formatWeekRanges(s.weeks);
              const loc = s.location && s.location !== course.location ? `(${s.location})` : '';
              const timeStr = `${weekdayLabels[s.weekday]} ${s.start_time}-${s.end_time}`;
              return [weekLabel, timeStr, loc].filter(Boolean).join(' ');
            }).join('；');
            const metaParts = [course.teacher, sessionTimes, course.location].filter(Boolean);
            const metaEl = scheduleElement('div', 'schedule-course-manage-meta', metaParts.join(' · ') || '无时间信息');
            info.append(nameEl, metaEl);

            const delBtn = scheduleElement('button', 'ui-button ui-button--secondary ui-button--sm schedule-course-manage-delete', '删除');
            delBtn.type = 'button';
            delBtn.title = `从课表中移除「${course.name}」`;
            delBtn.addEventListener('click', async (e) => {
              e.stopPropagation();
              const cName = course.name || '此课程';
              if (!confirm(`确定从课表中移除「${cName}」吗？\n移除后可通过重新导入课表恢复。`)) return;
              const cId = course.id || course.code || course.name;
              await deleteCourseById(cId, cName);
            });

            item.append(info, delBtn);
            coursesListEl.append(item);
          });
        } else {
          coursesSection.classList.add('hidden');
          coursesListEl.replaceChildren();
        }
      }

      const weekDates = getWeekDates(currentScheduleWeekOffset);
      const todayISO = formatDateISO(new Date());
      const semesterStart = courses.semester_start || '';
      const monday = weekDates[0];
      const sunday = weekDates[6];
      const weekNum = calculateWeekNumber(monday, semesterStart);
      document.getElementById('schedule-week-label').textContent =
        `${monday.getMonth() + 1}月${monday.getDate()}日—${sunday.getMonth() + 1}月${sunday.getDate()}日${weekNum ? ` · 第 ${weekNum} 周` : ''}`;

      return renderPeriodSchedule(data);
    }

    function updateScheduleNowLine() {
      const line = document.querySelector('.schedule-now-line');
      if (!line || currentScheduleWeekOffset !== 0) return;
      const now = new Date();
      line.style.top = `${(now.getHours() * 60 + now.getMinutes()) / 60 * scheduleHourHeight}px`;
      line.dataset.time = `${String(now.getHours()).padStart(2, '0')}:${String(now.getMinutes()).padStart(2, '0')}`;
    }

    window.addEventListener('resize', () => {
      if (!scheduleData || document.getElementById('dashboard-view-schedule')?.classList.contains('hidden')) return;
      cancelAnimationFrame(scheduleResizeFrame);
      scheduleResizeFrame = requestAnimationFrame(() => renderScheduleManager(scheduleData));
    });

    let currentViewingCourse = null;
    let currentViewingCourseEvent = null;

    function onScheduleCardClick(event, dateISO) {
      if (event.kind === 'course') {
        openScheduleCourseModal(event.raw, event);
        return;
      }
      openScheduleItemModal(event.kind, event.raw, {date: dateISO});
    }

    function openScheduleCourseModal(course, event) {
      currentViewingCourse = course;
      currentViewingCourseEvent = event;
      const modal = document.getElementById('schedule-course-modal');
      if (!modal) return;
      document.getElementById('schedule-course-title').textContent = course.name || '未命名课程';
      document.getElementById('schedule-course-teacher').textContent = course.teacher || '未指定';
      document.getElementById('schedule-course-time').textContent = `${event.start_time} - ${event.end_time}`;
      document.getElementById('schedule-course-location').textContent = event.location || course.location || '按课表安排';

      const weeksRow = document.getElementById('schedule-course-weeks-row');
      const weeksVal = document.getElementById('schedule-course-weeks');
      const session = event.session;
      let weeksText = '';
      if (session?.weeks?.length) {
        const parityText = session.parity === 'odd' ? '（单周）' : session.parity === 'even' ? '（双周）' : '';
        weeksText = `${formatWeekRanges(session.weeks)} ${parityText}`.trim();
      } else if (course.raw_time) {
        weeksText = course.raw_time;
      } else if (session?.date_start && session?.date_end) {
        weeksText = `${session.date_start} 至 ${session.date_end}`;
      }
      if (weeksText && weeksVal && weeksRow) {
        weeksVal.textContent = weeksText;
        weeksRow.classList.remove('hidden');
      } else if (weeksRow) {
        weeksRow.classList.add('hidden');
      }
      modal.classList.remove('hidden');
    }

    function closeScheduleCourseModal() {
      document.getElementById('schedule-course-modal')?.classList.add('hidden');
      currentViewingCourse = null;
      currentViewingCourseEvent = null;
    }

    async function deleteCourseFromModal() {
      if (!currentViewingCourse) return;
      const courseName = currentViewingCourse.name || '此课程';
      const courseId = currentViewingCourse.id || currentViewingCourse.code || currentViewingCourse.name;
      if (!confirm(`确定从课表中移除「${courseName}」吗？\n移除后可通过重新导入课表恢复。`)) return;
      closeScheduleCourseModal();
      await deleteCourseById(courseId, courseName);
    }

    function openScheduleOverlapPopover(events, dateISO, anchor) {
      const popover = document.getElementById('schedule-overlap-popover');
      const list = document.getElementById('schedule-overlap-list');
      list.replaceChildren();
      events.forEach((event) => {
        const button = scheduleElement('button', 'schedule-overlap-item');
        button.type = 'button';
        button.append(
          scheduleElement('strong', '', event.title),
          scheduleElement('span', '', `${event.start_time} - ${event.end_time}${event.location ? ` · ${event.location}` : ''}`)
        );
        button.addEventListener('click', () => {
          closeScheduleOverlapPopover();
          onScheduleCardClick(event, dateISO);
        });
        list.append(button);
      });
      const box = anchor.getBoundingClientRect();
      popover.style.left = `${Math.min(window.innerWidth - 300, box.left)}px`;
      popover.style.top = `${Math.min(window.innerHeight - 260, box.bottom + 6)}px`;
      popover.classList.remove('hidden');
    }

    function closeScheduleOverlapPopover() {
      document.getElementById('schedule-overlap-popover')?.classList.add('hidden');
    }

    function defaultScheduleStartTime() {
      const now = new Date();
      const rounded = Math.ceil((now.getHours() * 60 + now.getMinutes()) / 30) * 30;
      return minutesToTime(Math.max(8 * 60, Math.min(20 * 60, rounded)));
    }

    function openScheduleActionPicker() {
      if (typeof openActionSearch === 'function') {
        openActionSearch({
          onSelect: (action) => {
            linkScheduleAction(action);
          }
        });
      }
    }

    function linkScheduleAction(action) {
      if (!action) return;
      document.getElementById('schedule-form-title').value = action.title;
      document.getElementById('schedule-form-action-ref').value = action.ref;
      document.getElementById('schedule-form-title').readOnly = true;
      const hint = document.getElementById('schedule-link-hint');
      if (hint) hint.textContent = `已关联事项「${action.title}」，标题与完成状态保持同步。`;
      document.getElementById('schedule-btn-pick-action')?.classList.add('hidden');
      document.getElementById('schedule-btn-unlink-action')?.classList.remove('hidden');
      document.getElementById('field-schedule-create-todo-wrap')?.classList.add('hidden');
    }

    function unlinkScheduleAction() {
      document.getElementById('schedule-form-action-ref').value = '';
      document.getElementById('schedule-form-title').readOnly = false;
      const hint = document.getElementById('schedule-link-hint');
      if (hint) hint.textContent = '当前为独立日程，仅在日程中显示，不加入待办清单。';
      document.getElementById('schedule-btn-pick-action')?.classList.remove('hidden');
      document.getElementById('schedule-btn-unlink-action')?.classList.add('hidden');
      document.getElementById('field-schedule-create-todo-wrap')?.classList.remove('hidden');
    }

    function openScheduleItemModal(defaultKind = 'one-off', item = null, presets = {}) {
      const modal = document.getElementById('schedule-item-modal');
      const form = document.getElementById('schedule-modal-form');
      if (!modal || !form) return;
      form.reset();
      const errEl = document.getElementById('schedule-form-error');
      if (errEl) { errEl.textContent = ''; errEl.style.display = 'none'; }
      scheduleEditingKind = item ? (defaultKind === 'recurring' || item.kind === 'recurring' ? 'recurring' : 'one-off') : null;
      scheduleEditingItem = item;
      scheduleEditingOccurrenceDate = presets.date || item?.date || formatDateISO(new Date());
      const kind = scheduleEditingKind || defaultKind || 'one-off';
      document.getElementById('schedule-form-id').value = item?.id || '';
      document.getElementById('schedule-modal-title').textContent = item ? '编辑排程事项' : '添加排程事项';
      for (const radio of form.elements.kind) {
        radio.checked = radio.value === kind;
        radio.disabled = Boolean(item) && radio.value !== kind;
      }
      const startTime = item?.start_time || presets.start_time || defaultScheduleStartTime();
      const hasActionRef = Boolean(item?.action_ref || presets.action_ref);
      document.getElementById('schedule-form-title').value = item?.title || presets.title || '';
      document.getElementById('schedule-form-action-ref').value = item?.action_ref || presets.action_ref || '';
      document.getElementById('schedule-form-title').readOnly = hasActionRef;
      document.getElementById('schedule-form-details').value = item?.details || '';

      const linkHint = document.getElementById('schedule-link-hint');
      const pickBtn = document.getElementById('schedule-btn-pick-action');
      const unlinkBtn = document.getElementById('schedule-btn-unlink-action');
      const createWrap = document.getElementById('field-schedule-create-todo-wrap');
      const createCheck = document.getElementById('schedule-form-create-todo');
      if (createCheck) createCheck.checked = false;

      if (hasActionRef) {
        if (linkHint) linkHint.textContent = '已关联事项；这里调整时间，事项标题与完成状态保持同步。';
        pickBtn?.classList.add('hidden');
        unlinkBtn?.classList.remove('hidden');
        createWrap?.classList.add('hidden');
      } else {
        if (linkHint) linkHint.textContent = '当前为独立日程，仅在日程中显示，不加入待办清单。';
        pickBtn?.classList.remove('hidden');
        unlinkBtn?.classList.add('hidden');
        createWrap?.classList.toggle('hidden', Boolean(item));
      }

      document.getElementById('schedule-form-start').value = startTime;
      document.getElementById('schedule-form-end').value = item?.end_time || presets.end_time || minutesToTime(timeToMinutes(startTime) + 60);
      document.getElementById('schedule-form-location').value = item?.location || '';
      document.getElementById('schedule-form-date').value = item?.date || presets.date || formatDateISO(new Date());
      const currentWeekday = new Date().getDay() === 0 ? 6 : new Date().getDay() - 1;
      document.getElementById('schedule-form-weekday').value = item?.weekday ?? presets.weekday ?? currentWeekday;
      document.getElementById('schedule-form-repeat-start').value = item?.start_date || presets.date || formatDateISO(new Date());
      document.getElementById('schedule-form-repeat-end').value = item?.end_date || '';
      document.getElementById('schedule-edit-scope').classList.toggle('hidden', !(item && kind === 'recurring'));
      const hasOccurrence = Boolean(presets.date);
      form.elements.scope.value = hasOccurrence ? 'occurrence' : 'series';
      form.querySelector('[name=scope][value=occurrence]').disabled = !hasOccurrence;
      document.querySelector('#schedule-edit-scope legend').textContent = hasOccurrence ? `修改范围 · ${presets.date}` : '修改范围（从周排程选择某一天可仅调整本次）';
      document.getElementById('schedule-item-delete').classList.toggle('hidden', !item);
      toggleScheduleKindFields();
      modal.classList.remove('hidden');
      document.getElementById(item?.action_ref || presets.action_ref ? 'schedule-form-start' : 'schedule-form-title').focus();
    }

    function closeScheduleItemModal() {
      document.getElementById('schedule-item-modal')?.classList.add('hidden');
    }

    function toggleScheduleKindFields() {
      const form = document.getElementById('schedule-modal-form');
      if (!form) return;
      const kind = form.elements.kind.value;
      const recurring = document.getElementById('field-recurring-weekday');
      const oneOff = document.getElementById('field-one-off-date');
      recurring.classList.toggle('hidden', kind !== 'recurring');
      oneOff.classList.toggle('hidden', kind === 'recurring');
      document.getElementById('schedule-form-date').required = kind === 'one-off';
      document.getElementById('schedule-form-weekday').required = kind === 'recurring';
      document.getElementById('schedule-form-repeat-start').required = kind === 'recurring';
    }

    async function handleScheduleFormSubmit(event) {
      event.preventDefault();
      const form = event.currentTarget;
      const errorEl = document.getElementById('schedule-form-error');
      if (errorEl) {
        errorEl.textContent = '';
        errorEl.style.display = 'none';
      }

      const formData = new FormData(form);
      const kind = formData.get('kind');
      const startTime = formData.get('start_time');
      const endTime = formData.get('end_time');

      if (startTime && endTime && startTime >= endTime) {
        if (errorEl) {
          errorEl.textContent = '结束时间必须晚于开始时间';
          errorEl.style.display = 'block';
        } else {
          alert('结束时间必须晚于开始时间');
        }
        return;
      }

      const payload = {
        title: formData.get('title'),
        action_ref: formData.get('action_ref') || null,
        details: formData.get('details'),
        start_time: startTime,
        end_time: endTime,
        location: formData.get('location')
      };

      if (kind === 'recurring') {
        payload.weekday = Number(formData.get('weekday'));
        payload.start_date = formData.get('start_date');
        payload.end_date = formData.get('end_date') || null;
        payload.enabled = scheduleEditingItem?.enabled ?? true;
        payload.skipped_dates = scheduleEditingItem?.skipped_dates || [];
      } else {
        payload.date = formData.get('date');
      }

      const submitBtn = form.querySelector('button[type="submit"]');
      const origBtnText = submitBtn ? submitBtn.textContent : '保存事项';
      if (submitBtn) {
        submitBtn.disabled = true;
        submitBtn.setAttribute('aria-busy', 'true');
        submitBtn.textContent = '正在保存…';
      }

      try {
        if (!payload.action_ref && formData.get('create_todo')) {
          const todoResp = await fetch('/api/custom/todos', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({
              text: payload.title,
              due_date: payload.date || null,
              details: payload.details || '',
            }),
          });
          const todoData = await todoResp.json();
          if (!todoResp.ok || !todoData.ok) {
            throw new Error(todoData.error || '创建关联待办失败');
          }
          payload.action_ref = todoData.todo?.ref;
          if (typeof fetchCustomTodos === 'function') fetchCustomTodos();
        }

        if (scheduleEditingKind === 'recurring' && formData.get('scope') === 'occurrence') {
          const exceptionUrl = `/api/schedule/recurring/${scheduleEditingItem.id}/exception`;
          const exceptionBody = {
            date: scheduleEditingOccurrenceDate,
            expected_updated_at: scheduleEditingItem.updated_at,
            changes: {
              ...payload,
              date: payload.date || scheduleEditingOccurrenceDate,
            }
          };
          const response = await fetch(exceptionUrl, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify(exceptionBody),
          });
          const data = await response.json();
          if (!response.ok || !data.ok) {
            throw new Error(data.error || '单次排程修改失败');
          }
          setScheduleStatus(data.overlap ? '已保存；该事项与其他日程时间重叠' : '已保存');
          await loadScheduleManager();
          await loadTodaySchedule();
        } else {
          await saveScheduleItem(kind, scheduleEditingItem?.id || null, payload);
        }
        if (typeof notifyCrossTabChange === 'function') notifyCrossTabChange('schedule');
        closeScheduleItemModal();
      } catch (err) {
        if (errorEl) {
          errorEl.textContent = err.message || '保存失败，请检查输入后重试';
          errorEl.style.display = 'block';
        } else {
          alert('保存失败：' + (err.message || '网络异常'));
        }
      } finally {
        if (submitBtn) {
          submitBtn.disabled = false;
          submitBtn.removeAttribute('aria-busy');
          submitBtn.textContent = origBtnText;
        }
      }
    }

    async function deleteScheduleItemFromModal() {
      if (!scheduleEditingItem || !confirm(`确定删除「${scheduleEditingItem.title}」吗？`)) return;
      const form = document.getElementById('schedule-modal-form');
      const scope = new FormData(form).get('scope');
      try {
        if (scheduleEditingKind === 'recurring' && scope === 'occurrence') {
          const exceptionUrl = `/api/schedule/recurring/${scheduleEditingItem.id}/exception`;
          const response = await fetch(exceptionUrl, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({
              date: scheduleEditingOccurrenceDate,
              cancel: true,
              expected_updated_at: scheduleEditingItem.updated_at,
            }),
          });
          const data = await response.json();
          if (!response.ok || !data.ok) throw new Error(data.error || '删除本次安排失败');
          await loadScheduleManager();
          await loadTodaySchedule();
        } else {
          await deleteScheduleItem(scheduleEditingKind, scheduleEditingItem.id);
        }
        if (typeof notifyCrossTabChange === 'function') notifyCrossTabChange('schedule');
        closeScheduleItemModal();
      } catch (err) {
        alert('删除失败：' + err.message);
      }
    }

    function openScheduleManagementModal() {
      document.getElementById('schedule-management-modal')?.classList.remove('hidden');
    }

    function closeScheduleManagementModal() {
      document.getElementById('schedule-management-modal')?.classList.add('hidden');
    }

    async function loadScheduleManager() {
      setScheduleStatus('正在加载日程…');
      try {
        const response = await fetch('/api/schedule');
        const data = await response.json();
        if (!response.ok || !data.ok) throw new Error(data.error || 'load failed');
        renderScheduleManager(data);
        setScheduleStatus('');
      } catch (error) {
        setScheduleStatus('日程加载失败，请稍后重试', true);
      }
    }

    let tongjiLoginSessionToken = null;

    async function openTongjiLoginSession() {
      const button = document.getElementById('schedule-refresh-button');
      const popup = window.open('', 'tongji-enhanced-auth', 'popup,width=1280,height=900');
      if (!popup) {
        setScheduleStatus('浏览器拦截了认证窗口，请允许弹窗后重试', true);
        return;
      }
      popup.document.title = '正在打开同济认证窗口';
      popup.document.body.innerHTML = '<p style="font:16px sans-serif;padding:32px">正在打开同济统一身份认证窗口…</p>';
      button.disabled = true;
      setScheduleStatus('正在打开统一身份认证窗口…');
      try {
        const response = await fetch('/api/schedule/login-session', {method: 'POST'});
        const data = await response.json();
        if (!response.ok || !data.ok) throw new Error(data.error || '无法打开认证窗口');
        tongjiLoginSessionToken = data.token;
        popup.location.href = data.url;
        button.textContent = '我已完成认证，导入课表';
        button.onclick = completeTongjiLoginSession;
        setScheduleStatus('请在新窗口中完成微信扫码或短信验证码认证，再返回此处导入；系统会等待个人课表加载完成。');
      } catch (error) {
        const message = error.message || '认证窗口启动失败';
        popup.document.title = '无法打开同济认证窗口';
        popup.document.body.innerHTML = '<main style="max-width:640px;margin:64px auto;padding:0 24px;font:16px/1.6 sans-serif;color:#1f2937"><h1 style="font-size:24px">认证窗口未能启动</h1><p id="tongji-login-error"></p><p style="color:#64748b">本机调试需要 Docker Desktop 正在运行，并已构建受限浏览器镜像。</p></main>';
        popup.document.getElementById('tongji-login-error').textContent = message;
        setScheduleStatus(message, true);
      } finally {
        button.disabled = false;
      }
    }

    async function completeTongjiLoginSession() {
      if (!tongjiLoginSessionToken) return;
      const button = document.getElementById('schedule-refresh-button');
      button.disabled = true;
      setScheduleStatus('正在读取已认证会话中的课表…');
      try {
        const response = await fetch(`/api/schedule/login-session/${tongjiLoginSessionToken}/complete`, {method: 'POST'});
        const data = await response.json();
        if (!response.ok || !data.ok) throw new Error(data.error || '课表导入失败');
        tongjiLoginSessionToken = null;
        button.textContent = '统一身份认证登录';
        button.onclick = openTongjiLoginSession;
        setScheduleStatus(`已更新 ${data.courses.courses.length} 门课程`);
        renderScheduleManager({courses: data.courses, items: scheduleData?.items || {recurring: [], one_off: []}});
        await loadTodaySchedule();
      } catch (error) {
        setScheduleStatus(error.message || '课表导入失败，请在认证窗口完成验证后重试', true);
        button.disabled = false;
      }
    }

    async function importCourseSchedule(input) {
      const file = input.files && input.files[0];
      input.value = '';
      if (!file) return;
      const button = document.getElementById('schedule-import-button');
      button.disabled = true;
      setScheduleStatus('正在导入课表文件…');
      try {
        const body = new FormData();
        body.append('course_file', file);
        const response = await fetch('/api/schedule/import', {method: 'POST', body});
        const data = await response.json();
        if (!response.ok || !data.ok) throw new Error(data.error || 'import failed');
        setScheduleStatus(`已导入 ${data.courses.courses.length} 门课程`);
        renderScheduleManager({courses: data.courses, items: scheduleData?.items || {recurring: [], one_off: []}});
        await loadTodaySchedule();
      } catch (error) {
        setScheduleStatus(error.message || '课表导入失败，请确认文件来自课表插件', true);
      } finally {
        button.disabled = false;
      }
    }

    async function saveScheduleItem(kind, itemId, payload) {
      const url = itemId ? `/api/schedule/${kind === 'recurring' ? 'recurring' : 'one-off'}/${itemId}` : `/api/schedule/${kind === 'recurring' ? 'recurring' : 'one-off'}`;
      const response = await fetch(url, {method: itemId ? 'PUT' : 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(payload)});
      const data = await response.json();
      if (!response.ok || !data.ok) {
        setScheduleStatus(data.error || '保存失败', true);
        throw new Error(data.error || '保存失败');
      }
      setScheduleStatus(data.overlap ? '已保存；该事项与其他日程时间重叠' : '已保存');
      await loadScheduleManager(); await loadTodaySchedule();
      return data;
    }

    async function deleteScheduleItem(kind, itemId) {
      const response = await fetch(`/api/schedule/${kind === 'recurring' ? 'recurring' : 'one-off'}/${itemId}`, {method: 'DELETE'});
      const data = await response.json();
      if (!response.ok || !data.ok) { setScheduleStatus('删除失败', true); return; }
      await loadScheduleManager(); await loadTodaySchedule();
    }

    async function deleteCourseById(courseId, courseName = '') {
      setScheduleStatus('正在删除课程…');
      try {
        const response = await fetch(`/api/schedule/courses/${encodeURIComponent(courseId)}`, {method: 'DELETE'});
        const data = await response.json();
        if (!response.ok || !data.ok) throw new Error(data.error || '删除失败');
        setScheduleStatus(courseName ? `已从课表中移除「${courseName}」` : '已从课表中移除该课程');
        await loadScheduleManager();
        await loadTodaySchedule();
      } catch (error) {
        setScheduleStatus(error.message || '删除课程失败，请重试', true);
      }
    }

    async function clearAllCourses() {
      const courseList = scheduleData?.courses?.courses || [];
      if (courseList.length === 0) {
        alert('当前尚未导入课表，无需清空。');
        return;
      }
      if (!confirm('确定清空本学期已导入的所有课程吗？\n清空后课表将被重置，需通过统一身份认证或插件重新导入。')) return;
      setScheduleStatus('正在清空课表…');
      try {
        const response = await fetch('/api/schedule/courses', {method: 'DELETE'});
        const data = await response.json();
        if (!response.ok || !data.ok) throw new Error(data.error || '清空失败');
        setScheduleStatus('已清空本学期全部课程');
        closeScheduleManagementModal();
        await loadScheduleManager();
        await loadTodaySchedule();
      } catch (error) {
        setScheduleStatus(error.message || '清空课表失败，请重试', true);
      }
    }

    function formatScheduleTitle(title) {
      if (!title) return '';
      let cleaned = String(title).trim();
      cleaned = cleaned.replace(/^Day\s*\d+[^:]*:\s*/i, '');
      const parts = cleaned.split(/[;；]/).map(p => p.trim()).filter(Boolean);
      if (parts.length > 0) {
        let selected = parts[0];
        if ((selected === '--' || selected.includes('今日已完成')) && parts.length > 1) {
          selected = parts[1];
        }
        cleaned = selected;
      }
      cleaned = cleaned.replace(/^([\u{1F300}-\u{1F9FF}\u{2600}-\u{26FF}\u{2700}-\u{27BF}]\s*)?(?:学习任务|今日任务|目标|任务)\s*[:：]\s*/u, '');
      cleaned = cleaned.replace(/[;；\s\─\-]+$/, '').trim();
      return cleaned || title;
    }

    function renderTodaySchedule(data) {
      return loadForwardAgenda();
    }

    function renderTodayScheduleState(title, detail, isError = false) {
      const container = document.getElementById('today-schedule-content');
      if (!container) return;
      const state = scheduleElement('div', `ui-empty rail-empty-state${isError ? ' ui-empty--danger is-error' : ''}`);
      const art = scheduleElement('span', 'ui-empty__art');
      art.setAttribute('aria-hidden', 'true');
      if (!isError) {
        art.innerHTML = `<svg width="72" height="64" viewBox="0 0 72 64" fill="none" xmlns="http://www.w3.org/2000/svg"><circle cx="36" cy="32" r="28" fill="#EFF6FF" opacity="0.9"/><rect x="20" y="16" width="32" height="34" rx="5" fill="#FFFFFF" stroke="#93C5FD" stroke-width="1.5" stroke-dasharray="3 3"/><path d="M20 23H52" stroke="#BFDBFE" stroke-width="1.5"/><line x1="28" y1="13" x2="28" y2="17" stroke="#3B82F6" stroke-width="1.5" stroke-linecap="round"/><line x1="44" y1="13" x2="44" y2="17" stroke="#3B82F6" stroke-width="1.5" stroke-linecap="round"/><circle cx="36" cy="35" r="7" fill="#FFFFFF" stroke="#2563EB" stroke-width="1.5"/><path d="M36 31V35L39 37" stroke="#2563EB" stroke-width="1.5" stroke-linecap="round"/><path d="M52 38L52.7 40.3L55 41L52.7 41.7L52 44L51.3 41.7L49 41L51.3 40.3L52 38Z" fill="#3B82F6"/></svg>`;
      }
      state.append(art, scheduleElement('strong', '', title), scheduleElement('p', '', detail));
      container.replaceChildren(state);
    }

    async function loadTodaySchedule() {
      return loadForwardAgenda();
    }

(function initializeScheduleFeature() {
  const form = document.getElementById('schedule-modal-form');
  form?.addEventListener('submit', handleScheduleFormSubmit);
  form?.querySelectorAll('input[name="kind"]').forEach((input) => {
    input.addEventListener('change', toggleScheduleKindFields);
  });
  document.getElementById('schedule-file-input')?.addEventListener('change', (event) => importCourseSchedule(event.target));
})();
