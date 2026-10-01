<template>
	<Dialog :visible="visible" modal dismissable-mask maximizable :header="sheet ? `Lay Sheet · ${sheet.name}` : 'Create Lay Sheet'" class="laysheet-dialog" @update:visible="emit('update:visible', $event)">
		<div v-if="loading" class="laysheet-loading"><Skeleton v-for="index in 8" :key="index" height="3.2rem" /></div>
		<div v-else-if="!sheet" class="laysheet-create">
			<Message v-if="error" severity="error" :closable="false">{{ error }}</Message>
			<div class="create-intro"><i class="pi pi-list-check"></i><div><strong>Start a new Lay Sheet</strong><span>Select the submitted marker and cutting team. System dates are recorded automatically.</span></div></div>
			<div class="create-fields">
				<LinkField v-model="createForm.cutting_marker" label="Cutting Marker *" help-text="Search by marker name or ID." doctype="SD YRP Cutting Marker" :filters="{ cutting_plan: cuttingPlan, docstatus: 1 }" :show-open-button="false" />
				<LinkField v-model="createForm.cutting_spreader" label="Cutting Spreader *" doctype="SD YRP Cutting Spreader" :show-open-button="false" />
				<LinkField v-model="createForm.cutter" label="Cutter *" doctype="SD YRP Cutter" :show-open-button="false" />
			</div>
		</div>
		<div v-else-if="sheet" class="laysheet-content">
			<Message v-if="error" severity="error" :closable="false">{{ error }}</Message>
			<Message v-if="success" severity="success" :closable="false">{{ success }}</Message>

			<div class="laysheet-summary">
				<div><span>Lay No</span><strong>{{ sheet.lay_no ?? '—' }}</strong></div>
				<div><span>Marker</span><strong>{{ sheet.marker_name || sheet.cutting_marker || '—' }}</strong></div>
				<div><span>Status</span><strong><span class="status-pill" :class="statusClass">{{ sheet.status || '—' }}</span></strong></div>
				<div><span>Bundles</span><strong>{{ sheet.bundles?.length || 0 }}</strong></div>
			</div>

			<Tabs v-model:value="activeTab">
				<TabList><Tab value="details">Details</Tab><Tab value="cloth">Cloth Details</Tab><Tab value="ratios">Marker Ratios</Tab><Tab value="bundles">Bundles</Tab></TabList>
				<TabPanels>
					<TabPanel value="details">
						<div class="detail-grid"><div v-for="item in detailRows" :key="item.label"><span>{{ item.label }}</span><strong>{{ display(item.value) }}</strong></div></div>
					</TabPanel>
					<TabPanel value="cloth">
						<Message v-if="detailError" severity="error" :closable="false">{{ detailError }}</Message>
						<section class="data-block editable-data-block">
							<header><div class="data-block__title"><h3>Cloth Details</h3><span>{{ sheet.cloth_details?.length || 0 }} rows</span></div><Button v-if="canEditDetails" label="Add Cloth" icon="pi pi-plus" size="small" @click="openClothEditor()" /></header>
							<div v-if="sheet.cloth_details?.length" class="table-scroll"><table class="laysheet-table"><thead><tr><th>S.No.</th><th v-for="item in clothColumns" :key="item.field">{{ item.label }}</th><th v-if="canEditDetails">Actions</th></tr></thead><tbody><tr v-for="(row, index) in sheet.cloth_details" :key="row.name || index"><td>{{ index + 1 }}</td><td v-for="item in clothColumns" :key="item.field">{{ item.format(row[item.field]) }}</td><td v-if="canEditDetails" class="row-actions"><Button icon="pi pi-pencil" severity="secondary" text rounded aria-label="Edit cloth" @click="openClothEditor(row, index)" /><Button icon="pi pi-trash" severity="danger" text rounded aria-label="Delete cloth" :loading="detailBusy === `cloth-${index}`" @click="deleteCloth(index)" /></td></tr></tbody></table></div>
							<div v-else class="empty-data">No cloth details yet.</div>
						</section>
						<section class="data-block editable-data-block">
							<header><div class="data-block__title"><h3>Accessory Details</h3><span>{{ sheet.accessory_details?.length || 0 }} rows</span></div><Button v-if="canEditDetails" label="Add Accessory" icon="pi pi-plus" size="small" :disabled="!editorAccessories.length" :title="editorAccessories.length ? 'Add accessory detail' : 'No cloth accessories are configured for this plan'" @click="openAccessoryEditor()" /></header>
							<div v-if="sheet.accessory_details?.length" class="table-scroll"><table class="laysheet-table"><thead><tr><th>S.No.</th><th v-for="item in accessoryColumns" :key="item.field">{{ item.label }}</th><th v-if="canEditDetails">Actions</th></tr></thead><tbody><tr v-for="(row, index) in sheet.accessory_details" :key="row.name || index"><td>{{ index + 1 }}</td><td v-for="item in accessoryColumns" :key="item.field">{{ item.format(row[item.field]) }}</td><td v-if="canEditDetails" class="row-actions"><Button icon="pi pi-pencil" severity="secondary" text rounded aria-label="Edit accessory" @click="openAccessoryEditor(row, index)" /><Button icon="pi pi-trash" severity="danger" text rounded aria-label="Delete accessory" :loading="detailBusy === `accessory-${index}`" @click="deleteAccessory(index)" /></td></tr></tbody></table></div>
							<div v-else class="empty-data">No accessory details yet.</div>
						</section>
					</TabPanel>
					<TabPanel value="ratios"><DataBlock title="Marker Ratios" :rows="sheet.ratios" :columns="ratioColumns" /></TabPanel>
					<TabPanel value="bundles"><DataBlock title="Cut Bundles" :rows="sheet.bundles" :columns="bundleColumns" /></TabPanel>
				</TabPanels>
			</Tabs>
		</div>

		<template #footer>
			<div class="laysheet-footer">
				<div class="laysheet-footer__secondary">
					<DocumentPrintButton
						v-if="sheet && (sheet.permissions?.can_print_laysheet || sheet.permissions?.can_print_movement_chart)"
						doctype="SD YRP Cutting LaySheet"
						:name="sheet.name"
						:formats="sheet.print_formats || []"
						:disabled="Boolean(busy)"
					/>
				</div>
				<div class="laysheet-footer__primary">
					<Button label="Close" severity="secondary" text :disabled="Boolean(busy)" @click="emit('update:visible', false)" />
					<Button v-if="!sheet && canCreate" label="Create Lay Sheet" icon="pi pi-plus" :loading="busy === 'create'" @click="createLaySheet" />
					<Button v-if="sheet?.permissions?.can_revert_labels" label="Revert Labels" severity="warn" outlined :loading="busy === 'revert'" @click="runStatusAction('revert_labels', 'revert')" />
					<Button v-if="sheet?.permissions?.can_restore_labels" label="Restore Label Status" severity="secondary" outlined :loading="busy === 'restore'" @click="runStatusAction('update_label_print_status', 'restore')" />
					<Button v-if="sheet?.permissions?.can_cancel" label="Cancel Lay Sheet" icon="pi pi-ban" severity="danger" outlined :loading="busy === 'cancel'" @click="cancelLaySheet" />
					<Button v-if="sheet?.permissions?.can_approve" label="Approve Grammage" icon="pi pi-check" :loading="busy === 'approve'" @click="runStatusAction('approve_grammage', 'approve')" />
					<Button v-if="sheet?.permissions?.can_generate" label="Generate Bundles" icon="pi pi-box" outlined @click="openGenerate" />
					<Button v-if="sheet?.permissions?.can_print_labels" label="Print Labels" icon="pi pi-print" @click="openPrinter" />
				</div>
			</div>
		</template>
	</Dialog>

	<Dialog v-model:visible="generateOpen" modal dismissable-mask header="Generate Bundles" class="laysheet-subdialog">
		<div class="subdialog-stack">
			<Message v-if="subdialogError" severity="error" :closable="false">{{ subdialogError }}</Message>
			<label><span>Bundle Generated Date *</span><DatePicker v-model="bundleDate" date-format="yy-mm-dd" show-icon fluid /></label>
			<div class="generation-numbers">
				<label v-if="!sheet?.is_manual_entry"><span>Maximum No of Plys *</span><InputNumber v-model="maximumPlys" :min="1" fluid /></label>
				<label v-if="!sheet?.is_manual_entry"><span>Maximum Allow Percent *</span><InputNumber v-model="maximumAllow" :min="0" suffix="%" fluid /></label>
			</div>
			<div class="table-scroll"><table class="laysheet-table"><thead><tr><th>Panel</th><th>Bundle Group</th></tr></thead><tbody><tr v-for="(row, index) in generationParts" :key="row.part"><td>{{ row.part }}</td><td><InputNumber v-model="row.value" :min="1" :disabled="busy === 'generate'" fluid /></td></tr></tbody></table></div>
		</div>
		<template #footer><Button label="Close" severity="secondary" text @click="generateOpen = false" /><Button label="Generate" icon="pi pi-box" :loading="busy === 'generate'" @click="generateBundles" /></template>
	</Dialog>

	<Dialog v-model:visible="printerOpen" modal dismissable-mask header="Print Labels" class="laysheet-subdialog">
		<div class="subdialog-stack">
			<Message v-if="subdialogError" severity="error" :closable="false">{{ subdialogError }}</Message>
			<div v-if="loadingPrinters" class="printer-loading"><i class="pi pi-spin pi-spinner"></i><span>Connecting to QZ Tray and finding printers…</span></div>
			<template v-else>
				<label><span>Printer *</span><Select v-model="selectedPrinter" :options="printers" filter placeholder="Select printer" fluid /></label>
				<label><span>Print Order By</span><Select v-model="printOrder" :options="['Panel', 'Bundle No']" fluid /></label>
			</template>
		</div>
		<template #footer><Button label="Close" severity="secondary" text @click="printerOpen = false" /><Button label="Print" icon="pi pi-print" :disabled="!selectedPrinter || loadingPrinters" :loading="busy === 'print'" @click="printLabels" /></template>
	</Dialog>

	<Dialog v-model:visible="clothEditorOpen" modal dismissable-mask :header="clothEditIndex < 0 ? 'Add Cloth Detail' : 'Edit Cloth Detail'" class="laysheet-detail-dialog">
		<div class="detail-editor">
			<Message v-if="editorError" severity="error" :closable="false">{{ editorError }}</Message>
			<div class="detail-editor__grid">
				<label><span>Cloth Type *</span><Select v-model="clothForm.cloth_type" :options="editorAttributes.cloth_type" filter fluid @change="clothTypeChanged" /></label>
				<label><span>Colour *</span><Select v-model="clothForm.colour" :options="editorAttributes.colour" filter fluid @change="loadSetFields()" /></label>
				<label><span>Dia *</span><Select v-model="clothForm.dia" :options="clothDiaOptions" filter fluid @change="clothDiaChanged" /></label>
				<label><span>Actual Dia *</span><Select v-model="clothForm.actual_dia" :options="clothDiaOptions" filter fluid /></label>
				<label><span>Shade *</span><InputText v-model="clothForm.shade" fluid /></label>
				<label><span>Fabric Type *</span><Select v-model="clothForm.fabric_type" :options="['Open Width', 'Tubler']" fluid /></label>
				<label><span>Weight (kg) *</span><InputNumber v-model="clothForm.weight" :min="0" :max-fraction-digits="3" fluid /></label>
				<label><span>Balance Weight (kg) *</span><InputNumber v-model="clothForm.balance_weight" :min="0" :max-fraction-digits="3" fluid /></label>
				<label><span>No of Rolls *</span><InputNumber v-model="clothForm.no_of_rolls" :min="0" fluid /></label>
				<label v-if="!sheet?.is_manual_entry"><span>No of Bits *</span><InputNumber v-model="clothForm.no_of_bits" :min="0" fluid /></label>
				<label v-if="!sheet?.is_manual_entry"><span>End Bit Weight (kg) *</span><InputNumber v-model="clothForm.end_bit_weight" :min="0" :max-fraction-digits="3" fluid /></label>
				<label v-for="field in visibleSetFields" :key="field.fieldname"><span>{{ field.label }}{{ field.default === undefined || field.default === null || field.default === '' ? ' *' : '' }}</span><Select v-if="field.fieldtype === 'Select'" v-model="clothForm.set_combination[field.fieldname]" :options="fieldOptions(field)" :disabled="hasFieldDefault(field)" filter fluid /><InputText v-else v-model="clothForm.set_combination[field.fieldname]" :disabled="hasFieldDefault(field)" fluid /></label>
				<label v-if="!sheet?.is_manual_entry" class="detail-editor__wide"><span>Comments</span><Textarea v-model="clothForm.comments" rows="2" fluid /></label>
			</div>
		</div>
		<template #footer><Button label="Close" severity="secondary" text :disabled="detailBusy === 'cloth-save'" @click="clothEditorOpen = false" /><Button :label="clothEditIndex < 0 ? 'Add Cloth' : 'Update Cloth'" icon="pi pi-check" :loading="detailBusy === 'cloth-save'" @click="saveCloth" /></template>
	</Dialog>

	<Dialog v-model:visible="accessoryEditorOpen" modal dismissable-mask :header="accessoryEditIndex < 0 ? 'Add Accessory Detail' : 'Edit Accessory Detail'" class="laysheet-detail-dialog">
		<div class="detail-editor">
			<Message v-if="editorError" severity="error" :closable="false">{{ editorError }}</Message>
			<div class="detail-editor__grid">
				<label><span>Accessory *</span><Select v-model="accessoryForm.accessory" :options="editorAccessories" filter fluid /></label>
				<label><span>Cloth Type *</span><Select v-model="accessoryForm.cloth_type" :options="editorAttributes.cloth_type" filter fluid @change="accessoryClothTypeChanged" /></label>
				<label><span>Colour *</span><Select v-model="accessoryForm.colour" :options="editorAttributes.colour" filter fluid /></label>
				<label><span>Dia *</span><Select v-model="accessoryForm.dia" :options="accessoryDiaOptions" filter fluid @change="accessoryDiaChanged" /></label>
				<label><span>Actual Dia *</span><Select v-model="accessoryForm.actual_dia" :options="accessoryDiaOptions" filter fluid /></label>
				<label><span>Shade *</span><InputText v-model="accessoryForm.shade" fluid /></label>
				<label><span>Weight (kg) *</span><InputNumber v-model="accessoryForm.weight" :min="0" :max-fraction-digits="3" fluid /></label>
				<label><span>No of Rolls *</span><InputNumber v-model="accessoryForm.no_of_rolls" :min="0" fluid /></label>
			</div>
		</div>
		<template #footer><Button label="Close" severity="secondary" text :disabled="detailBusy === 'accessory-save'" @click="accessoryEditorOpen = false" /><Button :label="accessoryEditIndex < 0 ? 'Add Accessory' : 'Update Accessory'" icon="pi pi-check" :loading="detailBusy === 'accessory-save'" @click="saveAccessory" /></template>
	</Dialog>
