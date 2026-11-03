import assert from "node:assert/strict"
import test from "node:test"
import { previewAdditions, previewAddWeightDrafts } from "../src/engine/lotClothProgram.js"

const preview = {
	tables: [
		{
			cloth_item: "Cloth",
			colours: ["Navy", "Red"],
			fabric_groups: [
				{ fabric_type: "Main Fabric", additions: { Navy: 22, Red: 0 } },
				{ fabric_type: "Folding Fabric", additions: { Navy: 0, Red: -4 } },
			],
		},
	],
}

test("popup Add Weight inputs start from the preview's kg per fabric type and colour", () => {
	assert.deepEqual(previewAddWeightDrafts(preview), {
		"Cloth\u0000Main Fabric\u0000Navy": 22,
		"Cloth\u0000Main Fabric\u0000Red": 0,
		"Cloth\u0000Folding Fabric\u0000Navy": 0,
		"Cloth\u0000Folding Fabric\u0000Red": -4,
	})
})

test("Calculate and Save send every fabric type and colour, keeping negative kg", () => {
	const drafts = { ...previewAddWeightDrafts(preview), "Cloth\u0000Main Fabric\u0000Red": 5 }
	assert.deepEqual(previewAdditions(preview, drafts), [
		{ cloth_item: "Cloth", fabric_type: "Main Fabric", colour: "Navy", additional_weight: 22 },
		{ cloth_item: "Cloth", fabric_type: "Main Fabric", colour: "Red", additional_weight: 5 },
		{ cloth_item: "Cloth", fabric_type: "Folding Fabric", colour: "Navy", additional_weight: 0 },
		{ cloth_item: "Cloth", fabric_type: "Folding Fabric", colour: "Red", additional_weight: -4 },
	])
})

test("a colourless cloth sends an empty colour, not the No Colour label", () => {
	const colourless = { tables: [{ cloth_item: "Rib", colours: ["No Colour"], fabric_groups: [{ fabric_type: "Main Fabric", additions: { "No Colour": 3 } }] }] }
	assert.deepEqual(previewAdditions(colourless, previewAddWeightDrafts(colourless)), [
		{ cloth_item: "Rib", fabric_type: "Main Fabric", colour: "", additional_weight: 3 },
	])
})
