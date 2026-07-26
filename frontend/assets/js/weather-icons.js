/* Soft monoline weather icons shared by the dashboard header and greeting badge. */
(function attachDashboardWeatherIcons() {
  'use strict';

  const icons = Object.freeze({
    sun: '<svg class="weather-outline-icon" viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="12" r="3.5"></circle><path d="M12 2.5v2M12 19.5v2M2.5 12h2M19.5 12h2M5.28 5.28l1.42 1.42M17.3 17.3l1.42 1.42M18.72 5.28 17.3 6.7M6.7 17.3l-1.42 1.42"></path></svg>',
    cloudSun: '<svg class="weather-outline-icon" viewBox="0 0 24 24" aria-hidden="true"><circle cx="9" cy="8" r="2.5"></circle><path d="M9 2.5v1.5M4.9 3.9 6 5M3.5 8h1.5M14 8h1.5M12 3.9 11 5M5.5 18.5h10.25a3.25 3.25 0 1 0-.85-6.39A4.75 4.75 0 0 0 6 13.5a2.5 2.5 0 0 0-.5 5Z"></path></svg>',
    cloud: '<svg class="weather-outline-icon" viewBox="0 0 24 24" aria-hidden="true"><path d="M5.25 18.5h10.5a3.5 3.5 0 1 0-.95-6.87A5 5 0 0 0 5.25 13a2.75 2.75 0 0 0 0 5.5Z"></path></svg>',
    rain: '<svg class="weather-outline-icon" viewBox="0 0 24 24" aria-hidden="true"><path d="M5.25 14.5h10.5a3.5 3.5 0 1 0-.95-6.87A5 5 0 0 0 5.25 9a2.75 2.75 0 0 0 0 5.5Z"></path><path d="m8 17.5-.5 2M12 17.5l-.5 2M16 17.5l-.5 2"></path></svg>',
    storm: '<svg class="weather-outline-icon" viewBox="0 0 24 24" aria-hidden="true"><path d="M5.25 14.5h10.5a3.5 3.5 0 1 0-.95-6.87A5 5 0 0 0 5.25 9a2.75 2.75 0 0 0 0 5.5Z"></path><path d="m12 16-1.5 3h2l-1 3.5 3-4.5h-2l1-2Z"></path></svg>',
    snow: '<svg class="weather-outline-icon" viewBox="0 0 24 24" aria-hidden="true"><path d="M5.25 14.5h10.5a3.5 3.5 0 1 0-.95-6.87A5 5 0 0 0 5.25 9a2.75 2.75 0 0 0 0 5.5Z"></path><path d="M9 17.5v4M7.3 18.5l3.4 2M10.7 18.5l-3.4 2M15 17.5v4M13.3 18.5l3.4 2M16.7 18.5l-3.4 2"></path></svg>',
    fog: '<svg class="weather-outline-icon" viewBox="0 0 24 24" aria-hidden="true"><path d="M5.25 13h10.5a3.5 3.5 0 1 0-.95-6.87A5 5 0 0 0 5.25 7.5a2.75 2.75 0 0 0 0 5.5Z"></path><path d="M4 16.5h16M6 19.5h12"></path></svg>',
    moon: '<svg class="weather-outline-icon" viewBox="0 0 24 24" aria-hidden="true"><path d="M19.5 15.2A8 8 0 0 1 8.8 4.5 8 8 0 1 0 19.5 15.2Z"></path></svg>',
    dawn: '<svg class="weather-outline-icon" viewBox="0 0 24 24" aria-hidden="true"><path d="M4 18.5h16M7 15.5a5 5 0 0 1 10 0M12 3v3M5.6 6.6l2.1 2.1M18.4 6.6l-2.1 2.1M3.5 12h3M17.5 12h3"></path></svg>',
  });

  function weatherType(description, fallback) {
    const value = `${description || ''} ${fallback || ''}`;
    if (/雷/.test(value)) return 'storm';
    if (/雪|冰雹/.test(value)) return 'snow';
    if (/雨|阵雨/.test(value)) return 'rain';
    if (/雾|霾|沙尘/.test(value)) return 'fog';
    if (/夜|月/.test(value)) return 'moon';
    if (/晴/.test(value)) return 'sun';
    if (/多云|少云/.test(value)) return 'cloudSun';
    if (/阴|云/.test(value)) return 'cloud';
    return 'cloudSun';
  }

  function setIcon(element, type, label) {
    if (!element) return;
    element.innerHTML = icons[type] || icons.cloudSun;
    element.setAttribute('role', 'img');
    element.setAttribute('aria-label', label || '天气');
  }

  window.DashboardWeatherIcons = Object.freeze({
    renderWeather(element, description, fallback) {
      setIcon(element, weatherType(description, fallback), description || '天气');
    },
    renderGreeting(element, greetingIcon) {
      const type = greetingIcon === '🌙' ? 'moon'
        : greetingIcon === '🌅' ? 'dawn'
          : greetingIcon === '🌤️' ? 'cloudSun' : 'sun';
      setIcon(element, type, '当前时段');
    },
  });
}());
