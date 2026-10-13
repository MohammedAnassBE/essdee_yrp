#!/usr/bin/env node

import { createRequire } from "node:module"
import { readFileSync } from "node:fs"

const require = createRequire("/home/anas/.claude/playwright/package.json")
const { chromium } = require("playwright")
const SITE = process.env.ESSDEE_TEST_SITE || "http://erp-migration-test.site:8001"
const CREDENTIALS = "/home/anas/.frappe-debug-creds-mrp3"
const PRODUCT_WORKSPACE = "essdee_yrp.product_development.web_workspace"
const LOTWISE_WORKSPACE = "essdee_yrp.product_development.lotwise_workspace"
const PRODUCT_METHOD = "essdee_yrp.essdee_yrp.doctype.sd_yrp_product.sd_yrp_product"
const IMAGE_METHOD = "essdee_yrp.essdee_yrp.doctype.sd_yrp_product_image.sd_yrp_product_image"
const LOTWISE_COMMANDS = [
	"recalculate",
	"load_product_sizes",
	"load_item_sizes",
	"add_rate",
	"build_piece_cloth_weight",
	"calculate_cloth_qty",
	"apply_discount_template",
	"apply_other_cost_template",
	"apply_production_cost_template",
	"fetch_lot_qty",
	"calculate_rate",
]

function assert(condition, message) {
	if (!condition) throw new Error(message)
}

function timestamp() {
	return `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`
}

function pdfBuffer() {
	const objects = [
		"<< /Type /Catalog /Pages 2 0 R >>",
		"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
		"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 72 72] /Contents 4 0 R >>",
		"<< /Length 4 >>\nstream\nq\nQ\nendstream",
	]
	let document = "%PDF-1.4\n"
	const offsets = [0]
	for (const [index, object] of objects.entries()) {
		offsets.push(Buffer.byteLength(document))
		document += `${index + 1} 0 obj\n${object}\nendobj\n`
	}
	const crossReference = Buffer.byteLength(document)
	document += `xref\n0 ${objects.length + 1}\n0000000000 65535 f \n`
	document += offsets.slice(1).map((offset) => `${String(offset).padStart(10, "0")} 00000 n \n`).join("")
	document += `trailer\n<< /Size ${objects.length + 1} /Root 1 0 R >>\nstartxref\n${crossReference}\n%%EOF\n`
	return Buffer.from(document)
}

const PNG = Buffer.from(
	"iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII=",
	"base64",
)

class FrappeSession {
	constructor(context, page, csrfToken, user) {
		this.context = context
		this.page = page
		this.csrfToken = csrfToken
		this.user = user
	}

	static async login(browser, user, password) {
		const context = await browser.newContext()
		const login = await context.request.post(`${SITE}/api/method/login`, { form: { usr: user, pwd: password } })
		assert(login.ok(), `Login failed for ${user}: HTTP ${login.status()} ${await login.text()}`)
		const page = await context.newPage()
		await page.goto(`${SITE}/web`, { waitUntil: "domcontentloaded" })
		const csrfToken = await page.evaluate(() => window.csrf_token || window.frappe?.csrf_token || "")
		assert(csrfToken, `No CSRF token was exposed for ${user}`)
		return new FrappeSession(context, page, csrfToken, user)
	}

	async close() {
		await this.context.close()
	}

	async request(method, path, options = {}) {
		return this.context.request[method](`${SITE}${path}`, {
			headers: { "X-Frappe-CSRF-Token": this.csrfToken, ...(options.headers || {}) },
			...options,
		})
	}

	async call(method, args = {}) {
		return this.request("post", `/api/method/${method}`, { data: args })
	}

	async callOk(method, args = {}) {
		const response = await this.call(method, args)
		const body = await response.json().catch(() => ({}))
		assert(response.ok() && !body.exc, `${method} failed for ${this.user}: HTTP ${response.status()} ${JSON.stringify(body)}`)
		return body.message
	}

	async getResource(doctype, query = "") {
		return this.request("get", `/api/resource/${encodeURIComponent(doctype)}${query}`)
	}

	async getUrl(url) {
		return this.context.request.get(url.startsWith("http") ? url : `${SITE}${url}`)
	}

	async createResource(doctype, values) {
		return this.request("post", `/api/resource/${encodeURIComponent(doctype)}`, { data: values })
	}

	async deleteResource(doctype, name) {
		return this.request("delete", `/api/resource/${encodeURIComponent(doctype)}/${encodeURIComponent(name)}`)
	}

	async upload({ buffer, filename, mimeType, doctype, docname, fieldname, method = "", fields = {} }) {
		const multipart = {
			file: { name: filename, mimeType, buffer },
			is_private: "1",
			doctype,
			docname,
			fieldname,
			...(method ? { method } : {}),
			...fields,
		}
		const response = await this.request("post", "/api/method/upload_file", { multipart })
		const body = await response.json().catch(() => ({}))
		assert(response.ok() && !body.exc, `Upload failed for ${this.user}: HTTP ${response.status()} ${JSON.stringify(body)}`)
		return body.message
	}
}

