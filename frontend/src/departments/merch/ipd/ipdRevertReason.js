export function revertReasonPayload(reason) {
	const trimmed = String(reason ?? "").trim()
	return trimmed ? { reason: trimmed } : null
}
