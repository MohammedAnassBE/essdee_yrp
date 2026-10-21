<template>
	<Dialog :visible="visible" modal dismissable-mask maximizable :header="sheet ? `Lay Sheet · ${sheet.name}` : 'Create Lay Sheet'" class="laysheet-dialog erp-entity-dialog" @update:visible="emit('update:visible', $event)">
		<div v-if="loading" class="laysheet-loading"><Skeleton v-for="index in 8" :key="index" height="3.2rem" /></div>
		<div v-else-if="!sheet" class="laysheet-create">
			<Message v-if="error" severity="error" :closable="false">{{ error }}</Message>
			<div class="create-intro"><i class="pi pi-list-check"></i><div><strong>Start a new Lay Sheet</strong><span>Select the submitted marker and cutting team. System dates are recorded automatically.</span></div></div>
			<div class="laysheet-create__sections">
				<section class="laysheet-create__section">
					<header><div><span>Source</span><h3>Marker source</h3></div><small>Select the submitted marker for this Lay Sheet.</small></header>
					<div class="create-fields create-fields--single"><LinkField v-model="createForm.cutting_marker" label="Cutting Marker *" help-text="Search by marker name or ID." doctype="SD YRP Cutting Marker" :filters="markerFilters" :show-open-button="false" /></div>
				</section>
				<section class="laysheet-create__section">
					<header><div><span>Team</span><h3>Cutting team</h3></div><small>Assign spreading and cutting responsibility.</small></header>
					<div class="create-fields">
						<LinkField v-model="createForm.cutting_spreader" label="Cutting Spreader *" doctype="SD YRP Cutting Spreader" :show-open-button="false" />
						<LinkField v-model="createForm.cutter" label="Cutter *" doctype="SD YRP Cutter" :show-open-button="false" />
					</div>
				</section>
			</div>
		</div>
		<div v-else-if="sheet" class="laysheet-content">
			<Message v-if="error" severity="error" :closable="false">{{ error }}</Message>
			<Message v-if="success" severity="success" :closable="false">{{ success }}</Message>

			<div class="laysheet-summary">
				<div><span>Lay No</span><strong>{{ sheet.lay_no ?? '—' }}</strong></div>
				<div><span>Marker</span><strong>{{ sheet.marker_name || sheet.cutting_marker || '—' }}</strong></div>
				<div><span>Status</span><strong><DocumentStatusBadge :docstatus="sheet.docstatus" :label="sheet.status || 'Draft'" /></strong></div>
				<div><span>Bundles</span><strong>{{ sheet.bundles?.length || 0 }}</strong></div>
			</div>

			<Tabs v-model:value="activeTab">
				<TabList><Tab value="details">Details</Tab><Tab value="cloth">Cloth Details</Tab><Tab value="ratios">Marker Ratios</Tab><Tab value="bundles">Bundles</Tab></TabList>
				<TabPanels>
					<TabPanel value="details">
						<DocumentOverview class="laysheet-overview" :fields="laysheetOverviewFields" :definitions="laysheetOverviewDefinitions" include-empty aria-label="Cutting Lay Sheet overview" id-prefix="cutting-laysheet-overview" />
					</TabPanel>
					<TabPanel value="cloth">
						<Message v-if="detailError" severity="error" :closable="false">{{ detailError }}</Message>
						<section class="data-block editable-data-block">
							<header><div class="data-block__title"><h3>Cloth Details</h3><span>{{ sheet.cloth_details?.length || 0 }} rows</span></div><Button v-if="canEditDetails" label="Add Cloth" icon="pi pi-plus" size="small" @click="openClothEditor()" /></header>
							<MaterialRequirementGroups
								v-if="sheet.cloth_details?.length"
								class="laysheet-material-groups--cloth"
								:rows="sheet.cloth_details"
								:columns="clothColumns"
								:editable="canEditDetails"
								:busy-key="detailBusy"
								@edit="openClothEditor"
								@delete="deleteCloth"
							/>
							<div v-else class="empty-data">No cloth details yet.</div>
						</section>
						<section class="data-block editable-data-block">
							<header><div class="data-block__title"><h3>Accessory Details</h3><span>{{ sheet.accessory_details?.length || 0 }} rows</span></div><Button v-if="canEditDetails" label="Add Accessory" icon="pi pi-plus" size="small" :disabled="!editorAccessories.length" :title="editorAccessories.length ? 'Add accessory detail' : 'No cloth accessories are configured for this plan'" @click="openAccessoryEditor()" /></header>
							<MaterialRequirementGroups
								v-if="sheet.accessory_details?.length"
								class="laysheet-material-groups--accessory"
								:rows="sheet.accessory_details"
								:columns="accessoryColumns"
								kind="accessory"
								:editable="canEditDetails"
								:busy-key="detailBusy"
								@edit="openAccessoryEditor"
								@delete="deleteAccessory"
							/>
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
					<DocumentDeleteButton v-if="sheet?.name" doctype="SD YRP Cutting LaySheet" :name="sheet.name" :docstatus="sheet.docstatus" :disabled="Boolean(busy) || Boolean(detailBusy)" :redirect="false" @deleted="documentDeleted" />
					<CustomPrintButtons v-if="sheet?.name" doctype="SD YRP Cutting LaySheet" :record="sheet" :permissions="sheet.permissions" :disabled="Boolean(busy)" />
					<DocumentPrintButton
						v-if="sheet?.name"
						doctype="SD YRP Cutting LaySheet"
						:name="sheet.name"
						:docstatus="sheet.docstatus"
						:disabled="Boolean(busy)"
					/>
				</div>
				<div class="laysheet-footer__primary">
					<Button label="Close" severity="secondary" text :disabled="Boolean(busy)" @click="emit('update:visible', false)" />
					<Button v-if="!sheet && canCreate" label="Create Lay Sheet" icon="pi pi-plus" :loading="busy === 'create'" @click="createLaySheet" />
					<Button v-if="sheet?.permissions?.can_revert_labels" label="Revert Labels" severity="warn" outlined :loading="busy === 'revert'" @click="revertLabels" />
					<Button v-if="sheet?.permissions?.can_restore_labels" label="Update Status" severity="secondary" outlined :loading="busy === 'restore'" @click="runStatusAction('update_label_print_status', 'restore')" />
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
			<DateField v-model="bundleDate" value-type="date" label="Bundle Generated Date" required />
			<div class="generation-numbers">
				<label v-if="!sheet?.is_manual_entry"><span>Maximum No of Plys *</span><InputNumber v-model="maximumPlys" :min="1" fluid /></label>
				<label v-if="!sheet?.is_manual_entry"><span>Maximum Allow Percent *</span><InputNumber v-model="maximumAllow" :min="0" suffix="%" fluid /></label>
			</div>
			<div class="table-scroll" role="region" tabindex="0" aria-label="Bundle generation groups"><table class="laysheet-table"><thead><tr><th>Panel</th><th>Bundle Group</th></tr></thead><tbody><tr v-for="(row, index) in generationParts" :key="row.part"><td>{{ row.part }}</td><td><InputNumber v-model="row.value" :aria-label="`Bundle group for ${row.part || `panel ${index + 1}`}`" :min="1" :disabled="busy === 'generate'" fluid /></td></tr></tbody></table></div>
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
		<template #footer><Button label="Close" severity="secondary" text @click="printerOpen = false" /><Button v-if="subdialogError && !printers.length" label="Retry" icon="pi pi-refresh" severity="secondary" :disabled="loadingPrinters" @click="loadPrinters" /><Button label="Print" icon="pi pi-print" :disabled="!selectedPrinter || loadingPrinters" :loading="busy === 'print'" @click="printLabels" /></template>
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
	<DocumentErrorDialog :message="actionError" title="Cutting Lay Sheet action failed" @dismiss="actionError = ''" />