async function resourceRows(session, doctype, { fields = ["name"], filters = [], limit = 500, parent = null } = {}) {
	const query = new URLSearchParams({
		fields: JSON.stringify(fields),
		filters: JSON.stringify(filters),
		limit_page_length: String(limit),
	})
	if (parent) query.set("parent", parent)
	const response = await session.getResource(doctype, `?${query}`)
	const body = await response.json().catch(() => ({}))
	assert(response.ok(), `Could not query ${doctype}: HTTP ${response.status()} ${JSON.stringify(body)}`)
	return body.data || []
}

async function resourceDocument(session, doctype, name) {
	const response = await session.getResource(doctype, `/${encodeURIComponent(name)}`)
	const body = await response.json().catch(() => ({}))
	assert(response.ok(), `Could not read ${doctype} ${name}: HTTP ${response.status()} ${JSON.stringify(body)}`)
	return body.data
}

async function assertResourceAbsent(session, doctype, name, label) {
	const response = await session.getResource(doctype, `/${encodeURIComponent(name)}`)
	const body = await response.json().catch(() => ({}))
	const detail = JSON.stringify(body)
	assert(
		response.status() === 404 || body.exc_type === "DoesNotExistError" || detail.includes("DoesNotExistError"),
		`${label} still exists after deletion: HTTP ${response.status()} ${detail}`,
	)
}

async function resolveAttributeValues(session, values) {
	const linkedNames = [...new Set(values.filter((value) => String(value).startsWith("IAV-")))]
	if (!linkedNames.length) return values
	const rows = await resourceRows(session, "YRP Item Attribute Value", {
		fields: ["name", "attribute_value"],
		filters: [["name", "in", linkedNames]],
		limit: linkedNames.length,
	})
	const byName = Object.fromEntries(rows.map((row) => [row.name, row.attribute_value]))
	for (const name of linkedNames) assert(byName[name], `Could not resolve Item Attribute Value ${name}`)
	return values.map((value) => byName[value] || value)
}

async function createUser(admin, email, password, roles) {
	const response = await admin.createResource("User", {
		email,
		first_name: "PD API Verification",
		enabled: 1,
		send_welcome_email: 0,
		new_password: password,
		roles: roles.map((role) => ({ role })),
	})
	const body = await response.json().catch(() => ({}))
	assert(response.ok(), `Could not create ${email}: HTTP ${response.status()} ${JSON.stringify(body)}`)
}

function permissionFailure(response, body) {
	const text = JSON.stringify(body)
	return response.status() === 403
		|| body.exc_type === "PermissionError"
		|| text.includes("PermissionError")
		|| text.includes("Not permitted")
}

async function expectDenied(label, response) {
	const body = await response.json().catch(() => ({}))
	assert(permissionFailure(response, body), `${label} did not reject access: HTTP ${response.status()} ${JSON.stringify(body)}`)
}

async function expectMethodDenied(session, label, method, args) {
	await expectDenied(label, await session.call(method, args))
}

async function createProduct(session, name, group, sizeRange, sizes) {
	return session.callOk(`${PRODUCT_WORKSPACE}.save_product`, {
		values: {
			style_no: name,
			item_name: "PD API Verification",
			product_group: group,
			description: "Throwaway Product created by verify_pd_api.mjs",
			fabric_details: "Cotton",
			is_set_item: 0,
			size_range: sizeRange,
			sizes,
		},
		images: {},
	})
}

function lotwiseValues(product, lot) {
	return {
		product,
		lot,
		lot_costing_type: "Costing",
		gst: 0,
		additional_rate: 0,
		qty_rate_chart: [{ size: "PD-E2E", qty: 2, rate: 10, weight: 100, group_index: 1 }],
		cloth_value: [],
		piece_cloth_weight: [],
		cmt: [],
		packing_materials: [],
		trims: [],
		trade_discounts: [],
		other_costs: [],
	}
}

async function testWorkspaceEndpoints(session, state) {
	const capabilities = await session.callOk(`${PRODUCT_WORKSPACE}.get_capabilities`)
	assert(capabilities.sections.products.can_read, "PD role cannot read the Products workspace")
	await session.callOk(`${PRODUCT_WORKSPACE}.get_new_product_defaults`)
	const sizes = await session.callOk(`${PRODUCT_WORKSPACE}.get_size_range_sizes`, {
		size_range: state.sizeRange,
	})
	assert(Array.isArray(sizes) && sizes.length, `Size Range ${state.sizeRange} has no sizes`)
	const workspace = await createProduct(
		session,
		state.productName,
		state.productGroup,
		state.sizeRange,
		sizes,
	)
	state.productModified = workspace.modified
	state.productSizeLinks = workspace.record.sizes.map((row) => row.attribute_value)
	assert(workspace.record.name === state.productName, "save_product returned the wrong Product")
	await session.callOk(`${PRODUCT_WORKSPACE}.get_product_workspace`, { name: state.productName })
	const updated = await session.callOk(`${PRODUCT_WORKSPACE}.save_product`, {
		values: { ...workspace.record, item_name: "PD API Verification Updated" },
		images: workspace.images,
		name: state.productName,
		expected_modified: workspace.modified,
	})
	state.productModified = updated.modified
	console.log("OK api-workspace: capabilities, Product defaults/read/create/update and size range")
}