</template>

<script setup>
import Button from "primevue/button"
import DatePicker from "primevue/datepicker"
import Dialog from "primevue/dialog"
import InputNumber from "primevue/inputnumber"
import InputText from "primevue/inputtext"
import Message from "primevue/message"
import Select from "primevue/select"
import Skeleton from "primevue/skeleton"
import Tab from "primevue/tab"
import TabList from "primevue/tablist"
import TabPanel from "primevue/tabpanel"
import TabPanels from "primevue/tabpanels"
import Tabs from "primevue/tabs"
import Textarea from "primevue/textarea"
import { computed, defineComponent, h, reactive, ref, watch } from "vue"

import { callMethod } from "../../api/frappe.js"
import { getQzPrinters, printQzRaw } from "../../api/qzPrinter.js"
import LinkField from "../../components/common/LinkField.vue"
import DocumentPrintButton from "./DocumentPrintButton.vue"

const props = defineProps({
	visible: Boolean,
	cuttingPlan: { type: String, required: true },
	laysheetName: { type: String, default: "" },
	canCreate: { type: Boolean, default: false },
})
const emit = defineEmits(["update:visible", "changed"])

const loading = ref(false)
const busy = ref("")
const error = ref("")
const success = ref("")
const sheet = ref(null)
const activeTab = ref("details")
const generateOpen = ref(false)
const generationParts = ref([])
const bundleDate = ref(new Date())
const maximumPlys = ref(null)
const maximumAllow = ref(null)
const printerOpen = ref(false)
const loadingPrinters = ref(false)
const printers = ref([])
const selectedPrinter = ref("")
const printOrder = ref("Panel")
const subdialogError = ref("")
const createForm = reactive(emptyCreateForm())
const detailError = ref("")
const editorError = ref("")
const detailBusy = ref("")
const clothEditorOpen = ref(false)
const clothEditIndex = ref(-1)
const clothForm = reactive(emptyClothForm())
const setFields = ref([])
const setFieldsSequence = ref(0)
const accessoryEditorOpen = ref(false)
const accessoryEditIndex = ref(-1)
const accessoryForm = reactive(emptyAccessoryForm())