</template>

<script setup>
import CustomPrintButtons from "../../components/documents/CustomPrintButtons.vue"
import DocumentDeleteButton from "../../components/documents/DocumentDeleteButton.vue"
import Button from "primevue/button"
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
import DateField from "../../components/common/DateField.vue"
import LinkField from "../../components/common/LinkField.vue"
import DocumentErrorDialog from "../../components/documents/DocumentErrorDialog.vue"
import DocumentOverview from "../../components/documents/DocumentOverview.vue"
import DocumentStatusBadge from "../../components/documents/DocumentStatusBadge.vue"
import { useActionConfirmation } from "../../utils/useActionConfirmation.js"
import DocumentPrintButton from "./DocumentPrintButton.vue"
import MaterialRequirementGroups from "./shared/MaterialRequirementGroups.vue"

const props = defineProps({
	visible: Boolean,
	cuttingPlan: { type: String, default: "" },
	parentDoctype: { type: String, default: "SD YRP Cutting Plan" },
	parentName: { type: String, default: "" },
	laysheetName: { type: String, default: "" },
	canCreate: { type: Boolean, default: false },
})
const emit = defineEmits(["update:visible", "changed"])
const confirmAction = useActionConfirmation()

const loading = ref(false)
const busy = ref("")
const error = ref("")
const actionError = ref("")
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
let loadSequence = 0
const laysheetName = ref("")
const resolvedParentName = computed(() => props.parentName || props.cuttingPlan)
const resolvedParentField = computed(() => props.parentDoctype === "SD YRP Cutting Order" ? "cutting_order" : "cutting_plan")
const parentArgs = computed(() => ({ [resolvedParentField.value]: resolvedParentName.value }))
const markerFilters = computed(() => ({ [resolvedParentField.value]: resolvedParentName.value, docstatus: 1 }))

