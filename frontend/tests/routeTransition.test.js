import assert from "node:assert/strict"
import { readFileSync } from "node:fs"
import test from "node:test"

const read = (path) => readFileSync(new URL(`../src/${path}`, import.meta.url), "utf8")

test("route changes mount the next page without waiting for a leave animation", () => {
	const app = read("App.vue")
	assert.match(app, /<Transition name="app-route">/)
	assert.doesNotMatch(app, /mode="out-in"/)
})

test("route transition is enter-only and hides the leaving page at once", () => {
	const css = read("styles/main.css")
	assert.match(css, /\.app-route-leave-active \{\n\tdisplay: none;\n\}/)
	assert.doesNotMatch(css, /\.app-route-leave-active[^{]*\{[^}]*transition/)
	assert.doesNotMatch(css, /\.app-route-leave-to/)
	const motionBlock = css.slice(css.indexOf("@media (prefers-reduced-motion: no-preference)"), css.indexOf(".app-route-leave-active"))
	assert.match(motionBlock, /\.app-route-enter-from \{\n\t\topacity: 0;\n\t\}/)
	assert.equal((css.match(/\.app-route-enter-from/g) || []).length, 1)
})
