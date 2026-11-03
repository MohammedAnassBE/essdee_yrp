import assert from "node:assert/strict"
import test from "node:test"
import { addWeightDrafts, serializeAddWeight } from "../src/engine/lotClothProgram.js"

const fabrics = [
	{
		cloth_item: "Cloth",
		program: [
			{ dia: "13 Dia", colour: "Navy", weight: 90, fabric_split: [{ fabric_type: "Main Fabric", weight: 90 }] },
			{ dia: "20 Dia", colour: "Red", weight: 84, fabric_split: [{ fabric_type: "Folding Fabric", weight: 84 }] },
		],
		additions: { "Main Fabric": { Navy: 22 }, "Folding Fabric": { Red: -4 } },
	},
]

test("Add Weight drafts start from the saved kg per fabric type and colour", () => {
	assert.deepEqual(addWeightDrafts(fabrics), {
		"Cloth\u0000Main Fabric\u0000Navy": 22,
		"Cloth\u0000Folding Fabric\u0000Red": -4,
	})
})

test("Calculate sends every fabric type and colour, keeping negative kg", () => {
	const drafts = { ...addWeightDrafts(fabrics), "Cloth\u0000Main Fabric\u0000Navy": 5 }
	assert.deepEqual(serializeAddWeight(fabrics, drafts), [
		{ cloth_item: "Cloth", fabric_type: "Main Fabric", colour: "Navy", additional_weight: 5 },
		{ cloth_item: "Cloth", fabric_type: "Folding Fabric", colour: "Red", additional_weight: -4 },
	])
})
