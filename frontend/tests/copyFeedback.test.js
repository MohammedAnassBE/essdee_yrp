import assert from "node:assert/strict"
import test from "node:test"
import { Vue, mountComponent } from "../../scripts/helpers/vue_renderer.mjs"

const { COPIED_RESET_MS, useCopyFeedback } = await import("../src/composables/useCopyFeedback.js")
const { COPY_AGAIN_MESSAGE, COPY_BLOCKED_MESSAGE, copyPendingImage, copyWithCommand, writeImageToClipboard } = await import("../src/components/reports/copyElementAsImage.js")

globalThis.FileReader ??= class {
	async readAsDataURL(blob) {
		this.result = `data:${blob.type};base64,${Buffer.from(await blob.arrayBuffer()).toString("base64")}`
		this.onload()
	}
}

function fakeTimers() {
	const pending = []
	return { pending, setTimeout: (run, delay) => pending.push({ run, delay }), clearTimeout() {} }
}

test("copy feedback flips to copied for 1.5 s and ignores a second click while copying", async () => {
	const timers = fakeTimers(), toasts = []
	let feedback
	mountComponent({ setup() { feedback = useCopyFeedback({ toast: { add: message => toasts.push(message) }, timers }); return () => null } })
	let finish
	const first = feedback.runCopy(() => new Promise(done => { finish = done }))
	assert.equal(await feedback.runCopy(async () => {}), false)
	assert.equal(feedback.copying.value, true)
	finish()
	assert.equal(await first, true)
	assert.deepEqual([feedback.copying.value, feedback.copied.value, toasts.length, timers.pending[0].delay], [false, true, 1, COPIED_RESET_MS])
	timers.pending[0].run()
	assert.equal(feedback.copied.value, false)
	await Vue.nextTick()
})

function fakeDocument(execResult = true) {
	const listeners = []
	const written = {}
	return {
		written,
		addEventListener: (_type, handler) => listeners.push(handler),
		removeEventListener: (_type, handler) => listeners.splice(listeners.indexOf(handler), 1),
		execCommand() {
			if (!execResult) return false
			for (const handler of [...listeners]) handler({ preventDefault() {}, clipboardData: { setData: (type, value) => { written[type] = value } } })
			return true
		},
		listeners,
	}
}

test("on plain http the report image is copied through execCommand as HTML plus text", async () => {
	const doc = fakeDocument()
	await writeImageToClipboard(new Blob(["png"], { type: "image/png" }), "Lot\tQty", { clipboard: undefined, doc })
	assert.match(doc.written["text/html"], /^<img src="data:image\/png;base64,/)
	assert.equal(doc.written["text/plain"], "Lot\tQty")
	assert.equal(doc.listeners.length, 0)
})

test("a blocked execCommand copy fails loudly instead of reporting success", async () => {
	assert.equal(copyWithCommand(fakeDocument(false), { "text/plain": "x" }), false)
	await assert.rejects(writeImageToClipboard(new Blob(["png"]), "", { clipboard: undefined, doc: fakeDocument(false) }), { message: COPY_BLOCKED_MESSAGE })
})

test("a capture that outlives the click is kept and copied by the next click", async () => {
	Object.defineProperty(globalThis.navigator, "userActivation", { value: { isActive: false }, configurable: true })
	try {
		const key = {}
		await assert.rejects(writeImageToClipboard(new Blob(["png"], { type: "image/png" }), "Lot", { key, clipboard: undefined, doc: fakeDocument(false) }), { message: COPY_AGAIN_MESSAGE, retryable: true })
		assert.equal(copyPendingImage({}, fakeDocument()), false)
		await assert.rejects(writeImageToClipboard(new Blob(["png"], { type: "image/png" }), "Lot", { key, clipboard: undefined, doc: fakeDocument(false) }))
		const doc = fakeDocument()
		assert.equal(copyPendingImage(key, doc), true)
		assert.equal(doc.written["text/plain"], "Lot")
		assert.equal(copyPendingImage(key, fakeDocument()), false)
	} finally { delete globalThis.navigator.userActivation }
})
