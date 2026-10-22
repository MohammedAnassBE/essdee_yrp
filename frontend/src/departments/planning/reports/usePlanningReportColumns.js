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

	return { ...layout, pickerVisible, formattedCell }
}
