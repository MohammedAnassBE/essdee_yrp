import { computed } from "vue"
import { cellAlign, normalizeReportColumn } from "../../../composables/reportColumns.js"
import { formatReportCell } from "../../finishing/reports/finishingReports.js"

export function usePlanningQuantityColumns(reportKey, sourceColumns, sourceRows) {
	const columns = computed(() => sourceColumns.value.map(normalizeReportColumn))
	const rows = sourceRows
	function downloadCsv() {
		const exportColumns = reportKey === "planning-month-wise-detail" ? [{ fieldname: "item", label: "Item" }, ...columns.value] : columns.value
		const values = [exportColumns.map((column) => column.label), ...rows.value.map((row) => exportColumns.map((column) => row[column.fieldname]))]
		const quote = (value) => '"' + String(value ?? "").replaceAll('"', '""') + '"'
		const url = URL.createObjectURL(new Blob(["\uFEFF", values.map((row) => row.map(quote).join(",")).join("\r\n")], { type: "text/csv;charset=utf-8" }))
		const link = document.createElement("a")
		link.href = url
		link.download = reportKey + ".csv"
		link.click()
		window.setTimeout(() => URL.revokeObjectURL(url), 1000)
	}
	return { columns, rows, cellAlign, formattedCell: formatReportCell, downloadCsv }
}