const laysheetOverviewDefinitions = [
	{ key: "measurements", label: "Lay measurements", description: "Dimensions and cutting limits", icon: "pi pi-arrows-alt", fields: ["length", "width", "maximum_no_of_plys", "maximum_allow_percentage"] },
	{ key: "team", label: "Cutting team", description: "People assigned to spreading and cutting", icon: "pi pi-users", fields: ["cutting_spreader", "cutter"] },
	{ key: "material", label: "Material usage", description: "Roll, bit and weight consumption", icon: "pi pi-box", fields: ["no_of_rolls", "no_of_bits", "weight", "accessory_weight", "end_bit_weight", "total_used_weight"] },
	{ key: "production", label: "Production & approval", description: "Output, printing and approval references", icon: "pi pi-check-circle", fields: ["bundle_generated_date", "printed_time", "total_no_of_pieces", "piece_weight", "required_pcs_weight", "approved_by", "goods_received_note"] },
]
const laysheetOverviewFields = computed(() => {
	const row = sheet.value || {}
	return [
		{ fieldname: "length", label: "Length (m)", fieldtype: "Float", value: row.length },
		{ fieldname: "width", label: "Width (in)", fieldtype: "Float", value: row.width },
		{ fieldname: "maximum_no_of_plys", label: "Maximum No Of Plys", fieldtype: "Int", value: row.maximum_no_of_plys },
		{ fieldname: "maximum_allow_percentage", label: "Maximum Allow Percentage", fieldtype: "Percent", value: row.maximum_allow_percentage },
		{ fieldname: "cutting_spreader", label: "Cutting Spreader", fieldtype: "Link", options: "SD YRP Cutting Spreader", value: row.cutting_spreader },
		{ fieldname: "cutter", label: "Cutter", fieldtype: "Link", options: "SD YRP Cutter", value: row.cutter },
		{ fieldname: "no_of_rolls", label: "No Of Rolls", fieldtype: "Int", value: row.no_of_rolls },
		{ fieldname: "no_of_bits", label: "No Of Bits", fieldtype: "Int", value: row.no_of_bits },
		{ fieldname: "weight", label: "Weight (kg)", fieldtype: "Float", value: row.weight },
		{ fieldname: "accessory_weight", label: "Accessory Weight (kg)", fieldtype: "Float", value: row.accessory_weight },
		{ fieldname: "end_bit_weight", label: "End Bit Weight (kg)", fieldtype: "Float", value: row.end_bit_weight },
		{ fieldname: "total_used_weight", label: "Total Used Weight (kg)", fieldtype: "Float", value: row.total_used_weight },
		{ fieldname: "bundle_generated_date", label: "Bundle Generated Date", fieldtype: "Date", value: row.bundle_generated_date },
		{ fieldname: "printed_time", label: "Printed Time", fieldtype: "Datetime", value: row.printed_time },
		{ fieldname: "total_no_of_pieces", label: "Total No Of Pieces", fieldtype: "Int", value: row.total_no_of_pieces },
		{ fieldname: "piece_weight", label: "Piece Weight (kg)", fieldtype: "Float", precision: 4, value: row.piece_weight },
		{ fieldname: "required_pcs_weight", label: "Required Piece Weight (kg)", fieldtype: "Float", precision: 4, value: row.required_pcs_weight },
		{ fieldname: "approved_by", label: "Approved By", fieldtype: "Link", options: "User", value: row.approved_by },
		{ fieldname: "goods_received_note", label: "Goods Received Note", fieldtype: "Link", options: "YRP Goods Received Note", value: row.goods_received_note },
	]
})
const canEditDetails = computed(() => Boolean(sheet.value?.permissions?.can_edit_details))
const editorAttributes = computed(() => sheet.value?.editor?.attributes || { cloth_type: [], colour: [], dia: [], cloth_type_dia_map: {} })
const editorAccessories = computed(() => sheet.value?.editor?.accessories || [])
const visibleSetFields = computed(() => setFields.value.filter((field) => !field.hidden))
const clothDiaOptions = computed(() => diaOptions(clothForm.cloth_type))
const accessoryDiaOptions = computed(() => diaOptions(accessoryForm.cloth_type))

