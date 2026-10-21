import assert from "node:assert/strict"
import test from "node:test"
import { readFileSync } from "node:fs"
import { isChunkLoadError, reloadChunkTarget } from "../src/router/chunkReload.js"

function browser() {
	const storage = new Map(), assigned = []
	return {
		assigned,
		sessionStorage: { getItem: key => storage.get(key) ?? null, setItem: (key, value) => storage.set(key, value) },
		location: { assign: path => assigned.push(path) },
	}
}

test("chunk detection covers dynamic imports and CSS preload failures only", () => {
	for (const message of ["Failed to fetch dynamically imported module: /assets/new.js", "Importing a module script failed.", "Unable to preload CSS for /assets/new.css", "error loading dynamically imported module: /assets/new.js"]) {
		assert.equal(isChunkLoadError(new TypeError(message)), true)
		assert.equal(isChunkLoadError(message.toUpperCase()), true)
	}
	for (const error of [null, new Error("Permission denied"), new Error("Network error"), new TypeError("Cannot read properties of undefined")]) assert.equal(isChunkLoadError(error), false)
})

test("chunk reload persists a per-target ten-second guard across page loads", () => {
	const tab = browser(), path = "/web/cutting/plans/CP-1?tab=summary#totals"
	assert.equal(reloadChunkTarget(path, tab, 1000), true)
	assert.equal(reloadChunkTarget(path, tab, 10999), false)
	assert.equal(reloadChunkTarget("/web/cutting/plans", tab, 2000), true)
	assert.equal(reloadChunkTarget(path, { sessionStorage: tab.sessionStorage, location: tab.location }, 11000), true)
	assert.deepEqual(tab.assigned, [path, "/web/cutting/plans", path])
	assert.equal(reloadChunkTarget("", tab, 12000), false)
})

test("chunk reload avoids loops when session storage is unavailable", () => {
	const tab = browser()
	tab.sessionStorage.getItem = () => { throw new Error("Storage blocked") }
	assert.equal(reloadChunkTarget("/web/target", tab), false)
	assert.deepEqual(tab.assigned, [])
})

test("router and Vite recover the intended route with one shared reload guard", () => {
	const tab = browser(), hooks = {}
	const router = {
		currentRoute: { value: { path: "/current", fullPath: "/current" } },
		beforeEach: fn => { hooks.before = fn }, afterEach: fn => { hooks.after = fn }, onError: fn => { hooks.error = fn },
		resolve: to => ({ href: `/web${to.fullPath}` }),
	}
	const source = readFileSync(new URL("../src/router/index.js", import.meta.url), "utf8")
	const registration = source.slice(source.indexOf("let chunkReloadTarget = null")).replace("export function", "function").replace("export default router", "return reloadRouteChunk")
	const reloadRouteChunk = new Function("router", "getLockedRedirect", "getPermissionRedirect", "isChunkLoadError", "reloadChunkTarget", registration)(router, () => {}, () => {}, isChunkLoadError, path => reloadChunkTarget(path, tab, 5000))
	const main = readFileSync(new URL("../src/main.js", import.meta.url), "utf8")
	const preload = main.match(/window.addEventListener\("vite:preloadError",[\s\S]*?\n\}\)/)[0]
	new Function("window", "reloadRouteChunk", preload)({ addEventListener: (_name, handler) => { hooks.preload = handler } }, reloadRouteChunk)
	const target = { path: "/cutting/plans/CP-2", fullPath: "/cutting/plans/CP-2?new=1#details" }
	hooks.before(target)
	hooks.error(new Error("Permission denied"), target)
	assert.deepEqual(tab.assigned, [])
	hooks.error(new TypeError("Failed to fetch dynamically imported module"), target)
	let prevented = 0
	hooks.preload({ preventDefault: () => prevented++ })
	assert.equal(prevented, 1)
	assert.deepEqual(tab.assigned, ["/web/cutting/plans/CP-2?new=1#details"])

	// A preload event can arrive before the router reports the failure.
	const next = { path: "/cutting/plans/new", fullPath: "/cutting/plans/new?lot=LOT-1" }
	hooks.before(next)
	hooks.preload({ preventDefault: () => prevented++ })
	hooks.error(new Error("Unable to preload CSS"), next)
	assert.deepEqual(tab.assigned, ["/web/cutting/plans/CP-2?new=1#details", "/web/cutting/plans/new?lot=LOT-1"])
	hooks.after()
	hooks.preload({ preventDefault: () => prevented++ })
	assert.equal(tab.assigned.at(-1), "/web/current")
})