async function testImageEndpoints(session, state) {
	const created = await session.callOk(`${IMAGE_METHOD}.create_product_image`, {
		image_title: state.imageName,
		title_header: "PD E2E API Image",
	})
	state.imageName = created.name
	const rows = await session.callOk(`${IMAGE_METHOD}.get_image_list`, { query: state.imageName })
	assert(rows.some((row) => row.image_name === state.imageName), "Created Product Image was not searchable")
	const uploaded = await session.upload({
		buffer: PNG,
		filename: "pd-api-image.png",
		mimeType: "image/png",
		doctype: "SD YRP Product Image",
		docname: state.imageName,
		fieldname: "image",
	})
	await session.callOk(`${PRODUCT_METHOD}.delete_and_update_file`, {
		file_url: null,
		fieldname: "image",
		doctype: "SD YRP Product Image",
		docname: state.imageName,
		updated_url: uploaded.file_url,
		file_name: uploaded.name,
	})
	console.log("OK api-images: create, search, upload and attachment replacement")
}

async function testProductMediaEndpoints(session, state) {
	const silhouette = await session.upload({
		buffer: PNG,
		filename: "pd-api-silhouette.png",
		mimeType: "image/png",
		doctype: "SD YRP Product",
		docname: state.productName,
		fieldname: "product_image",
	})
	await session.callOk(`${PRODUCT_METHOD}.delete_and_update_file`, {
		file_url: null,
		fieldname: "product_image",
		doctype: "SD YRP Product",
		docname: state.productName,
		updated_url: silhouette.file_url,
		file_name: silhouette.name,
	})
	const singlePagePdf = await session.upload({
		buffer: pdfBuffer(),
		filename: "pd-api-silhouette.pdf",
		mimeType: "application/pdf",
		doctype: "SD YRP Product",
		docname: state.productName,
		fieldname: "product_image",
	})
	await session.callOk(`${PRODUCT_METHOD}.process_single_page_pdf`, {
		file_url: singlePagePdf.file_url,
		doctype: "SD YRP Product",
		docname: state.productName,
		fieldname: "product_image",
	})
	let workspace = await session.callOk(`${PRODUCT_WORKSPACE}.get_product_workspace`, { name: state.productName })
	const convertedUrl = workspace.record.product_image
	assert(convertedUrl, "Silhouette PDF conversion did not persist an image URL")
	assert(convertedUrl !== silhouette.file_url, "Silhouette PDF conversion retained the preceding PNG URL")
	assert(convertedUrl !== singlePagePdf.file_url, "Silhouette PDF conversion persisted the PDF URL")
	const convertedImage = await session.getUrl(convertedUrl)
	assert(convertedImage.ok(), `Converted silhouette did not load: HTTP ${convertedImage.status()}`)
	assert(
		String(convertedImage.headers()["content-type"] || "").startsWith("image/"),
		`Converted silhouette is not an image: ${convertedImage.headers()["content-type"] || "missing type"}`,
	)
	const graphic = await session.upload({
		buffer: PNG,
		filename: "pd-api-graphic.png",
		mimeType: "image/png",
		doctype: "SD YRP Product",
		docname: state.productName,
		fieldname: "product_designs",
		method: `${PRODUCT_METHOD}.upload_graphics_file`,
		fields: { upload_type: "PD API Graphic" },
	})
	assert(graphic.file_url, "upload_graphics_file returned no file URL")
	workspace = await session.callOk(`${PRODUCT_WORKSPACE}.get_product_workspace`, { name: state.productName })
	const graphicRow = workspace.record.product_designs.find((row) => row.upload_name === "PD API Graphic")
	assert(graphicRow, "upload_graphics_file did not append a graphics row")
	await session.callOk(`${PRODUCT_METHOD}.remove_graphic_image`, {
		detail: { name: graphicRow.name },
		docname: state.productName,
	})
	const graphicsPdf = await session.upload({
		buffer: pdfBuffer(),
		filename: "pd-api-graphics.pdf",
		mimeType: "application/pdf",
		doctype: "SD YRP Product",
		docname: state.productName,
		fieldname: "product_designs",
	})
	await session.callOk(`${PRODUCT_METHOD}.process_pdf_to_images`, {
		file_url: graphicsPdf.file_url,
		docname: state.productName,
		table_name: "product_designs",
	})
	workspace = await session.callOk(`${PRODUCT_WORKSPACE}.get_product_workspace`, { name: state.productName })
	for (const row of workspace.record.product_designs || []) {
		await session.callOk(`${PRODUCT_METHOD}.remove_graphic_image`, {
			detail: { name: row.name },
			docname: state.productName,
		})
	}
	console.log("OK api-product-media: silhouette image/PDF, graphics image/PDF and removal")
}

async function testReleaseEndpoints(session, state) {
	state.releaseName = await session.callOk(`${PRODUCT_METHOD}.release_tech_pack`, { doc_name: state.productName })
	const release = await session.callOk(`${PRODUCT_WORKSPACE}.get_product_release_workspace`, { name: state.releaseName })
	assert(release.product === state.productName, "Released Tech Pack does not point to the throwaway Product")
	console.log("OK api-release: Product-write permission created and read the throwaway Release")
}