const detailRows = computed(() => {
	const row = sheet.value || {}
	return [
		["Cutting Marker", row.cutting_marker], ["Marker Name", row.marker_name], ["Lay No", row.lay_no],
		["Length (Meters)", number(row.length, 3)], ["Width (Inches)", number(row.width, 3)],
		["Cutting Spreader", row.cutting_spreader], ["Cutter", row.cutter], ["Maximum No of Plys", row.maximum_no_of_plys], ["Maximum Allow Percentage", percent(row.maximum_allow_percentage)],
		["Bundle Generated Date", row.bundle_generated_date], ["Printed Time", row.printed_time],
		["No of Rolls", row.no_of_rolls], ["No of Bits", row.no_of_bits], ["Weight", number(row.weight, 3)], ["Accessory Weight", number(row.accessory_weight, 3)],
		["End Bit Weight", number(row.end_bit_weight, 3)], ["Total Used Weight", number(row.total_used_weight, 3)], ["Total No of Pieces", row.total_no_of_pieces], ["Piece Weight", number(row.piece_weight, 4)],
		["Required Piece Weight", number(row.required_pcs_weight, 4)], ["Approved By", row.approved_by], ["Goods Received Note", row.goods_received_note],
	].map(([label, value]) => ({ label, value }))
})
const statusClass = computed(() => `status-pill--${String(sheet.value?.status || "").toLowerCase().replaceAll(" ", "-")}`)
const canEditDetails = computed(() => Boolean(sheet.value?.permissions?.can_edit_details))
const editorAttributes = computed(() => sheet.value?.editor?.attributes || { cloth_type: [], colour: [], dia: [], cloth_type_dia_map: {} })
const editorAccessories = computed(() => sheet.value?.editor?.accessories || [])
const visibleSetFields = computed(() => setFields.value.filter((field) => !field.hidden))
const clothDiaOptions = computed(() => diaOptions(clothForm.cloth_type))
const accessoryDiaOptions = computed(() => diaOptions(accessoryForm.cloth_type))

