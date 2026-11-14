// Client-side timing of one case (S4.2 design K-d).
// Gated by HELIOS_ENABLE_CONSOLE (helios/api/__init__.py).
//
// The server's decision_ms (view token issued -> decision received) is the
// binding E-H7 measure. This timer adds the client's own view of the same
// interval: client_ms from the moment the case is revealed to the click, and
// client_hidden_ms, how long the page was hidden or the window out of focus
// while the case was on screen. Times come from a monotonic clock
// (performance.now()), passed in so the timer can be tested.

const PLACES = 1000;

function round(ms) {
  return Math.round(ms * PLACES) / PLACES;
}

export function createCaseTimer() {
  let revealedAt = null;
  let hiddenSince = null;
  let hiddenMs = 0;
  let stopped = false;

  return {
    get revealed() {
      return revealedAt !== null && !stopped;
    },

    // The case became visible. `hidden` is the page's state at that moment.
    reveal(now, hidden = false) {
      revealedAt = now;
      hiddenMs = 0;
      hiddenSince = hidden ? now : null;
      stopped = false;
    },

    // The page was hidden or shown again (visibilitychange, blur, focus).
    visibility(now, hidden) {
      if (revealedAt === null || stopped) return;
      if (hidden && hiddenSince === null) {
        hiddenSince = now;
      } else if (!hidden && hiddenSince !== null) {
        hiddenMs += now - hiddenSince;
        hiddenSince = null;
      }
    },

    // The decision was clicked: both client measures, in milliseconds.
    stop(now) {
      if (revealedAt === null || stopped) {
        throw new Error("the case was not revealed");
      }
      const open = hiddenSince === null ? 0 : now - hiddenSince;
      stopped = true;
      return {
        client_ms: round(now - revealedAt),
        client_hidden_ms: round(hiddenMs + open),
      };
    },
  };
}
