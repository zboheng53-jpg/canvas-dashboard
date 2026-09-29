/* Dashboard: core/context.js; loaded in index.html order. */
    // ---- Clock & Greeting ----
    let serverTime = null;
    let clockStart = null;

    function getGreetingInfo(dateObj) {
      const hour = dateObj.getHours();
      const isNight = hour >= 19 || hour < 5;
      if (hour >= 0 && hour < 5) {
        return { greeting: '夜深了', icon: '🌙', isNight };
      } else if (hour >= 5 && hour < 9) {
        return { greeting: '早上好', icon: '🌅', isNight };
      } else if (hour >= 9 && hour < 12) {
        return { greeting: '上午好', icon: '☀️', isNight };
      } else if (hour >= 12 && hour < 14) {
        return { greeting: '中午好', icon: '☀️', isNight };
      } else if (hour >= 14 && hour < 19) {
        return { greeting: '下午好', icon: '🌤️', isNight };
      } else {
        return { greeting: '晚上好', icon: '🌙', isNight };
      }
    }

    function updateGreeting(nowDate) {
      const greetingEl = document.getElementById('sidebar-greeting');
      const titleEl = document.getElementById('sidebar-greeting-title');
      if (!greetingEl && !titleEl) return;

      const info = getGreetingInfo(nowDate || new Date());

      if (titleEl) {
        titleEl.textContent = `${info.greeting}，`;
      }
      if (greetingEl) {
        const username = greetingEl.getAttribute('data-username') || 'anuode';
        greetingEl.textContent = username;
      }
      const iconEl = document.getElementById('sidebar-greeting-icon');
      if (iconEl) {
        window.DashboardWeatherIcons.renderGreeting(iconEl, info.icon);
        iconEl.classList.toggle('is-night', info.isNight);
        iconEl.classList.toggle('is-daytime', !info.isNight);
      }
    }

    async function initClock() {
      const resp = await fetch('/api/clock');
      const data = await resp.json();
      serverTime = new Date(data.iso).getTime();
      clockStart = Date.now();
      updateClock(data);
    }

    function updateClock(data) {
      document.getElementById('time').textContent = data.time;
      document.getElementById('date').textContent = data.date;
      document.getElementById('weekday').textContent = data.weekday;
      if (serverTime) {
        updateGreeting(new Date(serverTime));
      } else {
        updateGreeting(new Date());
      }
    }

    function tickClock() {
      if (!serverTime) { initClock(); updateGreeting(new Date()); return; }
      const elapsed = Date.now() - clockStart;
      const now = new Date(serverTime + elapsed);
      const h = String(now.getHours()).padStart(2, '0');
      const m = String(now.getMinutes()).padStart(2, '0');
      const s = String(now.getSeconds()).padStart(2, '0');
      document.getElementById('time').textContent = `${h}:${m}:${s}`;
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
      const savedCampus = window.localStorage.getItem(WEATHER_CAMPUS_STORAGE_KEY);
      const activateCampus = (campus) => {
        campusOptions.forEach((option) => {
          const isActive = option.dataset.campus === campus;
          option.classList.toggle('is-active', isActive);
          option.setAttribute('aria-selected', String(isActive));
        });
      };
      if (savedCampus === 'siping' || savedCampus === 'jiading') activateCampus(savedCampus);
      campusOptions.forEach((option) => option.addEventListener('click', () => {
        activateCampus(option.dataset.campus);
        window.localStorage.setItem(WEATHER_CAMPUS_STORAGE_KEY, selectedWeatherCampus());
        fetchWeather();
      }));
    }

    async function fetchWeather() {
      try {
        const resp = await fetch(`/api/weather?campus=${encodeURIComponent(selectedWeatherCampus())}`);
        const data = await resp.json();
        if (data.ok) {
          window.DashboardWeatherIcons.renderWeather(
            document.getElementById('weather-emoji'),
            data.weather_desc,
            data.weather_emoji,
          );
          document.getElementById('weather-temp').textContent = `${data.temperature}\u00b0C`;
          document.getElementById('weather-desc').textContent = data.weather_desc;
          document.getElementById('weather-detail').textContent = `\u6e7f\u5ea6 ${data.humidity}%`;
        }
      } catch (e) { console.error('Weather fetch failed:', e); }
    }

    async function fetchTerm() {
      try {
        const resp = await fetch('/api/term');
        const data = await resp.json();
        if (data.ok) {
          const holidayHint = data.is_holiday ? ` · ${data.holiday_name}` : '';
          const weekBadge = document.getElementById('term-week-badge');
          if (weekBadge) weekBadge.textContent = `第 ${data.week} 周${holidayHint}`;
          const termEl = document.getElementById('term-info');
          if (termEl) termEl.textContent = data.term;
        } else {
          const weekBadge = document.getElementById('term-week-badge');
          if (weekBadge) weekBadge.textContent = '获取失败';
          const termEl = document.getElementById('term-info');
          if (termEl) termEl.textContent = '学期信息获取失败';
        }
      } catch (e) {
        const termEl = document.getElementById('term-info');
        if (termEl) termEl.textContent = '学期信息加载失败';
      }
    }


    // Initial fetches

