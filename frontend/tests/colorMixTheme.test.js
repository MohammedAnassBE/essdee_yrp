import assert from "node:assert/strict"
import { readdirSync, readFileSync } from "node:fs"
import test from "node:test"

const sourceFiles = (dir) => readdirSync(dir, { withFileTypes: true }).flatMap((entry) => {
	const path = `${dir}/${entry.name}`
	if (entry.isDirectory()) return sourceFiles(path)
	return /\.(vue|css)$/.test(entry.name) ? [path] : []
})

test("F-G08 colour mixes tint over the theme surface, never hard-coded white", () => {
	const root = new URL("../src", import.meta.url).pathname
	const offenders = sourceFiles(root).filter((path) => /color-mix\([^;]*,\s*white\)/.test(readFileSync(path, "utf8")))
	assert.deepEqual(offenders, [])
})