const clothColumns = [column("cloth_item_variant", "Cloth"), column("cloth_type", "Cloth Type"), column("colour", "Colour"), column("actual_dia", "Dia"), column("shade", "Shade"), column("weight", "Weight"), column("no_of_rolls", "Rolls"), column("no_of_bits", "Bits"), column("used_weight", "Used Weight"), column("balance_weight", "Balance Weight")]
const accessoryColumns = [column("accessory", "Accessory"), column("cloth_item_variant", "Cloth"), column("cloth_type", "Cloth Type"), column("colour", "Colour"), column("actual_dia", "Dia"), column("shade", "Shade"), column("weight", "Weight"), column("no_of_rolls", "Rolls")]
const ratioColumns = [column("size", "Size"), column("panel", "Panel"), column("ratio", "Ratio")]
const bundleColumns = [column("bundle_no", "Bundle No"), column("size", "Size"), column("colour", "Colour"), column("shade", "Shade"), column("part", "Panel"), column("quantity", "Quantity"), column("is_moved", "Moved", (value) => Number(value) ? "Yes" : "No")]

watch(
	() => [props.visible, props.laysheetName, props.cuttingPlan],
	([visible]) => {
		if (!visible) return
		if (props.laysheetName) load()
		else startCreate()
	},
)

function startCreate() {
	sheet.value = null
	loading.value = false
	busy.value = ""
	error.value = ""
	success.value = ""
	Object.assign(createForm, emptyCreateForm())
}

async function createLaySheet() {
	error.value = ""
	if (!createForm.cutting_marker || !createForm.cutting_spreader || !createForm.cutter) {
		error.value = "Select the Cutting Marker, Cutting Spreader, and Cutter."
		return
	}
	busy.value = "create"
	try {
		sheet.value = await callMethod(laysheetMethod("create_web_laysheet"), {
			cutting_plan: props.cuttingPlan,
			values: createForm,
		})
		activeTab.value = "details"
		success.value = "Lay Sheet created."
		emit("changed", sheet.value)
	} catch (reason) {
		error.value = reason.message || "Unable to create the Cutting LaySheet."
	} finally {
		busy.value = ""
	}
}

function diaOptions(clothType) {
	const mapped = editorAttributes.value.cloth_type_dia_map?.[clothType]
	return mapped?.length ? mapped : editorAttributes.value.dia || []
}

function clothTypeChanged() {
	if (!clothDiaOptions.value.includes(clothForm.dia)) clothForm.dia = ""
	if (!clothDiaOptions.value.includes(clothForm.actual_dia)) clothForm.actual_dia = ""
}

