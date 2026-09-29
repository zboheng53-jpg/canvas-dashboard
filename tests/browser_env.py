"""Deterministic Playwright environment and waiting helpers for the browser suite.

Why this module exists
----------------------
The browser tests used to measure geometry while the page was still moving: CSS
entry animations, hover/theme transitions, the blinking caret and the first
asynchronous platform refresh all changed the layout between two reads.  That is
what forced the ``abs=4`` tolerances in the desktop shell assertions and the
ad-hoc ``wait_for_function("Object.values(platformRequests)...")`` polling that
was copy-pasted into individual tests.  The helpers below remove those random
sources structurally instead of relaxing the assertions further:

* :func:`apply_stable_defaults` plus :data:`STABLE_MOTION_SCRIPT` give every
  context a fixed viewport, ``device_scale_factor=1``, a reduced-motion
  preference and a 0.001s ceiling for animation/transition durations.  The
  duration override mirrors the rule the app itself ships for
  ``prefers-reduced-motion: reduce``; ``animation-name`` is deliberately left
  alone so assertions inspecting it keep their original meaning.  A test that
  validates the motion path opts out by passing ``reduced_motion`` explicitly
  (``"no-preference"`` for "animations must really run").
* :func:`wait_for_layout_settled` is a bounded condition wait (never a fixed
  sleep): document loaded, fonts ready, no animation or transition running, the
  platform refresh queue drained **and** two consecutive frames producing the
  identical layout fingerprint.
* :func:`wait_for_stable_geometry` applies the same "two consecutive identical
  samples" rule to a caller supplied measurement.
* :func:`assert_close` states the few remaining tolerances explicitly and gives
  the measured difference in the failure message.
"""
import time

# Reason: the desktop shell assertions were written against this design
# viewport; pinning it removes the implicit Playwright default from the
# equation, so a missing ``viewport`` can never silently change a layout.
DEFAULT_VIEWPORT = {"width": 1440, "height": 900}

# Reason: 0.001s (instead of 0s) keeps ``animationend``/``transitionend``
# events firing, so progressive-reveal JavaScript still completes, while the
# element reaches its final frame before any measurement can observe it.
# ``animation-name``/``transition-property`` stay untouched on purpose.
STABLE_MOTION_SCRIPT = """(() => {
  const css = `
    *, *::before, *::after {
      animation-delay: 0s !important;
      animation-duration: 0.001s !important;
      animation-iteration-count: 1 !important;
      transition-delay: 0s !important;
      transition-duration: 0.001s !important;
    }
    html { scroll-behavior: auto !important; }
    * { caret-color: transparent !important; }
  `;
  const apply = () => {
    if (!document.head) return;
    const style = document.createElement('style');
    style.setAttribute('data-test-stable-motion', 'true');
    style.textContent = css;
    document.head.append(style);
  };
  if (document.head) apply();
  else document.addEventListener('DOMContentLoaded', apply, { once: true });
})();"""

# The dashboard globals only exist on dashboard pages; auth pages must not throw.
_SETTLED_SCRIPT = """() => {
  if (document.readyState !== 'complete') return false;
  if (document.fonts && document.fonts.status !== 'loaded') return false;
  const animations = document.getAnimations ? document.getAnimations() : [];
  if (animations.some(animation => animation.playState === 'running')) return false;
  try {
    if (Object.values(platformRequests).some(count => count !== 0)) return false;
    if (workspaceRefreshing) return false;
  } catch (error) {
    // Auth pages do not load the dashboard script that defines these globals.
  }
  return true;
}"""

# Geometry only: text/colour changes are covered by Playwright's auto-retrying
# assertions, while the flaky failures were always layout shifts.  Values are
# rounded to quarter pixels so sub-pixel anti-aliasing cannot masquerade as a
# moving layout, yet a scrollbar appearing (>= 15px) is still detected.
_LAYOUT_FINGERPRINT_SCRIPT = """() => {
  const parts = [
    window.innerWidth, window.innerHeight, window.scrollX, window.scrollY,
    document.documentElement.scrollWidth, document.documentElement.scrollHeight,
    document.body ? document.body.scrollHeight : 0,
  ];
  const nodes = document.body ? document.body.getElementsByTagName('*') : [];
  for (const node of nodes) {
    const rect = node.getBoundingClientRect();
    parts.push(
      Math.round(rect.left * 4), Math.round(rect.top * 4),
      Math.round(rect.width * 4), Math.round(rect.height * 4),
    );
  }
  return parts.join('|');
}"""

_NEXT_FRAME_SCRIPT = (
    "() => new Promise(resolve => "
    "requestAnimationFrame(() => requestAnimationFrame(() => resolve(true))))"
)

_MISSING = object()


def apply_stable_defaults(kwargs):
    """Fill the deterministic context defaults and report whether motion is frozen.

    A caller that passes ``reduced_motion`` explicitly keeps full control: that is
    how the one test validating the animation lifecycle asks for real motion
    (``no-preference``) instead of the frozen default.
    """
    kwargs.setdefault("viewport", dict(DEFAULT_VIEWPORT))
    kwargs.setdefault("device_scale_factor", 1)
    kwargs.setdefault("reduced_motion", "reduce")
    return kwargs.get("reduced_motion") != "no-preference"


def wait_for_layout_settled(page, *, timeout=6.0):
    """Wait until the page layout is final and identical across two frames.

    Replaces the ad-hoc ``page.wait_for_function("Object.values(platformRequests)...")``
    polling: it additionally requires fonts, running animations/transitions and
    the layout fingerprint itself to be quiet, so a measurement taken right after
    this call cannot race the next re-render.
    """
    try:
        page.wait_for_function(_SETTLED_SCRIPT, timeout=timeout * 1000)
    except Exception as error:
        raise AssertionError(
            f"layout was still busy after {timeout}s "
            f"(loaded/fonts/animations/platform refresh never went quiet)"
        ) from error
    return wait_for_stable_geometry(
        page, _LAYOUT_FINGERPRINT_SCRIPT, timeout=timeout, label="dashboard layout")


def wait_for_stable_geometry(page, expression, *, samples=2, timeout=6.0, label="geometry"):
    """Return the first value that ``samples`` consecutive frames agree on.

    Frames are advanced with ``requestAnimationFrame`` rather than a fixed sleep,
    and the wait is bounded: a layout that keeps moving fails with the label of
    the measurement instead of surfacing later as an unexplained off-by-N pixel.
    """
    deadline = time.monotonic() + timeout
    previous = _MISSING
    identical = 0
    current = None
    while True:
        current = page.evaluate(expression)
        if current == previous:
            identical += 1
            if identical >= samples - 1:
                return current
        else:
            identical = 0
        previous = current
        if time.monotonic() >= deadline:
            raise AssertionError(
                f"{label} never settled within {timeout}s "
                f"(last sample: {str(current)[:200]})")
        page.evaluate(_NEXT_FRAME_SCRIPT)


def assert_close(actual, expected, tolerance, *, label="geometry"):
    """Compare two layout numbers, stating the tolerated difference explicitly.

    Only sub-pixel anti-aliasing differences (tolerance <= 1px) may use this;
    anything larger needs a comment naming the layout property it comes from.
    """
    difference = abs(actual - expected)
    assert difference <= tolerance, (
        f"{label}: {actual} differs from {expected} by {difference:.3f}px, "
        f"tolerance is {tolerance}px")
    return difference
