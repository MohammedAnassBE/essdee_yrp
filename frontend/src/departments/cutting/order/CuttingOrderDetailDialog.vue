<template>
	<Dialog
		:visible="visible"
		modal
		dismissable-mask
		maximizable
		:header="'Cutting Order Detail'"
		class="cutting-order-detail-dialog erp-entity-dialog"
		@update:visible="requestVisible"
	>
		<div v-if="loading" class="detail-loading"><Skeleton v-for="index in 7" :key="index" height="3rem" /></div>
		<div v-else class="detail-editor">
			<Message v-if="error" severity="error" :closable="false">{{ error }}</Message>
			<div class="detail-identity">
				<div><span>{{ form.name || "New detail" }}</span><strong>{{ form.item || "Item not selected" }}</strong></div>
				<Tag v-if="form.version" :value="`Version ${form.version}`" severity="secondary" rounded />
			</div>

			<Tabs v-model:value="activeTab" class="erp-tabs detail-tabs">
				<TabList>
					<Tab value="setup">Setup</Tab>
					<Tab value="colours">Colours</Tab>
					<Tab value="panels">Panels</Tab>
					<Tab value="cloth">Cloth</Tab>
					<Tab value="combinations">Combinations</Tab>
				</TabList>
				<TabPanels>
					<TabPanel value="setup">
						<section class="detail-section">
							<div class="detail-fields">
								<label><span>Item *</span><InputText v-model="form.item" :disabled="!canEdit || Boolean(form.name)" fluid /></label>
								<label><span>Attribute No</span><InputNumber v-model="form.attribute_no" :min="0" :disabled="!canEdit" fluid /></label>
								<label class="check-field"><Checkbox v-model="form.is_set_item" binary :true-value="1" :false-value="0" :disabled="!canEdit" /><span>Set Item</span></label>
								<label v-if="form.is_set_item"><span>Set Item Attribute</span><InputText v-model="form.set_item_attribute" :disabled="!canEdit" fluid /></label>
								<label v-if="form.is_set_item"><span>Major Attribute Value</span><InputText v-model="form.major_attribute_value" :disabled="!canEdit" fluid /></label>
								<label><span>Major Panel Value</span><InputText v-model="form.major_panel_value" :disabled="!canEdit" fluid /></label>
								<label class="check-field"><Checkbox v-model="form.is_same_colour" binary :true-value="1" :false-value="0" :disabled="!canEdit" /><span>Same colour for panels</span></label>
							</div>
						</section>
						<section class="detail-section">
							<header><div><h3>Item Attributes</h3><small>Attribute mappings and their available values.</small></div><Button v-if="canEdit" label="Add Attribute" icon="pi pi-plus" text size="small" @click="addAttribute" /></header>
							<div class="table-scroll" role="region" tabindex="0" aria-label="Item attribute mappings"><table v-entry-table="{ add: canEdit ? addAttribute : null }" class="detail-table"><thead><tr><th>Attribute</th><th>Mapping</th><th>Values (comma separated)</th><th v-if="canEdit"></th></tr></thead><tbody><tr v-for="(row, index) in attributes" :key="row._row_key || index"><td><InputText v-model="row.attribute" :aria-label="`Attribute row ${index + 1}`" :disabled="!canEdit || Boolean(row._row_key && !row._row_key.startsWith('new:'))" fluid /></td><td>{{ row.mapping || "Created on save" }}</td><td><InputText v-model="row.valuesText" :aria-label="`Values for attribute row ${index + 1}`" :disabled="!canEdit" fluid /></td><td v-if="canEdit"><Button icon="pi pi-trash" severity="danger" text rounded :aria-label="`Remove attribute row ${index + 1}`" @click="attributes.splice(index, 1)" /></td></tr></tbody></table></div>
							<div v-if="!attributes.length" class="detail-empty">Save the item once to load its default attributes.</div>
						</section>
					</TabPanel>

					<TabPanel value="colours">
						<RowEditor title="Colour Values" add-label="Add Colour" :editable="canEdit" :rows="colours" @add="colours.push({ attribute_value: '' })" @remove="colours.splice($event, 1)">
							<template #header><th>Colour</th></template>
							<template #row="{ row, index }"><td><InputText v-model="row.attribute_value" :aria-label="`Colour row ${index + 1}`" :disabled="!canEdit" fluid /></td></template>
						</RowEditor>
					</TabPanel>

					<TabPanel value="panels">
						<RowEditor title="Panel Details" add-label="Add Panel" :editable="canEdit" :rows="panels" @add="panels.push({ stiching_attribute_value: '', set_item_attribute_value: '', quantity: 1, is_default: 0 })" @remove="panels.splice($event, 1)">
							<template #header><th>Panel</th><th v-if="form.is_set_item">Part</th><th>Quantity</th><th v-if="form.is_set_item">Default</th></template>
							<template #row="{ row, index }"><td><InputText v-model="row.stiching_attribute_value" :aria-label="`Panel row ${index + 1}`" :disabled="!canEdit" fluid /></td><td v-if="form.is_set_item"><InputText v-model="row.set_item_attribute_value" :aria-label="`Part for panel row ${index + 1}`" :disabled="!canEdit" fluid /></td><td><InputNumber v-model="row.quantity" :aria-label="`Quantity for panel row ${index + 1}`" :min="1" :disabled="!canEdit" fluid /></td><td v-if="form.is_set_item"><Checkbox v-model="row.is_default" binary :true-value="1" :false-value="0" :disabled="!canEdit" :aria-label="`Use panel row ${index + 1} as default`" /></td></template>
						</RowEditor>
					</TabPanel>

					<TabPanel value="cloth">
						<RowEditor title="Cloth Details" add-label="Add Cloth" :editable="canEdit" :rows="clothDetails" @add="clothDetails.push({ name1: '', dia: [], diaText: '' })" @remove="clothDetails.splice($event, 1)">
							<template #header><th>Cloth Type</th><th>Dia (comma separated)</th></template>
							<template #row="{ row, index }"><td><InputText v-model="row.name1" :aria-label="`Cloth type row ${index + 1}`" :disabled="!canEdit" fluid /></td><td><InputText v-model="row.diaText" :aria-label="`Dia values for cloth row ${index + 1}`" :disabled="!canEdit" fluid /></td></template>
						</RowEditor>
					</TabPanel>

					<TabPanel value="combinations">
						<div v-if="canEdit" class="combination-actions"><Button label="Generate from Setup" icon="pi pi-sync" severity="secondary" outlined size="small" :loading="saving" @click="save(true)" /></div>
						<CombinationMatrix v-if="form.is_set_item" title="Set Item Combination" :model="setCombination" :editable="canEdit" />
						<CombinationMatrix title="Panel Combination" :model="stitchingCombination" :editable="canEdit" />
						<div v-if="!setCombination.values?.length && !stitchingCombination.values?.length" class="detail-empty">Combination values are generated from the saved attribute, colour, and panel setup.</div>
					</TabPanel>
				</TabPanels>
			</Tabs>
		</div>

		<template #footer>
			<Button label="Close" severity="secondary" text :disabled="saving" @click="requestVisible(false)" />
			<Button v-if="canEdit" label="Save Detail" icon="pi pi-save" :loading="saving" :disabled="!form.item" @click="save(false)" />
		</template>
	</Dialog>

	<Dialog v-model:visible="discardVisible" class="erp-dialog--sm" header="Discard unsaved changes?" modal :closable="false">
		<p class="discard-copy">Your Cutting Order Detail changes will be lost.</p>
		<template #footer><Button label="Keep Editing" severity="secondary" text @click="discardVisible = false" /><Button label="Discard Changes" severity="danger" @click="discard" /></template>
	</Dialog>
	<DocumentErrorDialog :message="actionError" title="Cutting Order Detail could not be saved" @dismiss="actionError = ''" />