function clothDiaChanged() {
	if (!clothForm.actual_dia) clothForm.actual_dia = clothForm.dia
}

function accessoryClothTypeChanged() {
	if (!accessoryDiaOptions.value.includes(accessoryForm.dia)) accessoryForm.dia = ""
	if (!accessoryDiaOptions.value.includes(accessoryForm.actual_dia)) accessoryForm.actual_dia = ""
}

function accessoryDiaChanged() {
	if (!accessoryForm.actual_dia) accessoryForm.actual_dia = accessoryForm.dia
}

async function openClothEditor(row = null, index = -1) {
	detailError.value = ""
	editorError.value = ""
	clothEditIndex.value = index
	Object.assign(clothForm, emptyClothForm(), row ? clothRow(row) : {})
	clothEditorOpen.value = true
	await loadSetFields(parseObject(row?.set_combination))
}

async function loadSetFields(existing = null) {
	const sequence = ++setFieldsSequence.value
	setFields.value = []
	clothForm.set_combination = {}
	if (!clothForm.colour || !sheet.value?.cutting_marker) return
	try {
		const result = await callMethod(laysheetMethod("get_input_fields"), {
			cutting_marker: sheet.value.cutting_marker,
			colour: clothForm.colour,
			select_attributes: editorAttributes.value,
		})
		if (sequence !== setFieldsSequence.value) return
		const current = existing || {}
		const values = {}
		for (const field of result?.input_fields || []) {
			const options = fieldOptions(field)
			values[field.fieldname] = Object.hasOwn(current, field.fieldname)
				? current[field.fieldname]
				: field.default ?? (field.fieldtype === "Check" ? 0 : options.length === 1 ? options[0] : "")
		}
		setFields.value = result?.input_fields || []
		clothForm.set_combination = values
	} catch (reason) {
		if (sequence === setFieldsSequence.value) editorError.value = reason.message || "Unable to load set details."
	}
}

function openAccessoryEditor(row = null, index = -1) {
	detailError.value = ""
	editorError.value = ""
	accessoryEditIndex.value = index
	Object.assign(accessoryForm, emptyAccessoryForm(), row ? accessoryRow(row) : {})
	accessoryEditorOpen.value = true
}

async function saveCloth() {
	editorError.value = ""
	const required = ["cloth_type", "colour", "dia", "actual_dia", "shade", "fabric_type", "weight", "balance_weight", "no_of_rolls"]
	if (!sheet.value?.is_manual_entry) required.push("no_of_bits", "end_bit_weight")
	if (required.some((fieldname) => !hasValue(clothForm[fieldname]))) {
		editorError.value = "Complete every required cloth field."
		return
	}
	if (Number(clothForm.balance_weight) >= Number(clothForm.weight)) {
		editorError.value = "Balance Weight must be less than Weight."
		return
	}
	for (const field of visibleSetFields.value) {
		if (!hasValue(clothForm.set_combination[field.fieldname])) {
			editorError.value = `Enter ${field.label}.`
			return
		}
	}

	const rows = (sheet.value.cloth_details || []).map(clothRow)
	const row = clothRow(clothForm)
	if (clothEditIndex.value < 0) rows.push(row)
	else rows.splice(clothEditIndex.value, 1, row)
	detailBusy.value = "cloth-save"
	try {
		await persistDetails(rows, (sheet.value.accessory_details || []).map(accessoryRow), clothEditIndex.value < 0 ? "Cloth detail added." : "Cloth detail updated.")
		clothEditorOpen.value = false
	} catch (reason) {
		editorError.value = reason.message || "Unable to save the cloth detail."
	} finally {
		detailBusy.value = ""
	}
}

async function saveAccessory() {
	editorError.value = ""
	const required = ["accessory", "cloth_type", "colour", "dia", "actual_dia", "shade", "weight", "no_of_rolls"]
	if (required.some((fieldname) => !hasValue(accessoryForm[fieldname]))) {
		editorError.value = "Complete every required accessory field."
		return
	}
	const rows = (sheet.value.accessory_details || []).map(accessoryRow)
	const row = accessoryRow(accessoryForm)
	if (accessoryEditIndex.value < 0) rows.push(row)
	else rows.splice(accessoryEditIndex.value, 1, row)
	detailBusy.value = "accessory-save"
	try {
		await persistDetails((sheet.value.cloth_details || []).map(clothRow), rows, accessoryEditIndex.value < 0 ? "Accessory detail added." : "Accessory detail updated.")
		accessoryEditorOpen.value = false
	} catch (reason) {
		editorError.value = reason.message || "Unable to save the accessory detail."
	} finally {
		detailBusy.value = ""
	}
}

async function deleteCloth(index) {
	if (!window.confirm("Delete this cloth detail?")) return
	detailBusy.value = `cloth-${index}`
	detailError.value = ""
	try {
		const rows = (sheet.value.cloth_details || []).map(clothRow)
		rows.splice(index, 1)
		await persistDetails(rows, (sheet.value.accessory_details || []).map(accessoryRow), "Cloth detail deleted.")
	} catch (reason) {
		detailError.value = reason.message || "Unable to delete the cloth detail."
	} finally {
		detailBusy.value = ""
	}
}

async function deleteAccessory(index) {
	if (!window.confirm("Delete this accessory detail?")) return
	detailBusy.value = `accessory-${index}`
	detailError.value = ""
	try {
		const rows = (sheet.value.accessory_details || []).map(accessoryRow)
		rows.splice(index, 1)
		await persistDetails((sheet.value.cloth_details || []).map(clothRow), rows, "Accessory detail deleted.")
	} catch (reason) {
		detailError.value = reason.message || "Unable to delete the accessory detail."
	} finally {
		detailBusy.value = ""
	}
}