async function loadLotQuantityFixture(admin) {
	const rows = await resourceRows(admin, "SD YRP Lot Planned Qty", {
		fields: ["parent", "size", "qty", "cut_qty", "final_qty", "idx"],
		filters: [["parenttype", "=", "SD YRP Lot"]],
		parent: "SD YRP Lot",
		limit: 5000,
	})
	const quantityTypes = [
		{ field: "qty", costingType: "Planned Qty" },
		{ field: "cut_qty", costingType: "Cutting Qty" },
		{ field: "final_qty", costingType: "Final Qty" },
	]
	const selectedType = quantityTypes.find(({ field }) => rows.some((row) => Number(row[field])))
	if (!selectedType) return null
	const selectedParent = rows.find((row) => Number(row[selectedType.field]))?.parent
	const sourceRows = rows.filter((row) => row.parent === selectedParent && row.size && Number(row[selectedType.field]))
	const sizes = await resolveAttributeValues(admin, sourceRows.map((row) => row.size))
	const expected = Object.fromEntries(sourceRows.map((row, index) => [sizes[index], Math.trunc(Number(row[selectedType.field]))]))
	return {
		name: selectedParent,
		costingType: selectedType.costingType,
		quantities: Object.entries(expected).map(([size, qty]) => ({ size, qty })),
		expected,
	}
}

function valuesForCommand(command, state) {
	const values = lotwiseValues(state.productName, state.lot)
	const sentinel = `${state.productName}-SENTINEL`
	const changes = {
		recalculate: () => {},
		load_product_sizes: () => { values.qty_rate_chart = [{ size: sentinel, qty: 99, rate: 99 }] },
		load_item_sizes: () => {
			values.item = state.itemName
			values.qty_rate_chart = [{ size: sentinel, qty: 99, rate: 99 }]
		},
		add_rate: () => {
			values.additional_rate = 5
			values.qty_rate_chart = [
				{ size: "PD-E2E-S", qty: 1, rate: 10 },
				{ size: "PD-E2E-M", qty: 1, rate: 20 },
			]
		},
		build_piece_cloth_weight: () => {
			values.qty_rate_chart = [{ size: "PD-E2E-S" }, { size: "PD-E2E-M" }]
			values.cloth_value = [{ yarn: "PD-E2E-A" }, { yarn: "PD-E2E-B" }]
			values.piece_cloth_weight = []
		},
		calculate_cloth_qty: () => {
			values.qty_rate_chart = [{ size: "PD-E2E-S", qty: 4 }, { size: "PD-E2E-M", qty: 3 }]
			values.cloth_value = [{ yarn: "PD-E2E-A", qty: 0, rate: 20 }]
			values.piece_cloth_weight = [
				{ size: "PD-E2E-S", cloth_group: "PD-E2E-A", weight: 250 },
				{ size: "PD-E2E-M", cloth_group: "PD-E2E-A", weight: 500 },
			]
		},
		apply_discount_template: () => {
			values.trade_discounts_template = state.discountTemplate
			values.trade_discounts = [{ costing_name: sentinel, based_on: "Total Qty", rate: 98765 }]
		},
		apply_other_cost_template: () => {
			values.other_costs_template = state.otherCostTemplate
			values.other_costs = [{ costing_name: sentinel, based_on: "Total Qty", rate: 98765 }]
		},
		apply_production_cost_template: () => {
			values.production_cost_template = state.productionTemplate
			for (const table of ["cmt", "packing_materials", "trims"]) {
				values[table] = [{ costing_name: sentinel, cost: 98765 }]
			}
		},
		fetch_lot_qty: () => {
			values.lot = state.lotQuantityFixture?.name || state.lot
			values.lot_costing_type = state.lotQuantityFixture?.costingType || "Costing"
			values.qty_rate_chart = (state.lotQuantityFixture?.quantities || []).map((row) => ({
				size: row.size,
				qty: 0,
			}))
		},
		calculate_rate: () => {
			values.qty_rate_chart = [{ size: "PD-E2E-S", qty: 10, rate: 7, group_index: 1 }]
			values.cloth_value = [{ yarn: "PD-E2E-A", rate: 100 }]
			values.piece_cloth_weight = [{ size: "PD-E2E-S", cloth_group: "PD-E2E-A", weight: 500 }]
			values.cmt = [{ costing_name: "PD-E2E-STITCH", cost: 50 }]
		},
	}
	assert(changes[command], `No command fixture exists for ${command}`)
	changes[command]()
	return values
}

function additionalRows(rows) {
	return (rows || []).map((row) => ({
		costing_name: row.costing_name,
		based_on: row.based_on,
		rate: Number(row.rate || 0),
	}))
}

function breakupRows(rows) {
	return (rows || []).map((row) => ({ costing_name: row.costing_name, cost: Number(row.cost || 0) }))
}

function assertSameRows(actual, expected, label) {
	assert(JSON.stringify(actual) === JSON.stringify(expected), `${label}: ${JSON.stringify(actual)}`)
}

function assertTemplateResult(command, record, state) {
	if (command === "apply_discount_template") {
		assertSameRows(additionalRows(record.trade_discounts), state.discountRows, "Discount template rows differ")
	}
	if (command === "apply_other_cost_template") {
		assertSameRows(additionalRows(record.other_costs), state.otherCostRows, "Other Cost template rows differ")
	}
	if (command === "apply_production_cost_template") {
		for (const table of ["cmt", "packing_materials", "trims"]) {
			assertSameRows(breakupRows(record[table]), state.productionRows[table], `${table} template rows differ`)
		}
	}
}

function assertRecalculated(record) {
	assert(Number(record.total_qty) === 2, "Recalculate did not produce total quantity 2")
	assert(Number(record.total_selling_value) === 20, "Recalculate did not produce selling value 20")
}

