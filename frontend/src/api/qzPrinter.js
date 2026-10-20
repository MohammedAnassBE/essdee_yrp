let initialised = false

function loadScript(src, signal) {
	return new Promise((resolve, reject) => {
		const existing = document.querySelector(`script[src="${src}"]`)
		if (existing?.dataset.loaded === "true") return resolve()
		const script = existing || document.createElement("script")
		let timer
		const finish = (error) => {
			clearTimeout(timer)
			script.removeEventListener("load", loaded)
			script.removeEventListener("error", failed)
			signal?.removeEventListener("abort", failed)
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
		if (signal?.aborted) return failed()
		script.addEventListener("load", loaded, { once: true })
		script.addEventListener("error", failed, { once: true })
		signal?.addEventListener("abort", failed, { once: true })
		timer = setTimeout(failed, 15000)
		if (!existing) {
			script.src = src
			script.async = true
			document.head.appendChild(script)
		}
	})
}

async function initialise(signal) {
	if (initialised && window.qz) return window.qz
	if (!window.sha256) await loadScript("/assets/frappe/node_modules/js-sha256/build/sha256.min.js", signal)
	if (!window.qz) await loadScript("/assets/frappe/node_modules/qz-tray/qz-tray.js", signal)
	if (!window.qz || !window.sha256) throw new Error("QZ Tray printing assets are unavailable.")
	window.qz.api.setPromiseType((resolver) => new Promise(resolver))
	window.qz.api.setSha256Type((data) => window.sha256(data))
	initialised = true
	return window.qz
}

export async function getQzPrinters() {
	const message = "Could not connect to QZ Tray. Start QZ Tray on this computer and try again."
	const controller = new AbortController()
	let timer
	try {
		return await Promise.race([
			(async () => {
				const qz = await initialise(controller.signal)
				if (!qz.websocket.isActive()) await qz.websocket.connect({ retries: 2, delay: 1 })
				return qz.printers.find()
			})(),
			new Promise((_, reject) => { timer = setTimeout(() => reject(new Error(message)), 15000) }),
		])
	} catch {
		throw new Error(message)
	} finally {
		clearTimeout(timer)
		controller.abort()
	}
}

export async function printQzRaw(printer, data) {
	const qz = await initialise()
	if (!qz.websocket.isActive()) await qz.websocket.connect({ retries: 2, delay: 1 })
	return qz.print(qz.configs.create(printer), [data])
}
