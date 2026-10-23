import assert from "node:assert/strict"
import { readFileSync } from "node:fs"
import test from "node:test"

const style = path => readFileSync(new URL(`../src/${path}`, import.meta.url), "utf8").split("<style scoped>")[1]
const rule = (css, selector) => css.match(new RegExp(`^${selector.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")} \\{([^}]*)\\}`, "m"))?.[1] ?? ""

test("Audit Pending puts its fixed height on the clipping panels so Copy Report can grow them", () => {
	const css = style("departments/accounts/reports/AuditPendingFinishingPlans.vue")
	const layout = rule(css, ".master-detail-layout")
	const panels = rule(css, ".master-panel, .detail-panel")
	assert.doesNotMatch(layout, /height/, "a fixed height on the non-clipping grid is skipped by expandForCapture and the panels spill")
	assert.match(panels, /height: clamp\(540px, calc\(100dvh - 350px\), 820px\)/)
	assert.match(panels, /overflow: hidden/)
	assert.doesNotMatch(css, /\.master-detail-layout \{[^}]*height: auto/)
})

test("Sewing summaries let the matrix widen to its table once Copy Report stops it scrolling", () => {
	assert.match(style("departments/sewing/reports/SewingItemSummary.vue"), /\.item-summary-group :deep\(\.sewing-report-matrix\) \{ min-width: auto; \}/)
	assert.match(style("departments/sewing/reports/SewingMonthlySummary.vue"), /\[data-sewing-report="monthly-summary"\] :deep\(\.sewing-report-matrix\) \{ min-width: auto; \}/)
})
