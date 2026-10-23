import { getCurrentInstance, onBeforeUnmount, onMounted } from "vue"

import { createDocumentShortcutHandler } from "../utils/documentShortcuts.js"
import { useActionConfirmation } from "../utils/useActionConfirmation.js"

const registrations = new Set()
let handleKeydown = null

/**
 * Registers a document form for Ctrl/Cmd+S (save, else submit) and Ctrl/Cmd+D (cancel).
 * Pass getters for availability and the form's own button handlers; `element` scopes the form to its dialog or page.
 */
export function useDocumentShortcuts({ element, isBusy = false, canSave = false, save, canSubmit = false, submit, submitConfirms = false, canCancel = false, cancel, cancelConfirms = false }) {
	const instance = getCurrentInstance()
	const registration = {
		element: element || (() => instance?.proxy?.$el || null),
		isBusy, canSave, save, canSubmit, submit, submitConfirms, canCancel, cancel, cancelConfirms,
		confirm: useActionConfirmation(),
	}
	onMounted(() => {
		registrations.add(registration)
		if (handleKeydown) return
		handleKeydown = createDocumentShortcutHandler(registrations)
		window.addEventListener("keydown", handleKeydown, true)
	})
	onBeforeUnmount(() => {
		registrations.delete(registration)
		if (registrations.size || !handleKeydown) return
		window.removeEventListener("keydown", handleKeydown, true)
		handleKeydown = null
	})
	return registration
}
