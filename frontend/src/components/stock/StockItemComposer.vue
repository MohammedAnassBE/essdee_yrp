<template>
	<div class="stock-composer" :class="{ 'stock-composer--natural-table-flow': naturalTableFlow }">
		<section v-if="!readOnly" class="stock-composer__builder">
			<header class="stock-composer__heading">
				<div>
					<span class="stock-composer__eyebrow">Item builder</span>
					<h3>Stock dimensions &amp; item</h3>
				</div>
				<span class="stock-composer__step" aria-label="Steps: Select, Get Item, Add">
					<span><b class="stock-composer__step-number">1</b>Select</span>
					<span><b class="stock-composer__step-number">2</b>Get Item</span>
					<span><b class="stock-composer__step-number">3</b>Add</span>
				</span>
			</header>

			<div class="stock-composer__fields">
				<LinkField
					v-for="dimension in dimensions"
					:key="dimension.fieldname"
					v-model="dimensionValues[dimension.fieldname]"
					:label="`${dimension.label}${dimension.mandatory ? ' *' : ''}`"
					:doctype="dimension.options"
					:filters="dimension.filters || {}"
					:disabled="disabled || lockedDimensions.includes(dimension.fieldname)"
					:show-clear="!lockedDimensions.includes(dimension.fieldname)"
					:show-open-button="false"
				/>
				<LinkField
					:model-value="itemName"
					label="Item *"
					doctype="Item"
					:filters="editor.item_filters || { is_stock_item: 1, disabled: 0, variant_of: ['is', 'not set'] }"
					:show-open-button="false"
					:disabled="disabled"
					@update:model-value="setItem"
				/>
				<div class="stock-composer__fetch">
					<Button label="Get Item" icon="pi pi-search" :loading="fetching" :disabled="disabled || !itemName" @click="fetchItem" />
				</div>
			</div>

			<Message v-if="editorError" severity="error" :closable="false">{{ editorError }}</Message>

			<div v-if="itemSchema" class="stock-composer__attributes">
				<div class="stock-composer__item-strip">
					<div><span>Selected item</span><strong>{{ itemSchema.item }}</strong></div>
					<div><span>Stock UOM</span><strong>{{ activeUom || "—" }}</strong></div>
					<div v-if="activePrimary"><span>Quantity grid</span><strong>{{ activePrimary }}</strong></div>
				</div>

				<div v-if="dependentAttribute || nonPrimaryAttributes.length" class="stock-composer__attribute-grid">
					<LinkField
						v-if="dependentAttribute"
						:model-value="attributeValues[dependentAttribute] || ''"
						:label="`${dependentAttribute} *`"
						doctype="Item Attribute Value"
						:search-handler="(text) => searchAttribute(dependentAttribute, text)"
						:show-open-button="false"
						:disabled="disabled"
						@update:model-value="setAttribute(dependentAttribute, $event)"
					/>
					<LinkField
						v-for="attribute in nonPrimaryAttributes"
						:key="attribute"
						:model-value="attributeValues[attribute] || ''"
						:label="`${attribute} *`"
						doctype="Item Attribute Value"
						:search-handler="(text) => searchAttribute(attribute, text)"
						create-doctype="YRP Item Attribute Value"
						:create-values="{ attribute_name: attribute }"
						create-value-field="attribute_value"
						:show-open-button="false"
						:disabled="disabled"
						@update:model-value="setAttribute(attribute, $event)"
					/>
				</div>

				<slot name="entry-fields" :values="entryValues" :schema="itemSchema" :editing="Boolean(editing)" />

				<div class="stock-composer__quantity-card">
					<header>
						<div><h4>{{ activePrimary ? `${activePrimary} quantities` : quantityLabel }}</h4><p>{{ quantityHelp }}</p></div>
						<strong v-if="activePrimaryValues.length > 1" class="stock-composer__entry-total">Total {{ formatQty(entryTotals.qty) }}<template v-if="rateEditable && entryTotals.amount"> · Amount {{ formatMoney(entryTotals.amount) }}</template></strong>
						<span>{{ activeUom || "UOM" }}</span>
					</header>
					<div v-if="activePrimaryValues.length" class="stock-composer__quantity-grid">
						<label v-for="value in activePrimaryValues" :key="value" class="stock-composer__quantity-cell">
							<strong>{{ value }}</strong>
							<span>{{ quantityLabel }}</span>
							<input v-model.number="quantities[value]" type="number" min="0" step="0.001" :disabled="disabled" @input="quantityTouched[value] = true" />
							<template v-if="rateEditable"><span>Rate</span><input v-model.number="receiptRates[value]" type="number" min="0" step="0.0001" :disabled="disabled" /></template>
							<template v-if="offersSecondary">
								<span>{{ itemSchema.secondary_uom }}</span>
								<input v-model.number="secondaryQuantities[value]" type="number" min="0" step="0.001" :disabled="disabled" />
							</template>
						</label>
					</div>
					<div v-else class="stock-composer__single-quantity">
						<label><span>{{ quantityLabel }} *</span><input v-model.number="quantities.default" type="number" min="0" step="0.001" :disabled="disabled" @input="quantityTouched.default = true" /></label>
						<label v-if="rateEditable"><span>Rate</span><input v-model.number="receiptRates.default" type="number" min="0" step="0.0001" :disabled="disabled" /></label>
						<label v-if="offersSecondary"><span>Secondary Qty · {{ itemSchema.secondary_uom }}</span><input v-model.number="secondaryQuantities.default" type="number" min="0" step="0.001" :disabled="disabled" /></label>
					</div>
				</div>

				<label v-if="operation === 'stock_entry'" class="stock-composer__remarks"><span>Remarks</span><textarea v-model="rowRemarks" rows="2" aria-label="Row remarks" :disabled="disabled"></textarea></label>

				<div class="stock-composer__builder-footer">
					<label v-if="operation === 'stock_reconciliation'" class="stock-composer__check"><input v-model="allowZeroValuation" type="checkbox" /><span>Allow zero valuation when no prior rate exists</span></label>
					<span v-else></span>
					<div>
						<Button v-if="editing" label="Cancel Edit" severity="secondary" text size="small" :disabled="disabled" @click="resetEditor" />
						<Button :label="editing ? 'Update Item' : 'OK · Add Item'" :icon="editing ? 'pi pi-check' : 'pi pi-plus'" size="small" :loading="preparing" :disabled="disabled || preparing" @click="stageItem" />
					</div>
				</div>
			</div>
		</section>

		<section class="stock-composer__staged">
			<header class="stock-composer__heading">
				<div><span class="stock-composer__eyebrow">Transaction lines</span><h3>Added items</h3></div>
				<span class="stock-composer__count">{{ rowCount }} {{ rowCount === 1 ? "item" : "items" }}</span>
			</header>

			<div v-if="groups.length" class="stock-composer__tables">
				<div v-for="(group, groupIndex) in groups" :key="groupKey(group, groupIndex)" class="stock-composer__table-card">
					<div class="stock-composer__table-title"><strong>{{ group.primary_attribute ? `${group.primary_attribute} matrix` : "Quantity" }}</strong><span>{{ group.items.length }} {{ group.items.length === 1 ? "row" : "rows" }}</span></div>
					<div class="stock-composer__table-scroll" tabindex="0" role="region" :aria-label="`${group.name || group.item || 'Added items'} table`">
						<table>
							<thead><tr><th>#</th><th>Item</th><th v-for="dimension in dimensions" :key="dimension.fieldname">{{ dimension.label }}</th><th v-for="attribute in group.attributes" :key="attribute">{{ attribute }}</th><template v-if="operation === 'purchase_order'"><th>Delivery location</th><th>Required by</th><th class="stock-composer__number">Discount</th></template><th v-for="value in group.primary_attribute_values" :key="value" class="stock-composer__number">{{ value }}</th><th v-if="!group.primary_attribute">{{ quantityLabel }}</th><th class="stock-composer__number">Total</th><th>UOM</th><th v-if="!readOnly"></th></tr></thead>
								<tbody><tr v-for="(row, itemIndex) in group.items" :key="`${row.name}-${itemIndex}`"><td>{{ itemIndex + 1 }}</td><td><strong>{{ row.name }}</strong><span v-if="rowNote(row)" class="stock-composer__row-note">{{ rowNote(row) }}</span><slot name="row-warning" :row="row" :group="group" :group-index="groupIndex" :item-index="itemIndex" /></td><td v-for="dimension in dimensions" :key="dimension.fieldname">{{ row.dimensions?.[dimension.fieldname] || "—" }}</td><td v-for="attribute in group.attributes" :key="attribute">{{ row.attributes?.[attribute] || "—" }}</td><template v-if="operation === 'purchase_order'"><td>{{ row.delivery_location || "—" }}</td><td>{{ formatDate(row.schedule_date) }}</td><td class="stock-composer__number">{{ formatQty(row.discount_percentage) }}%</td></template><td v-for="value in group.primary_attribute_values" :key="value" class="stock-composer__number stock-composer__metric"><strong>{{ formatQty(row.values?.[value]?.qty) }}</strong><span v-if="rateLabel" class="stock-composer__price">{{ rateLabel }} {{ formatMoney(row.values?.[value]?.rate) }}</span><template v-if="operation === 'purchase_order'"><span class="stock-composer__price">Amount {{ formatMoney(cellAmount(row.values?.[value])) }}</span></template></td><td v-if="!group.primary_attribute" class="stock-composer__number stock-composer__metric"><strong>{{ formatQty(row.values?.default?.qty) }}</strong><span v-if="rateLabel" class="stock-composer__price">{{ rateLabel }} {{ formatMoney(row.values?.default?.rate) }}</span><template v-if="operation === 'purchase_order'"><span class="stock-composer__price">Amount {{ formatMoney(cellAmount(row.values?.default)) }}</span></template></td><td class="stock-composer__number stock-composer__total stock-composer__metric"><strong>{{ formatQty(rowTotal(row)) }}</strong><span v-if="operation === 'purchase_order'" class="stock-composer__price">Amount {{ formatMoney(rowAmount(row)) }}</span></td><td>{{ row.default_uom || "—" }}</td><td v-if="!readOnly"><div class="stock-composer__actions"><button type="button" title="Edit item" :aria-label="`Edit ${row.name}`" :disabled="disabled || preparing" @click="editItem(groupIndex, itemIndex)"><i class="pi pi-pencil" aria-hidden="true"></i></button><button type="button" title="Delete item" :aria-label="`Delete ${row.name}`" class="stock-composer__delete" :disabled="disabled || preparing" @click="removeItem(groupIndex, itemIndex)"><i class="pi pi-trash" aria-hidden="true"></i></button></div></td></tr></tbody>
							<tfoot v-if="group.items.length > 1"><tr v-for="bucket in groupTotals(group)" :key="bucket.uom" class="stock-composer__footer"><th :colspan="footerLabelSpan(group)" scope="row">{{ footerLabel(group, bucket) }}</th><td v-for="value in valueKeys(group)" :key="value" class="stock-composer__number stock-composer__metric"><strong>{{ formatQty(bucket.values[value].qty) }}</strong><span v-if="operation === 'purchase_order'" class="stock-composer__price">Amount {{ formatMoney(bucket.values[value].amount) }}</span></td><td class="stock-composer__number stock-composer__total stock-composer__metric"><strong>{{ formatQty(bucket.total.qty) }}</strong><span v-if="operation === 'purchase_order' || bucket.total.amount" class="stock-composer__price">Amount {{ formatMoney(bucket.total.amount) }}</span></td><td>{{ bucket.uom || "—" }}</td><td v-if="!readOnly"></td></tr></tfoot>
						</table>
					</div>
				</div>
			</div>
			<div v-else class="stock-composer__empty"><i class="pi pi-box"></i><div><strong>No items added</strong><span>Set the stock dimensions, fetch an item, enter its attribute quantities, and click OK.</span></div></div>
		</section>
	</div>