const clothColumns = [
	column("colour", "Colour"),
	column("actual_dia", "Dia"),
	column("shade", "Shade"),
	column("weight", "Weight", (value) => number(value, 3), true),
	column("no_of_rolls", "Rolls", display, true),
	column("no_of_bits", "Bits", display, true),
	column("used_weight", "Used Weight", (value) => number(value, 3), true),
	column("balance_weight", "Balance Weight", (value) => number(value, 3), true),
]
const accessoryColumns = [
	column("colour", "Colour"),
	column("actual_dia", "Dia"),
	column("shade", "Shade"),
	column("weight", "Weight", (value) => number(value, 3), true),
	column("no_of_rolls", "Rolls", display, true),
]
const ratioColumns = [column("size", "Size"), column("panel", "Panel"), column("ratio", "Ratio")]
const bundleColumns = [column("bundle_no", "Bundle No"), column("size", "Size"), column("colour", "Colour"), column("shade", "Shade"), column("part", "Panel"), column("quantity", "Quantity"), column("is_moved", "Moved", (value) => Number(value) ? "Yes" : "No")]

watch(
	() => [props.visible, props.laysheetName, resolvedParentName.value],
	([visible]) => {
		if (!visible) {
			loadSequence += 1
			loading.value = false
			return
		}
		laysheetName.value = props.laysheetName
		if (laysheetName.value) load()
		else startCreate()
	},
)

function startCreate() {
	loadSequence += 1
	sheet.value = null
	activeTab.value = "details"
	loading.value = false
	busy.value = ""
	error.value = ""
	actionError.value = ""
	success.value = ""
	Object.assign(createForm, emptyCreateForm())
}

async function createLaySheet() {
	error.value = ""
	if (!createForm.cutting_marker || !createForm.cutting_spreader || !createForm.cutter) {
		error.value = "Select the Cutting Marker, Cutting Spreader, and Cutter."
		return
	}
	const sequence = loadSequence
	busy.value = "create"
	try {
		const created = await callMethod(laysheetMethod("create_web_laysheet"), {
			...parentArgs.value,
			values: createForm,
		})
		emit("changed", created)
		if (sequence !== loadSequence) return
		sheet.value = created
		laysheetName.value = created.name
		activeTab.value = "details"
		success.value = "Lay Sheet created."
	} catch (reason) {
		actionError.value = reason.message || "Unable to create the Cutting LaySheet."
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
		actionError.value = reason.message || "Unable to save the cloth detail."
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
		actionError.value = reason.message || "Unable to save the accessory detail."
	} finally {
		detailBusy.value = ""
	}
}

