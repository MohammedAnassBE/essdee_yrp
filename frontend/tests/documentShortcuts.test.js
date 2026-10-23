import assert from "node:assert/strict"
import test from "node:test"
import { resolve } from "node:path"
import { Vue, findNodes, loadComponent, mountComponent } from "../../scripts/helpers/vue_renderer.mjs"
import * as shortcuts from "../src/utils/documentShortcuts.js"

const { createDocumentShortcutHandler, getShortcutCommand, withShortcutHint } = shortcuts
const tick = async () => { await new Promise(resolve => setImmediate(resolve)); await Vue.nextTick() }

function element(name, children = []) {
	return { name, isConnected: true, contains(node) { return node === this || children.some(child => child === node || child.contains?.(node)) } }
}
function keyEvent(key, extra = {}) {
	const event = { key, ctrlKey: true, prevented: 0, preventDefault() { this.prevented += 1 }, ...extra }
	return event
}
function form(state = {}, calls = []) {
	const root = state.root || element("form")
	return {
		element: () => root,
		isBusy: () => Boolean(state.busy),
		canSave: () => Boolean(state.canSave), save: () => calls.push(`${root.name}:save`),
		canSubmit: () => Boolean(state.canSubmit), submit: () => calls.push(`${root.name}:submit`), submitConfirms: Boolean(state.submitConfirms),
		canCancel: () => Boolean(state.canCancel), cancel: () => calls.push(`${root.name}:cancel`), cancelConfirms: Boolean(state.cancelConfirms),
		confirm: (options) => calls.push({ message: options.message, accept: options.accept }),
	}
}
function harness(registrations, { dialogs = [], active = null, settle } = {}) {
	const set = new Set(registrations)
	return createDocumentShortcutHandler(set, {
		getOpenDialogs: () => dialogs,
		getActiveElement: () => active,
		settle: settle || (async () => {}),
	})
}

test("shortcut keys map Ctrl/Cmd+S and Ctrl/Cmd+D only", () => {
	assert.equal(getShortcutCommand({ key: "s", ctrlKey: true }), "save")
	assert.equal(getShortcutCommand({ key: "S", metaKey: true }), "save")
	assert.equal(getShortcutCommand({ key: "d", ctrlKey: true }), "cancel")
	assert.equal(getShortcutCommand({ key: "s" }), "")
	assert.equal(getShortcutCommand({ key: "s", ctrlKey: true, shiftKey: true }), "")
	assert.equal(getShortcutCommand({ key: "s", ctrlKey: true, altKey: true }), "")
	assert.equal(withShortcutHint("Save", "save", "Linux x86_64"), "Save (Ctrl+S)")
	assert.equal(withShortcutHint("Submit", "submit", "MacIntel"), "Submit (Cmd+S)")
	assert.equal(withShortcutHint("Cancel Document", "cancel", "Win32"), "Cancel Document (Ctrl+D)")
	assert.equal(withShortcutHint("Edit", undefined), "Edit")
})

test("Ctrl+S saves when dirty and permitted, and prevents the browser save dialog", async () => {
	const calls = []
	const event = keyEvent("s")
	await harness([form({ canSave: true, canSubmit: true }, calls)])(event)
	assert.deepEqual(calls, ["form:save"])
	assert.equal(event.prevented, 1)
})

test("Ctrl+S commits the focused field before deciding to save", async () => {
	const calls = [], state = { canSave: false, canSubmit: true }
	const input = { tagName: "INPUT", blur() { calls.push("blur"); state.canSave = true } }
	await harness([form(state, calls)], { active: input, settle: async () => calls.push("settle") })(keyEvent("s"))
	assert.deepEqual(calls, ["blur", "settle", "form:save"])
})

test("Ctrl+S on a clean permitted draft asks to submit and submits only on confirm", async () => {
	const calls = []
	await harness([form({ canSubmit: true }, calls)])(keyEvent("s"))
	assert.equal(calls.length, 1)
	assert.equal(calls[0].message, "Submit this document?")
	calls[0].accept()
	assert.equal(calls[1], "form:submit")
	const existing = []
	await harness([form({ canSubmit: true, submitConfirms: true }, existing)])(keyEvent("s"))
	assert.deepEqual(existing, ["form:submit"], "a handler with its own confirmation is called directly")
})

test("Ctrl+S does nothing on submitted or unpermitted documents but still prevents the browser", async () => {
	const calls = []
	const event = keyEvent("s")
	await harness([form({ canCancel: true }, calls)])(event)
	assert.deepEqual(calls, [])
	assert.equal(event.prevented, 1)
	const unregistered = keyEvent("s")
	await harness([])(unregistered)
	assert.equal(unregistered.prevented, 0)
})

test("Ctrl+D asks to cancel only when submitted and permitted", async () => {
	const calls = []
	const event = keyEvent("d")
	await harness([form({ canCancel: true }, calls)])(event)
	assert.equal(event.prevented, 1)
	assert.equal(calls[0].message, "Cancel this document?")
	calls[0].accept()
	assert.equal(calls[1], "form:cancel")
	const draft = []
	const draftEvent = keyEvent("d")
	await harness([form({ canSave: true, canSubmit: true }, draft)])(draftEvent)
	assert.deepEqual(draft, [])
	assert.equal(draftEvent.prevented, 1)
	const existing = []
	await harness([form({ canCancel: true, cancelConfirms: true }, existing)])(keyEvent("d"))
	assert.deepEqual(existing, ["form:cancel"])
})

