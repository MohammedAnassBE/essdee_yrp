export function validatePanelWiseMatrix(matrix) {
	if (!matrix) return "Panel-wise consumption matrix is not loaded"

	for (const panel of matrix.panels || []) {
		const packingValues = panel.packing_values || matrix.packing_values || []
		for (const row of panel.rows || []) {
			for (const packing of packingValues) {
				const cell = row.values?.[packing] || {}
				if (!cell.dia) {
					return `Panel matrix: enter Dia for ${panel.panel_value}, ${row.primary_value}, ${packing}`
				}
				if (!(Number(cell.weight) > 0)) {
					return `Panel matrix: enter consumption for ${panel.panel_value}, ${row.primary_value}, ${packing}`
				}
			}
		}
	}

	return null
}