async function persistDetails(clothDetails, accessoryDetails, message) {
	const saved = await callMethod(laysheetMethod("save_web_laysheet_details"), {
		cutting_plan: props.cuttingPlan,
		cutting_laysheet: sheet.value.name,
		cloth_details: clothDetails,
		accessory_details: accessoryDetails,
		modified: sheet.value.modified,
	})
	sheet.value = saved
	success.value = message
	detailError.value = ""
	emit("changed", saved)
}

async function load() {
	loading.value = true
	error.value = ""
	success.value = ""
	try {
		sheet.value = await callMethod(laysheetMethod("get_web_laysheet"), { cutting_plan: props.cuttingPlan, cutting_laysheet: props.laysheetName })
	} catch (reason) {
		error.value = reason.message || "Unable to load the Cutting LaySheet."
	} finally {
		loading.value = false
	}
}

async function openGenerate() {
	generateOpen.value = true
	subdialogError.value = ""
	maximumPlys.value = Number(sheet.value.maximum_no_of_plys || 0)
	maximumAllow.value = Number(sheet.value.maximum_allow_percentage || 0)
	bundleDate.value = parseDate(sheet.value.bundle_generated_date) || new Date()
	try {
		generationParts.value = await callMethod(laysheetMethod("get_parts"), { cutting_marker: sheet.value.cutting_marker }) || []
	} catch (reason) {
		subdialogError.value = reason.message || "Unable to load marker panels."
	}
}

async function generateBundles() {
	if (!bundleDate.value || generationParts.value.some((row) => !Number(row.value))) {
		subdialogError.value = "Enter the bundle date and grouping for every panel."
		return
	}
	busy.value = "generate"
	subdialogError.value = ""
	try {
		await callMethod(laysheetMethod("get_cut_sheet_data"), {
			doc_name: sheet.value.name,
			cutting_marker: sheet.value.cutting_marker,
			laysheet_details: [],
			manual_item_details: [],
			items: generationParts.value,
			max_plys: Number(maximumPlys.value || 0),
			maximum_allow: Number(maximumAllow.value || 0),
			bundle_generated_date: formatDate(bundleDate.value),
		})
		generateOpen.value = false
		success.value = "Bundles generated."
		await reloadChanged()
	} catch (reason) {
		subdialogError.value = reason.message || "Unable to generate bundles."
	} finally {
		busy.value = ""
	}
}

async function openPrinter() {
	error.value = ""
	try {
		const tolerance = Number(await callMethod(laysheetMethod("get_piece_weight_tolerance"), { doc_name: sheet.value.name }) || 0.003)
		const difference = Math.abs(Number(sheet.value.piece_weight || 0) - Number(sheet.value.required_pcs_weight || 0))
		if (difference > tolerance && !sheet.value.approved_by) {
			await callMethod(laysheetMethod("request_grammage_approval"), { doc_name: sheet.value.name })
			success.value = `Approval requested because the weight difference (${difference.toFixed(4)} kg) exceeds ${tolerance.toFixed(4)} kg.`
			await reloadChanged()
			return
		}
	} catch (reason) {
		error.value = reason.message || "Unable to validate grammage approval."
		return
	}

	printerOpen.value = true
	loadingPrinters.value = true
	subdialogError.value = ""
	selectedPrinter.value = ""
	try {
		printers.value = await getQzPrinters()
	} catch (reason) {
		subdialogError.value = reason.message || "Unable to connect to QZ Tray."
	} finally {
		loadingPrinters.value = false
	}
}

async function printLabels() {
	busy.value = "print"
	subdialogError.value = ""
	try {
		await callMethod(laysheetMethod("update_cutting_plan"), { cutting_laysheet: sheet.value.name, check_cp: true })
		const result = await callMethod(laysheetMethod("print_labels"), {
			print_items: [], lay_no: sheet.value.lay_no, doc_name: sheet.value.name, print_order: printOrder.value, cutting_plan: props.cuttingPlan,
		})
		await printQzRaw(selectedPrinter.value, result.zpl)
		await callMethod(laysheetMethod("mark_labels_printed"), { doc_name: sheet.value.name, grn: result.grn || undefined })
		printerOpen.value = false
		success.value = "Labels sent to the printer."
		await reloadChanged()
	} catch (reason) {
		subdialogError.value = reason.message || "Label printing failed. The LaySheet can be retried."
	} finally {
		busy.value = ""
	}
}

async function runStatusAction(method, action) {
	busy.value = action
	error.value = ""
	try {
		await callMethod(laysheetMethod(method), { doc_name: sheet.value.name })
		success.value = action === "approve" ? "Grammage approved." : "LaySheet status updated."
		await reloadChanged()
	} catch (reason) {
		error.value = reason.message || "Unable to update the LaySheet."
	} finally {
		busy.value = ""
	}
}

async function cancelLaySheet() {
	if (!window.confirm(`Cancel Cutting LaySheet ${sheet.value.name}?`)) return
	await runStatusAction("cancel_laysheet", "cancel")
}

async function reloadChanged() {
	await load()
	emit("changed", sheet.value)
}