function assertAddedRate(record) {
	assertSameRows(record.qty_rate_chart.map((row) => Number(row.rate)), [15, 25], "Add Rate values differ")
	assert(Number(record.additional_rate) === 0, "Add Rate did not reset Additional Rate")
}

function assertPieceClothCombinations(record) {
	const combinations = record.piece_cloth_weight.map((row) => [row.cloth_group, row.size, Number(row.weight)])
	assertSameRows(combinations, [
		["PD-E2E-A", "PD-E2E-S", 0], ["PD-E2E-A", "PD-E2E-M", 0],
		["PD-E2E-B", "PD-E2E-S", 0], ["PD-E2E-B", "PD-E2E-M", 0],
	], "Piece cloth combinations differ")
}

function assertFetchedLotQuantities(record, state) {
	const quantities = Object.fromEntries(record.qty_rate_chart.map((row) => [row.size, Number(row.qty)]))
	assertSameRows(quantities, state.lotQuantityFixture.expected, "Fetched Lot quantities differ")
}

function assertCalculatedRate(record) {
	const expectedRate = ((500 / 1000) * 100 + 50) / (1 - 20 / 100)
	assert(Math.abs(Number(record.qty_rate_chart[0]?.rate) - expectedRate) < 1e-9, "Calculated Rate did not equal 125")
}

function assertCommandResult(command, record, state) {
	assert(record && typeof record === "object", `${command} returned no costing record`)
	assert(Array.isArray(record.qty_rate_chart), `${command} returned no quantity chart`)
	const sizes = record.qty_rate_chart.map((row) => row.size)
	const assertions = {
		recalculate: () => assertRecalculated(record),
		load_product_sizes: () => assertSameRows(sizes, state.productSizes, "Product sizes differ"),
		load_item_sizes: () => assertSameRows(sizes, state.itemSizes, "Item sizes differ"),
		add_rate: () => assertAddedRate(record),
		build_piece_cloth_weight: () => assertPieceClothCombinations(record),
		calculate_cloth_qty: () => assert(Math.abs(Number(record.cloth_value[0]?.qty) - 2.5) < 1e-9, "Cloth quantity did not equal 2.5"),
		apply_discount_template: () => assertTemplateResult(command, record, state),
		apply_other_cost_template: () => assertTemplateResult(command, record, state),
		apply_production_cost_template: () => assertTemplateResult(command, record, state),
		fetch_lot_qty: () => assertFetchedLotQuantities(record, state),
		calculate_rate: () => assertCalculatedRate(record),
	}
	assertions[command]()
}

async function runLotwiseCommands(session, state) {
	for (const command of LOTWISE_COMMANDS) {
		const values = valuesForCommand(command, state)
		if (command === "fetch_lot_qty" && !state.lotQuantityFixture) {
			const response = await session.call(`${LOTWISE_WORKSPACE}.run_lotwise_command`, {
				values, command, name: state.lotwiseName,
			})
			const body = await response.json().catch(() => ({}))
			const detail = JSON.stringify(body)
			const expected = "Lot quantities are not used when Lot Costing Type is Costing."
			assert(!response.ok() && detail.includes(expected), `fetch_lot_qty did not reject Costing: ${detail}`)
			console.warn("WARN api-lotwise: no existing Lot has non-zero planned, cutting or final quantities; verified the Costing validation instead")
			continue
		}
		const result = await session.callOk(`${LOTWISE_WORKSPACE}.run_lotwise_command`, {
			values,
			command,
			payload: command === "calculate_rate" ? { percent: 20 } : null,
			name: state.lotwiseName,
		})
		assertCommandResult(command, result.record, state)
	}
}

async function testLotwiseEndpoints(session, state) {
	const values = lotwiseValues(state.productName, state.lot)
	const defaults = await session.callOk(`${LOTWISE_WORKSPACE}.get_lotwise_workspace`, {
		product: state.productName,
	})
	assert(defaults.commands.length === LOTWISE_COMMANDS.length, "Lotwise command inventory is incomplete")
	const saved = await session.callOk(`${LOTWISE_WORKSPACE}.save_lotwise_item_profit`, { values })
	state.lotwiseName = saved.record.name
	state.lotwiseModified = saved.modified
	await runLotwiseCommands(session, state)
	const unchanged = await session.callOk(`${LOTWISE_WORKSPACE}.get_lotwise_workspace`, { name: state.lotwiseName })
	assert(unchanged.modified === state.lotwiseModified, "A Lotwise command unexpectedly saved the document")
	const previousModified = state.lotwiseModified
	const changedAdditionalRate = 7.5
	const updated = await session.callOk(`${LOTWISE_WORKSPACE}.save_lotwise_item_profit`, {
		values: { ...values, additional_rate: changedAdditionalRate },
		name: state.lotwiseName,
		expected_modified: previousModified,
	})
	const persisted = await session.callOk(`${LOTWISE_WORKSPACE}.get_lotwise_workspace`, { name: state.lotwiseName })
	assert(Number(persisted.record.additional_rate) === changedAdditionalRate, "Lotwise update did not persist Additional Rate")
	assert(persisted.modified === updated.modified, "Lotwise update returned a stale modified timestamp")
	assert(persisted.modified !== previousModified, "Lotwise update did not change the modified timestamp")
	state.lotwiseModified = persisted.modified
	console.log(`OK api-lotwise: create/read/update and all ${LOTWISE_COMMANDS.length} commands without command saves`)
}

