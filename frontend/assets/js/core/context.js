/* Dashboard: core/context.js; loaded in index.html order. */
// ---- Clock & Greeting ----
let serverTime = null;
let clockStart = null;
let clockInFlight = false;
let clockFailures = 0;
let nextClockRetryAt = 0;

function getGreetingInfo(dateObj) {
  const hour = dateObj.getHours();
  const isNight = hour >= 19 || hour < 5;
  if (hour >= 0 && hour < 5) {
    return { greeting: '夜深了', icon: '🌙', isNight };
  }
  if (hour >= 5 && hour < 9) {
    return { greeting: '早上好', icon: '🌅', isNight };
  }
  if (hour >= 9 && hour < 12) {
    return { greeting: '上午好', icon: '☀️', isNight };
  }
  if (hour >= 12 && hour < 14) {
    return { greeting: '中午好', icon: '☀️', isNight };
  }
  if (hour >= 14 && hour < 19) {
    return { greeting: '下午好', icon: '🌤️', isNight };
  }
  return { greeting: '晚上好', icon: '🌙', isNight };
}

function updateGreeting(nowDate) {
  const greetingEl = document.getElementById('sidebar-greeting');
  const titleEl = document.getElementById('sidebar-greeting-title');
  if (!greetingEl && !titleEl) return;

  const info = getGreetingInfo(nowDate || new Date());
  const nextTitle = `${info.greeting}，`;
  if (titleEl && titleEl.textContent !== nextTitle) {
    titleEl.textContent = nextTitle;
  }

  if (greetingEl) {
    const username = greetingEl.getAttribute('data-username');
    if (username && greetingEl.textContent !== username) {
      greetingEl.textContent = username;
    }
  }

  const iconEl = document.getElementById('sidebar-greeting-icon');
  if (iconEl) {
    if (iconEl.dataset.greetingIconKey !== info.icon) {
      window.DashboardWeatherIcons?.renderGreeting(iconEl, info.icon);
      iconEl.dataset.greetingIconKey = info.icon;
    }
    iconEl.classList.toggle('is-night', info.isNight);
    iconEl.classList.toggle('is-daytime', !info.isNight);
  }
}

function renderLocalClockFallback(nowDate) {
  const now = nowDate || new Date();
  const h = String(now.getHours()).padStart(2, '0');
  const m = String(now.getMinutes()).padStart(2, '0');
  const s = String(now.getSeconds()).padStart(2, '0');
  const timeEl = document.getElementById('time');
  if (timeEl) timeEl.textContent = `${h}:${m}:${s}`;
  const dateEl = document.getElementById('date');
  if (dateEl && dateEl.textContent.includes('----')) {
    const year = now.getFullYear();
    const month = String(now.getMonth() + 1).padStart(2, '0');
    const day = String(now.getDate()).padStart(2, '0');
    dateEl.textContent = `${year}年${month}月${day}日`;
  }
  const weekdayEl = document.getElementById('weekday');
  if (weekdayEl && weekdayEl.textContent === '星期-') {
    const weekdays = ['星期日', '星期一', '星期二', '星期三', '星期四', '星期五', '星期六'];
    weekdayEl.textContent = weekdays[now.getDay()] || '星期一';
  }
}

async function initClock() {
  if (clockInFlight) return;
  clockInFlight = true;
  try {
    const resp = await fetch('/api/clock');
    if (!resp.ok) {
      throw new Error(`HTTP ${resp.status}`);
    }
    const data = await resp.json();
    const parsedIso = Date.parse(data?.iso || '');
    if (!Number.isFinite(parsedIso)) {
      throw new Error('Invalid clock payload');
    }
    serverTime = parsedIso;
    clockStart = Date.now();
    clockFailures = 0;
    nextClockRetryAt = 0;
    updateClock(data);
  } catch (_) {
    clockFailures += 1;
    const backoffMs = Math.min(60000, 5000 * Math.pow(2, clockFailures - 1));
    nextClockRetryAt = Date.now() + backoffMs;
    renderLocalClockFallback(new Date());
  } finally {
    clockInFlight = false;
  }
}

function updateClock(data) {
  const timeEl = document.getElementById('time');
  const dateEl = document.getElementById('date');
  const weekdayEl = document.getElementById('weekday');
  if (timeEl && data.time) timeEl.textContent = data.time;
  if (dateEl && data.date) dateEl.textContent = data.date;
  if (weekdayEl && data.weekday) weekdayEl.textContent = data.weekday;
  if (serverTime) {
    updateGreeting(new Date(serverTime));
  } else {
    updateGreeting(new Date());
  }
}

function tickClock() {
  if (!serverTime) {
    const now = new Date();
    renderLocalClockFallback(now);
    updateGreeting(now);
    if (!clockInFlight && Date.now() >= nextClockRetryAt) {
      initClock();
    }
    return;
  }
  const elapsed = Date.now() - clockStart;
  const now = new Date(serverTime + elapsed);
  const h = String(now.getHours()).padStart(2, '0');
  const m = String(now.getMinutes()).padStart(2, '0');
  const s = String(now.getSeconds()).padStart(2, '0');
  const timeEl = document.getElementById('time');
  if (timeEl) timeEl.textContent = `${h}:${m}:${s}`;
  updateGreeting(now);
  if (now.getSeconds() === 0 && typeof renderForwardAgenda === 'function' && typeof workspaceTodayData !== 'undefined' && workspaceTodayData) {
    renderForwardAgenda();
  }
}

setInterval(() => { initClock(); }, 10 * 60 * 1000);
setInterval(tickClock, 1000);