</template>

<script setup>
import Button from "primevue/button"
import Message from "primevue/message"
import { computed, reactive, ref, watch } from "vue"

import LinkField from "../../components/common/LinkField.vue"
import { callMethod } from "../../api/frappe.js"
import { getEntryPrimaryValues, mergeStockItemDraft, offersSecondaryQuantity, stockRateLabels } from "../../utils/stockItemComposer.js"
import { cellAmount, getEntryTotals, getUomTotals, rowAmount } from "../../engine/stock/stockItemTotals.js"
import { formatDisplayDate } from "../../utils/dateFormat.js"

const props = defineProps({
	modelValue: { type: Array, default: () => [] },
	operation: { type: String, required: true },
	purpose: { type: String, default: "" },
	updateType: { type: String, default: "" },
	editor: { type: Object, required: true },
	schemaLoader: { type: Function, required: true },
	rowPreparer: { type: Function, default: null },
	groupsPreparer: { type: Function, default: null },
	currency: { type: String, default: "" },
	readOnly: { type: Boolean, default: false },
	naturalTableFlow: { type: Boolean, default: false },
	disabled: { type: Boolean, default: false },
	entryDefaults: { type: Object, default: () => ({}) },
	entryFields: { type: Array, default: () => [] },
})
const emit = defineEmits(["update:modelValue", "dirty", "preparing-change"])