</template>

<script setup>
import Button from "primevue/button"
import Checkbox from "primevue/checkbox"
import Dialog from "primevue/dialog"
import InputNumber from "primevue/inputnumber"
import InputText from "primevue/inputtext"
import Message from "primevue/message"
import Skeleton from "primevue/skeleton"
import Tab from "primevue/tab"
import TabList from "primevue/tablist"
import TabPanel from "primevue/tabpanel"
import TabPanels from "primevue/tabpanels"
import Tabs from "primevue/tabs"
import Tag from "primevue/tag"
import { computed, defineComponent, h, reactive, ref, watch, withDirectives } from "vue"
import { vEntryTable } from "../../../components/common/childGrid/entryTable.js"

import { getCuttingOrderDetail, saveCuttingOrderDetail } from "../../../api/cuttingOrder.js"
import DocumentErrorDialog from "../../../components/documents/DocumentErrorDialog.vue"

const props = defineProps({ visible: Boolean, name: { type: String, default: "" }, item: { type: String, default: "" } })
const emit = defineEmits(["update:visible", "saved"])
const activeTab = ref("setup")
const loading = ref(false)
const saving = ref(false)
const error = ref("")
const actionError = ref("")
const discardVisible = ref(false)
const pendingClose = ref(false)
const form = reactive(emptyForm())
const attributes = ref([])
const colours = ref([])
const panels = ref([])
const clothDetails = ref([])
const setCombination = reactive({ attributes: [], values: [] })
const stitchingCombination = reactive({ attributes: [], values: [] })
const permissions = reactive({ can_create: false, can_write: false })
const cleanSignature = ref("")
const canEdit = computed(() => form.name ? permissions.can_write : permissions.can_create)
const signature = computed(() => JSON.stringify(payloadValues()))
const dirty = computed(() => !loading.value && signature.value !== cleanSignature.value)

