import assert from "node:assert/strict"
import test from "node:test"

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
