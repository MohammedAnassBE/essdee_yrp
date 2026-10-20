const reloadWindowMs = 10000
const storagePrefix = "essdee:chunk-reload:"

export function isChunkLoadError(error) {
	return /Failed to fetch dynamically imported module|Importing a module script failed|Unable to preload CSS|error loading dynamically imported module/i.test(error?.message || String(error || ""))
}

export function reloadChunkTarget(targetFullPath, browser = window, now = Date.now()) {
	if (!targetFullPath) return false
	const key = `${storagePrefix}${targetFullPath}`
	try {
		const previous = JSON.parse(browser.sessionStorage.getItem(key))
		if (Number.isFinite(previous) && now - previous < reloadWindowMs) return false
		browser.sessionStorage.setItem(key, JSON.stringify(now))
	} catch {
		// Without persistent storage a reload could loop.
		return false
	}
	browser.location.assign(targetFullPath)
	return true
}
