/** Persisted display preferences (best effort: storage may be unavailable). */
const KEY = 'hololink.prefs.v1';
const DEFAULTS = Object.freeze({ scale: 0.34, gap: 0.04, guide: false });

export function loadPrefs() {
  try {
    const raw = JSON.parse(localStorage.getItem(KEY) ?? '{}');
    return { ...DEFAULTS, ...raw };
  } catch {
    return { ...DEFAULTS };
  }
}

export function savePrefs(prefs) {
  try { localStorage.setItem(KEY, JSON.stringify(prefs)); } catch { /* ignore */ }
}
