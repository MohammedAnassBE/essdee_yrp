import assert from "node:assert/strict"
import { readFileSync, readdirSync } from "node:fs"
import { createRequire } from "node:module"
import {
	MERCH_ROUTES,
	merchLauncherItems,
	visibleMerchLauncherItems,
} from "../frontend/src/departments/merch/merchViews.js"
import {
	MERCH_DETAIL_GROUPS,
	MERCH_LOT_TABS,
	applyBoxGrid,
	boxCellError,
	boxGrid,
	boxGridErrors,
	isBoxLocked,
	merchLotActions,
	totalsWarning,
} from "../frontend/src/departments/merch/lot/merchLotViews.js"
import {
	buildSelection,
	clothErrors,
	clothSelection,
} from "../frontend/src/departments/merch/lot/clothProgram.js"
import {
	clearedLotContext,
	clone,
	lotEditorCleanSignature,
	lotEditorTabs,
	lotSavePayload,
} from "../frontend/src/departments/purchase/lot/lotEditor.js"
import { webDocumentPath } from "../frontend/src/router/webDocumentRoutes.js"
import { applyBlock, fillRight } from "../frontend/src/components/common/entryGrid.js"
import { formatLotDate } from "../frontend/src/departments/purchase/lot/lotViews.js"

assert.equal(merchLauncherItems()[0].key, "lots")
assert.deepEqual(visibleMerchLauncherItems({ lots: { can_read: true } }), [merchLauncherItems()[0]])
assert.deepEqual(visibleMerchLauncherItems({ lots: { can_create: true } }), [])
assert.equal(merchLauncherItems()[0].to, "/merch/lots")
assert.deepEqual(
	[MERCH_ROUTES.lots, MERCH_ROUTES.lotNew, MERCH_ROUTES.lot, MERCH_ROUTES.lotEdit],
	["merch-lots", "merch-lot-new", "merch-lot", "merch-lot-edit"],
)
assert.deepEqual(
	MERCH_LOT_TABS.map((tab) => tab.label),
	[
		"Details",
		"Order Items",
		"Lot Order Details",
		"Cloth Program",
		"PPO",
		"BOM Summary",
		"OCR Detail",
	],
)
assert.deepEqual(
	lotEditorTabs({}, [], true).map((tab) => tab.key),
	["details"],
)
assert.deepEqual(
	lotEditorTabs({ item: "Item", production_detail: "IPD" }, [], true).map((tab) => tab.key),
	["details", "order-items"],
)
for (const field of [
	"expected_delivery_date",
	"packing_combo",
	"tech_pack_version",
	"pattern_version",
])
	assert.ok(MERCH_DETAIL_GROUPS.some((group) => group.fields.includes(field)))

const canWrite = {
	capabilities: {
		edit: { allowed: true, visible: true, label: "Edit" },
		calculate_bom: {
			allowed: false,
			visible: true,
			label: "Calculate BOM",
			reason: "Run Calculate Order Items first.",
		},
		change_ppo: { allowed: false, visible: false, label: "Change PPO" },
	},
}
const commands = []
const actions = merchLotActions(canWrite, (command) => commands.push(command))
assert.deepEqual(
	actions.map((action) => action.key),
	["edit", "calculate_bom"],
)
assert.equal(actions[1].disabled, true)
assert.equal(actions[1].disabledReason, "Run Calculate Order Items first.")
actions[0].command()
assert.deepEqual(commands, ["edit"])
assert.equal(merchLotActions(canWrite, () => {}, "saving")[0].disabled, true)
assert.deepEqual(
	merchLotActions({ permissions: { can_write: false } }, () => {}),
	[],
)

