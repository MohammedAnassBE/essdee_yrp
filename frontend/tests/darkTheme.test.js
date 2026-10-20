import assert from "node:assert/strict"
import { readFileSync } from "node:fs"
import test from "node:test"
import { runInNewContext } from "node:vm"

import {
	THEME_STORAGE_KEY,
	initializeTheme,
	toggleTheme,
} from "../src/utils/themePreference.js"

function makeEnvironment() {
	const classes = new Set()
	const root = {
		classList: {
			contains: (name) => classes.has(name),
			toggle(name, force) {
				if (force) classes.add(name)
				else classes.delete(name)
			},
		},
		dataset: {},
	}
	const meta = {
		content: null,
		setAttribute(name, value) {
			if (name === "content") this.content = value
		},
	}
	return { root, meta }
}

for (const entry of ["../index.html", "../../essdee_yrp/www/web.html"]) {
	test(`${entry} restores the theme synchronously before assets or content`, () => {
		const html = readFileSync(new URL(entry, import.meta.url), "utf8")
		const head = html.match(/<head>([\s\S]*?)<\/head>/)[1]
		const script = head.match(/<script>([\s\S]*?)<\/script>/)
		assert.ok(script, "entry point needs an inline synchronous theme script")
		assert.ok(script.index < head.search(/<link|<style|<script\s/))

		for (const saved of ["dark", "light", null, "invalid"]) {
			const { root } = makeEnvironment()
			const localStorage = {
				getItem(key) {
					assert.equal(key, THEME_STORAGE_KEY)
					return saved
				},
			}
			runInNewContext(script[1], { document: { documentElement: root }, localStorage })
			assert.equal(root.classList.contains("erp-dark"), saved === "dark")
		}
	})

	test(`${entry} starts even when storage access throws`, () => {
		const html = readFileSync(new URL(entry, import.meta.url), "utf8")
		const head = html.match(/<head>([\s\S]*?)<\/head>/)[1]
		const script = head.match(/<script>([\s\S]*?)<\/script>/)
		assert.ok(script, "entry point needs an inline synchronous theme script")
		for (const failGetter of [true, false]) {
			const { root } = makeEnvironment()
			const context = { document: { documentElement: root } }
			Object.defineProperty(context, "localStorage", {
				get() {
					if (failGetter) throw new Error("storage blocked")
					return { getItem() { throw new Error("read blocked") } }
				},
			})
			assert.doesNotThrow(() => runInNewContext(script[1], context))
			assert.equal(root.classList.contains("erp-dark"), false)
		}
	})
}

test("first visit keeps the light theme", () => {
	const { root, meta } = makeEnvironment()
	const storage = { getItem: () => null }

	assert.equal(initializeTheme({ storage, root, meta }), "light")
	assert.equal(root.classList.contains("erp-dark"), false)
	assert.equal(root.dataset.theme, "light")
	assert.equal(meta.content, "#ffffff")
})

test("stored preference loads and the toggle persists both states", () => {
	const { root, meta } = makeEnvironment()
	const writes = []
	const storage = {
		getItem: () => "dark",
		setItem: (...args) => writes.push(args),
	}

	assert.equal(initializeTheme({ storage, root, meta }), "dark")
	assert.equal(root.classList.contains("erp-dark"), true)
	assert.equal(meta.content, "#0d0e0d")

	assert.equal(toggleTheme({ storage, root, meta }), "light")
	assert.equal(root.classList.contains("erp-dark"), false)
	assert.deepEqual(writes.at(-1), [THEME_STORAGE_KEY, "light"])

	assert.equal(toggleTheme({ storage, root, meta }), "dark")
	assert.equal(root.classList.contains("erp-dark"), true)
	assert.deepEqual(writes.at(-1), [THEME_STORAGE_KEY, "dark"])
})

test("an inaccessible localStorage getter does not prevent startup", () => {
	const previousWindow = globalThis.window
	const { root, meta } = makeEnvironment()

	Object.defineProperty(globalThis, "window", {
		configurable: true,
		value: Object.defineProperty({}, "localStorage", {
			get() {
				throw new Error("storage blocked")
			},
		}),
	})

	try {
		assert.doesNotThrow(() => initializeTheme({ root, meta }))
		assert.equal(root.dataset.theme, "light")
	} finally {
		if (previousWindow === undefined) delete globalThis.window
		else globalThis.window = previousWindow
	}
})