async function testDeniedEndpoints(session, state) {
	const capabilities = await session.callOk(`${PRODUCT_WORKSPACE}.get_capabilities`)
	assert(
		Object.values(capabilities.sections).every((section) => !section.can_read && !section.can_create && !section.can_write),
		"Unprivileged capabilities exposed a PD permission",
	)
	const protectedCalls = [
		["Product read", `${PRODUCT_WORKSPACE}.get_product_workspace`, { name: state.productName }],
		["Release read", `${PRODUCT_WORKSPACE}.get_product_release_workspace`, { name: state.releaseName }],
		["Product defaults", `${PRODUCT_WORKSPACE}.get_new_product_defaults`, {}],
		["Size range read", `${PRODUCT_WORKSPACE}.get_size_range_sizes`, { size_range: state.sizeRange }],
		["Product create", `${PRODUCT_WORKSPACE}.save_product`, {
			values: {
				style_no: `${state.productName}-denied`, item_name: "Denied", product_group: state.productGroup,
				description: "Denied throwaway", fabric_details: "Cotton",
			},
			images: {},
		}],
		["Product delete", `${PRODUCT_WORKSPACE}.delete_product`, { name: state.productName, expected_modified: state.productModified }],
		["Release delete", `${PRODUCT_WORKSPACE}.delete_product_release`, { name: state.releaseName }],
		["Lotwise read", `${LOTWISE_WORKSPACE}.get_lotwise_workspace`, { name: state.lotwiseName }],
		["Lotwise command", `${LOTWISE_WORKSPACE}.run_lotwise_command`, { values: lotwiseValues(state.productName, state.lot), command: "recalculate" }],
		["Lotwise save", `${LOTWISE_WORKSPACE}.save_lotwise_item_profit`, { values: lotwiseValues(state.productName, state.lot) }],
		["Lotwise delete", `${LOTWISE_WORKSPACE}.delete_lotwise_item_profit`, { name: state.lotwiseName, expected_modified: state.lotwiseModified }],
		["Image search", `${IMAGE_METHOD}.get_image_list`, { query: state.imageName }],
		["Image create", `${IMAGE_METHOD}.create_product_image`, { image_title: `${state.imageName}-denied`, title_header: "Denied" }],
		["Attachment replace", `${PRODUCT_METHOD}.delete_and_update_file`, { file_url: null, fieldname: "product_image", doctype: "SD YRP Product", docname: state.productName }],
		["Graphic remove", `${PRODUCT_METHOD}.remove_graphic_image`, { detail: { name: "missing" }, docname: state.productName }],
		["Tech Pack release", `${PRODUCT_METHOD}.release_tech_pack`, { doc_name: state.productName }],
		["Graphics PDF", `${PRODUCT_METHOD}.process_pdf_to_images`, { file_url: "/private/files/denied.pdf", docname: state.productName, table_name: "product_designs" }],
		["Silhouette PDF", `${PRODUCT_METHOD}.process_single_page_pdf`, { file_url: "/private/files/denied.pdf", doctype: "SD YRP Product", docname: state.productName, fieldname: "product_image" }],
	]
	for (const [label, method, args] of protectedCalls) {
		await expectMethodDenied(session, label, method, args)
	}
	await expectDenied("Graphics upload", await session.request("post", "/api/method/upload_file", {
		multipart: {
			file: { name: "denied.png", mimeType: "image/png", buffer: PNG },
			is_private: "1",
			doctype: "SD YRP Product",
			docname: state.productName,
			fieldname: "product_designs",
			method: `${PRODUCT_METHOD}.upload_graphics_file`,
			upload_type: "Denied",
		},
	}))
	console.log("OK api-permissions: unprivileged reads and mutations rejected; capabilities stay all-false")
}

function uniqueNames(rows, remembered = []) {
	return [...new Set([...rows.map((row) => row.name), ...remembered].filter(Boolean))]
}

async function cleanupRows(admin, doctype, options, failures, label) {
	try {
		return await resourceRows(admin, doctype, options)
	} catch (reason) {
		failures.push(`${label}: ${reason.message}`)
		return []
	}
}

async function discoverRunFixtures(admin, state, failures) {
	const productFilter = [["name", "like", `${state.productPrefix}%`]]
	const productLinks = [["product", "like", `${state.productPrefix}%`]]
	const [products, releases, lotwise, images, users] = await Promise.all([
		cleanupRows(admin, "SD YRP Product", { filters: productFilter }, failures, "discover Products"),
		cleanupRows(admin, "SD YRP Product Release", { filters: productLinks }, failures, "discover Releases"),
		cleanupRows(admin, "SD YRP Lotwise Item Profit", { filters: productLinks }, failures, "discover costing sheets"),
		cleanupRows(admin, "SD YRP Product Image", { filters: [["name", "like", `${state.imagePrefix}%`]] }, failures, "discover images"),
		cleanupRows(admin, "User", { filters: [["name", "like", `%${state.runId}%`]] }, failures, "discover users"),
	])
	const attachedNames = uniqueNames([...products, ...releases, ...lotwise, ...images], [
		state.productName, state.releaseName, state.lotwiseName, state.imageName,
	])
	const files = attachedNames.length ? await cleanupRows(admin, "File", {
		fields: ["name", "is_folder", "folder", "attached_to_name"],
		filters: [["attached_to_name", "in", attachedNames]],
	}, failures, "discover attached files") : []
	const folderFiles = await cleanupRows(admin, "File", {
		fields: ["name", "is_folder", "folder", "attached_to_name"],
		filters: [["folder", "like", `${state.productFolder}%`]],
	}, failures, "discover folder contents")
	const folders = await cleanupRows(admin, "File", {
		fields: ["name", "is_folder", "folder", "attached_to_name"],
		filters: [["name", "like", `${state.productFolder}%`]],
	}, failures, "discover Product folders")
	return { products, releases, lotwise, images, users, files: [...files, ...folderFiles], folders, attachedNames }
}