function display(value) { return value === null || value === undefined || value === "" ? "—" : value }
function number(value, precision) { return value === null || value === undefined || value === "" ? "—" : Number(value).toFixed(precision) }
function percent(value) { return value === null || value === undefined || value === "" ? "—" : `${Number(value)}%` }
function column(field, label, format = display) { return { field, label, format } }
function parseDate(value) { if (!value) return null; const [year, month, day] = String(value).split("-").map(Number); return new Date(year, month - 1, day) }
function formatDate(value) { const pad = (part) => String(part).padStart(2, "0"); return `${value.getFullYear()}-${pad(value.getMonth() + 1)}-${pad(value.getDate())}` }
function fieldOptions(field) {
	if (Array.isArray(field?.options)) return field.options.filter((value) => value !== "")
	return String(field?.options || "").split("\n").filter(Boolean)
}
function hasFieldDefault(field) { return field?.default !== undefined && field?.default !== null && field?.default !== "" }
function hasValue(value) { return value !== null && value !== undefined && value !== "" }
function parseValue(value, fallback) {
	if (value === null || value === undefined || value === "") return fallback
	if (typeof value !== "string") return value
	try {
		const parsed = JSON.parse(value)
		return typeof parsed === "string" ? JSON.parse(parsed) : parsed
	} catch {
		return fallback
	}
}
function parseObject(value) {
	const parsed = parseValue(value, {})
	return parsed && typeof parsed === "object" && !Array.isArray(parsed) ? { ...parsed } : {}
}
function clothRow(row) {
	const weight = hasValue(row.weight) ? Number(row.weight) : null
	const balance = hasValue(row.balance_weight) ? Number(row.balance_weight) : 0
	return {
		cloth_type: row.cloth_type || "",
		colour: row.colour || "",
		dia: row.dia || "",
		actual_dia: row.actual_dia || row.dia || "",
		shade: row.shade || "",
		weight,
		balance_weight: balance,
		used_weight: weight === null ? 0 : weight - balance,
		no_of_rolls: hasValue(row.no_of_rolls) ? Number(row.no_of_rolls) : null,
		no_of_bits: hasValue(row.no_of_bits) ? Number(row.no_of_bits) : null,
		end_bit_weight: hasValue(row.end_bit_weight) ? Number(row.end_bit_weight) : null,
		fabric_type: row.fabric_type || "Open Width",
		comments: row.comments || "",
		items_json: parseValue(row.items_json, {}),
		set_combination: parseObject(row.set_combination),
	}
}
function accessoryRow(row) {
	return {
		accessory: row.accessory || "",
		cloth_type: row.cloth_type || "",
		colour: row.colour || "",
		dia: row.dia || "",
		actual_dia: row.actual_dia || row.dia || "",
		shade: row.shade || "",
		weight: hasValue(row.weight) ? Number(row.weight) : null,
		no_of_rolls: hasValue(row.no_of_rolls) ? Number(row.no_of_rolls) : null,
		moved_weight: Number(row.moved_weight || 0),
	}
}
function emptyCreateForm() { return { cutting_marker: "", cutting_spreader: "", cutter: "" } }
function emptyClothForm() { return clothRow({ balance_weight: 0, fabric_type: "Open Width", items_json: {}, set_combination: {} }) }
function emptyAccessoryForm() { return accessoryRow({}) }
function laysheetMethod(name) { return `essdee_yrp.essdee_yrp.doctype.sd_yrp_cutting_laysheet.sd_yrp_cutting_laysheet.${name}` }

const DataBlock = defineComponent({
	props: { title: String, rows: { type: Array, default: () => [] }, columns: { type: Array, default: () => [] } },
	setup(blockProps) {
		return () => h("section", { class: "data-block" }, [
			h("header", [h("h3", blockProps.title), h("span", `${blockProps.rows.length} rows`)]),
			blockProps.rows.length
				? h("div", { class: "table-scroll" }, [h("table", { class: "laysheet-table" }, [
					h("thead", [h("tr", [h("th", "S.No."), ...blockProps.columns.map((item) => h("th", item.label))])]),
					h("tbody", blockProps.rows.map((row, index) => h("tr", [h("td", index + 1), ...blockProps.columns.map((item) => h("td", item.format(row[item.field]))) ]))),
				])])
				: h("div", { class: "empty-data" }, "No details."),
		])
	},
})
</script>

