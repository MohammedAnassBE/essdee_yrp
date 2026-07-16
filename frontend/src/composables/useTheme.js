import { ref, computed } from "vue"

// Singleton theme state. Persisted to localStorage; first-visit default follows
// the OS (prefers-color-scheme). `.dark` on <html> drives both the --esd-* token
// overrides (global.css) and PrimeVue's colorScheme.dark (darkModeSelector: ".dark").
const STORAGE_KEY = "essdee-theme"
const _theme = ref("light")
let _inited = false

function apply(t) {
	const dark = t === "dark"
	const el = document.documentElement
	el.classList.toggle("dark", dark)
	el.style.colorScheme = dark ? "dark" : "light"
}

function read() {
	let saved = null
	try { saved = localStorage.getItem(STORAGE_KEY) } catch { /* private mode */ }
	if (saved === "light" || saved === "dark") return saved
	const prefersDark =
		typeof window.matchMedia === "function" &&
		window.matchMedia("(prefers-color-scheme: dark)").matches
	return prefersDark ? "dark" : "light"
}

// Called once from main.js BEFORE mount so the first paint is already themed
// (no light→dark flash for a dark-preferring user).
export function initTheme() {
	if (_inited) return
	_inited = true
	_theme.value = read()
	apply(_theme.value)
}

// Class-only mode setter for the @yrp/web-engine theme applier (spec §9 item 1,
// §19 nit 2). "light"/"dark" force the mode class WITHOUT writing localStorage
// (a forced-mode layout must never ratchet the user's stored choice, and
// View-as must never pollute the SM's); "user" — or anything else — re-applies
// the user's own stored/OS choice. The reactive ref is kept in sync so the
// topbar toggle reflects what is actually on screen.
export function applyMode(mode) {
	_theme.value = mode === "light" || mode === "dark" ? mode : read()
	apply(_theme.value)
}

export function useTheme() {
	function setTheme(t) {
		_theme.value = t === "dark" ? "dark" : "light"
		apply(_theme.value)
		try { localStorage.setItem(STORAGE_KEY, _theme.value) } catch { /* ignore */ }
	}
	function toggleTheme() {
		setTheme(_theme.value === "dark" ? "light" : "dark")
	}
	const isDark = computed(() => _theme.value === "dark")
	return { theme: _theme, isDark, setTheme, toggleTheme }
}
