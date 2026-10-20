export function orphanProcessNotices(notices, rows = [], embellishments = {}, removed = null) {
	const processes = new Set((rows || []).map((row) => row.process_name))
	const candidates = removed ? [...notices, removed] : notices
	return [...new Set(candidates)].filter((process) => processes.has(process) && !Object.hasOwn(embellishments || {}, process))
}
