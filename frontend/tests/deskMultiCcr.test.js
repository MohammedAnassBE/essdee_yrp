import assert from "node:assert/strict"
import { readFileSync } from "node:fs"
import test from "node:test"
import { Vue, findNodes, loadComponent, mountComponent } from "../../scripts/helpers/vue_renderer.mjs"

const completed = {
	attributes: ["Colour"],
	primary_attribute_values: ["S", "M"],
	total_qty: { S: 60, M: 40 },
	is_set_item: 0,
	stiching_attr: "Panel",
	Panel: ["Front", "Back"],
	items: [{ attributes: { Colour: "Red" }, item_keys: { major_colour: "Red" }, values: { S: 60, M: 40 }, total_qty: 100 }],
}
const cloth = [{ cloth_item_variant: "Jersey-Red", cloth_type: "Jersey", colour: "Red", dia: "30", required_weight: 16, weight: 20, used_weight: 15, balance_weight: 5 }]
const clothTotal = { required: 16, received: 20, used: 15, balance: 5 }
const report = {
	output_lots: ["LOT-1"],
	output_items: ["Tee"],
	data: {
		"LOT-1": {
			item: "Tee", version: "V3", total_qty: 100, completed_json: [completed], cloth_details: cloth, cloth_total: clothTotal,
			panel_groups: [{
				cutting_plan: "CP-1", panels: "Back, Front", sizes: ["S", "M"],
				rows: [{ colour: "Red", cloth_type: "Jersey", received_weight: 20, used_weight: 15, balance_weight: 5, sizes: { S: 60, M: 40 }, total_pieces: 100, piece_weight: 0.15, required_weight: 0.16 }],
				totals: { received_weight: 20, used_weight: 15, balance_weight: 5, sizes: { S: 60, M: 40 }, total_pieces: 100, piece_weight: 0.15, required_weight: 0.16 },
			}],
			recut_summary: { rows: [{ cloth_type: "Jersey", colour: "Red", dia: "30", shade: "A", weight: 1.25, no_of_rolls: 2 }], totals: { weight: 1.25, no_of_rolls: 2 } },
		},
	},
	item_data: {
		Tee: {
			total_qty: 100, completed_json: [completed], cloth_details: cloth, cloth_total: clothTotal,
			average_piece_weight_by_colour: { Red: 0.15 }, average_required_weight_by_colour: { Red: 0.16 },
		},
	},
}

function installDeskGlobals() {
	const control = (value) => ({ get_value: () => value, set_value() {} })
	const values = { lot: ["LOT-1"], item: [], lot_status: "", product_category: "" }
	globalThis.$ = () => ({ find: () => ({ html() {} }) })
	globalThis.essdee_yrp = { get_colour_attribute: () => "Colour" }
	globalThis.frappe = {
		ui: { form: { make_control: ({ df }) => control(values[df.fieldname]) } },
		msgprint() {},
		call: ({ callback }) => callback({ message: report }),
	}
}

const text = (root) => findNodes(root, (node) => typeof node.text === "string" && node.text).map((node) => node.text.trim()).filter(Boolean)

test("Desk Multi CCR shows the per-plan CCR panel groups, recut summary and style-wise averages like production_api", async () => {
	installDeskGlobals()
	const component = loadComponent(new URL("../../essdee_yrp/public/js/CuttingPlan/components/MultiCCR.vue", import.meta.url).pathname, {
		"../../components/MultiSelectListConverter.vue": () => null,
	})
	const root = mountComponent(component)
	const button = findNodes(root, (node) => node.type === "button" && text(node).includes("Show Report"))[0]
	button.props.onClick()
	await Vue.nextTick()
	const rendered = text(root)

	for (const heading of ["Back, Front", "Piece Weight", "Required Weight", "Recut Summary", "Average Piece Weight", "Average Reqd Weight"]) {
		assert.ok(rendered.includes(heading), `missing ${heading}`)
	}
	assert.ok(rendered.includes("0.1500"), "piece weight 15 kg / 100 pieces")
	assert.ok(rendered.includes("0.1600"), "required piece weight")
	assert.ok(rendered.includes("1.250"), "recut weight")
	assert.ok(!rendered.includes("NaN"), "missing weights must not render NaN")
})

test("web Multi CCR picks the product category from SD YRP Product Category, the doctype Item links to", () => {
	const page = readFileSync(new URL("../src/departments/cutting/reports/MultiCCRReport.vue", import.meta.url), "utf8")
	assert.match(page, /<LinkField v-model="filters\.category" doctype="SD YRP Product Category"/)
})