const groups = ref(clone(props.modelValue))
const itemName = ref("")
const itemSchema = ref(null)
const fetching = ref(false)
const editorError = ref("")
const dimensionValues = reactive({})
const attributeValues = reactive({})
const entryValues = reactive({})
const quantities = reactive({ default: 0 })
const quantityTouched = reactive({ default: false })
const receiptRates = reactive({ default: 0 })
const secondaryQuantities = reactive({ default: 0 })
const allowZeroValuation = ref(false)
const rowRemarks = ref("")
const editing = ref(null)
const preparing = ref(false)

const dimensions = computed(() => props.editor.dimensions || [])
const offersSecondary = computed(() => offersSecondaryQuantity(props.operation, itemSchema.value))
const rateLabel = computed(() => stockRateLabels[props.operation] || (props.operation === "purchase_order" ? "Rate" : ""))
const rateEditable = computed(() => props.operation === "stock_reconciliation" || (props.operation === "stock_entry" && props.purpose === "Material Receipt"))
const lockedDimensions = computed(() => {
	const locked = props.editor.locked_dimensions
		|| dimensions.value.filter((dimension) => dimension.locked).map((dimension) => dimension.fieldname)
	return locked
})
const dependentAttribute = computed(() => itemSchema.value?.dependent_attribute || "")
const activeStage = computed(() => {
	if (!dependentAttribute.value) return null
	return itemSchema.value?.dependent_attribute_details?.attr_list?.[attributeValues[dependentAttribute.value]] || null
})
const activePrimary = computed(() => activeStage.value?.primary_attribute ?? itemSchema.value?.primary_attribute ?? "")
const activePrimaryValues = computed(() => activeStage.value?.primary_attribute_values ?? itemSchema.value?.primary_attribute_values ?? [])
const activeUom = computed(() => activeStage.value?.uom || itemSchema.value?.default_uom || "")
const applicableAttributes = computed(() => activeStage.value?.attributes || itemSchema.value?.attributes || [])
const nonPrimaryAttributes = computed(() => applicableAttributes.value.filter((attribute) => attribute !== activePrimary.value && attribute !== dependentAttribute.value))
const quantityLabel = computed(() => {
	if (props.operation === "stock_reconciliation") return "Counted Qty"
	if (props.operation === "stock_update") return `${props.updateType || "Update"} Qty`
	if (props.operation === "lot_transfer") return "Transfer Qty"
	return "Quantity"
})
const quantityHelp = computed(() => {
	if (props.operation === "stock_reconciliation") return "Enter the counted closing quantity. Zero is valid."
	if (props.operation === "stock_update") return `Enter the quantity to ${String(props.updateType || "update").toLowerCase()}.`
	if (props.operation === "lot_transfer") return "Enter the quantity to move from the source lot to the selected target lot."
	return "Enter quantity against each applicable item value."
})
const entryTotals = computed(() => getEntryTotals(quantities, rateEditable.value ? receiptRates : {}, activePrimaryValues.value))
const rowCount = computed(() => groups.value.reduce((total, group) => total + (group.items?.length || 0), 0))

