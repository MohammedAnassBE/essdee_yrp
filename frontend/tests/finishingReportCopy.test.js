import assert from "node:assert/strict"
import fs from "node:fs"
import path from "node:path"
import test from "node:test"

const reports = path.resolve(import.meta.dirname, "../src/departments/finishing/reports")
const finishingCss = fs.readFileSync(path.resolve(reports, "../finishing.css"), "utf8")

for (const file of ["FinishingPackingDpr.vue", "FinishingIroningDpr.vue", "FinishingDispatchReport.vue"]) {
	test(`${file}: Copy Report captures every row because every row is in the DOM`, () => {
		const source = fs.readFileSync(path.join(reports, file), "utf8")
		assert.match(source, /<ReportShell\b[^\n]*\scopyable\s/)
		assert.match(source, /class="finishing-scroll"/)
		for (const lazy of [/useIncrementalRows/, /virtualScroller/, /paginator/, /:rows=/, /\.slice\(/, /max-height/]) {
			assert.doesNotMatch(source, lazy, `${file} must not limit the rendered rows (${lazy})`)
		}
	})
}

test("finishing tables only clip through overflow, which the copy helper expands", () => {
	const scroll = finishingCss.match(/\.finishing-scroll\s*{([^}]*)}/)[1]
	assert.match(scroll, /overflow:\s*auto/)
	assert.doesNotMatch(scroll, /(max-)?height:/)
})
