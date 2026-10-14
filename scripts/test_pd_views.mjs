#!/usr/bin/env node
import assert from "node:assert/strict"
import { existsSync, readFileSync } from "node:fs"

import {
	LOTWISE_SECTIONS,
	LOTWISE_TABLE_COLUMNS,
	PRODUCT_FIELD_GROUPS,
	addImage,
	appendProductColours,
	cleanFileStem,
	colourOptionsFor,
	colourOptionsFromForm,
	copiedImageGroups,
	copiedProductDraft,
	createDebouncedSearch,
	editableValues,
	hasMinimumQuery,
	imagePayload,
	isFieldReadOnly,
	lotwiseChildMeta,
	mergeComputedValues,
	mergeFilteredSelection,
	moveItem,
	newColourName,
	pdRecordPath,
	productActionItems,
	readableTextColour,
	renumberRows,
	releaseTabs,
	retainColoursForPart,
	rowsMissingTrimDetails,
	toggleAllColours,
	visibleForSetItem,
} from "../frontend/src/departments/pd/pdViews.js"
import { webDocumentPath } from "../frontend/src/router/webDocumentRoutes.js"

assert.equal(pdRecordPath("product", "AW26-05/34324"), "/web/pd/products/AW26-05%2F34324")
assert.equal(pdRecordPath("release", "abc 1"), "/web/pd/product-releases/abc%201")
assert.equal(pdRecordPath("lotwise", "x#1"), "/web/pd/lotwise-item-profits/x%231")
assert.throws(() => pdRecordPath("unknown", "x"))
assert.equal(webDocumentPath("SD YRP Product", "AW26-05/34324"), "/web/pd/products/AW26-05%2F34324")
assert.equal(webDocumentPath("SD YRP Product Release", "r1"), "/web/pd/product-releases/r1")
assert.equal(webDocumentPath("SD YRP Lotwise Item Profit", "c4e7lub90m"), "/web/pd/lotwise-item-profits/c4e7lub90m")
assert.deepEqual(releaseTabs().map((tab) => tab.key).includes("costing"), false)
assert.deepEqual(releaseTabs().map((tab) => tab.key).includes("extras"), false)

const productActions = productActionItems(
	{ can_write: true, can_release: true, can_create: true, can_delete: true },
	{ edit: () => "edit", release: () => "release", duplicate: () => "duplicate", delete: () => "delete" },
	{ busy: true, acting: "release" },
)
assert.deepEqual(productActions.map((action) => action.key), ["edit", "release", "duplicate", "delete"])
assert.equal(productActions.find((action) => action.key === "edit").primary, true)
assert.equal(productActions.find((action) => action.key === "release").loading, true)
assert.equal(productActions.find((action) => action.key === "delete").menuOnly, true)
assert.equal(productActions.find((action) => action.key === "duplicate").menuOnly, true)
assert.equal(productActions.every((action) => action.disabled), true)

assert.equal(readableTextColour("#ffffff"), "#000")
assert.equal(readableTextColour("#000000"), "#fff")
assert.equal(readableTextColour(""), "#000")

assert.deepEqual(moveItem(["a", "b", "c"], 0, 2), ["b", "c", "a"])
assert.deepEqual(moveItem(["a", "b"], 1, 1), ["a", "b"])
assert.equal(cleanFileStem("logo_black-v2.png"), "logo black v2")
assert.equal(cleanFileStem(".png", "Option 1"), "Option 1")

