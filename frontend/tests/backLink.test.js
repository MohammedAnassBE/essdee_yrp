import assert from "node:assert/strict"
import test from "node:test"
import fs from "node:fs"

const read = (path) => fs.readFileSync(new URL(`../src/${path}`, import.meta.url), "utf8")

test("every page back button uses the shared accent BackLink", () => {
	const backLink = read("components/navigation/BackLink.vue")
	assert.match(backLink, /class="back-link-button"/)
	assert.doesNotMatch(backLink, /<span|text:/)
	assert.match(backLink, /<i class="pi pi-arrow-left" aria-hidden="true" \/>/)
	assert.match(backLink, /:aria-label="`Back to \$\{label\}`"/)
	assert.match(backLink, /width: 38px;\s*height: 38px;/)
	assert.match(backLink, /color: var\(--erp-accent-ink\);/)
	assert.match(backLink, /v-if="!isLockedExit\(to\)"/)
	assert.match(backLink, /background: var\(--erp-accent-soft\);/)
	assert.match(backLink, /border: 1px solid var\(--erp-accent-border\);/)
	assert.match(backLink, /width: 44px; height: 44px;/)
	assert.match(read("components/navigation/InlinePageNavigation.vue"), /<BackLink :to="resolvedBackTo" :label="backLabel"/)
	assert.match(read("components/DepartmentPage.vue"), /<BackLink :to="backTo" :label="backLabel" \/>/)
	assert.match(read("departments/sewing/SewingBackLink.vue"), /<BackLink :to="to" :label="label" \/>/)
})

test("prev/next arrows keep the neutral style so Back stands apart", () => {
	const steps = read("components/navigation/DocumentStepButtons.vue")
	assert.match(steps, /color: var\(--erp-text-muted\);/)
	assert.doesNotMatch(steps, /accent-soft/)
})
