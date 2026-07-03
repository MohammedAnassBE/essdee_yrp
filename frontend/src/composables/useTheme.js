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