// ---- Weather ----
const WEATHER_CAMPUS_STORAGE_KEY = 'dashboard.weatherCampus';

function selectedWeatherCampus() {
  return document.querySelector('.weather-campus-option.is-active')?.dataset.campus || 'siping';
}

function initializeWeatherCampus() {
  const campusOptions = document.querySelectorAll('.weather-campus-option');
  if (!campusOptions.length) return;
  let savedCampus = null;
  try {
    savedCampus = window.localStorage.getItem(WEATHER_CAMPUS_STORAGE_KEY);
  } catch (_) { /* Storage may be disabled. */ }

  const activateCampus = (campus) => {
    let activeOption = null;
    campusOptions.forEach((option) => {
      const isActive = option.dataset.campus === campus;
      option.classList.toggle('is-active', isActive);
      option.setAttribute('aria-selected', String(isActive));
      if (isActive) activeOption = option;
    });
    const switchEl = (activeOption || campusOptions[0])?.closest('.weather-campus-switch');
    if (switchEl && activeOption && window.uiMotion && typeof window.uiMotion.glideIndicator === 'function') {
      window.uiMotion.glideIndicator(switchEl, activeOption);
    }
  };

  if (savedCampus === 'siping' || savedCampus === 'jiading') {
    activateCampus(savedCampus);
  } else {
    activateCampus(selectedWeatherCampus());
  }

  campusOptions.forEach((option) => option.addEventListener('click', () => {
    activateCampus(option.dataset.campus);
    try {
      window.localStorage.setItem(WEATHER_CAMPUS_STORAGE_KEY, selectedWeatherCampus());
    } catch (_) { /* Storage may be disabled. */ }
    fetchWeather();
  }));
}

let weatherPollTimer = null;
let weatherRequestId = 0;

function clearContextRetry(el) {
  if (!el) return;
  delete el.dataset.contextRetry;
  el.removeAttribute('role');
  el.removeAttribute('tabindex');
}

function markContextRetry(el, target, message) {
  if (!el) return;
  el.textContent = message;
  el.dataset.contextRetry = target;
  el.setAttribute('role', 'button');
  el.tabIndex = 0;
}

async function fetchWeather() {
  clearTimeout(weatherPollTimer);
  const requestId = ++weatherRequestId;
  const tempEl = document.getElementById('weather-temp');
  const descEl = document.getElementById('weather-desc');
  const detailEl = document.getElementById('weather-detail');
  const emojiEl = document.getElementById('weather-emoji');
  const weatherHost = tempEl?.closest('.opt1-col') || tempEl?.parentElement;

  weatherHost?.classList.add('is-weather-loading');
  try {
    const resp = await fetch(`/api/weather?campus=${encodeURIComponent(selectedWeatherCampus())}`);
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    const data = await resp.json();
    if (requestId !== weatherRequestId) return;

    if (data.pending) {
      weatherPollTimer = setTimeout(fetchWeather, 2000);
    }
    if (data.ok) {
      if (emojiEl) {
        window.DashboardWeatherIcons?.renderWeather(emojiEl, data.weather_desc, data.weather_emoji);
      }
      if (tempEl) tempEl.textContent = `${data.temperature}\u00b0C`;
      if (descEl) {
        clearContextRetry(descEl);
        descEl.textContent = data.weather_desc;
      }
      if (detailEl) detailEl.textContent = `\u6e7f\u5ea6 ${data.humidity}%`;
    } else if (!data.pending) {
      markContextRetry(descEl, 'weather', '天气获取失败 · 点击重试');
      if (detailEl) detailEl.textContent = '';
    }
  } catch (e) {
    if (requestId !== weatherRequestId) return;
    console.error('Weather fetch failed:', e);
    markContextRetry(descEl, 'weather', '天气获取失败 · 点击重试');
    if (detailEl) detailEl.textContent = '';
  } finally {
    if (requestId === weatherRequestId) {
      weatherHost?.classList.remove('is-weather-loading');
    }
  }
}

async function fetchTerm() {
  const weekBadge = document.getElementById('term-week-badge');
  const termEl = document.getElementById('term-info');
  try {
    const resp = await fetch('/api/term');
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    const data = await resp.json();
    if (data.ok) {
      const holidayHint = data.is_holiday ? ` · ${data.holiday_name}` : '';
      if (weekBadge) {
        clearContextRetry(weekBadge);
        weekBadge.textContent = `第 ${data.week} 周${holidayHint}`;
      }
      if (termEl) {
        clearContextRetry(termEl);
        termEl.textContent = data.term;
      }
    } else {
      if (weekBadge) markContextRetry(weekBadge, 'term', '获取失败');
      if (termEl) markContextRetry(termEl, 'term', '学期信息获取失败 · 点击重试');
    }
  } catch (_) {
    if (weekBadge) markContextRetry(weekBadge, 'term', '加载失败');
    if (termEl) markContextRetry(termEl, 'term', '学期信息加载失败 · 点击重试');
  }
}

function handleContextRetryTrigger(el) {
  const retryTarget = el?.dataset?.contextRetry;
  if (retryTarget === 'weather') {
    fetchWeather();
  } else if (retryTarget === 'term') {
    fetchTerm();
  }
}

document.addEventListener('click', (event) => {
  const trigger = event.target.closest('[data-context-retry]');
  if (trigger) {
    handleContextRetryTrigger(trigger);
  }
});

document.addEventListener('keydown', (event) => {
  if (event.key !== 'Enter' && event.key !== ' ') return;
  const trigger = event.target.closest?.('[data-context-retry]');
  if (!trigger) return;
  event.preventDefault();
  handleContextRetryTrigger(trigger);
});
