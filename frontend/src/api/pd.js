import { callMethod, callRead, uploadFile } from "./frappe.js"

const PRODUCT_METHOD = "essdee_yrp.essdee_yrp.doctype.sd_yrp_product.sd_yrp_product"
const IMAGE_METHOD = "essdee_yrp.essdee_yrp.doctype.sd_yrp_product_image.sd_yrp_product_image"
const WORKSPACE = "essdee_yrp.product_development.web_workspace"
const LOTWISE = "essdee_yrp.product_development.lotwise_workspace"

export function getPdCapabilities() {
	return callRead(`${WORKSPACE}.get_capabilities`)
}

export function getProductWorkspace(name) {
	return callMethod(`${WORKSPACE}.get_product_workspace`, { name })
}

export function getNewProductDefaults() {
	return callMethod(`${WORKSPACE}.get_new_product_defaults`)
}

export function saveProduct(values, images, { name = null, expectedModified = null } = {}) {
	return callMethod(`${WORKSPACE}.save_product`, {
		values,
		images,
		name,
		expected_modified: expectedModified,
	})
}

export function deleteProduct(name, expectedModified) {
	return callMethod(`${WORKSPACE}.delete_product`, { name, expected_modified: expectedModified })
}

export function getSizeRangeSizes(sizeRange) {
	return callMethod(`${WORKSPACE}.get_size_range_sizes`, { size_range: sizeRange })
}

export function getSubmittedColourCodes(query = "") {
	return callMethod(`${WORKSPACE}.search_submitted_colour_codes`, { query })
}

export function createColourCode(colour, colourCode) {
	return callMethod(`${WORKSPACE}.create_colour_code`, { colour, colour_code: colourCode })
}

export function searchProductImages(query) {
	return callMethod(`${IMAGE_METHOD}.get_image_list`, { query })
}

export function createProductImage(imageTitle, titleHeader) {
	return callMethod(`${IMAGE_METHOD}.create_product_image`, {
		image_title: imageTitle,
		title_header: titleHeader,
	})
}

export async function replaceAttachment({ doctype, docname, fieldname, oldUrl, file }) {
	const uploaded = await uploadFile(file, { doctype, docname, fieldname, isPrivate: 1 })
	return callMethod(`${PRODUCT_METHOD}.delete_and_update_file`, {
		file_url: oldUrl || null,
		fieldname,
		doctype,
		docname,
		updated_url: uploaded.file_url,
		file_name: uploaded.name,
	})
}

export async function uploadSinglePagePdf({ doctype, docname, fieldname, file }) {
	const uploaded = await uploadFile(file, { doctype, docname, fieldname, isPrivate: 1 })
	return callMethod(`${PRODUCT_METHOD}.process_single_page_pdf`, {
		file_url: uploaded.file_url,
		doctype,
		docname,
		fieldname,
	})
}

function uploadProductDraftFile(docname, fieldname, file) {
	return uploadFile(file, {
		doctype: "SD YRP Product",
		docname,
		fieldname,
		isPrivate: 1,
	})
}

export async function stageProductAttachment({ docname, fieldname, file }) {
	const uploaded = await uploadProductDraftFile(docname, fieldname, file)
	return uploaded.file_url
}

export async function stageProductAttachmentPdf({ docname, fieldname, file }) {
	const uploaded = await uploadProductDraftFile(docname, fieldname, file)
	const image = await callMethod(`${PRODUCT_METHOD}.process_single_page_pdf`, {
		file_url: uploaded.file_url,
		doctype: "SD YRP Product",
		docname,
		fieldname,
		defer_save: 1,
	})
	return image.file_url
}

export async function stageProductGraphic({ docname, uploadType, file, isBox }) {
	const fieldname = isBox ? "product_box_details" : "product_designs"
	const uploaded = await uploadProductDraftFile(docname, fieldname, file)
	return {
		graphic_image: uploaded.file_url,
		upload_name: uploadType,
		file: uploaded.name,
		filename: uploaded.file_name,
	}
}

export async function stageProductGraphicsPdf({ docname, tableName, file }) {
	const uploaded = await uploadProductDraftFile(docname, tableName, file)
	return callMethod(`${PRODUCT_METHOD}.process_pdf_to_images`, {
		file_url: uploaded.file_url,
		docname,
		table_name: tableName,
		defer_save: 1,
	})
}

export function releaseTechPack(productName) {
	return callMethod(`${PRODUCT_METHOD}.release_tech_pack`, { doc_name: productName })
}

export function getProductReleaseWorkspace(name) {
	return callMethod(`${WORKSPACE}.get_product_release_workspace`, { name })
}

export function deleteProductRelease(name) {
	return callMethod(`${WORKSPACE}.delete_product_release`, { name })
}

export function getLotwiseWorkspace({ name = null, product = null, duplicateFrom = null } = {}) {
	return callMethod(`${LOTWISE}.get_lotwise_workspace`, { name, product, duplicate_from: duplicateFrom })
}

export function runLotwiseCommand(values, command, payload = null, name = null) {
	return callMethod(`${LOTWISE}.run_lotwise_command`, { values, command, payload, name })
}

export function saveLotwiseItemProfit(values, { name = null, expectedModified = null } = {}) {
	return callMethod(`${LOTWISE}.save_lotwise_item_profit`, {
		values,
		name,
		expected_modified: expectedModified,
	})
}

export function deleteLotwiseItemProfit(name, expectedModified) {
	return callMethod(`${LOTWISE}.delete_lotwise_item_profit`, {
		name,
		expected_modified: expectedModified,
	})
}