assert.equal(isBoxLocked({}, "", true), false)
assert.equal(isBoxLocked({}, "PPO", false), false)
assert.equal(isBoxLocked({}, "PPO", true), true)
assert.equal(isBoxLocked({ order_details: true }, "", false), true)
const details = {
	item: "Item",
	primary_attribute: "Size",
	primary_attribute_values: ["S", "M"],
	items: [
		{
			attributes: { Colour: "Assorted" },
			values: { S: { qty: 1, ratio: 2, mrp: 10 }, M: { qty: 2, ratio: 3, mrp: 20 } },
		},
	],
}
const grid = boxGrid(details)
assert.deepEqual(
	grid.columns.map((column) => column.label),
	["S · Qty", "S · Ratio", "S · MRP", "M · Qty", "M · Ratio", "M · MRP", "Total Qty"],
)
assert.deepEqual(grid.values[0], {
	"0:qty": 1,
	"0:ratio": 2,
	"0:mrp": 10,
	"1:qty": 2,
	"1:ratio": 3,
	"1:mrp": 20,
	total: 3,
})
const changed = applyBoxGrid(details, { 0: { ...grid.values[0], "0:qty": 4, "1:mrp": 30 } })
assert.equal(changed.items[0].values.S.qty, 4)
assert.equal(changed.items[0].values.M.mrp, 30)
assert.equal(details.items[0].values.S.qty, 1)
assert.deepEqual(changed.items[0].attributes, details.items[0].attributes)
assert.deepEqual(boxGridErrors(details), {})
assert.deepEqual(boxGridErrors(null), {})
for (const [field, label] of Object.entries({ qty: "Qty", ratio: "Ratio", mrp: "MRP" })) {
	const pasted = applyBlock(
		grid.values,
		grid.rows,
		grid.columns,
		{ row: 0, col: grid.columns.findIndex((column) => column.key === `0:${field}`) },
		[["-10"]],
	)
	assert.deepEqual(pasted.invalid, [], "keep the negative input visible")
	const negative = applyBoxGrid(details, pasted.model)
	assert.equal(negative.items[0].values.S[field], -10, "never clamp negative input")
	assert.deepEqual(boxGridErrors(negative), {
		0: { [`0:${field}`]: `${label} cannot be negative.` },
	})
	assert.equal(boxCellError(field, 0), "")
	assert.equal(boxCellError(field, 10), "")
	assert.equal(boxCellError(field, "-1"), `${label} cannot be negative.`)
}
const negativePrefill = {
	...details,
	items: [{ attributes: {}, values: { S: { qty: -10 }, M: { qty: -100, ratio: -2, mrp: -3 } } }],
}
assert.deepEqual(boxGridErrors(negativePrefill), {
	0: {
		"0:qty": "Qty cannot be negative.",
		"1:qty": "Qty cannot be negative.",
		"1:ratio": "Ratio cannot be negative.",
		"1:mrp": "MRP cannot be negative.",
	},
})
const negativeGrid = boxGrid(negativePrefill)
const filled = fillRight(negativeGrid.values, negativeGrid.rows, negativeGrid.columns, {
	top: 0,
	bottom: 0,
	left: 0,
	right: 2,
})
assert.equal(Object.keys(boxGridErrors(applyBoxGrid(negativePrefill, filled.model))[0]).length, 6)
const plainNegative = {
	primary_attribute: null,
	items: [{ attributes: {}, values: { qty: -950, ratio: -1, mrp: -1 } }],
}
assert.deepEqual(boxGridErrors(plainNegative), {
	0: {
		"0:qty": "Qty cannot be negative.",
		"0:ratio": "Ratio cannot be negative.",
		"0:mrp": "MRP cannot be negative.",
	},
})
assert.equal(formatLotDate("2026-12-01"), "01-12-2026")
assert.equal(formatLotDate(null), "—")
const groups = [{ items: [{ attributes: {}, values: { S: { qty: 10 }, M: { qty: 20 } } }] }]
assert.equal(totalsWarning(details, groups, 10), "")
groups[0].items[0].values.S.qty = 9
assert.match(totalsWarning(details, groups, 10), /29 pieces.*30.*still save/)
groups[0].items.push({
	is_set_item: true,
	set_attr: "Part",
	major_attr_value: "Top",
	attributes: { Part: "Bottom" },
	values: { S: { qty: 900 } },
})
assert.match(totalsWarning(details, groups, 10), /29 pieces/)
const payload = lotSavePayload({ lot_name: "ZZ", lot_fabric_details: [] }, changed, groups)
assert.deepEqual(payload.item_details, [changed])
assert.deepEqual(payload.order_item_details, groups)