watch(() => props.modelValue, (value) => { if (JSON.stringify(value || []) !== JSON.stringify(groups.value)) groups.value = clone(value || []) }, { deep: true })
watch(() => [props.editor, props.operation], resetAll, { immediate: true })
watch(() => props.entryDefaults, (value) => {
	if (!editing.value && !itemSchema.value) resetEntryValues(value)
}, { deep: true })

function resetAll() {
	groups.value = clone(props.modelValue || [])
	resetEditor()
}

function resetDimensions() {
	for (const key of Object.keys(dimensionValues)) delete dimensionValues[key]
	const defaults = props.editor.default_dimensions || props.editor.defaults?.dimensions
		|| Object.fromEntries(dimensions.value.filter((dimension) => dimension.default_value).map((dimension) => [dimension.fieldname, dimension.default_value]))
	Object.assign(dimensionValues, clone(defaults || {}))
}

function resetEditor() {
	resetDimensions()
	resetEntryValues()
	itemName.value = ""
	itemSchema.value = null
	editing.value = null
	allowZeroValuation.value = false
	rowRemarks.value = ""
	editorError.value = ""
	clearReactive(attributeValues)
	clearReactive(quantities)
	clearReactive(quantityTouched)
	clearReactive(secondaryQuantities)
	quantities.default = props.operation === "stock_reconciliation" ? null : 0
	quantityTouched.default = false
	secondaryQuantities.default = 0
}

function setItem(value) {
	itemName.value = value || ""
	itemSchema.value = null
	clearReactive(attributeValues)
}

async function fetchItem() {
	if (props.disabled) return
	if (!itemName.value) return
	fetching.value = true
	editorError.value = ""
	try {
		itemSchema.value = await props.schemaLoader(props.operation, itemName.value)
		itemName.value = itemSchema.value?.item || itemName.value
		clearReactive(attributeValues)
		mergeAdditionalParameters()
		prepareQuantities()
	} catch (error) {
		editorError.value = error.message || "Unable to get the item attributes."
	} finally {
		fetching.value = false
	}
}

function prepareQuantities(existing = null) {
	clearReactive(quantities)
	clearReactive(quantityTouched)
	clearReactive(secondaryQuantities)
	clearReactive(receiptRates)
	const values = activePrimaryValues.value.length ? activePrimaryValues.value : ["default"]
	for (const value of values) {
		const hasExistingValue = Boolean(existing && Object.prototype.hasOwnProperty.call(existing, value))
		quantities[value] = hasExistingValue
			? Number(existing[value]?.qty || 0)
			: props.operation === "stock_reconciliation" ? null : 0
		quantityTouched[value] = hasExistingValue
		secondaryQuantities[value] = Number(existing?.[value]?.secondary_qty || 0)
		receiptRates[value] = Number(existing?.[value]?.rate || 0)
	}
}

function setAttribute(attribute, value) {
	attributeValues[attribute] = value || ""
	if (attribute === dependentAttribute.value) {
		for (const key of Object.keys(attributeValues)) if (key !== attribute) delete attributeValues[key]
		prepareQuantities()
	}
}

async function searchAttribute(attribute, text) {
	const values = await callMethod("yrp.yrp.doctype.yrp_item.yrp_item.search_item_attribute_values", {
		txt: text, attribute, item: itemSchema.value?.item, page_len: 20,
	})
	return (values || []).map((value) => ({ name: value, label: value }))
}

