/* Dashboard Apple-grade GPU-composited motion primitives: window.uiMotion */
(function attachUiMotion(global) {
  const flipAnimations = new WeakMap();
  const numberRafIds = new WeakMap();
  const nudgeAnimations = new WeakMap();
  const glideStateMap = new WeakMap();

  function prefersReducedMotion() {
    return Boolean(global.matchMedia && global.matchMedia('(prefers-reduced-motion: reduce)').matches);
  }

  function findDirectChild(parent, className) {
    for (const child of parent.children) {
      if (child.classList && child.classList.contains(className)) {
        return child;
      }
    }
    return null;
  }

  function cancelGlideAnimation(state) {
    if (state && state.anim) {
      try { state.anim.cancel(); } catch (_) {}
      state.anim = null;
    }
  }

  function positionGlidePill(containerEl, activeEl, indicatorClass, state, { animate = true } = {}) {
    if (!containerEl) return;
    let pill = findDirectChild(containerEl, indicatorClass);
    if (!activeEl || !containerEl.contains(activeEl)) {
      cancelGlideAnimation(state);
      if (pill) pill.style.opacity = '0';
      return;
    }

    containerEl.classList.add('ui-glide-host', 'has-glide-indicator');
    const cRect = containerEl.getBoundingClientRect();
    const aRect = activeEl.getBoundingClientRect();
    if (cRect.width <= 0 || aRect.width <= 0 || aRect.height <= 0) {
      return;
    }

    const reduced = prefersReducedMotion();
    const hadInitialized = Boolean(pill && pill.dataset.initialized === '1');
    let prevBox = null;
    if (hadInitialized && animate && !reduced && typeof pill.animate === 'function') {
      const pRect = pill.getBoundingClientRect();
      if (pRect.width > 0 && pRect.height > 0) {
        prevBox = {
          left: (pRect.left - cRect.left) - containerEl.clientLeft + containerEl.scrollLeft,
          top: (pRect.top - cRect.top) - containerEl.clientTop + containerEl.scrollTop,
          width: pRect.width,
          height: pRect.height,
        };
      }
    }

    cancelGlideAnimation(state);

    if (!pill) {
      pill = document.createElement('span');
      pill.className = indicatorClass;
      pill.setAttribute('aria-hidden', 'true');
      containerEl.prepend(pill);
    }

    const nextLeft = Math.round(((aRect.left - cRect.left) - containerEl.clientLeft + containerEl.scrollLeft) * 100) / 100;
    const nextTop = Math.round(((aRect.top - cRect.top) - containerEl.clientTop + containerEl.scrollTop) * 100) / 100;
    const nextWidth = Math.round(aRect.width * 100) / 100;
    const nextHeight = Math.round(aRect.height * 100) / 100;

    pill.style.width = `${nextWidth}px`;
    pill.style.height = `${nextHeight}px`;
    pill.style.transform = `translate3d(${nextLeft}px, ${nextTop}px, 0)`;
    pill.style.opacity = '1';

    const activeRadius = global.getComputedStyle(activeEl).borderRadius;
    if (activeRadius) {
      pill.style.borderRadius = activeRadius;
    }

    if (!hadInitialized) {
      void pill.offsetWidth;
      pill.dataset.initialized = '1';
      return;
    }

    if (
      prevBox
      && state
      && nextWidth > 0
      && nextHeight > 0
      && (
        Math.abs(prevBox.left - nextLeft) > 0.5
        || Math.abs(prevBox.top - nextTop) > 0.5
        || Math.abs(prevBox.width - nextWidth) > 0.5
        || Math.abs(prevBox.height - nextHeight) > 0.5
      )
    ) {
      const scaleX = prevBox.width / nextWidth;
      const scaleY = prevBox.height / nextHeight;
      const anim = pill.animate(
        [
          { transform: `translate3d(${prevBox.left}px, ${prevBox.top}px, 0) scale(${scaleX}, ${scaleY})` },
          { transform: `translate3d(${nextLeft}px, ${nextTop}px, 0) scale(1, 1)` },
        ],
        {
          duration: 220,
          easing: 'cubic-bezier(0.22, 1, 0.36, 1)',
        },
      );
      state.anim = anim;
      const clearAnim = () => {
        if (state.anim === anim) {
          state.anim = null;
        }
      };
      anim.onfinish = clearAnim;
      anim.oncancel = clearAnim;
    }
  }

  function glideIndicator(containerEl, activeEl, { indicatorClass = 'ui-glide-pill' } = {}) {
    if (!containerEl) return;
    let state = glideStateMap.get(containerEl);
    if (!state) {
      state = { activeEl: null, indicatorClass, observer: null, anim: null };
      if (typeof ResizeObserver === 'function') {
        state.observer = new ResizeObserver(() => {
          if (state.activeEl && document.contains(state.activeEl)) {
            positionGlidePill(containerEl, state.activeEl, state.indicatorClass, state, { animate: false });
          }
        });
        state.observer.observe(containerEl);
      }
      glideStateMap.set(containerEl, state);
    }
    const targetChanged = state.activeEl !== (activeEl || null);
    state.activeEl = activeEl || null;
    state.indicatorClass = indicatorClass;
    positionGlidePill(containerEl, state.activeEl, indicatorClass, state, { animate: targetChanged });
  }

  function cancelRunningFlip(el) {
    const running = flipAnimations.get(el);
    if (running) {
      try { running.cancel(); } catch (_) {}
      flipAnimations.delete(el);
    }
  }

  function flipList(containerEl, itemSelector, mutateFn, { maxItems = 40, duration = 260 } = {}) {
    if (typeof mutateFn !== 'function') return;
    if (!containerEl || prefersReducedMotion() || typeof Element.prototype.animate !== 'function') {
      mutateFn();
      return;
    }

    const beforeItems = Array.from(containerEl.querySelectorAll(itemSelector));
    if (beforeItems.length > maxItems) {
      mutateFn();
      return;
    }

    const firstRects = new Map();
    beforeItems.forEach((el) => {
      const key = el.getAttribute('data-flip-key');
      if (!key) return;
      cancelRunningFlip(el);
      firstRects.set(key, el.getBoundingClientRect());
    });

    mutateFn();

    const afterItems = Array.from(containerEl.querySelectorAll(itemSelector));
    if (afterItems.length > maxItems) return;

    const entering = [];
    afterItems.forEach((el) => {
      const key = el.getAttribute('data-flip-key');
      if (!key) return;
      const last = el.getBoundingClientRect();
      if (last.width <= 0 || last.height <= 0) return;

      const first = firstRects.get(key);
      if (!first) {
        entering.push(el);
        return;
      }

      const dx = first.left - last.left;
      const dy = first.top - last.top;
      if (Math.abs(dx) < 0.5 && Math.abs(dy) < 0.5) return;

      cancelRunningFlip(el);
      const anim = el.animate(
        [
          { transform: `translate3d(${dx}px, ${dy}px, 0)` },
          { transform: 'translate3d(0, 0, 0)' },
        ],
        {
          duration,
          easing: 'cubic-bezier(0.22, 1, 0.36, 1)',
        },
      );
      flipAnimations.set(el, anim);
      const cleanup = () => {
        if (flipAnimations.get(el) === anim) {
          flipAnimations.delete(el);
        }
      };
      anim.onfinish = cleanup;
      anim.oncancel = cleanup;
    });

    if (entering.length > 0 && entering.length <= 6) {
      entering.forEach((el) => {
        const anim = el.animate(
          [
            { opacity: 0, transform: 'translateY(6px)' },
            { opacity: 1, transform: 'translateY(0)' },
          ],
          {
            duration: Math.min(200, duration),
            easing: 'cubic-bezier(0.22, 1, 0.36, 1)',
          },
        );
        flipAnimations.set(el, anim);
        const cleanup = () => {
          if (flipAnimations.get(el) === anim) {
            flipAnimations.delete(el);
          }
        };
        anim.onfinish = cleanup;
        anim.oncancel = cleanup;
      });
    }
  }

  function animateNumber(el, nextValue, { suffix = '', duration = 220 } = {}) {
    if (!el) return;
    const prevRaf = numberRafIds.get(el);
    if (prevRaf) {
      global.cancelAnimationFrame(prevRaf);
      numberRafIds.delete(el);
    }

    const target = Number(nextValue);
    if (!Number.isFinite(target)) {
      el.textContent = `${String(nextValue ?? '')}${suffix}`;
      return;
    }

    const stored = Number(el.dataset.motionNum);
    const parsedCurrent = Number.isFinite(stored) ? stored : parseFloat(String(el.textContent || ''));
    if (
      prefersReducedMotion()
      || !Number.isFinite(parsedCurrent)
      || parsedCurrent === target
      || duration <= 0
      || typeof global.requestAnimationFrame !== 'function'
    ) {
      el.dataset.motionNum = String(target);
      el.textContent = `${target}${suffix}`;
      return;
    }

    const startValue = parsedCurrent;
    const delta = target - startValue;
    const isInt = Number.isInteger(target) && Number.isInteger(startValue);
    const startTime = global.performance ? global.performance.now() : Date.now();

    const step = (now) => {
      const elapsed = Math.max(0, (now || Date.now()) - startTime);
      const t = Math.min(1, elapsed / duration);
      const eased = 1 - Math.pow(1 - t, 3);
      const raw = startValue + delta * eased;
      const formatted = isInt ? Math.round(raw) : Math.round(raw * 10) / 10;
      el.textContent = `${formatted}${suffix}`;
      if (t < 1) {
        const rafId = global.requestAnimationFrame(step);
        numberRafIds.set(el, rafId);
      } else {
        numberRafIds.delete(el);
        el.dataset.motionNum = String(target);
        el.textContent = `${target}${suffix}`;
      }
    };

    const rafId = global.requestAnimationFrame(step);
    numberRafIds.set(el, rafId);
  }

  function enhanceDisclosure(detailsEl) {
    if (!detailsEl || detailsEl.dataset.uiDisclosureEnhanced === '1') return;
    const summary = Array.from(detailsEl.children).find((node) => node.tagName === 'SUMMARY');
    if (!summary) return;
    detailsEl.dataset.uiDisclosureEnhanced = '1';

    let panel = detailsEl.querySelector(':scope > .ui-disclosure-panel');
    if (!panel) {
      panel = document.createElement('div');
      panel.className = 'ui-disclosure-panel';
      const nodesToMove = Array.from(detailsEl.childNodes).filter((node) => node !== summary);
      nodesToMove.forEach((node) => panel.appendChild(node));
      detailsEl.appendChild(panel);
    }

    let currentAnim = null;

    summary.addEventListener('click', (event) => {
      if (prefersReducedMotion() || typeof panel.animate !== 'function') {
        return;
      }
      event.preventDefault();
      if (currentAnim) {
        try { currentAnim.cancel(); } catch (_) {}
        currentAnim = null;
      }

      if (!detailsEl.open) {
        detailsEl.open = true;
        const targetHeight = panel.scrollHeight;
        panel.style.overflow = 'hidden';
        currentAnim = panel.animate(
          [
            { height: '0px', opacity: 0 },
            { height: `${targetHeight}px`, opacity: 1 },
          ],
          { duration: 200, easing: 'cubic-bezier(0.22, 1, 0.36, 1)' },
        );
        const finishOpen = () => {
          currentAnim = null;
          panel.style.overflow = '';
          panel.style.height = '';
        };
        currentAnim.onfinish = finishOpen;
        currentAnim.oncancel = finishOpen;
      } else {
        const startHeight = panel.offsetHeight || panel.scrollHeight;
        panel.style.overflow = 'hidden';
        currentAnim = panel.animate(
          [
            { height: `${startHeight}px`, opacity: 1 },
            { height: '0px', opacity: 0 },
          ],
          { duration: 180, easing: 'cubic-bezier(0.22, 1, 0.36, 1)' },
        );
        const finishClose = () => {
          currentAnim = null;
          detailsEl.open = false;
          panel.style.overflow = '';
          panel.style.height = '';
        };
        currentAnim.onfinish = finishClose;
        currentAnim.oncancel = () => {
          currentAnim = null;
          panel.style.overflow = '';
          panel.style.height = '';
        };
      }
    });
  }

  function pulseArrival(el) {
    if (!el || prefersReducedMotion()) return;
    el.classList.remove('ui-arrival-pulse');
    void el.offsetWidth;
    el.classList.add('ui-arrival-pulse');
    let cleared = false;
    const cleanup = () => {
      if (cleared) return;
      cleared = true;
      el.classList.remove('ui-arrival-pulse');
    };
    el.addEventListener('animationend', cleanup, { once: true });
    global.setTimeout(cleanup, 850);
  }

  function nudgeError(el) {
    if (!el || prefersReducedMotion() || typeof el.animate !== 'function') return;
    const running = nudgeAnimations.get(el);
    if (running) {
      try { running.cancel(); } catch (_) {}
    }
    const anim = el.animate(
      [
        { transform: 'translateX(0)' },
        { transform: 'translateX(-5px)' },
        { transform: 'translateX(5px)' },
        { transform: 'translateX(-3px)' },
        { transform: 'translateX(3px)' },
        { transform: 'translateX(0)' },
      ],
      { duration: 240, easing: 'cubic-bezier(0.2, 0, 0, 1)' },
    );
    nudgeAnimations.set(el, anim);
    const cleanup = () => {
      if (nudgeAnimations.get(el) === anim) {
        nudgeAnimations.delete(el);
      }
    };
    anim.onfinish = cleanup;
    anim.oncancel = cleanup;
  }

  global.uiMotion = Object.freeze({
    prefersReducedMotion,
    glideIndicator,
    flipList,
    animateNumber,
    enhanceDisclosure,
    pulseArrival,
    nudgeError,
  });
})(window);
