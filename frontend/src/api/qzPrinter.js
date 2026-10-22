let initialised = false

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

async function initialise() {
	if (initialised && window.qz) return window.qz
	if (!window.sha256) await loadScript("/assets/frappe/node_modules/js-sha256/build/sha256.min.js")
	if (!window.qz) await loadScript("/assets/frappe/node_modules/qz-tray/qz-tray.js")
	if (!window.qz || !window.sha256) throw new Error("QZ Tray printing assets are unavailable.")
	window.qz.api.setPromiseType((resolver) => new Promise(resolver))
	window.qz.api.setSha256Type((data) => window.sha256(data))
	initialised = true
	return window.qz
}

const UNREACHABLE = "Unable to establish connection with QZ"

function qzError(reason) {
	const message = String(reason?.message || reason || "")
	if (message.startsWith(UNREACHABLE)) return new Error("Could not connect to QZ Tray. Start QZ Tray on this computer and try again.")
	return new Error(`QZ Tray: ${message || "the request was not completed."}`)
}

async function initialiseOrExplain() {
	try {
		return await initialise()
	} catch {
		throw new Error("Could not load QZ Tray printing support from this site. Reload the page and try again.")
	}
}

// Connect and printer lookup wait on QZ Tray's own site-approval prompts, so they are not time-limited.
export async function getQzPrinters() {
	const qz = await initialiseOrExplain()
	try {
		if (!qz.websocket.isActive()) await qz.websocket.connect({ retries: 2, delay: 1 })
		return await qz.printers.find()
	} catch (reason) {
		throw qzError(reason)
	}
}

export async function printQzRaw(printer, data) {
	const qz = await initialise()
	if (!qz.websocket.isActive()) await qz.websocket.connect({ retries: 2, delay: 1 })
	return qz.print(qz.configs.create(printer), [data])
}