async function stageItem() {
	if (props.disabled) return
	editorError.value = ""
	for (const dimension of dimensions.value) {
		if (dimension.mandatory && !dimensionValues[dimension.fieldname]) return fail(`${dimension.label} is required.`)
	}
	if (!itemSchema.value) return fail("Click Get Item before adding the row.")
	if (dependentAttribute.value && !attributeValues[dependentAttribute.value]) return fail(`${dependentAttribute.value} is required.`)
	for (const attribute of nonPrimaryAttributes.value) if (!attributeValues[attribute]) return fail(`${attribute} is required.`)

	const valueKeys = activePrimaryValues.value.length ? activePrimaryValues.value : ["default"]
	const values = {}
	let total = 0
	for (const value of valueKeys) {
		if (props.operation === "stock_reconciliation" && !quantityTouched[value]) continue
		const qty = Number(quantities[value] || 0)
		if (qty < 0) return fail("Quantity cannot be negative.")
		total += qty
		values[value] = { qty }
		if (!editing.value?.row?.values?.[value]) values[value].rate = 0
		if (rateEditable.value) values[value].rate = Number(receiptRates[value] || 0)
		if (offersSecondary.value) {
			values[value].secondary_qty = Number(secondaryQuantities[value] || 0)
			values[value].secondary_uom = itemSchema.value.secondary_uom
		}
	}
	if (props.operation === "stock_reconciliation" && !Object.keys(values).length) return fail("Enter at least one counted quantity. Zero is valid.")
	if (props.operation !== "stock_reconciliation" && total <= 0) return fail("Enter a quantity greater than zero.")

	const row = mergeStockItemDraft(editing.value?.row, {
		...clone(entryValues),
		name: itemSchema.value.item,
		dimensions: clone(dimensionValues),
		attributes: Object.fromEntries(Object.entries(attributeValues).filter(([, value]) => value)),
		primary_attribute: activePrimary.value,
		values,
		default_uom: activeUom.value,
		secondary_uom: itemSchema.value.secondary_uom || "",
		allow_zero_valuation_rate: props.operation === "stock_reconciliation" ? allowZeroValuation.value : false,
	})
	if (props.operation === "lot_transfer") Object.assign(row, clone(dimensionValues))
	if (props.operation === "stock_entry") row.remarks = rowRemarks.value.trim()
	const previousGroups = clone(groups.value)
	setPreparing(true)
	try {
		if (props.rowPreparer) {
			const prepared = await props.rowPreparer(clone(row))
			if (prepared) Object.assign(row, prepared)
		}
		const groupShape = {
			attributes: [...new Set([dependentAttribute.value, ...nonPrimaryAttributes.value].filter(Boolean))],
			primary_attribute: activePrimary.value,
			dependent_attribute: dependentAttribute.value,
			dependent_attribute_details: clone(itemSchema.value.dependent_attribute_details || {}),
			primary_attribute_values: getEntryPrimaryValues(activePrimaryValues.value, row),
		}

		if (editing.value) {
			const old = editing.value
			groups.value[old.groupIndex].items.splice(old.itemIndex, 1)
			if (!groups.value[old.groupIndex].items.length) groups.value.splice(old.groupIndex, 1)
		}
		let group = groups.value.find((candidate) => sameGroup(candidate, groupShape))
		if (!group) {
			group = { ...groupShape, items: [] }
			groups.value.push(group)
		}
		group.items.push(row)
		if (props.groupsPreparer) {
			const prepared = await props.groupsPreparer(clone(groups.value))
			if (prepared) groups.value = clone(prepared)
		}
	} catch (error) {
		groups.value = previousGroups
		return fail(error?.message || "Unable to prepare this item.")
	} finally {
		setPreparing(false)
	}
	commit()
	if (editing.value) resetEditor()
	else {
		rowRemarks.value = ""
		prepareQuantities()
	}
}

async function editItem(groupIndex, itemIndex) {
	if (props.disabled) return
	const group = groups.value[groupIndex]
	const row = clone(group.items[itemIndex])
	editing.value = { groupIndex, itemIndex, row }
	Object.assign(dimensionValues, row.dimensions || {})
	itemName.value = row.name
	editorError.value = ""
	fetching.value = true
	try {
		itemSchema.value = await props.schemaLoader(props.operation, row.name)
		clearReactive(attributeValues)
		Object.assign(attributeValues, row.attributes || {})
		resetEntryValues(row)
		mergeAdditionalParameters()
		allowZeroValuation.value = Boolean(row.allow_zero_valuation_rate)
		rowRemarks.value = row.remarks || ""
		prepareQuantities(row.values || {})
	} catch (error) {
		editorError.value = error.message || "Unable to edit this item."
	} finally {
		fetching.value = false
	}
}

async function removeItem(groupIndex, itemIndex) {
	if (props.disabled) return
	const previousGroups = clone(groups.value)
	setPreparing(true)
	editorError.value = ""
	try {
		groups.value[groupIndex].items.splice(itemIndex, 1)
		if (!groups.value[groupIndex].items.length) groups.value.splice(groupIndex, 1)
		if (props.groupsPreparer) {
			const prepared = await props.groupsPreparer(clone(groups.value))
			if (prepared) groups.value = clone(prepared)
		}
		commit()
		if (editing.value?.groupIndex === groupIndex && editing.value?.itemIndex === itemIndex) resetEditor()
	} catch (error) {
		groups.value = previousGroups
		fail(error?.message || "Unable to refresh item prices after removing this item.")
	} finally {
		setPreparing(false)
	}
}

function commit() {
	const value = clone(groups.value)
	emit("update:modelValue", value)
	emit("dirty")
}

function sameGroup(left, right) {
	return left.primary_attribute === right.primary_attribute
		&& left.dependent_attribute === right.dependent_attribute
		&& JSON.stringify([...(left.attributes || [])].sort()) === JSON.stringify([...(right.attributes || [])].sort())
		&& JSON.stringify([...(left.primary_attribute_values || [])].sort()) === JSON.stringify([...(right.primary_attribute_values || [])].sort())
}

