import assert from "node:assert/strict"
import { readFileSync } from "node:fs"
import test from "node:test"

import { stockCellValue } from "../src/components/reports/reportUtils.js"
import { formatDocumentOverviewValue } from "../src/utils/documentOverview.js"
import {
	formatDatesInText,
	formatDisplayByFieldtype,
	formatDisplayDate,
	formatDisplayDatetime,
	getDateParts,
} from "../src/utils/dateFormat.js"
import { formatFullDateTime } from "../src/utils/prettyDate.js"

const source = (path) => readFileSync(new URL(path, import.meta.url), "utf8")

test("dates display as DD-MM-YYYY from ISO strings, datetimes, Date objects and display strings", () => {
	assert.equal(formatDisplayDate("2026-10-23"), "23-10-2026")
	assert.equal(formatDisplayDate("2026-10-23 14:05:09.123456"), "23-10-2026")
	assert.equal(formatDisplayDate("2026-10-23T14:05:09"), "23-10-2026")
	assert.equal(formatDisplayDate(new Date(2026, 9, 3, 8, 4)), "03-10-2026")
	assert.equal(formatDisplayDate("23-10-2026"), "23-10-2026")
})

test("empty dates use the fallback and unparseable text is left alone", () => {
	assert.equal(formatDisplayDate(null), "—")
	assert.equal(formatDisplayDate(undefined), "—")
	assert.equal(formatDisplayDate(""), "—")
	assert.equal(formatDisplayDate("", ""), "")
	assert.equal(formatDisplayDate("Not set"), "Not set")
	assert.equal(formatDisplayDate(new Date("invalid")), "—")
	assert.equal(getDateParts(new Date("invalid")), null)
})

test("datetimes display as DD-MM-YYYY HH:mm, with seconds on request", () => {
	assert.equal(formatDisplayDatetime("2026-10-23 14:05:09.123456"), "23-10-2026 14:05")
	assert.equal(formatDisplayDatetime("2026-10-23T09:05"), "23-10-2026 09:05")
	assert.equal(formatDisplayDatetime("2026-10-23 9:05:07", { seconds: true }), "23-10-2026 09:05:07")
	assert.equal(formatDisplayDatetime(new Date(2026, 9, 23, 7, 3, 4)), "23-10-2026 07:03")
	assert.equal(formatDisplayDatetime("2026-10-23"), "23-10-2026")
	assert.equal(formatDisplayDatetime("23-10-2026 14:05:09"), "23-10-2026 14:05")
	assert.equal(formatDisplayDatetime(null), "—")
	assert.equal(formatDisplayDatetime("", { fallback: "" }), "")
})

test("fieldtype dispatch formats Date and Datetime only", () => {
	assert.equal(formatDisplayByFieldtype("2026-10-23 14:05:09", "Date"), "23-10-2026")
	assert.equal(formatDisplayByFieldtype("2026-10-23 14:05:09", "Datetime"), "23-10-2026 14:05")
	assert.equal(formatDisplayByFieldtype("2026-10-23", "Data"), "2026-10-23")
	assert.equal(formatDisplayByFieldtype("", "Date", { fallback: "" }), "")
})

test("ISO dates embedded in text become DD-MM-YYYY without touching document names", () => {
	assert.equal(formatDatesInText("Lot report 2026-10-01 to 2026-10-23"), "Lot report 01-10-2026 to 23-10-2026")
	assert.equal(formatDatesInText("Posted on 2026-10-23 14:05:09."), "Posted on 23-10-2026 14:05:09.")
	assert.equal(formatDatesInText("PO-2026-10-23-0001 and SE-2026-00012"), "PO-2026-10-23-0001 and SE-2026-00012")
	assert.equal(formatDatesInText(null), null)
})

test("shared formatters route through the date helper", () => {
	assert.equal(formatFullDateTime("2026-10-22 09:05:07.947516"), "22-10-2026 09:05:07")
	assert.equal(formatFullDateTime("bad"), "")
	assert.equal(stockCellValue("2026-10-23", { fieldtype: "Date" }), "23-10-2026")
	assert.equal(stockCellValue("2026-10-23 14:05:09", { fieldtype: "Datetime" }), "23-10-2026 14:05")
	assert.equal(stockCellValue("2026-10-23", { fieldtype: "Data" }), "2026-10-23")
	assert.equal(formatDocumentOverviewValue({ fieldtype: "Date", value: "2026-10-23" }), "23-10-2026")
	assert.equal(formatDocumentOverviewValue({ fieldtype: "Datetime", value: "2026-10-23 14:05:09" }), "23-10-2026 14:05")
})

test("shared list, side panel and transaction dialog use the date helper", () => {
	assert.match(source("../src/components/common/ListView.vue"), /\["Date", "Datetime"\]\.includes\(column\.fieldtype\)\) return formatDisplayByFieldtype\(value, column\.fieldtype\)/)
	assert.match(source("../src/components/common/DocumentSidePanel.vue"), /formatDisplayDatetime\(doc\.modified\)/)
	const dialog = source("../src/components/documents/DocumentTransactionDialog.vue")
	assert.match(dialog, /Updated \{\{ formatDisplayDatetime\(payload\.record\.modified\) \}\}/)
	assert.doesNotMatch(dialog, /function formatDate/)
	assert.match(source("../src/components/common/TemporalFieldBase.vue"), /const dateFormat = computed\(\(\) => "dd-mm-yy"\)/)
})