const pickerPaths = [
	"frontend/src/departments/pd/components/ProductImagePicker.vue",
	"frontend/src/departments/pd/components/ProductTrimCombination.vue",
]
for (const path of pickerPaths) {
	const source = readFileSync(path, "utf8")
	for (const removed of ["Upload images", "ProductImageBulkDialog", "queueDroppedFiles", "bulkVisible", "__drop"]) {
		assert.equal(source.includes(removed), false, `${path} still contains ${removed}`)
	}
	assert.match(source, /object-fit:\s*contain/, `${path} must contain image previews`)
}
assert.equal(
	existsSync("frontend/src/departments/pd/components/ProductImageBulkDialog.vue"),
	false,
)
assert.ok(
	readFileSync("frontend/src/departments/pd/components/ProductGraphics.vue", "utf8").includes("Upload images"),
)
assert.equal(
	readFileSync("frontend/src/departments/pd/components/ProductWorkspaceContent.vue", "utf8")
		.includes("Save or cancel your edits to upload images."),
	false,
)
assert.match(
	readFileSync("frontend/src/departments/pd/ProductPage.vue", "utf8"),
	/const canUploadImages = computed\(\(\) => !isNew\.value\s*&& permissions\.value\.can_write/,
)
assert.ok(
	readFileSync("frontend/src/departments/pd/ProductPage.vue", "utf8")
		.includes('@edit-requested="startMediaEditing"'),
)
assert.match(
	readFileSync("frontend/src/departments/pd/ProductPage.vue", "utf8"),
	/allowNavigation = target !== route\.path/,
)
for (const component of ["ProductSilhouette.vue", "ProductGraphics.vue"]) {
	assert.ok(
		readFileSync(`frontend/src/departments/pd/components/${component}`, "utf8")
			.includes('emit("edit-requested")'),
	)
}
assert.ok(
	readFileSync("frontend/src/departments/pd/components/ProductGraphicsUploadDialog.vue", "utf8")
		.includes("stageProductGraphic"),
)
const releaseSource = readFileSync("frontend/src/departments/pd/ProductReleasePage.vue", "utf8")
for (const component of ["ProductImagePicker", "ProductTrimCombination", "ProductGraphics"]) {
	assert.ok(releaseSource.includes(`<${component}`), `Product Release must reuse ${component}`)
}

const item = { image_name: "btn", image_title: "Button", image_url: "/x.png" }
assert.equal(addImage([item], item, { allowDuplicates: false }).length, 1)
assert.equal(addImage([item], item, { allowDuplicates: true, isSetItem: true }).length, 2)
assert.deepEqual(addImage([], item, { allowDuplicates: true, isSetItem: true })[0].selected_part, "Top")
assert.deepEqual(
	addImage([], item, { allowDuplicates: false, isSetItem: false, withColours: true })[0].selected_colours,
	[],
)

const colours = {
	is_set_item: true,
	top: [{ colour: "Red" }],
	bottom: [{ colour: "Blue" }],
	all: [],
}
assert.deepEqual(colourOptionsFor(colours, "Bottom").map((row) => row.colour), ["Blue"])
assert.deepEqual(colourOptionsFor(colours, "Top").map((row) => row.colour), ["Red"])
assert.deepEqual(
	colourOptionsFor({ is_set_item: false, all: [{ colour: "Green" }] }, "").map((row) => row.colour),
	["Green"],
)

const swappedColours = colourOptionsFromForm(
	{
		is_set_item: 1,
		product_set_colours: [{
			top_colour: "Blue",
			top_colour_code: "#form-blue",
			bottom_colour: "Red",
			bottom_colour_code: "#form-red",
		}],
	},
	{
		is_set_item: true,
		top: [{ colour: "Red", colour_code: "#red", image: "/red.png" }],
		bottom: [{ colour: "Blue", colour_code: "#blue", image: "/blue.png" }],
		all: [],
	},
)
assert.deepEqual(swappedColours.top, [{ colour: "Blue", colour_code: "#blue", image: "/blue.png" }])
assert.deepEqual(swappedColours.bottom, [{ colour: "Red", colour_code: "#red", image: "/red.png" }])
assert.deepEqual(
	retainColoursForPart(
		{ selected_part: "Bottom", selected_colours: ["Red", "Blue"] },
		swappedColours,
	).selected_colours,
	["Red"],
)
assert.deepEqual(
	colourOptionsFromForm(
		{
			is_set_item: 0,
			product_colours: [
				{ product_colour: "Green", colour_code: "#green" },
				{ product_colour: "Green", colour_code: "#duplicate" },
				{ product_colour: "New", colour_code: "#new" },
			],
		},
		{ is_set_item: true, top: [{ colour: "Green", colour_code: "#workspace-green", image: "/green.png" }] },
	).all,
	[
		{ colour: "Green", colour_code: "#workspace-green", image: "/green.png" },
		{ colour: "New", colour_code: "#new", image: "" },
	],
)
assert.deepEqual(
	colourOptionsFromForm(
		{
			is_set_item: 0,
			product_colours: [{ product_colour: "Green", colour_code: "#red" }],
		},
		{ is_set_item: false, all: [{ colour: "Red", colour_code: "#red", image: "/red.png" }] },
	).all,
	[{ colour: "Green", colour_code: "#red", image: "" }],
)

assert.deepEqual(
	Object.keys(imagePayload({ placement: [], trims: [], combination: [], accessories: [] })).sort(),
	["accessory_images", "placement_images", "product_trims_images", "trim_comb"],
)

const mergedLotwiseValues = mergeComputedValues(
	{ gst: 5, total_qty: 1, qty_rate_chart: [{ size: "S", qty: 3, rate: 10, net_rate: 0 }] },
	{ gst: 0, total_qty: 3, qty_rate_chart: [{ size: "S", qty: 3, rate: 10, net_rate: 30 }] },
)
assert.equal(mergedLotwiseValues.gst, 5)
assert.equal(mergedLotwiseValues.total_qty, 3)
assert.equal(mergedLotwiseValues.qty_rate_chart[0].net_rate, 30)
assert.deepEqual(LOTWISE_SECTIONS.header, ["product", "item", "lot", "lot_costing_type", "disabled"])
assert.deepEqual(LOTWISE_SECTIONS.productionCost, [
	"production_cost_template",
	"cmt",
	"packing_materials",
	"trims",
])
const lotwiseTableInputs = {
	qty_rate_chart: ["size", "qty", "rate", "weight", "group_index"],
	cloth_value: [
		"yarn",
		"qty",
		"rate",
		"knitting_cost",
		"dyeing_cost",
		"compacting_cost",
		"wastage_allowance",
	],
	piece_cloth_weight: ["size", "cloth_group", "weight"],
	cmt: ["costing_name", "cost"],
	packing_materials: ["costing_name", "cost"],
	trims: ["costing_name", "cost"],
	trade_discounts: ["costing_name", "based_on", "rate"],
	other_costs: ["costing_name", "based_on", "rate"],
}
for (const [table, inputs] of Object.entries(lotwiseTableInputs)) {
	for (const fieldname of inputs) {
		assert.ok(LOTWISE_TABLE_COLUMNS[table].includes(fieldname), `${table}.${fieldname} must be visible`)
	}
}
const clothMeta = lotwiseChildMeta("cloth_value", {
	fields: LOTWISE_TABLE_COLUMNS.cloth_value.map((fieldname) => ({ fieldname })),
})
assert.deepEqual(clothMeta.fields.map((field) => field.fieldname), LOTWISE_TABLE_COLUMNS.cloth_value)
assert.equal(clothMeta.fields.find((field) => field.fieldname === "wastage_allowance").in_list_view, 1)
assert.equal(clothMeta.fields.find((field) => field.fieldname === "total_cost").read_only, 1)
assert.deepEqual(
	mergeComputedValues(
		{ qty_rate_chart: [{ size: "S", qty: 3, rate: 10, net_rate: 0 }] },
		{ qty_rate_chart: [{ size: "S", qty: 7, rate: 90, net_rate: 630 }] },
	).qty_rate_chart,
	[{ size: "S", qty: 3, rate: 10, net_rate: 630 }],
)
assert.deepEqual(
	mergeComputedValues(
		{ qty_rate_chart: [{ size: "S", qty: 3, rate: 10, net_rate: 0 }] },
		{ qty_rate_chart: [
			{ size: "S", qty: 7, rate: 90, net_rate: 630 },
			{ size: "M", qty: 1, rate: 20, net_rate: 20 },
		] },
	).qty_rate_chart,
	[{ size: "S", qty: 3, rate: 10, net_rate: 0 }],
)

assert.equal(hasMinimumQuery("a"), false)
assert.equal(hasMinimumQuery("ab"), true)

assert.deepEqual(
	rowsMissingTrimDetails([
		{ image_title: "A", selected_part: "Top", selected_colours: [] },
		{ image_title: "B", selected_part: "Top", selected_colours: ["Red"] },
	], true),
	["A"],
)
assert.deepEqual(rowsMissingTrimDetails([{ image_title: "A", selected_colours: [] }], false), [])
assert.deepEqual(
	toggleAllColours(
		{ selected_colours: ["Red"] },
		[{ colour: "Red" }, { colour: "Blue" }],
	).selected_colours,
	["Red", "Blue"],
)
assert.deepEqual(
	toggleAllColours(
		{ selected_colours: ["Red", "Blue"] },
		[{ colour: "Red" }, { colour: "Blue" }],
	).selected_colours,
	[],
)
assert.deepEqual(
	retainColoursForPart(
		{ selected_part: "Bottom", selected_colours: ["Red", "Blue"] },
		{ is_set_item: true, top: [{ colour: "Red" }], bottom: [{ colour: "Blue" }] },
	).selected_colours,
	["Blue"],
)

assert.equal(visibleForSetItem("product_set_colours", false), false)
assert.equal(visibleForSetItem("measurement", false), true)
assert.equal(visibleForSetItem("item_name", true), true)
assert.equal(isFieldReadOnly("style_no", false), true)
assert.equal(isFieldReadOnly("style_no", true), false)
assert.equal(isFieldReadOnly("item_name", false), false)
assert.deepEqual(
	Object.keys(editableValues({ item_name: "A", tech_pack_no: 4, sizes: [] })).sort(),
	["item_name", "sizes"],
)
assert.deepEqual(
	editableValues({ sizes: [{ name: "row-1", attribute_value: "IAV-1", size: "60 cm" }] }).sizes,
	[{ name: "row-1", attribute_value: "IAV-1" }],
)
assert.deepEqual(
	editableValues({
		product_image: "/private/files/silhouette.png",
		product_designs: [{ upload_name: "Option 5", graphic_image: "/private/files/graphic.png" }],
		product_box_details: [{ upload_name: "Box 2", graphic_image: "/private/files/box.png" }],
	}),
	{
		product_image: "/private/files/silhouette.png",
		product_designs: [{ upload_name: "Option 5", graphic_image: "/private/files/graphic.png" }],
		product_box_details: [{ upload_name: "Box 2", graphic_image: "/private/files/box.png" }],
	},
)
assert.deepEqual(
	appendProductColours(
		[{ product_colour: "Black", colour_code: "#000000" }],
		[{ name: "Black", colour: "Black", colour_code: "#000000", image: "/black.png" }],
	),
	[
		{ product_colour: "Black", colour_code: "#000000", idx: 1 },
		{ product_colour: "Black", colour_code: "#000000", image: "/black.png", idx: 2 },
	],
)
const savedColours = [
	{ name: "colour-1", product_colour: "Red", idx: 1 },
	{ name: "colour-2", product_colour: "Blue", idx: 2 },
	{ name: "colour-3", product_colour: "Green", idx: 3 },
	{ name: "colour-4", product_colour: "Black", idx: 4 },
]
const coloursAfterRemoval = renumberRows(savedColours.filter((_row, index) => index > 1))
assert.deepEqual(coloursAfterRemoval, [
	{ name: "colour-3", product_colour: "Green", idx: 1 },
	{ name: "colour-4", product_colour: "Black", idx: 2 },
])
assert.deepEqual(
	appendProductColours(coloursAfterRemoval, [{ name: "White", colour_code: "#ffffff" }]),
	[
		{ name: "colour-3", product_colour: "Green", idx: 1 },
		{ name: "colour-4", product_colour: "Black", idx: 2 },
		{ product_colour: "White", colour_code: "#ffffff", image: "", idx: 3 },
	],
)
const redOption = { name: "red", colour: "Red" }
const blueOption = { name: "blue", colour: "Blue" }
assert.deepEqual(
	mergeFilteredSelection([redOption], [blueOption], [blueOption]),
	[redOption, blueOption],
)
assert.deepEqual(
	mergeFilteredSelection([redOption, blueOption], [redOption], [blueOption]),
	[redOption],
)
assert.equal(newColourName("  orange ", { searchSucceeded: true }), "orange")
assert.equal(newColourName("orange", { searchSucceeded: false }), "")
assert.equal(newColourName("orange", { searchSucceeded: true, exactNameExists: true }), "")
assert.equal(newColourName("   ", { searchSucceeded: true }), "")

const oldSearch = deferred()
const currentSearch = deferred()
const cancelledSearch = deferred()
const failedSearch = deferred()
const searchResponses = new Map([
	["old", oldSearch],
	["current", currentSearch],
	["cancelled", cancelledSearch],
	["failed", failedSearch],
])
const requestedSearches = []
const appliedSearches = []
const searchErrors = []
const scheduledSearches = []
let settledSearches = 0
const colourSearch = createDebouncedSearch(
	(query) => {
		requestedSearches.push(query)
		return searchResponses.get(query).promise
	},
	{
		onResult: (result) => appliedSearches.push(result),
		onError: (reason) => searchErrors.push(reason.message),
		onSettled: () => { settledSearches += 1 },
	},
	{
		schedule(callback, delay) {
			const timer = { callback, cancelled: false, delay }
			scheduledSearches.push(timer)
			return timer
		},
		cancel(timer) { timer.cancelled = true },
	},
)

const oldLoad = colourSearch.load("old")
colourSearch.queue("current")
oldSearch.resolve("stale result")
await oldLoad
assert.deepEqual(appliedSearches, [])
assert.equal(settledSearches, 0)
assert.equal(scheduledSearches[0].delay, 250)
scheduledSearches[0].callback()
currentSearch.resolve("current result")
await nextTask()
assert.deepEqual(requestedSearches, ["old", "current"])
assert.deepEqual(appliedSearches, ["current result"])
assert.equal(settledSearches, 1)

colourSearch.queue("queued then cancelled")
const queuedTimer = scheduledSearches.at(-1)
colourSearch.invalidate()
assert.equal(queuedTimer.cancelled, true)

const cancelledLoad = colourSearch.load("cancelled")
colourSearch.invalidate()
cancelledSearch.resolve("must not overwrite a created colour")
await cancelledLoad
assert.deepEqual(appliedSearches, ["current result"])
assert.equal(settledSearches, 1)

const failedLoad = colourSearch.load("failed")
failedSearch.reject(new Error("search failed"))
await failedLoad
assert.deepEqual(searchErrors, ["search failed"])
assert.equal(settledSearches, 2)

assert.deepEqual(PRODUCT_FIELD_GROUPS.basic.map((group) => group.label), [
	"Style", "Fabric", "Sizes", "Production setup",
])
assert.equal(PRODUCT_FIELD_GROUPS.basic.flatMap((group) => group.fields).includes("tech_pack_no"), false)
const copiedDraft = copiedProductDraft(
	{ item_name: "New default", product_image: "/new.png" },
	{
		style_no: "OLD-1",
		item_name: "Source",
		product_image: "/source.png",
		sizes: [{ name: "size-row", parent: "SOURCE", attribute_value: "IAV-1", size: "60 cm" }],
		product_colours: [{ name: "colour-row", product_colour: "Black" }],
	},
)
assert.equal(copiedDraft.style_no, "")
assert.equal(copiedDraft.item_name, "Source")
assert.equal(copiedDraft.product_image, "/new.png")
assert.deepEqual(copiedDraft.sizes, [{ attribute_value: "IAV-1", size: "60 cm", idx: 1 }])
assert.deepEqual(copiedDraft.product_colours, [{ product_colour: "Black", idx: 1 }])
assert.deepEqual(
	copiedImageGroups({ placement: [item], trims: [], combination: [item], accessories: [] }),
	{ placement: [item], trims: [], combination: [item], accessories: [] },
)

function deferred() {
	let resolve
	let reject
	const promise = new Promise((resolvePromise, rejectPromise) => {
		resolve = resolvePromise
		reject = rejectPromise
	})
	return { promise, resolve, reject }
}

function nextTask() {
	return new Promise((resolve) => setImmediate(resolve))
}

console.log("pd views ok")