async function deleteCloth(index) {
	return confirmAction({
		header: "Delete cloth detail?",
		message: "Delete this cloth detail? This removes it from the Lay Sheet.",
		acceptLabel: "Delete Cloth",
		rejectLabel: "Keep Cloth",
		acceptIcon: "pi pi-trash",
		accept: () => deleteClothConfirmed(index),
	})
}

async function deleteClothConfirmed(index) {
	detailBusy.value = `cloth-${index}`
	detailError.value = ""
	try {
		const rows = (sheet.value.cloth_details || []).map(clothRow)
		rows.splice(index, 1)
		await persistDetails(rows, (sheet.value.accessory_details || []).map(accessoryRow), "Cloth detail deleted.")
	} catch (reason) {
		actionError.value = reason.message || "Unable to delete the cloth detail."
	} finally {
		detailBusy.value = ""
	}
}

async function deleteAccessory(index) {
	return confirmAction({
		header: "Delete accessory detail?",
		message: "Delete this accessory detail? This removes it from the Lay Sheet.",
		acceptLabel: "Delete Accessory",
		rejectLabel: "Keep Accessory",
		acceptIcon: "pi pi-trash",
		accept: () => deleteAccessoryConfirmed(index),
	})
}

async function deleteAccessoryConfirmed(index) {
	detailBusy.value = `accessory-${index}`
	detailError.value = ""
	try {
		const rows = (sheet.value.accessory_details || []).map(accessoryRow)
		rows.splice(index, 1)
		await persistDetails((sheet.value.cloth_details || []).map(clothRow), rows, "Accessory detail deleted.")
	} catch (reason) {
		actionError.value = reason.message || "Unable to delete the accessory detail."
	} finally {
		detailBusy.value = ""
	}
}

async function persistDetails(clothDetails, accessoryDetails, message) {
	const saved = await callMethod(laysheetMethod("save_web_laysheet_details"), {
		...parentArgs.value,
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
	const sequence = ++loadSequence
	const requestedName = laysheetName.value
	const requestedParent = { ...parentArgs.value }
	loading.value = true
	sheet.value = null
	activeTab.value = "details"
	error.value = ""
	actionError.value = ""
	success.value = ""
	try {
		const data = await callMethod(laysheetMethod("get_web_laysheet"), { ...requestedParent, cutting_laysheet: requestedName })
		if (sequence !== loadSequence || !props.visible || requestedName !== laysheetName.value) return
		sheet.value = data
	} catch (reason) {
		if (sequence === loadSequence && props.visible && requestedName === laysheetName.value) error.value = reason.message || "Unable to load the Cutting LaySheet."
	} finally {
		if (sequence === loadSequence && requestedName === laysheetName.value) loading.value = false
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
		actionError.value = reason.message || "Unable to generate bundles."
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
		actionError.value = reason.message || "Unable to validate grammage approval."
		return
	}

	printerOpen.value = true
	await loadPrinters()
}

async function loadPrinters() {
	loadingPrinters.value = true
	subdialogError.value = ""
	selectedPrinter.value = ""
	try {
		printers.value = await getQzPrinters()
	} catch (reason) {
		printers.value = []
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
			print_items: [], lay_no: sheet.value.lay_no, doc_name: sheet.value.name, print_order: printOrder.value, ...parentArgs.value,
		})
		await printQzRaw(selectedPrinter.value, result.zpl)
		await callMethod(laysheetMethod("mark_labels_printed"), { doc_name: sheet.value.name, grn: result.grn || undefined })
		printerOpen.value = false
		success.value = "Labels sent to the printer."
		await reloadChanged()
	} catch (reason) {
		actionError.value = reason.message || "Label printing failed. The LaySheet can be retried."
	} finally {
		busy.value = ""
	}
}

