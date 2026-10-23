const STORAGE_PREFIX = "yrp.report-workspace:"

/** Reports whose label or group contains every search word, grouped in first-seen order. */
export function reportGroups(reports = [], search = "") {
	const words = String(search).toLowerCase().split(/\s+/).filter(Boolean)
	const groups = []
	for (const report of reports) {
		const text = `${report.label} ${report.group || ""}`.toLowerCase()
		if (!words.every(word => text.includes(word))) continue
		const label = report.group || ""
		let group = groups.find(item => item.label === label)
		if (!group) groups.push(group = { label, reports: [] })
		group.reports.push(report)
	}
	return groups
}

export function chooseReport(reports = [], requested, remembered) {
	for (const value of [requested, remembered]) {
		if (value && reports.some(report => report.value === value)) return value
	}
	return reports[0]?.value || ""
}

/** Next value in `values` from `current`, clamped to the ends. */
export function stepReport(values, current, delta) {
	if (!values.length) return ""
	const index = values.indexOf(current)
	if (index < 0) return delta > 0 ? values[0] : values.at(-1)
	return values[Math.min(values.length - 1, Math.max(0, index + delta))]
}

export function readRememberedReport(key) {
	try {
		return globalThis.localStorage?.getItem(STORAGE_PREFIX + key) || ""
	} catch {
		return ""
	}
}

export function rememberReport(key, value) {
	try {
		globalThis.localStorage?.setItem(STORAGE_PREFIX + key, value)
	} catch {
		// Private windows and blocked storage only lose the last-used default.
	}
}