function groupKey(group, index) { return `${group.primary_attribute || "default"}-${(group.attributes || []).join("-")}-${index}` }
function rowNote(row) { return props.operation === "purchase_order" ? row.comments : row.remarks }
function rowTotal(row) { return Object.values(row.values || {}).reduce((sum, value) => sum + Number(value?.qty || 0), 0) }
function valueKeys(group) { return [...(group.primary_attribute_values || []), ...(group.primary_attribute ? [] : ["default"])] }
function groupTotals(group) { return getUomTotals(group.items, valueKeys(group)) }
function footerLabelSpan(group) { return 2 + dimensions.value.length + (group.attributes || []).length + (props.operation === "purchase_order" ? 3 : 0) }
function footerLabel(group, bucket) { return groupTotals(group).length > 1 ? `Total · ${bucket.uom || "No UOM"}` : "Total" }
function formatQty(value) { return Number(value || 0).toLocaleString(undefined, { maximumFractionDigits: 3 }) }
function formatMoney(value) { return `${props.currency ? `${props.currency} ` : ""}${Number(value || 0).toLocaleString("en-IN", { maximumFractionDigits: 2 })}` }
const formatDate = (value) => formatDisplayDate(value)
function resetEntryValues(source = props.entryDefaults) {
	clearReactive(entryValues)
	Object.assign(entryValues, clone(props.entryDefaults || {}))
	if (!source || source === props.entryDefaults) return
	for (const key of new Set([...Object.keys(props.entryDefaults || {}), ...(props.entryFields || [])])) {
		if (Object.prototype.hasOwnProperty.call(source, key)) entryValues[key] = clone(source[key])
	}
}
function mergeAdditionalParameters() {
	if (!Object.prototype.hasOwnProperty.call(props.entryDefaults || {}, "additional_parameters")) return
	let current = entryValues.additional_parameters || []
	if (typeof current === "string") {
		try { current = JSON.parse(current || "[]") } catch { current = [] }
	}
	const selected = new Map((current || []).map((row) => [row.additional_parameter_key, row.additional_parameter_value || ""]))
	const configured = (itemSchema.value?.additional_parameters || []).map((row) => ({
		additional_parameter_key: row.additional_parameter_key,
		additional_parameter_value: selected.has(row.additional_parameter_key)
			? selected.get(row.additional_parameter_key)
			: row.additional_parameter_value || "",
	}))
	const configuredKeys = new Set(configured.map((row) => row.additional_parameter_key))
	entryValues.additional_parameters = [
		...configured,
		...(current || []).filter((row) => row.additional_parameter_key && !configuredKeys.has(row.additional_parameter_key)),
	]
}
function fail(message) { editorError.value = message; return false }
function setPreparing(value) { preparing.value = value; emit("preparing-change", value) }
function clearReactive(value) { for (const key of Object.keys(value)) delete value[key] }
function clone(value) { return value === undefined ? {} : JSON.parse(JSON.stringify(value)) }
</script>

<style scoped>
.stock-composer {
	display: grid;
	gap: var(--erp-space-3);
}

.stock-composer__builder,
.stock-composer__staged {
	overflow: hidden;
	border: 1px solid var(--erp-border);
	border-radius: var(--erp-panel-radius);
	background: var(--erp-surface);
	box-shadow: var(--erp-shadow-xs);
}

.stock-composer__heading {
	display: flex;
	align-items: center;
	justify-content: space-between;
	gap: var(--erp-space-3);
	padding: 10px var(--erp-space-3);
	border-bottom: 1px solid var(--erp-border);
	background: var(--erp-surface-soft);
}

.stock-composer__heading h3 {
	margin: 2px 0 0;
	color: var(--erp-text);
	font-size: 14px;
	font-weight: 750;
}

.stock-composer__eyebrow {
	color: var(--erp-accent-dark);
	font-size: var(--erp-font-size-min);
	font-weight: 800;
	letter-spacing: 0.055em;
	text-transform: uppercase;
}

.stock-composer__step {
	display: inline-flex;
	align-items: center;
	gap: 10px;
	color: var(--erp-text-muted);
	font-size: var(--erp-font-size-caption);
}

.stock-composer__step > span {
	display: inline-flex;
	align-items: center;
	gap: 5px;
	white-space: nowrap;
}

.stock-composer__step-number {
	display: grid;
	width: 19px;
	height: 19px;
	color: var(--erp-accent-dark);
	font-size: var(--erp-font-size-min);
	font-weight: 800;
	background: var(--erp-accent-soft);
	border: 1px solid color-mix(in srgb, var(--erp-accent) 18%, var(--erp-border));
	border-radius: 50%;
	place-items: center;
}

.stock-composer__count {
	padding: 3px var(--erp-space-2);
	border-radius: var(--erp-pill-radius);
	background: var(--erp-accent-soft);
	color: var(--erp-accent);
	font-size: var(--erp-font-size-min);
	font-weight: 750;
}

.stock-composer__fields {
	display: grid;
	grid-template-columns: repeat(4, minmax(0, 1fr));
	gap: 10px;
	padding: 12px;
}

.stock-composer__fetch {
	display: flex;
	align-items: flex-end;
}

.stock-composer__fetch :deep(.p-button) {
	width: 100%;
}

.stock-composer__attributes {
	display: grid;
	gap: var(--erp-space-3);
	padding: 0 var(--erp-space-3) var(--erp-space-3);
}

.stock-composer__item-strip {
	display: grid;
	grid-template-columns: repeat(3, minmax(0, 1fr));
	overflow: hidden;
	border: 1px solid var(--erp-border);
	border-radius: var(--erp-control-radius);
	background: var(--erp-surface);
	box-shadow: var(--erp-shadow-xs);
}

.stock-composer__item-strip > div {
	display: grid;
	gap: 2px;
	padding: 9px 11px;
	border-right: 1px solid var(--erp-border);
}

.stock-composer__item-strip > div:last-child {
	border-right: 0;
}

