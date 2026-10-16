import { onMounted, ref } from "vue"
import { useReportColumns } from "../../../composables/useReportColumns.js"
import { formatReportCell } from "../../finishing/reports/finishingReports.js"

export function usePlanningReportColumns(reportKey, sourceColumns, sourceRows, options = {}) {
	const layout = useReportColumns({ reportKey, sourceColumns, sourceRows })
	const pickerVisible = ref(false)
	onMounted(layout.loadLayout)

	function formattedCell(column, row) {
		return formatReportCell(column, { [column.fieldname]: options.cellValue ? options.cellValue(row, column, layout.cellValue) : layout.cellValue(row, column) })
	}

	function downloadCsv() {
		const columns = layout.displayColumns.value
		const exportRows = options.exportRows ? options.exportRows() : layout.rows.value
		const lines = [columns.map((column) => column.label), ...exportRows.map((row) => columns.map((column) => options.cellValue ? options.cellValue(row, column, layout.cellValue) : layout.cellValue(row, column)))]
		const csvCell = (value) => '"' + String(value ?? "").replaceAll('"', '""') + '"'
		const url = URL.createObjectURL(new Blob(["\uFEFF", lines.map((line) => line.map(csvCell).join(",")).join("\r\n")], { type: "text/csv;charset=utf-8" }))
		const link = document.createElement("a")
		link.href = url
		link.download = reportKey + ".csv"
		link.click()
		window.setTimeout(() => URL.revokeObjectURL(url), 1000)
	}

	return { ...layout, pickerVisible, formattedCell, downloadCsv }
}