test("Ctrl+D outside any document form keeps the browser default", async () => {
	const event = keyEvent("d")
	await harness([form({ canCancel: true, root: element("page") })], { dialogs: [element("unrelated")] })(event)
	assert.equal(event.prevented, 0)
})

test("repeats, busy forms and unrelated modals are ignored", async () => {
	const calls = []
	const repeated = keyEvent("s", { repeat: true })
	await harness([form({ canSave: true }, calls)])(repeated)
	assert.equal(repeated.prevented, 1)
	await harness([form({ canSave: true, busy: true }, calls)])(keyEvent("s"))
	await harness([form({ canSave: true, root: element("page") }, calls)], { dialogs: [element("confirm")] })(keyEvent("s"))
	assert.deepEqual(calls, [])
})

test("an open dialog takes precedence over the page", async () => {
	const calls = []
	const dialogForm = element("dialog-form")
	const dialog = element("dialog", [dialogForm])
	const page = form({ canSave: true, canCancel: true, root: element("page") }, calls)
	const inDialog = form({ canSave: true, canCancel: true, cancelConfirms: true, root: dialogForm }, calls)
	await harness([inDialog, page], { dialogs: [dialog] })(keyEvent("s"))
	await harness([page, inDialog], { dialogs: [dialog] })(keyEvent("d"))
	assert.deepEqual(calls, ["dialog-form:save", "dialog-form:cancel"])
	await harness([page, inDialog], { dialogs: [] })(keyEvent("s"))
	assert.equal(calls.at(-1), "dialog-form:save", "with no dialog open the latest registration wins")
	const topOnly = []
	const lowerForm = element("lower-form")
	await harness([form({ canSave: true, root: lowerForm }, topOnly)], { dialogs: [element("lower", [lowerForm]), dialog] })(keyEvent("s"))
	assert.deepEqual(topOnly, [])
})

test("save is preferred over submit across forms in the same scope", async () => {
	const calls = []
	const submitter = form({ canSubmit: true, submitConfirms: true, root: element("strip") }, calls)
	const saver = form({ canSave: true, root: element("quantity") }, calls)
	await harness([saver, submitter])(keyEvent("s"))
	assert.deepEqual(calls, ["quantity:save"])
})

test("DocumentSaveButton and DocumentActionStrip register their own enabled handlers", async () => {
	const registered = []
	const modules = {
		"primevue/button": props => Vue.h("button", props, props.label),
		"primevue/menu": () => null,
		"../../composables/useDocumentShortcuts.js": { useDocumentShortcuts: options => registered.push(options) },
		"../../utils/documentShortcuts.js": shortcuts,
		"../../utils/useActionConfirmation.js": { useActionConfirmation: () => options => registered.push({ confirmed: options.message }) },
		"./documentPrimaryAction.js": await import("../src/components/documents/documentPrimaryAction.js"),
	}
	const events = []
	const saveProps = Vue.reactive({ saved: true, dirty: true, showSubmit: true, onSave: () => events.push("save"), onSubmit: () => events.push("submit") })
	const saveRoot = mountComponent(loadComponent(resolve("frontend/src/components/documents/DocumentSaveButton.vue"), modules), saveProps)
	const button = registered[0]
	assert.match(findNodes(saveRoot, n => n.type === "button")[0].props.title, /^Save \((Ctrl|Cmd)\+S\)$/)
	assert.equal(button.canSave(), true); assert.equal(button.canSubmit(), false)
	button.save(); assert.deepEqual(events, ["save"])
	saveProps.dirty = false; await tick()
	assert.equal(button.canSave(), false); assert.equal(button.canSubmit(), true); assert.equal(button.submitConfirms(), true)
	saveProps.loading = true; await tick()
	assert.equal(button.isBusy(), true); assert.equal(button.canSubmit(), false)
	saveProps.loading = false; saveProps.docstatus = 1; await tick()
	assert.equal(button.canSave(), false); assert.equal(button.canSubmit(), false)

	const runs = []
	const actions = Vue.reactive({ actions: [
		{ key: "save", label: "Edit", command: () => runs.push("edit") },
		{ key: "submit", label: "Submit", primary: true, shortcut: "submit", command: () => runs.push("submit") },
		{ key: "cancel", label: "Cancel Document", menuOnly: true, shortcut: "cancel", disabled: true, command: () => runs.push("cancel") },
	] })
	const stripRoot = mountComponent(loadComponent(resolve("frontend/src/components/documents/DocumentActionStrip.vue"), modules), actions)
	const strip = registered.at(-1)
	assert.match(findNodes(stripRoot, n => n.type === "button")[0].props.title, /^Submit \((Ctrl|Cmd)\+S\)$/)
	assert.equal(strip.canSave(), false, "an action is a shortcut only when it opts in")
	assert.equal(strip.canSubmit(), true); assert.equal(strip.submitConfirms(), true)
	assert.equal(strip.canCancel(), false, "disabled actions are not run")
	strip.submit(); assert.deepEqual(runs, ["submit"])
	actions.actions[2].disabled = false; actions.actions[1].confirms = false
	assert.equal(strip.canCancel(), true); assert.equal(strip.submitConfirms(), false)
	strip.cancel(); assert.deepEqual(runs, ["submit", "cancel"])
})