async function runStatusAction(method, action) {
	busy.value = action
	error.value = ""
	try {
		await callMethod(laysheetMethod(method), { doc_name: sheet.value.name }, { silent: true })
		success.value = action === "approve" ? "Grammage approved." : "LaySheet status updated."
		await reloadChanged()
	} catch (reason) {
		actionError.value = reason.message || "Unable to update the LaySheet."
	} finally {
		busy.value = ""
	}
}

function revertLabels() {
	const { name, goods_received_note } = sheet.value
	return confirmAction({
		header: "Revert labels?",
		message: `Revert labels for ${name}? This cancels ${goods_received_note ? `Goods Received Note ${goods_received_note} and ` : ""}the bundle ledger; labels must be updated again.`,
		acceptLabel: "Revert Labels",
		accept: () => runStatusAction("revert_labels", "revert"),
	})
}

async function cancelLaySheet() {
	return confirmAction({
		header: "Cancel Cutting LaySheet?",
		message: `Cancel Cutting LaySheet ${sheet.value.name}? This changes the document status and cannot be undone here.`,
		acceptLabel: "Cancel Lay Sheet",
		acceptIcon: "pi pi-ban",
		accept: () => runStatusAction("cancel_laysheet", "cancel"),
	})
}

async function reloadChanged() {
	const message = success.value
	await load()
	success.value = message
	emit("changed", sheet.value)
}

function display(value) { return value === null || value === undefined || value === "" ? "—" : value }
function number(value, precision) { return value === null || value === undefined || value === "" ? "—" : Number(value).toFixed(precision) }
function column(field, label, format = display, numeric = false) { return { field, label, format, numeric } }
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
				? h("div", { class: "table-scroll", role: "region", tabindex: 0, "aria-label": blockProps.title }, [h("table", { class: "laysheet-table" }, [
					h("thead", [h("tr", [h("th", "S.No."), ...blockProps.columns.map((item) => h("th", item.label))])]),
					h("tbody", blockProps.rows.map((row, index) => h("tr", [h("td", index + 1), ...blockProps.columns.map((item) => h("td", item.format(row[item.field]))) ]))),
				])])
				: h("div", { class: "empty-data" }, "No details."),
		])
	},
})
function documentDeleted() {
	emit("update:visible", false)
	emit("changed")
}
</script>