const cloth = clothSelection(
	{
		cloth_item: "Jersey",
		item_yarns: [{ yarn_item: "Yarn", ratio: 100 }],
		required_colours: ["Olive", "Navy"],
		required_routes: [
			{ dia: "30", colour: "Olive" },
			{ dia: "30", colour: "Navy" },
		],
		profile: {
			fabric_routes: [{ finished_colour: "Olive", finished_dia: "30", knitting_output_dia: "36" }],
		},
	},
	{
		knitting_process: "Knitting",
		dyeing_process: "Dyeing",
		compacting_process: "Compacting",
		knitting_output_colour: "Greige",
	},
)
assert.deepEqual(clothErrors(cloth), {})
const selection = buildSelection(cloth)
assert.equal(clothSelection({}).cloth_per_kg_yarn, 1)
assert.equal(clothSelection({}).compacting_process, null)
assert.equal(
	clothSelection({ profile: { knitting_process: "Stored" } }, { knitting_process: "Default" })
		.knitting_process,
	"Stored",
)
assert.equal(
	clothSelection({ profile: { cloth_per_kg_yarn: 0 } }, { cloth_per_kg_yarn: 2 }).cloth_per_kg_yarn,
	2,
)
assert.equal(selection.fabric_routes[0].knitting_output_dia, "36", "stored Dia change survives")
assert.equal(selection.fabric_routes[1].knitting_output_dia, "30")
assert.equal(selection.fabric_routes[0].knitting_output_colour, "Greige")
cloth.dyed_yarn_colours.push("Olive")
cloth.same_finished_colours.push("Navy")
assert.equal(buildSelection(cloth).fabric_routes[0].use_dyed_yarn, 1)
assert.equal(buildSelection(cloth).fabric_routes[0].knitting_output_colour, "Olive")
assert.equal(buildSelection(cloth).fabric_routes[1].knitting_output_colour, "Navy")
assert.deepEqual(
	clothErrors({ ...cloth, dyeing_process: "" }),
	{},
	"same and dyed colours need no dyeing",
)
assert.ok(clothErrors({ ...cloth, cloth_per_kg_yarn: 0 }).cloth_per_kg_yarn)
assert.ok(clothErrors({ ...cloth, knitting_process: "" }).knitting_process)
assert.ok(clothErrors({ ...cloth, item_yarns: [{ yarn_item: "Yarn", ratio: 99 }] }).item_yarns)
assert.ok(
	clothErrors({ ...cloth, dyed_yarn_colours: [], same_finished_colours: [], dyeing_process: "" })
		.dyeing_process,
)
assert.ok(clothErrors({ ...cloth, compacting_process: "" }).routes)

assert.equal(webDocumentPath("SD YRP Lot", "A/B", "/web/sales"), "/web/purchase/lots/A%2FB")
assert.equal(webDocumentPath("SD YRP Lot", "A/B", "/web/merch/lots"), "/web/merch/lots/A%2FB")
assert.equal(
	webDocumentPath("YRP Work Order", "WO-1", "/web/merch/lots/ZZ"),
	"/web/merch/work-orders/WO-1",
)
const router = readFileSync(new URL("../frontend/src/router/index.js", import.meta.url), "utf8")
assert.ok(router.indexOf('path: "/merch/lots/new"') < router.indexOf('path: "/merch/lots/:lotId"'))