<style scoped>
.laysheet-loading { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 12px; }
.laysheet-create { display: grid; gap: 16px; }
.create-intro { display: flex; align-items: center; gap: 11px; padding: 12px 14px; color: #315f48; background: #f2f8f4; border: 1px solid #dbe9e0; border-radius: 11px; }
.create-intro > i { font-size: 1.15rem; }
.create-intro > div { display: grid; gap: 3px; }
.create-intro strong { font-size: 0.86rem; }
.create-intro span { color: #6d7c73; font-size: 0.72rem; }
.create-fields { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 14px 18px; }
.create-fields > label { display: grid; gap: 6px; color: #34413a; font-size: 0.8rem; font-weight: 650; }
.laysheet-content { display: grid; gap: 14px; }
.laysheet-summary { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); overflow: hidden; border: 1px solid #dfe7e2; border-radius: 11px; }
.laysheet-summary > div { display: grid; gap: 4px; padding: 11px 13px; border-right: 1px solid #e3e9e5; }
.laysheet-summary > div:last-child { border-right: 0; }
.laysheet-summary span, .detail-grid span { color: #7b877f; font-size: 0.68rem; font-weight: 700; text-transform: uppercase; letter-spacing: 0.035em; }
.laysheet-summary strong, .detail-grid strong { color: #233b2e; font-size: 0.82rem; }
.status-pill { display: inline-flex; padding: 3px 7px; border-radius: 999px; color: #375b47; background: #e8f3ec; font-size: 0.68rem; }
.status-pill--cancelled { color: #983939; background: #fde7e7; }
.status-pill--approval-pending { color: #8a5b0e; background: #fff0cb; }
.detail-grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); border: 1px solid #e0e7e3; border-radius: 10px; overflow: hidden; }
.detail-grid > div { display: grid; gap: 5px; min-height: 65px; padding: 11px 13px; border-right: 1px solid #e5eae7; border-bottom: 1px solid #e5eae7; }
.data-block { display: grid; gap: 9px; margin-bottom: 14px; }
.data-block header { display: flex; align-items: center; justify-content: space-between; }
.data-block__title { display: flex; align-items: baseline; gap: 8px; }
.data-block h3 { margin: 0; color: #315f48; font-size: 0.88rem; }
.data-block header span { color: #7c8881; font-size: 0.7rem; }
.table-scroll { overflow-x: auto; border: 1px solid #e1e7e3; border-radius: 9px; }
.laysheet-table { width: 100%; min-width: 720px; border-collapse: collapse; font-size: 0.76rem; }
.laysheet-table th, .laysheet-table td { padding: 8px 9px; text-align: left; border-right: 1px solid #e4e9e6; border-bottom: 1px solid #e4e9e6; }
.laysheet-table th { color: #4c5b52; background: #f6f9f7; font-size: 0.69rem; white-space: nowrap; }
.laysheet-table tr:last-child td { border-bottom: 0; }
.laysheet-table th:last-child, .laysheet-table td:last-child { border-right: 0; }
.empty-data { display: grid; place-items: center; min-height: 70px; color: #7c8881; border: 1px dashed #dce4df; border-radius: 9px; font-size: 0.76rem; }
.editable-data-block :deep(.p-button) { flex: 0 0 auto; }
.row-actions { display: flex; align-items: center; gap: 2px; white-space: nowrap; }
.row-actions :deep(.p-button) { width: 1.8rem; height: 1.8rem; }
.detail-editor { display: grid; gap: 13px; }
.detail-editor__grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 13px 17px; }
.detail-editor__grid label { display: grid; align-content: start; gap: 5px; color: #425047; font-size: 0.75rem; font-weight: 700; }
.detail-editor__wide { grid-column: 1 / -1; }
.laysheet-content :deep(.data-block) { display: grid; gap: 9px; margin-bottom: 14px; }
.laysheet-content :deep(.data-block header) { display: flex; align-items: center; justify-content: space-between; }
.laysheet-content :deep(.data-block h3) { margin: 0; color: #315f48; font-size: 0.88rem; }
.laysheet-content :deep(.data-block header span) { color: #7c8881; font-size: 0.7rem; }
.laysheet-content :deep(.table-scroll) { overflow-x: auto; border: 1px solid #e1e7e3; border-radius: 9px; }
.laysheet-content :deep(.laysheet-table) { width: 100%; min-width: 720px; border-collapse: collapse; font-size: 0.76rem; }
.laysheet-content :deep(.laysheet-table th),
.laysheet-content :deep(.laysheet-table td) { padding: 8px 9px; text-align: left; border-right: 1px solid #e4e9e6; border-bottom: 1px solid #e4e9e6; }
.laysheet-content :deep(.laysheet-table th) { color: #4c5b52; background: #f6f9f7; font-size: 0.69rem; white-space: nowrap; }
.laysheet-content :deep(.laysheet-table tr:last-child td) { border-bottom: 0; }
.laysheet-content :deep(.laysheet-table th:last-child),
.laysheet-content :deep(.laysheet-table td:last-child) { border-right: 0; }
.laysheet-content :deep(.empty-data) { display: grid; place-items: center; min-height: 70px; color: #7c8881; border: 1px dashed #dce4df; border-radius: 9px; font-size: 0.76rem; }
.laysheet-footer, .laysheet-footer__secondary, .laysheet-footer__primary { display: flex; align-items: center; gap: 4px; }
.laysheet-footer { width: 100%; justify-content: space-between; }
.laysheet-footer__primary { justify-content: flex-end; flex-wrap: wrap; }
.subdialog-stack { display: grid; gap: 14px; }
.subdialog-stack label { display: grid; gap: 5px; color: #4d5b53; font-size: 0.75rem; font-weight: 700; }
.generation-numbers { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 12px; }
.printer-loading { display: flex; align-items: center; justify-content: center; gap: 9px; min-height: 90px; color: #627068; font-size: 0.78rem; }
:global(.laysheet-dialog) { width: min(96vw, 1250px); }
:global(.laysheet-subdialog) { width: min(94vw, 680px); }
:global(.laysheet-detail-dialog) { width: min(94vw, 820px); }

.laysheet-content :deep(.p-tabpanels) { padding: 14px 0 0; }
.laysheet-content :deep(.p-tab) { padding: 9px 13px; font-size: 0.76rem; }

@media (max-width: 760px) {
	.create-fields { grid-template-columns: 1fr; }
	.detail-editor__grid { grid-template-columns: 1fr; }
	.detail-editor__wide { grid-column: auto; }
	.laysheet-summary { grid-template-columns: repeat(2, minmax(0, 1fr)); }
	.detail-grid { grid-template-columns: 1fr; }
	.generation-numbers { grid-template-columns: 1fr; }
	.laysheet-footer { align-items: stretch; flex-direction: column; }
	.laysheet-footer__secondary, .laysheet-footer__primary { justify-content: flex-end; }
}
</style>
