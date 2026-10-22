export const REACH_TIMEOUT_MS = 20000
export const APPROVAL_TIMEOUT_MS = 120000

export const QZ_MESSAGES = {
	assets: "Could not load QZ Tray printing support from this site. Reload the page and try again.",
	blocked: "This browser is blocking this site from reaching QZ Tray. Click the site settings icon left of the address bar, allow Local network access (Apps on this device), reload the page and try again.",
	unreached: "The browser did not reach QZ Tray. If the browser asks to let this site access apps on this device, click Allow (or allow Local network access in the site settings left of the address bar). Make sure QZ Tray is running, then try again.",
	unreachable: "Could not connect to QZ Tray. Start QZ Tray on this computer and try again.",
	connectApproval: "QZ Tray did not answer the connection request. Find the QZ Tray Allow window (it may be behind other windows or on another screen), click Allow, then try again.",
	printerApproval: "QZ Tray did not return the printer list. Find the QZ Tray Allow window (it may be behind other windows or on another screen), click Allow, then try again.",
}

const SCRIPTS = ["/assets/frappe/node_modules/js-sha256/build/sha256.min.js", "/assets/frappe/node_modules/qz-tray/qz-tray.js"]
const UNREACHABLE = "Unable to establish connection with QZ"
const TIMED_OUT = Symbol("timed out")
const socketOpened = { notify: null }
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

/** Lets the connect stage tell "browser never reached QZ Tray" apart from "waiting for the QZ Allow prompt". */
function trackedWebSocket(Base) {
	return class TrackedWebSocket extends Base {
		constructor(...args) {
			super(...args)
			this.addEventListener("open", () => socketOpened.notify?.())
		}
	}
}

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
	if (typeof WebSocket === "function") window.qz.api.setWebSocketType?.(trackedWebSocket(WebSocket))
	configured = window.qz
	return window.qz
}

export async function getLocalNetworkAccess() {
	for (const name of ["loopback-network", "local-network-access"]) {
		try {
			return (await navigator.permissions.query({ name })).state
		} catch {
			// Older browsers do not know this permission name.
		}
	}
	return "unsupported"
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

function qzError(reason) {
	const message = String(reason?.message || reason || "")
	if (message.startsWith(UNREACHABLE)) return new Error(QZ_MESSAGES.unreachable)
	return new Error(`QZ Tray: ${message || "the request was not completed."}`)
}

async function openConnection(qz, onStatus) {
	const access = await getLocalNetworkAccess()
	if (access === "denied") throw new Error(QZ_MESSAGES.blocked)
	onStatus?.(access === "prompt" ? "browser-permission" : "connecting")
	const reached = new Promise((resolve) => { socketOpened.notify = resolve })
	const connected = qz.websocket.connect({ retries: 2, delay: 1 }).then(() => true, (reason) => { throw qzError(reason) })
	try {
		if (await within(Promise.race([reached, connected]), REACH_TIMEOUT_MS) === TIMED_OUT) throw abandon(qz, QZ_MESSAGES.unreached)
		onStatus?.("approve-connection")
		if (await within(connected, APPROVAL_TIMEOUT_MS) === TIMED_OUT) throw abandon(qz, QZ_MESSAGES.connectApproval)
	} finally {
		socketOpened.notify = null
		connected.catch(() => {})
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
