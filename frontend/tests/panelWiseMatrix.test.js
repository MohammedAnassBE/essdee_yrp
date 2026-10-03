import assert from "node:assert/strict"
import test from "node:test"

import { validatePanelWiseMatrix } from "../src/views/ipd/panelWiseMatrix.js"

const completeMatrix = () => ({
	packing_values: ["Black", "Navy"],
	panels: [
		{
			panel_value: "Front With Back",
			rows: [
				{
					primary_value: "75 cm",
					values: {
						Black: { dia: "26 Dia", weight: 0.0535 },
						Navy: { dia: "26 Dia", weight: 0.0535 },
					},
				},
			],
		},
	],
})

test("accepts a completed current-schema panel matrix", () => {
	assert.equal(validatePanelWiseMatrix(completeMatrix()), null)
})

test("validates the Dia stored in each colour cell", () => {
	const matrix = completeMatrix()
	matrix.panels[0].rows[0].values.Navy.dia = null

	assert.equal(
		validatePanelWiseMatrix(matrix),
		"Panel matrix: enter Dia for Front With Back, 75 cm, Navy",
	)
})

test("uses panel-specific colours when provided", () => {
	const matrix = completeMatrix()
	matrix.panels[0].packing_values = ["Black"]
	delete matrix.panels[0].rows[0].values.Navy

	assert.equal(validatePanelWiseMatrix(matrix), null)
})