watch(() => [props.visible, props.name], ([visible]) => { if (visible) load() })

async function load() {
	loading.value = true
	error.value = ""
	actionError.value = ""
	try { applyPayload(await getCuttingOrderDetail(props.name, props.item)) }
	catch (reason) { error.value = reason?.message || "Unable to load the Cutting Order Detail." }
	finally { loading.value = false; cleanSignature.value = signature.value }
}

function applyPayload(payload) {
	Object.assign(form, emptyForm(), payload?.record || {})
	attributes.value = clone(payload?.attributes || []).map((row) => ({ ...row, valuesText: (row.values || []).join(", ") }))
	colours.value = clone(payload?.colours || [])
	panels.value = clone(payload?.panels || [])
	clothDetails.value = clone(payload?.cloth_details || []).map((row) => ({ ...row, diaText: (row.dia || []).join(", ") }))
	Object.assign(setCombination, { attributes: [], values: [] }, clone(payload?.set_item_combination || {}))
	Object.assign(stitchingCombination, { attributes: [], values: [] }, clone(payload?.stiching_combination || {}))
	Object.assign(permissions, { can_create: false, can_write: false }, payload?.permissions || {})
	cleanSignature.value = signature.value
}

async function save(regenerateCombinations = false) {
	saving.value = true
	error.value = ""
	try {
		const values = { ...payloadValues(), regenerate_combinations: regenerateCombinations }
		const payload = await saveCuttingOrderDetail(values, { name: form.name, expectedModified: form.modified })
		applyPayload(payload)
		emit("saved", payload)
	} catch (reason) { actionError.value = reason?.message || "Unable to save the Cutting Order Detail." }
	finally { saving.value = false }
}