<style scoped>
.laysheet-loading { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 12px; }
.laysheet-create { display: grid; gap: 16px; }
.create-intro { display: flex; align-items: center; gap: 11px; padding: 12px 14px; color: var(--erp-text); background: var(--erp-surface-soft); border: 1px solid var(--erp-border); border-radius: var(--erp-panel-radius); }
.create-intro > i { font-size: 1.15rem; }
.create-intro > div { display: grid; gap: 3px; }
.create-intro strong { font-size: 0.86rem; }
.create-intro span { color: var(--erp-text-muted); font-size: var(--erp-font-size-min); }
.laysheet-create__sections { display: grid; grid-template-columns: minmax(0, .85fr) minmax(0, 1.15fr); gap: 14px; }
.laysheet-create__section { display: grid; align-content: start; gap: 13px; padding: 14px; background: var(--erp-surface); border: 1px solid var(--erp-border); border-radius: var(--erp-panel-radius); box-shadow: 0 5px 18px rgb(28 61 45 / 3.5%); }
.laysheet-create__section > header { display: flex; align-items: end; justify-content: space-between; gap: 12px; }
.laysheet-create__section > header > div { display: grid; gap: 2px; }
.laysheet-create__section > header span { color: var(--erp-text-muted); font-size: var(--erp-font-size-min); font-weight: 720; letter-spacing: .04em; text-transform: uppercase; }
.laysheet-create__section h3 { margin: 0; color: var(--erp-text); font-size: var(--erp-font-size-section); }
.laysheet-create__section small { color: var(--erp-text-muted); font-size: var(--erp-font-size-min); }
.create-fields { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 14px 18px; }
.create-fields--single { grid-template-columns: 1fr; }
.create-fields > label { display: grid; gap: 6px; color: var(--erp-text-secondary); font-size: var(--erp-font-size-caption); font-weight: 650; }
.laysheet-content { display: grid; gap: 14px; min-width: 0; max-width: 100%; }
.laysheet-summary { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); overflow: hidden; border: 1px solid var(--erp-border); border-radius: var(--erp-panel-radius); }
.laysheet-summary > div { display: grid; gap: 4px; padding: 11px 13px; border-right: 1px solid var(--erp-border); }
.laysheet-summary > div:last-child { border-right: 0; }
.laysheet-summary span { color: var(--erp-text-muted); font-size: var(--erp-font-size-min); font-weight: 700; text-transform: uppercase; letter-spacing: 0.035em; }
.laysheet-summary strong { color: var(--erp-text); font-size: var(--erp-font-size-caption); }
.data-block { display: grid; gap: 9px; margin-bottom: 14px; }
.data-block header { display: flex; align-items: center; justify-content: space-between; }
.data-block__title { display: flex; align-items: baseline; gap: 8px; }
.data-block h3 { margin: 0; color: var(--erp-text); font-size: var(--erp-font-size-section); }
.data-block__title > span,
.data-block > header > span { color: var(--erp-text-muted); font-size: var(--erp-font-size-min); }
.table-scroll { overflow-x: auto; border: 1px solid var(--erp-border); border-radius: var(--erp-control-radius); }
.table-scroll:focus-visible { outline: 2px solid var(--erp-accent-dark); outline-offset: -2px; }
.laysheet-table { width: 100%; min-width: 720px; border-collapse: collapse; font-size: 13px; }
.laysheet-table th, .laysheet-table td { padding: 8px 9px; text-align: left; border-right: 1px solid var(--erp-border); border-bottom: 1px solid var(--erp-border); }
.laysheet-table th { color: var(--erp-text-secondary); background: var(--erp-surface-muted); font-size: var(--erp-font-size-min); white-space: nowrap; }
.laysheet-table tr:last-child td { border-bottom: 0; }
.laysheet-table th:last-child, .laysheet-table td:last-child { border-right: 0; }
.empty-data { display: grid; place-items: center; min-height: 70px; color: var(--erp-text-muted); border: 1px dashed var(--erp-border-strong); border-radius: var(--erp-control-radius); font-size: var(--erp-font-size-caption); }
.editable-data-block :deep(.p-button) { flex: 0 0 auto; }
.row-actions { display: flex; align-items: center; gap: 2px; white-space: nowrap; }
.row-actions :deep(.p-button) { width: 1.8rem; height: 1.8rem; }
.detail-editor { display: grid; gap: 13px; }
.detail-editor__grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 13px 17px; }
.detail-editor__grid label { display: grid; align-content: start; gap: 5px; color: var(--erp-text); font-size: var(--erp-font-size-caption); font-weight: 680; }
.detail-editor__wide { grid-column: 1 / -1; }
.laysheet-content :deep(.data-block) { display: grid; gap: 9px; margin-bottom: 14px; }
.laysheet-content :deep(.data-block header) { display: flex; align-items: center; justify-content: space-between; }
.laysheet-content :deep(.data-block h3) { margin: 0; color: var(--erp-text); font-size: var(--erp-font-size-section); }
.laysheet-content :deep(.data-block__title > span),
.laysheet-content :deep(.data-block > header > span) { color: var(--erp-text-muted); font-size: var(--erp-font-size-min); }
.laysheet-content :deep(.table-scroll) { overflow-x: auto; border: 1px solid var(--erp-border); border-radius: var(--erp-control-radius); }
.laysheet-content :deep(.table-scroll:focus-visible) { outline: 2px solid var(--erp-accent-dark); outline-offset: -2px; }
.laysheet-content :deep(.laysheet-table) { width: 100%; min-width: 720px; border-collapse: collapse; font-size: 13px; }
.laysheet-content :deep(.laysheet-table th),
.laysheet-content :deep(.laysheet-table td) { padding: 8px 9px; text-align: left; border-right: 1px solid var(--erp-border); border-bottom: 1px solid var(--erp-border); }
.laysheet-content :deep(.laysheet-table th) { color: var(--erp-text-secondary); background: var(--erp-surface-muted); font-size: var(--erp-font-size-min); white-space: nowrap; }
.laysheet-content :deep(.laysheet-table tr:last-child td) { border-bottom: 0; }
.laysheet-content :deep(.laysheet-table th:last-child),
.laysheet-content :deep(.laysheet-table td:last-child) { border-right: 0; }
.laysheet-content :deep(.empty-data) { display: grid; place-items: center; min-height: 70px; color: var(--erp-text-muted); border: 1px dashed var(--erp-border-strong); border-radius: var(--erp-control-radius); font-size: var(--erp-font-size-caption); }
.laysheet-footer, .laysheet-footer__secondary, .laysheet-footer__primary { display: flex; align-items: center; gap: 4px; }
.laysheet-footer { width: 100%; justify-content: space-between; }
.laysheet-footer__primary { justify-content: flex-end; flex-wrap: wrap; }
.subdialog-stack { display: grid; gap: 14px; }
.subdialog-stack label { display: grid; gap: 5px; color: var(--erp-text-secondary); font-size: var(--erp-font-size-caption); font-weight: 700; }
.generation-numbers { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 12px; }
.printer-loading { display: flex; align-items: center; justify-content: center; gap: 9px; min-height: 90px; color: var(--erp-text-muted); font-size: var(--erp-font-size-caption); }
:global(.laysheet-dialog) { width: min(96vw, 1250px); }
:global(.laysheet-subdialog) { width: min(94vw, 680px); }
:global(.laysheet-detail-dialog) { width: min(94vw, 820px); }

