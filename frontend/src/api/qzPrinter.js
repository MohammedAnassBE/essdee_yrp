export const APPROVAL_TIMEOUT_MS = 120000

export const QZ_MESSAGES = {
	assets: "Could not load QZ Tray printing support from this site. Reload the page and try again.",
	insecure: "Chrome blocks QZ Tray on sites that are not opened over HTTPS, and this site is open over http://. Use Microsoft Edge, or open the site over HTTPS, then try again.",
	unreachable: "Could not connect to QZ Tray. Make sure QZ Tray is running on this computer. If the browser asks to let this site access apps on this device, click Allow, then try again.",
	connectApproval: "QZ Tray did not answer the connection request. Find the QZ Tray Allow window (it may be behind other windows or on another screen), click Allow, then try again.",
	printerApproval: "QZ Tray did not return the printer list. Find the QZ Tray Allow window (it may be behind other windows or on another screen), click Allow, then try again.",
}

const SCRIPTS = ["/assets/frappe/node_modules/js-sha256/build/sha256.min.js", "/assets/frappe/node_modules/qz-tray/qz-tray.js"]
const UNREACHABLE = "Unable to establish connection with QZ"
const LOOPBACK_HOSTS = ["localhost", "127.0.0.1", "[::1]"]
const TIMED_OUT = Symbol("timed out")
let configured = null
let connecting = null

function loadScript(src) {
	return new Promise((resolve, reject) => {
		const existing = document.querySelector(`script[src="${src}"]`)
		if (existing?.dataset.loaded === "true") return resolve()
		const script = existing || document.createElement("script")
		let timer
		const finish = (error) => {
			clearTimeout(timer)
			script.removeEventListener("load", loaded)
			script.removeEventListener("error", failed)
			if (error) {
				script.remove()
				reject(error)
			} else {
				script.dataset.loaded = "true"
				resolve()
			}
		}
		const loaded = () => finish()
		const failed = () => finish(new Error(`Unable to load ${src}`))
		script.addEventListener("load", loaded, { once: true })
		script.addEventListener("error", failed, { once: true })
		timer = setTimeout(failed, 15000)
		if (!existing) {
			script.src = src
			script.async = true
			document.head.appendChild(script)
		}
	})
}

/** Same setup as Frappe Desk's qz_init: plain qz-tray.js with its own WebSocket. */
async function initialise() {
	if (configured === window.qz && window.qz) return window.qz
	try {
		if (!window.sha256) await loadScript(SCRIPTS[0])
		if (!window.qz) await loadScript(SCRIPTS[1])
	} catch {
		throw new Error(QZ_MESSAGES.assets)
	}
	if (!window.qz?.api || typeof window.sha256 !== "function") throw new Error(QZ_MESSAGES.assets)
	window.qz.api.setPromiseType((resolver) => new Promise(resolver))
	window.qz.api.setSha256Type((data) => window.sha256(data))
	configured = window.qz
	return window.qz
}

function within(promise, milliseconds) {
	let timer
	const expiry = new Promise((resolve) => { timer = setTimeout(() => resolve(TIMED_OUT), milliseconds) })
	return Promise.race([promise, expiry]).finally(() => clearTimeout(timer))
}

function abandon(qz, message) {
	qz.websocket.disconnect().catch(() => {})
	return new Error(message)
}

function reasonText(reason) {
	return String(reason?.message || reason || "")
}

function isUnreachable(reason) {
	return reasonText(reason).startsWith(UNREACHABLE)
}

export function isInsecurePage() {
	const location = window.location
	return Boolean(location?.protocol) && location.protocol !== "https:" && !LOOPBACK_HOSTS.includes(location.hostname)
}

/** Keeps QZ Tray's own error text so a failure can be diagnosed from the dialog. */
function qzError(reason) {
	const detail = `QZ Tray: ${reasonText(reason) || "the request was not completed."}`
	if (!isUnreachable(reason)) return new Error(detail)
	return new Error(`${isInsecurePage() ? QZ_MESSAGES.insecure : QZ_MESSAGES.unreachable} (${detail})`)
}

/** Same sequence as Frappe Desk's qz_connect: one attempt, then launch QZ Tray and retry three times. */
function connectLikeDesk(qz) {
	return qz.websocket.connect().catch((reason) => {
		if (!isUnreachable(reason)) throw reason
		window.location?.assign?.("qz:launch")
		return qz.websocket.connect({ retries: 3, delay: 1 })
	})
}

async function openConnection(qz, onStatus) {
	onStatus?.("connecting")
	const connected = connectLikeDesk(qz).catch((reason) => { throw qzError(reason) })
	if (await within(connected, APPROVAL_TIMEOUT_MS) === TIMED_OUT) {
		connected.catch(() => {})
		throw abandon(qz, QZ_MESSAGES.connectApproval)
	}
}

/** One shared connect attempt; an open socket counts only after QZ Tray accepted it. */
export function connectQz(qz, onStatus) {
	if (!connecting && qz.websocket.isActive()) return Promise.resolve()
	connecting ||= openConnection(qz, onStatus).finally(() => { connecting = null })
	return connecting
}

export async function getQzPrinters({ onStatus } = {}) {
	const qz = await initialise()
	await connectQz(qz, onStatus)
	onStatus?.("approve-printers")
	const printers = await within(qz.printers.find().catch((reason) => { throw qzError(reason) }), APPROVAL_TIMEOUT_MS)
	if (printers === TIMED_OUT) throw abandon(qz, QZ_MESSAGES.printerApproval)
	return printers
}

// Printing is not time-limited: a late QZ approval would print after the caller had rolled the reservation back.
export async function printQzRaw(printer, data) {
	const qz = await initialise()
	await connectQz(qz)
	return qz.print(qz.configs.create(printer), [data])
}
