const STALE_SAVE_PATTERN = /changed after you opened it|modified after you have opened it/i
const LOCAL_KEY_PATTERN = /^__/

/** True for Frappe's TimestampMismatchError or the repo's "changed after you opened it" save rejection. */
export function isStaleDocumentError(reason) {
	if (!reason) return false
	if (reason.exc_type === "TimestampMismatchError") return true
	return STALE_SAVE_PATTERN.test(String(reason.message ?? reason))
}

/** True when a document read failed because the document no longer exists. */
export function isMissingDocumentError(reason) {
	if (!reason) return false
	return Number(reason.status) === 404 || reason.exc_type === "DoesNotExistError"
}

/**
 * Compares an edited document with its last loaded snapshot.
 * Empty values (null, undefined, "") are equal and local `__` keys are ignored, so a field that was
 * only touched and cleared again does not count as an edit. Child rows are compared the same way.
 */
export function isDocumentDirty(current, clean) {
	return !sameValue(current ?? {}, clean ?? {})
}

function sameValue(left, right) {
	const a = normalize(left)
	const b = normalize(right)
	if (Array.isArray(a) || Array.isArray(b)) {
		if (!Array.isArray(a) || !Array.isArray(b) || a.length !== b.length) return false
		return a.every((value, index) => sameValue(value, b[index]))
	}
	if (isPlainObject(a) || isPlainObject(b)) {
		if (!isPlainObject(a) || !isPlainObject(b)) return false
		const keys = new Set([...Object.keys(a), ...Object.keys(b)].filter((key) => !LOCAL_KEY_PATTERN.test(key)))
		return [...keys].every((key) => sameValue(a[key], b[key]))
	}
	return String(a) === String(b)
}

function normalize(value) {
	return value === null || value === undefined ? "" : value
}

function isPlainObject(value) {
	return value !== null && typeof value === "object" && !Array.isArray(value)
}

const SAVED_HANDOFF_MS = 60_000

/** Router location that tells the next document page this document was just saved (editor → view). */
export function withSavedHandoff(location) {
	return { ...location, state: { ...location.state, documentSavedAt: Date.now() } }
}

/** Save time handed over by `withSavedHandoff`, or null when absent or older than a minute. */
export function takeSavedHandoff() {
	const savedAt = Number(globalThis.window?.history?.state?.documentSavedAt || 0)
	return savedAt && Date.now() - savedAt < SAVED_HANDOFF_MS ? savedAt : null
}

/** Provided by document shells as a ref that turns true once the open document was deleted elsewhere. */
export const DOCUMENT_DELETED_KEY = Symbol("document-deleted")