async function attemptCleanup(failures, label, operation) {
	try {
		await operation()
	} catch (reason) {
		failures.push(`${label}: ${reason.message}`)
	}
}

async function deleteForCleanup(admin, doctype, name) {
	if (!name) return
	const response = await admin.deleteResource(doctype, name)
	if (response.status() === 404) return
	assert(response.ok(), `HTTP ${response.status()} ${await response.text()}`)
}

async function deleteDiscovered(admin, doctype, names, failures) {
	for (const name of names) {
		await attemptCleanup(failures, `delete ${doctype} ${name}`, () => deleteForCleanup(admin, doctype, name))
	}
}

async function verifyCleanup(admin, state, attachedNames, failures) {
	const checks = [
		["SD YRP Product", [["name", "like", `${state.productPrefix}%`]]],
		["SD YRP Product Release", [["product", "like", `${state.productPrefix}%`]]],
		["SD YRP Lotwise Item Profit", [["product", "like", `${state.productPrefix}%`]]],
		["SD YRP Product Image", [["name", "like", `${state.imagePrefix}%`]]],
		["User", [["name", "like", `%${state.runId}%`]]],
		["File", [["name", "like", `${state.productFolder}%`]]],
		["File", [["folder", "like", `${state.productFolder}%`]]],
	]
	if (attachedNames.length) checks.push(["File", [["attached_to_name", "in", attachedNames]]])
	for (const [doctype, filters] of checks) {
		const rows = await cleanupRows(admin, doctype, { filters }, failures, `verify ${doctype}`)
		if (rows.length) failures.push(`verify ${doctype}: ${JSON.stringify(rows)}`)
	}
}

async function cleanup(admin, state) {
	const failures = []
	const fixtures = await discoverRunFixtures(admin, state, failures)
	await deleteDiscovered(admin, "SD YRP Product Release", uniqueNames(fixtures.releases, [state.releaseName]), failures)
	await deleteDiscovered(admin, "SD YRP Lotwise Item Profit", uniqueNames(fixtures.lotwise, [state.lotwiseName]), failures)
	await deleteDiscovered(admin, "SD YRP Product", uniqueNames(fixtures.products, [state.productName]), failures)
	await deleteDiscovered(admin, "SD YRP Product Image", uniqueNames(fixtures.images, [state.imageName]), failures)
	await deleteDiscovered(admin, "User", uniqueNames(fixtures.users, [state.pdUser, state.deniedUser]), failures)
	await deleteDiscovered(admin, "File", uniqueNames(fixtures.files), failures)
	const afterDocuments = await discoverRunFixtures(admin, state, failures)
	await deleteDiscovered(admin, "File", uniqueNames(afterDocuments.files), failures)
	const folders = uniqueNames([...fixtures.folders, ...afterDocuments.folders])
		.sort((left, right) => right.length - left.length)
	await deleteDiscovered(admin, "File", folders, failures)
	await verifyCleanup(admin, state, fixtures.attachedNames, failures)
	if (failures.length) throw new Error(`Cleanup failures:\n${failures.join("\n")}`)
	console.log("OK api-cleanup: run-owned records, files and exact Product folders are absent")
}

const runId = timestamp()
const state = {
	runId,
	pdUser: `pd-e2e-api-${runId}@example.invalid`,
	deniedUser: `pd-e2e-denied-${runId}@example.invalid`,
	productName: `PD-API-${runId}`,
	productPrefix: `PD-API-${runId}`,
	productFolder: `Home/product/pd-api-${runId}`,
	imagePrefix: `pd-e2e-api-${runId}`,
	imageName: `pd-e2e-api-${runId}`,
	releaseName: "",
	lotwiseName: "",
}
const password = `PdE2E!${runId}Aa9#`
const [administrator, administratorPassword] = readFileSync(CREDENTIALS, "utf8").trim().split("\n").map((value) => value.trim())
const browser = await chromium.launch({ headless: true })
let admin
let pdSession
let deniedSession
let failure