.stock-composer__item-strip span {
	color: var(--erp-text-muted);
	font-size: var(--erp-font-size-min);
	font-weight: 700;
	text-transform: uppercase;
}

.stock-composer__item-strip strong {
	overflow: hidden;
	color: var(--erp-text);
	font-size: 13px;
	text-overflow: ellipsis;
	white-space: nowrap;
}

.stock-composer__attribute-grid {
	display: grid;
	grid-template-columns: repeat(3, minmax(0, 1fr));
	gap: 10px;
}

.stock-composer__quantity-card {
	overflow: hidden;
	border: 1px solid var(--erp-border);
	border-radius: var(--erp-control-radius);
	background: var(--erp-surface);
	box-shadow: var(--erp-shadow-xs);
}

.stock-composer__quantity-card > header {
	display: flex;
	align-items: center;
	justify-content: space-between;
	padding: 9px 11px;
	border-bottom: 1px solid var(--erp-border);
	background: var(--erp-surface-soft);
}

.stock-composer__quantity-card h4 {
	margin: 0;
	color: var(--erp-text);
	font-size: 13px;
}

.stock-composer__quantity-card p {
	margin: 2px 0 0;
	color: var(--erp-text-muted);
	font-size: var(--erp-font-size-min);
}

.stock-composer__quantity-card > header > span {
	padding: 3px 7px;
	border-radius: 6px;
	background: var(--erp-accent-soft);
	color: var(--erp-accent);
	font-size: var(--erp-font-size-min);
	font-weight: 700;
}

.stock-composer__quantity-grid {
	display: grid;
	grid-template-columns: repeat(auto-fit, minmax(112px, 1fr));
}

.stock-composer__quantity-cell {
	display: grid;
	gap: var(--erp-space-1);
	padding: 8px;
	border-right: 1px solid var(--erp-border-subtle);
	border-bottom: 1px solid var(--erp-border-subtle);
}

.stock-composer__quantity-cell:focus-within {
	position: relative;
	z-index: 1;
	background: color-mix(in srgb, var(--erp-accent) 4%, var(--erp-surface));
	box-shadow: inset 0 0 0 1px color-mix(in srgb, var(--erp-accent) 36%, var(--erp-surface));
}

.stock-composer__quantity-cell strong {
	color: var(--erp-text);
	font-size: var(--erp-font-size-caption);
}

.stock-composer__quantity-cell span,
.stock-composer__single-quantity span {
	color: var(--erp-text-muted);
	font-size: var(--erp-font-size-min);
}

.stock-composer input[type="number"] {
	width: 100%;
	height: var(--erp-control-height-compact);
	padding: 5px 7px;
	border: 1px solid var(--erp-border-strong);
	border-radius: 6px;
	background: var(--erp-surface);
	color: var(--erp-text);
	font: inherit;
	font-size: 13px;
	font-variant-numeric: tabular-nums;
}

.stock-composer input[type="number"]:focus {
	border-color: var(--erp-accent);
	outline: 2px solid color-mix(in srgb, var(--erp-accent) 12%, transparent);
}

.stock-composer__single-quantity {
	display: grid;
	grid-template-columns: repeat(2, minmax(0, 220px));
	gap: 10px;
	padding: 10px;
}

.stock-composer__single-quantity label {
	display: grid;
	gap: var(--erp-space-1);
}

.stock-composer__remarks {
	display: grid;
	gap: var(--erp-space-1);
	color: var(--erp-text-muted);
	font-size: var(--erp-font-size-min);
}

.stock-composer__remarks textarea {
	width: 100%;
	padding: 5px 7px;
	border: 1px solid var(--erp-border-strong);
	border-radius: 6px;
	background: var(--erp-surface);
	color: var(--erp-text);
	font: inherit;
	font-size: 13px;
	resize: vertical;
}

.stock-composer__builder-footer {
	display: flex;
	align-items: center;
	justify-content: space-between;
	gap: var(--erp-space-3);
}

.stock-composer__builder-footer > div {
	display: flex;
	gap: 7px;
}

.stock-composer__check {
	display: flex;
	align-items: center;
	gap: 7px;
	color: var(--erp-text-muted);
	font-size: var(--erp-font-size-caption);
}

.stock-composer__check input {
	accent-color: var(--erp-accent);
}

.stock-composer__tables {
	display: grid;
	gap: 10px;
	padding: 10px;
	background: var(--erp-surface-soft);
}

.stock-composer__table-card {
	overflow: hidden;
	border: 1px solid var(--erp-border);
	border-radius: var(--erp-control-radius);
	background: var(--erp-surface);
}

.stock-composer__table-title {
	display: flex;
	align-items: center;
	justify-content: space-between;
	padding: var(--erp-space-2) 10px;
	border-bottom: 1px solid var(--erp-border);
}

.stock-composer__table-title strong {
	color: var(--erp-text);
	font-size: var(--erp-font-size-caption);
}

.stock-composer__table-title span {
	color: var(--erp-text-muted);
	font-size: var(--erp-font-size-min);
}

.stock-composer__table-scroll {
	max-height: 260px;
	overflow: auto;
}

.stock-composer--natural-table-flow .stock-composer__table-scroll {
	max-height: none;
	overflow-x: auto;
	overflow-y: visible;
}

.stock-composer__table-scroll:focus-visible {
	outline: 2px solid var(--erp-accent-dark);
	outline-offset: -2px;
}