function payloadValues() {
	return {
		item: form.item,
		attribute_no: form.attribute_no,
		is_set_item: form.is_set_item,
		set_item_attribute: form.is_set_item ? form.set_item_attribute : null,
		major_attribute_value: form.is_set_item ? form.major_attribute_value : null,
		major_panel_value: form.major_panel_value,
		is_same_colour: form.is_same_colour,
		attributes: attributes.value.map(({ valuesText, ...row }) => ({ ...row, values: splitValues(valuesText) })),
		colours: colours.value,
		panels: panels.value,
		cloth_details: clothDetails.value.map(({ diaText, ...row }) => ({ ...row, dia: splitValues(diaText) })),
		set_item_combination: setCombination,
		stiching_combination: stitchingCombination,
	}
}

function requestVisible(value) {
	if (value) return emit("update:visible", true)
	if (dirty.value) { pendingClose.value = true; discardVisible.value = true; return }
	emit("update:visible", false)
}

function discard() {
	discardVisible.value = false
	if (pendingClose.value) emit("update:visible", false)
	pendingClose.value = false
}

function addAttribute() { attributes.value.push({ attribute: "", mapping: "", valuesText: "" }) }
function splitValues(value) { return String(value || "").split(",").map((item) => item.trim()).filter(Boolean) }
function clone(value) { return JSON.parse(JSON.stringify(value ?? null)) }
function emptyForm() { return { name: "", modified: "", item: "", version: 0, attribute_no: 0, is_set_item: 0, set_item_attribute: "", major_attribute_value: "", major_panel_value: "", is_same_colour: 0 } }

const RowEditor = defineComponent({
	props: { title: String, addLabel: String, editable: Boolean, rows: { type: Array, default: () => [] } },
	emits: ["add", "remove"],
	setup(componentProps, { slots, emit: childEmit }) {
		return () => h("section", { class: "detail-section row-editor" }, [
			h("header", [h("h3", componentProps.title), componentProps.editable ? h(Button, { label: componentProps.addLabel, icon: "pi pi-plus", text: true, size: "small", onClick: () => childEmit("add") }) : null]),
			componentProps.rows.length ? h("div", { class: "table-scroll", role: "region", tabindex: 0, "aria-label": componentProps.title }, withDirectives(h("table", { class: "detail-table" }, [
				h("thead", h("tr", [h("th", "S.No."), slots.header?.(), componentProps.editable ? h("th") : null])),
				h("tbody", componentProps.rows.map((row, index) => h("tr", { key: row._row_key || index }, [h("td", index + 1), slots.row?.({ row, index }), componentProps.editable ? h("td", h(Button, { icon: "pi pi-trash", severity: "danger", text: true, rounded: true, "aria-label": `Remove ${componentProps.title || "detail"} row ${index + 1}`, onClick: () => childEmit("remove", index) })) : null]))),
			]), [[vEntryTable, { add: componentProps.editable ? () => childEmit("add") : null }]])) : h("div", { class: "detail-empty" }, `No ${String(componentProps.title || "rows").toLowerCase()} yet.`),
		])
	},
})

const CombinationMatrix = defineComponent({
	props: { title: String, model: Object, editable: Boolean },
	setup(componentProps) {
		return () => h("section", { class: "detail-section combination-section" }, [
			h("header", h("h3", componentProps.title)),
			componentProps.model?.values?.length ? h("div", { class: "table-scroll", role: "region", tabindex: 0, "aria-label": componentProps.title }, h("table", { class: "detail-table combination-table" }, [
				h("thead", h("tr", [h("th", "Major Value"), ...(componentProps.model.attributes || []).map((attribute) => h("th", attribute))])),
				h("tbody", componentProps.model.values.map((row, index) => h("tr", { key: `${row.major_attribute}-${index}` }, [
					h("td", row.major_attribute),
					...(componentProps.model.attributes || []).map((attribute) => h("td", componentProps.editable ? h(InputText, { modelValue: row.val?.[attribute] || "", "aria-label": `${attribute} for ${row.major_attribute || `combination row ${index + 1}`}`, "onUpdate:modelValue": (value) => { row.val ||= {}; row.val[attribute] = value }, fluid: true }) : (row.val?.[attribute] || "—"))),
				]))),
			])) : h("div", { class: "detail-empty" }, "No combinations generated."),
		])
	},
})
</script>

