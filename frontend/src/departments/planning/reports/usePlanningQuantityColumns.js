import { computed } from "vue"
import { cellAlign, normalizeReportColumn } from "../../../composables/reportColumns.js"
import { formatReportCell } from "../../finishing/reports/finishingReports.js"

export function usePlanningQuantityColumns(reportKey, sourceColumns, sourceRows) {
	const columns = computed(() => sourceColumns.value.map(normalizeReportColumn))
	const rows = sourceRows
	return { columns, rows, cellAlign, formattedCell: formatReportCell }
}