@media (max-width: 900px) {
	.stock-composer__table-scroll {
		-webkit-mask-image: linear-gradient(to right, #000 0, #000 calc(100% - 18px), transparent 100%);
		mask-image: linear-gradient(to right, #000 0, #000 calc(100% - 18px), transparent 100%);
	}
}

.stock-composer table {
	width: 100%;
	min-width: 780px;
	border-collapse: collapse;
	font-size: var(--erp-font-size-caption);
}

.stock-composer th {
	position: sticky;
	top: 0;
	padding: 7px var(--erp-space-2);
	border-bottom: 1px solid var(--erp-border-strong);
	background: var(--erp-surface-muted);
	color: var(--erp-text-secondary);
	font-size: var(--erp-font-size-min);
	font-weight: 750;
	letter-spacing: 0.02em;
	text-align: left;
	text-transform: uppercase;
	white-space: nowrap;
}

.stock-composer td {
	padding: 7px var(--erp-space-2);
	border-top: 1px solid var(--erp-border-subtle);
	color: var(--erp-text-secondary);
	white-space: nowrap;
}

.stock-composer__row-note {
	display: block;
	max-width: 220px;
	margin-top: 3px;
	overflow: hidden;
	color: var(--erp-text-muted);
	font-size: var(--erp-font-size-min);
	font-weight: 500;
	text-overflow: ellipsis;
	white-space: nowrap;
}

.stock-composer tbody tr:hover td {
	background: color-mix(in srgb, var(--erp-accent) 3%, var(--erp-surface));
}

.stock-composer td > strong {
	display: block;
	max-width: 260px;
	overflow: hidden;
	color: var(--erp-text);
	font-size: var(--erp-font-size-caption);
	text-overflow: ellipsis;
	white-space: nowrap;
}

.stock-composer__number {
	font-variant-numeric: tabular-nums;
	text-align: right !important;
}

.stock-composer__metric > strong,
.stock-composer__price {
	display: block;
}

.stock-composer__price {
	margin-top: 2px;
	color: var(--erp-text-muted);
	font-size: var(--erp-font-size-min);
	font-weight: 650;
}

.stock-composer__total {
	color: var(--erp-accent) !important;
	font-weight: 750;
}

.stock-composer__footer th,
.stock-composer__footer td {
	position: sticky;
	z-index: 1;
	bottom: 0;
	border-top: 1px solid var(--erp-border-strong);
	background: var(--erp-surface-soft);
	color: var(--erp-text);
	font-weight: 750;
}

.stock-composer__footer th {
	top: auto;
	font-size: var(--erp-font-size-caption);
	text-transform: none;
}

.stock-composer__entry-total {
	margin: 0 var(--erp-space-2) 0 auto;
	color: var(--erp-text);
	font-size: var(--erp-font-size-caption);
	font-variant-numeric: tabular-nums;
}

.stock-composer__actions {
	display: flex;
	justify-content: flex-end;
	gap: 2px;
}

.stock-composer__actions button {
	display: grid;
	width: 36px;
	height: 36px;
	border: 0;
	border-radius: 6px;
	background: transparent;
	color: var(--erp-text-muted);
	place-items: center;
}

.stock-composer__actions button:hover {
	background: var(--erp-accent-soft);
	color: var(--erp-accent);
}

.stock-composer__actions button:focus-visible {
	color: var(--erp-accent-hover);
	background: var(--erp-accent-soft);
	outline: 3px solid color-mix(in srgb, var(--erp-accent) 16%, transparent);
	outline-offset: 1px;
}

.stock-composer__actions button:active {
	transform: translateY(1px);
}

.stock-composer__actions .stock-composer__delete:hover {
	background: var(--erp-danger-soft);
	color: var(--erp-danger);
}

.stock-composer__empty {
	display: flex;
	min-height: 108px;
	align-items: center;
	justify-content: center;
	gap: 10px;
	padding: 28px 22px;
	color: var(--erp-text-muted);
	background: var(--erp-surface);
}

.stock-composer__empty > i {
	display: grid;
	width: 36px;
	height: 36px;
	border-radius: var(--erp-control-radius);
	background: var(--erp-accent-soft);
	color: var(--erp-accent);
	place-items: center;
}

.stock-composer__empty > div {
	display: grid;
	gap: 2px;
}

.stock-composer__empty strong {
	color: var(--erp-text-secondary);
	font-size: 13px;
}

.stock-composer__empty span {
	font-size: var(--erp-font-size-caption);
}

@media (max-width: 980px) {
	.stock-composer__fields,
	.stock-composer__attribute-grid {
		grid-template-columns: repeat(2, minmax(0, 1fr));
	}
}

@media (max-width: 620px) {
	.stock-composer__fields,
	.stock-composer__attribute-grid,
	.stock-composer__item-strip,
	.stock-composer__single-quantity {
		grid-template-columns: 1fr;
	}

	.stock-composer__builder-footer,
	.stock-composer__heading {
		align-items: stretch;
		flex-direction: column;
	}

	.stock-composer__step {
		justify-content: space-between;
		gap: 7px;
	}

	.stock-composer__builder-footer > div {
		justify-content: flex-end;
	}

	.stock-composer__builder-footer > div :deep(.p-button) {
		flex: 1 1 auto;
	}
}
</style>
