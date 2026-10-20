export const THEME_STORAGE_KEY = "essdee-yrp-theme"

const DARK_THEME = "dark"
const LIGHT_THEME = "light"

function normalizedTheme(theme) {
	return theme === DARK_THEME ? DARK_THEME : LIGHT_THEME
}

function browserRoot(root) {
	return root ?? globalThis.document?.documentElement
}

function browserMeta(meta) {
	return meta ?? globalThis.document?.querySelector('meta[name="theme-color"]')
}

function browserStorage(storage) {
	if (storage !== undefined) return storage
	try {
		return globalThis.window?.localStorage
	} catch {
		return null
	}
}

export function currentTheme({ root } = {}) {
	return browserRoot(root)?.classList.contains("erp-dark") ? DARK_THEME : LIGHT_THEME
}

export function applyTheme(theme, { root, meta } = {}) {
	const nextTheme = normalizedTheme(theme)
	const themeRoot = browserRoot(root)
	themeRoot?.classList.toggle("erp-dark", nextTheme === DARK_THEME)
	if (themeRoot) themeRoot.dataset.theme = nextTheme
	browserMeta(meta)?.setAttribute("content", nextTheme === DARK_THEME ? "#0d0e0d" : "#ffffff")
	return nextTheme
}

export function initializeTheme({ storage, root, meta } = {}) {
	let storedTheme = LIGHT_THEME
	try {
		storedTheme = browserStorage(storage)?.getItem(THEME_STORAGE_KEY)
	} catch {
		// Storage can be unavailable in restricted browser contexts.
	}
	return applyTheme(storedTheme, { root, meta })
}

export function toggleTheme({ storage, root, meta } = {}) {
	const nextTheme = currentTheme({ root }) === DARK_THEME ? LIGHT_THEME : DARK_THEME
	applyTheme(nextTheme, { root, meta })
	try {
		browserStorage(storage)?.setItem(THEME_STORAGE_KEY, nextTheme)
	} catch {
		// Theme switching still works for the current page without persistence.
	}
	return nextTheme
}