.laysheet-content :deep(.p-tabpanels) { padding: 14px 0 0; }
.laysheet-content :deep(.p-tabs) { min-width: 0; max-width: 100%; }
.laysheet-content :deep(.p-tablist) { position: sticky; top: -1px; z-index: var(--erp-layer-sticky); min-width: 0; max-width: 100%; overflow: hidden; background: var(--erp-surface); }
.laysheet-content :deep(.p-tablist-content) { min-width: 0; overflow-x: auto; scrollbar-width: none; }
.laysheet-content :deep(.p-tablist-content::-webkit-scrollbar) { display: none; }
.laysheet-content :deep(.p-tablist-tab-list) { width: max-content; min-width: 100%; background: var(--erp-surface); }
.laysheet-content :deep(.p-tab) { padding: 9px 13px; font-size: var(--erp-font-size-caption); }

@media (max-width: 760px) {
	.laysheet-create__sections { grid-template-columns: 1fr; }
	.laysheet-create__section > header small { display: none; }
	.create-fields { grid-template-columns: 1fr; }
	.detail-editor__grid { grid-template-columns: 1fr; }
	.detail-editor__wide { grid-column: auto; }
	.laysheet-summary { grid-template-columns: repeat(2, minmax(0, 1fr)); }
	.generation-numbers { grid-template-columns: 1fr; }
	.laysheet-footer { align-items: stretch; flex-direction: column; }
	.laysheet-footer__secondary { justify-content: flex-start; }
	.laysheet-footer__primary { width: 100%; justify-content: flex-end; }
	.laysheet-content :deep(.p-tab) { flex: 0 0 auto; }
	.laysheet-content :deep(.table-scroll), .table-scroll { -webkit-mask-image: linear-gradient(to right, #000 0, #000 calc(100% - 18px), transparent 100%); mask-image: linear-gradient(to right, #000 0, #000 calc(100% - 18px), transparent 100%); }
	.row-actions :deep(.p-button) { width: 44px; min-width: 44px; height: 44px; min-height: 44px; }
}
</style>