try {
	admin = await FrappeSession.login(browser, administrator, administratorPassword)
	const [groups, lots, sizeRanges, items, discountTemplates, otherCostTemplates, productionTemplates] = await Promise.all([
		resourceRows(admin, "SD YRP Product Group", { limit: 1 }),
		resourceRows(admin, "SD YRP Lot", { limit: 1 }),
		resourceRows(admin, "SD YRP FG Item Size Range", { limit: 1 }),
		resourceRows(admin, "SD YRP FG Item Master", {
			fields: ["name", "available_sizes", "prices"],
			filters: [["available_sizes", "is", "set"]],
			limit: 1,
		}),
		resourceRows(admin, "SD YRP Lotwise Item Profit Additional Cost Template", { filters: [["type", "=", "Discounts"]], limit: 1 }),
		resourceRows(admin, "SD YRP Lotwise Item Profit Additional Cost Template", { filters: [["type", "=", "Other"]], limit: 1 }),
		resourceRows(admin, "SD YRP Lotwise Item Profit Breakup Template", { limit: 1 }),
	])
	assert(groups[0]?.name, "No Product Group is available for the API verification Product")
	assert(lots[0]?.name, "No Lot is available for the API verification costing sheet")
	assert(sizeRanges[0]?.name, "No FG Item Size Range is available for required size-range verification")
	assert(items[0]?.name, "No FG Item Master with available_sizes exists for load_item_sizes verification")
	assert(discountTemplates[0]?.name, "No Discounts template is available for command verification")
	assert(otherCostTemplates[0]?.name, "No Other Costs template is available for command verification")
	assert(productionTemplates[0]?.name, "No Production Cost template is available for command verification")
	const [discountTemplate, otherCostTemplate, productionTemplate, lotQuantityFixture] = await Promise.all([
		resourceDocument(admin, "SD YRP Lotwise Item Profit Additional Cost Template", discountTemplates[0].name),
		resourceDocument(admin, "SD YRP Lotwise Item Profit Additional Cost Template", otherCostTemplates[0].name),
		resourceDocument(admin, "SD YRP Lotwise Item Profit Breakup Template", productionTemplates[0].name),
		loadLotQuantityFixture(admin),
	])
	state.productGroup = groups[0].name
	state.lot = lots[0].name
	state.sizeRange = sizeRanges[0].name
	state.itemName = items[0].name
	state.itemSizes = items[0].available_sizes.split(",").map((size) => size.trim()).filter(Boolean)
	state.discountTemplate = discountTemplates[0].name
	state.discountRows = additionalRows(discountTemplate.value)
	state.otherCostTemplate = otherCostTemplates[0].name
	state.otherCostRows = additionalRows(otherCostTemplate.value)
	state.productionTemplate = productionTemplates[0].name
	state.productionRows = Object.fromEntries(
		["cmt", "packing_materials", "trims"].map((table) => [table, breakupRows(productionTemplate[table])]),
	)
	state.lotQuantityFixture = lotQuantityFixture
	await createUser(admin, state.pdUser, password, ["PD User", "PD Manager"])
	await createUser(admin, state.deniedUser, password, [])
	pdSession = await FrappeSession.login(browser, state.pdUser, password)
	deniedSession = await FrappeSession.login(browser, state.deniedUser, password)
	await testWorkspaceEndpoints(pdSession, state)
	state.productSizes = await resolveAttributeValues(admin, state.productSizeLinks)
	await testImageEndpoints(pdSession, state)
	await testProductMediaEndpoints(pdSession, state)
	const refreshed = await pdSession.callOk(`${PRODUCT_WORKSPACE}.get_product_workspace`, { name: state.productName })
	state.productModified = refreshed.modified
	await testReleaseEndpoints(pdSession, state)
	await testLotwiseEndpoints(pdSession, state)
	await testDeniedEndpoints(deniedSession, state)
	await admin.callOk(`${PRODUCT_WORKSPACE}.delete_product_release`, { name: state.releaseName })
	await assertResourceAbsent(admin, "SD YRP Product Release", state.releaseName, "Product Release")
	state.releaseName = ""
	console.log("OK api-release-delete: Administrator endpoint deleted the throwaway Release and immediate GET confirmed absence")
	await pdSession.callOk(`${LOTWISE_WORKSPACE}.delete_lotwise_item_profit`, {
		name: state.lotwiseName,
		expected_modified: state.lotwiseModified,
	})
	await assertResourceAbsent(pdSession, "SD YRP Lotwise Item Profit", state.lotwiseName, "Lotwise Item Profit")
	state.lotwiseName = ""
	console.log("OK api-lotwise-delete: PD Manager endpoint deleted the throwaway sheet and immediate GET confirmed absence")
	const finalProduct = await pdSession.callOk(`${PRODUCT_WORKSPACE}.get_product_workspace`, {
		name: state.productName,
	})
	await pdSession.callOk(`${PRODUCT_WORKSPACE}.delete_product`, {
		name: state.productName,
		expected_modified: finalProduct.modified,
	})
	await assertResourceAbsent(pdSession, "SD YRP Product", state.productName, "Product")
	console.log("OK api-product-delete: PD Manager endpoint deleted the throwaway Product and immediate GET confirmed absence")
} catch (reason) {
	failure = reason
} finally {
	await deniedSession?.close().catch(() => {})
	await pdSession?.close().catch(() => {})
	if (admin) {
		try {
			await cleanup(admin, state)
		} catch (cleanupError) {
			failure = failure
				? new Error(`${failure.message}\nCleanup failure: ${cleanupError.message}`)
				: cleanupError
		}
		await admin.close().catch(() => {})
	}
	await browser.close()
}

if (failure) throw failure
console.log("OK api: every PD web, costing, media, release and image endpoint was verified over HTTP")
