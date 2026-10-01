let initialised = false

function loadScript(src) {
	return new Promise((resolve, reject) => {
		const existing = document.querySelector(`script[src="${src}"]`)
		if (existing) {
			if (existing.dataset.loaded === "true") resolve()
			else {
				existing.addEventListener("load", resolve, { once: true })
				existing.addEventListener("error", reject, { once: true })
			}
			return
		}
		const script = document.createElement("script")
		script.src = src
		script.async = true
		script.addEventListener("load", () => {
			script.dataset.loaded = "true"
			resolve()
		}, { once: true })
		script.addEventListener("error", () => reject(new Error(`Unable to load ${src}`)), { once: true })
		document.head.appendChild(script)
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

export async function getQzPrinters() {
	const qz = await initialise()
	if (!qz.websocket.isActive()) {
		try {
			await qz.websocket.connect({ retries: 2, delay: 1 })
		} catch {
			throw new Error("Start QZ Tray on this computer, then try again.")
		}
	}
	return qz.printers.find()
}

export async function printQzRaw(printer, data) {
	const qz = await initialise()
	if (!qz.websocket.isActive()) await qz.websocket.connect({ retries: 2, delay: 1 })
	return qz.print(qz.configs.create(printer), [data])
}