const require = createRequire(new URL("../frontend/package.json", import.meta.url))
const { parse, compileScript, compileTemplate } = require("@vue/compiler-sfc")
const directory = new URL("../frontend/src/departments/merch/lot/", import.meta.url)
const source = (filename) => readFileSync(new URL(filename, directory), "utf8")
assert.match(source("MerchLotPage.vue"), /No cloth program yet\./)
assert.ok(
	/actions.filter\(\s*\(action\) => action.key === 'build_cloth_programs',?\s*\)/.test(
		source("MerchLotPage.vue"),
	),
	"empty state uses the Build capability action",
)
assert.match(source("MerchLotPpoPanel.vue"), /formatLotDate\(ppo.delivery_date\)/)
assert.match(source("MerchBoxQuantityEditor.vue"), /:errors="errors"/)
assert.match(source("MerchBoxQuantityEditor.vue"), /content: attr\(title\)/)
assert.match(source("useMerchLotEditor.js"), /boxGridErrors\(itemDetails.value\)/)
assert.match(source("MerchLotEditorDetails.vue"), /Cloth Excess Percentage/)
assert.doesNotMatch(source("MerchLotBomTab.vue"), /<h2>BOM Additional Items<\/h2>/)

const { computed, reactive, ref } = require("vue")
const editorCode = source("useMerchLotEditor.js")
	.replace(/^import[\s\S]*?from "[^"]+"\n/gm, "")
	.replace("export function", "function")
for (const lotId of [null, "ZZ LOT"]) {
	for (const field of ["qty", "ratio", "mrp"]) {
		const calls = []
		const route = reactive({ query: { tab: "details" } })
		const negative = structuredClone(negativePrefill)
		negative.items[0].values.S[field] = -10
		const dependencies = {
			computed,
			reactive,
			ref,
			onBeforeUnmount: () => {},
			useRoute: () => route,
			useRouter: () => ({
				replace: async (target) => {
					route.query = target.query || {}
					calls.push(target)
				},
			}),
			useToast: () => ({ add: () => {} }),
			getMeta: async () => [{ name: "SD YRP Lot Fabric Detail" }],
			getLotForm: async () => ({
				record: { name: lotId, modified: lotId ? "current" : null },
				values: { lot_fabric_details: [] },
				derived: {},
				fields: [],
				locks: {},
				item_details: negative,
				order_item_details: [],
				item_details_generated: true,
			}),
			saveLot: async (values, options) => {
				calls.push({ values, options })
				return { name: lotId || "Created Lot", modified: "saved" }
			},
			preserveListNavigationState: () => ({}),
			MERCH_ROUTES,
			clearedLotContext,
			clone,
			lotEditorCleanSignature,
			lotEditorTabs,
			lotSavePayload,
			boxGridErrors,
		}
		const useEditor = new Function(
			...Object.keys(dependencies),
			`${editorCode}\nreturn useMerchLotEditor`,
		)(...Object.values(dependencies))
		const state = useEditor(lotId)
		await new Promise(setImmediate)
		await state.editorActions.value.find((action) => action.key === "save").command()
		assert.equal(
			calls.some((call) => call.values),
			false,
			"negative PPO prefill blocks Create and Save from the Details tab",
		)
		assert.equal(route.query.tab, "order-items")
		assert.match(state.actionError.value, /Qty, Ratio and MRP cannot be negative/)
		assert.equal(
			state.itemDetails.value.items[0].values.S[field],
			-10,
			"validation preserves the negative value",
		)
		state.itemDetails.value = structuredClone(details)
		await state.editorActions.value.find((action) => action.key === "save").command()
		const saved = calls.find((call) => call.values)
		assert.deepEqual(saved.values.item_details, [details], "corrected values can save")
		assert.equal(saved.options.name, lotId)
	}
}
for (const filename of readdirSync(directory).filter((name) => name.endsWith(".vue"))) {
	const source = readFileSync(new URL(filename, directory), "utf8")
	assert.ok(!/><[A-Za-z/]/.test(source), `${filename}: put each template element on its own line`)
	const parsed = parse(source, { filename })
	assert.deepEqual(parsed.errors, [], filename)
	const script = compileScript(parsed.descriptor, { id: filename })
	const template = compileTemplate({
		source: parsed.descriptor.template.content,
		filename,
		id: filename,
		compilerOptions: { bindingMetadata: script.bindings },
	})
	assert.deepEqual(template.errors, [], filename)
}
console.log("Merch Lot view, grid, cloth route, navigation and Vue compilation tests passed")