<style scoped>
.detail-loading { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 12px; }
.detail-editor { display: grid; gap: 12px; min-width: 0; }
.detail-identity { display: flex; align-items: center; justify-content: space-between; gap: 12px; padding: 10px 12px; background: var(--erp-surface-soft); border: 1px solid var(--erp-border); border-radius: var(--erp-control-radius); }
.detail-identity > div { display: grid; gap: 2px; min-width: 0; }
.detail-identity span { color: var(--erp-text-muted); font-size: var(--erp-font-size-min); font-weight: 700; text-transform: uppercase; }
.detail-identity strong { overflow: hidden; color: var(--erp-text); font-size: 0.92rem; text-overflow: ellipsis; white-space: nowrap; }
.detail-tabs :deep(.p-tabpanels) { padding: 12px 0 0; }
.detail-section { display: grid; gap: 12px; min-width: 0; padding: 14px; background: var(--erp-surface); border: 1px solid var(--erp-border); border-radius: var(--erp-panel-radius); }
.detail-section + .detail-section { margin-top: 12px; }
.detail-section > header { display: flex; align-items: center; justify-content: space-between; gap: 12px; }
.detail-section header > div { display: grid; gap: 2px; }
.detail-section h3 { margin: 0; color: var(--erp-text); font-size: var(--erp-font-size-body); }
.detail-section small { color: var(--erp-text-muted); font-size: var(--erp-font-size-min); }
.detail-fields { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 12px 16px; }
.detail-fields label { display: grid; gap: 5px; color: var(--erp-text); font-size: var(--erp-font-size-caption); font-weight: 680; }
.detail-fields .check-field { display: flex; align-items: center; gap: 8px; min-height: var(--erp-control-height); padding-top: 20px; }
.table-scroll { max-width: 100%; overflow: auto; border: 1px solid var(--erp-border); border-radius: var(--erp-control-radius); }
.table-scroll:focus-visible { outline: 2px solid var(--erp-accent-dark); outline-offset: -2px; }
.detail-table { width: 100%; min-width: 680px; border-collapse: collapse; font-size: var(--erp-font-size-caption); }
.detail-table th, .detail-table td { padding: 8px 9px; text-align: left; border-right: 1px solid var(--erp-border); border-bottom: 1px solid var(--erp-border); }
.detail-table th { color: var(--erp-text-muted); font-size: var(--erp-font-size-min); font-weight: 750; background: var(--erp-surface-muted); }
.detail-table th:last-child, .detail-table td:last-child { border-right: 0; }
.detail-table tr:last-child td { border-bottom: 0; }
.detail-table td:first-child { width: 58px; color: var(--erp-text-muted); }
.detail-empty { display: grid; min-height: 88px; color: var(--erp-text-muted); font-size: var(--erp-font-size-caption); background: var(--erp-surface-soft); border: 1px dashed var(--erp-border-strong); border-radius: var(--erp-control-radius); place-items: center; }
.combination-section + .combination-section { margin-top: 12px; }
.combination-actions { display: flex; margin-bottom: 12px; justify-content: flex-end; }
.discard-copy { margin: 0; color: var(--erp-text-muted); }
:global(.cutting-order-detail-dialog) { width: min(96vw, 1180px); }
@media (max-width: 800px) { .detail-fields, .detail-loading { grid-template-columns: 1fr; } .table-scroll { -webkit-mask-image: linear-gradient(to right, #000 0, #000 calc(100% - 18px), transparent 100%); mask-image: linear-gradient(to right, #000 0, #000 calc(100% - 18px), transparent 100%); } }
</style>
