const DIALOG_SELECTOR = ".p-dialog, .p-drawer"
const EDITABLE_TAGS = new Set(["INPUT", "TEXTAREA", "SELECT"])
const COMMAND_KEYS = { save: "S", submit: "S", cancel: "D" }

/** Desk-style shortcut label for a document command, e.g. `Ctrl+S` or `Cmd+S`. */
export function documentShortcutKey(command, platform = globalThis.navigator?.platform || "") {
	const key = COMMAND_KEYS[command]
	if (!key) return ""
	return `${/mac|iphone|ipad/i.test(platform) ? "Cmd" : "Ctrl"}+${key}`
}

/** Button tooltip with the shortcut appended: `Save (Ctrl+S)`. */
export function withShortcutHint(label, command, platform) {
	const key = documentShortcutKey(command, platform)
	return key ? `${label} (${key})` : label
}

/** `save` for Ctrl/Cmd+S, `cancel` for Ctrl/Cmd+D, otherwise empty. */
export function getShortcutCommand(event) {
	if (!(event.ctrlKey || event.metaKey) || event.altKey || event.shiftKey || event.isComposing) return ""
	const key = String(event.key || "").toLowerCase()
	if (key === "s" || event.code === "KeyS") return "save"
	if (key === "d" || event.code === "KeyD") return "cancel"
	return ""
}

const read = (value) => (typeof value === "function" ? value() : value)

/** Registrations inside the topmost open dialog, or page registrations when no dialog is open. */
export function getScopedRegistrations(registrations, dialogs) {
	const top = dialogs.at(-1)
	return registrations.filter((registration) => {
		const element = registration.element()
		if (!element || element.isConnected === false) return false
		return top ? top.contains(element) : true
	})
}

function pickRegistration(candidates, isEligible, activeElement) {
	const eligible = candidates.filter(isEligible)
	return eligible.find((registration) => activeElement && registration.element()?.contains?.(activeElement)) || eligible.at(-1) || null
}

function confirmThen(registration, flag, message, acceptLabel, action) {
	if (read(registration[flag])) return action()
	registration.confirm({
		header: "Confirm",
		message,
		acceptLabel,
		acceptSeverity: acceptLabel === "Submit" ? "primary" : "danger",
		acceptIcon: acceptLabel === "Submit" ? "pi pi-check" : "pi pi-ban",
		accept: action,
	})
}

function runSave(candidates, activeElement) {
	const saver = pickRegistration(candidates, (registration) => read(registration.canSave), activeElement)
	if (saver) return saver.save()
	const submitter = pickRegistration(candidates, (registration) => read(registration.canSubmit), activeElement)
	if (submitter) confirmThen(submitter, "submitConfirms", "Submit this document?", "Submit", submitter.submit)
}

function runCancel(candidates, activeElement) {
	const canceller = pickRegistration(candidates, (registration) => read(registration.canCancel), activeElement)
	if (canceller) confirmThen(canceller, "cancelConfirms", "Cancel this document?", "Cancel Document", canceller.cancel)
}

/** Blurs the focused field so v-model, blur and change handlers commit its value. */
export function commitFocusedField(activeElement) {
	if (!activeElement?.blur) return false
	if (!EDITABLE_TAGS.has(activeElement.tagName) && !activeElement.isContentEditable) return false
	activeElement.blur()
	return true
}

function browserEnvironment() {
	const zIndex = (dialog) => Number(globalThis.getComputedStyle?.(dialog.parentElement || dialog)?.zIndex) || 0
	return {
		getOpenDialogs: () => [...document.querySelectorAll(DIALOG_SELECTOR)]
			.filter((dialog) => dialog.getClientRects().length)
			.map((dialog, index) => ({ dialog, index, z: zIndex(dialog) }))
			.sort((left, right) => left.z - right.z || left.index - right.index)
			.map(({ dialog }) => dialog),
		getActiveElement: () => document.activeElement,
		settle: () => new Promise((resolve) => setTimeout(resolve, 0)),
	}
}

/** One keydown handler shared by every registered document form; dialogs take precedence over the page. */
export function createDocumentShortcutHandler(registrations, environment = browserEnvironment()) {
	let running = false
	const scoped = () => getScopedRegistrations([...registrations], environment.getOpenDialogs())
	return async function handleKeydown(event) {
		const command = getShortcutCommand(event)
		if (!command || !registrations.size) return
		const candidates = scoped()
		if (command === "cancel" && !candidates.length) return
		event.preventDefault()
		if (event.repeat || running || !candidates.length || candidates.some((registration) => read(registration.isBusy))) return
		if (command === "cancel") return runCancel(candidates, environment.getActiveElement())
		running = true
		try {
			if (commitFocusedField(environment.getActiveElement())) await environment.settle()
			const settled = scoped()
			if (!settled.some((registration) => read(registration.isBusy))) runSave(settled, environment.getActiveElement())
		} finally {
			running = false
		}
	}
}
