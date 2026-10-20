<template>
	<Dialog
		:visible="visible"
		modal
		:dismissable-mask="false"
		:header="title"
		class="work-order-action-panel erp-entity-dialog"
		:class="largePanel ? 'erp-dialog--lg' : 'erp-dialog--md'"
		@update:visible="requestVisibility"
	>
		<div :data-mode="mode" class="work-order-action-panel__body">
			<div v-if="loading" class="work-order-action-panel__loading"><Skeleton height="74px" /><Skeleton height="180px" /></div>

			<template v-else-if="mode === 'calculate_garment'">
				<Message v-if="!garmentMatrixRows.length" severity="secondary" :closable="false">The Lot has no items available for this calculation.</Message>
				<div v-else class="work-order-garment-calculation">
					<div class="work-order-garment-calculation__toolbar"><span>Select the combinations to calculate, then adjust quantities if required.</span><div><Button label="Select all" size="small" severity="secondary" outlined @click="setAllGarmentRows(true)" /><Button label="Unselect all" size="small" severity="secondary" text @click="setAllGarmentRows(false)" /></div></div>
					<div class="work-order-action-panel__table-wrap" role="region" tabindex="0" aria-label="Garment calculation quantities">
						<table class="erp-data-table work-order-calculation-table">
							<thead><tr><th class="work-order-calculation-table__use">Use</th><th v-for="attribute in garmentDisplayAttributes" :key="attribute">{{ attribute }}</th><th v-for="value in garmentPrimaryValues" :key="value" class="erp-number">{{ value === "default" ? "Quantity" : value }}</th><th class="erp-number">Total</th></tr></thead>
							<tbody><tr v-for="(row, rowIndex) in garmentMatrixRows" :key="row.key || rowIndex" :class="{ 'work-order-calculation-table__row--disabled': !row.selected }"><td><Checkbox v-model="row.selected" binary :aria-label="`Use garment row ${rowIndex + 1}: ${attributeText(row.attributes) || row.key || 'item'}`" /></td><td v-for="attribute in garmentDisplayAttributes" :key="attribute">{{ row.attributes?.[attribute] || "—" }}</td><td v-for="value in garmentPrimaryValues" :key="value" class="erp-number work-order-calculation-table__quantity"><template v-if="row.values?.[value]"><InputNumber v-model="row.values[value].qty" :aria-label="`${value === 'default' ? 'Quantity' : value} for ${attributeText(row.attributes) || row.key || `garment row ${rowIndex + 1}`}`" :min="0" :max="Number(row.values[value].available_qty || 0)" :max-fraction-digits="3" :disabled="!row.selected" fluid /><small>Available {{ number(row.values[value].available_qty) }}</small></template><span v-else>—</span></td><td class="erp-number work-order-calculation-table__total">{{ number(garmentRowTotal(row)) }}</td></tr></tbody>
							<tfoot><tr><th :colspan="1 + garmentDisplayAttributes.length">Column totals</th><th v-for="value in garmentPrimaryValues" :key="value" class="erp-number">{{ number(garmentColumnTotal(value)) }}</th><th class="erp-number">{{ number(garmentGrandTotal) }}</th></tr></tfoot>
						</table>
					</div>
				</div>
			</template>

			<template v-else-if="mode === 'calculate_fabric'">
				<div v-if="fabricContext.source_process_options?.length" class="work-order-action-panel__field"><label for="wo-source-process">Fill from source process</label><Select id="wo-source-process" v-model="draft.source_process" :options="fabricContext.source_process_options" option-label="label" option-value="value" fluid @change="refreshFabricSource" /></div>
				<Message v-if="fabricUnavailable" severity="warn" :closable="false"><strong>No predecessor stock available</strong><br />{{ fabricUnavailable }}</Message>
				<Message v-for="warning in fabricContext.warnings || []" :key="warning" severity="warn" :closable="false">{{ warning }}</Message>
				<Message v-for="warning in fabricQuantityWarnings" :key="warning" severity="warn" :closable="false">{{ warning }}</Message>
				<div v-for="row in fabricRows" :key="row.fabric_row" class="work-order-fabric-row">
					<header><div><strong>{{ row.cloth_item || row.treated_item }}</strong><span>{{ row.kind }}</span></div><span>{{ row.production_detail }}</span></header>
					<div v-if="row.needs_colour" class="work-order-action-panel__field"><label>Cloth colour</label><Select v-model="row.colour" :aria-label="`Cloth colour for ${row.cloth_item || row.treated_item || 'fabric row'}`" :options="row.colour_options || []" show-clear fluid /><small v-if="fabricColourError(row)" class="work-order-fabric-row__error" role="alert">{{ fabricColourError(row) }}</small></div>
					<p v-if="row.manual_io" class="work-order-action-panel__copy">Enter the yarn quantities to deliver and the cloth quantity expected back for each knitting route.</p>
					<div class="work-order-fabric-row__routes">
						<section v-for="entry in row.entries" :key="entry.input_key" class="work-order-fabric-row__route">
							<strong>{{ fabricEntryLabel(entry) }}</strong>
							<small v-if="sourcePreview(entry)">{{ sourcePreview(entry) }}</small>
							<small v-if="fabricPlanningHint(row, entry)" class="work-order-fabric-row__hint">{{ fabricPlanningHint(row, entry) }}</small>
							<div class="work-order-fabric-row__quantities">
								<label>
									<span>{{ row.kind === 'knitting' ? 'Cloth quantity expected back' : 'Quantity to receive' }}</span>
									<InputNumber
										:model-value="entry.qty"
										:aria-label="`${fabricEntryLabel(entry)} quantity for ${row.cloth_item || row.treated_item || 'fabric row'}`"
										:aria-describedby="fabricEntryError(row, entry) ? `fabric-error-${entry.input_key}` : undefined"
										:invalid="Boolean(fabricEntryError(row, entry))"
										:min="0"
										:max-fraction-digits="2"
										fluid
										@update:model-value="setFabricClothQuantity(row, entry, $event)"
									/>
								</label>
								<template v-if="row.manual_io">
									<label v-for="input in entry.inputs" :key="input.key">
										<span>{{ input.item }}</span>
										<InputNumber v-model="input.qty" :aria-label="`${input.item} for ${fabricEntryLabel(entry)}`" :min="0" :max-fraction-digits="2" fluid />
										<small>{{ attributeText(input.attrs) }} · {{ input.uom || 'Kg' }}</small>
									</label>
								</template>
							</div>
							<small v-if="fabricEntryError(row, entry)" :id="`fabric-error-${entry.input_key}`" class="work-order-fabric-row__error" role="alert">{{ fabricEntryError(row, entry) }}</small>
						</section>
					</div>
					<div v-if="row.kind === 'knitting' && !row.manual_io && !row.reference_routed && (row.yarns || []).length <= 1" class="work-order-action-panel__field"><label>Yarn deliverable quantity</label><InputNumber v-model="row.yarn_qty" :aria-label="`Yarn deliverable quantity for ${row.cloth_item || row.treated_item || 'fabric row'}`" :min="0" :max-fraction-digits="2" fluid /></div>
					<div v-if="row.kind === 'knitting'" class="work-order-fabric-row__yarns" role="status" aria-label="Yarn totals"><span>Yarn totals</span><strong v-for="yarn in fabricYarnTotals(row).items" :key="yarn.item">{{ yarn.item }} · {{ number(yarn.qty) }} Kg</strong><strong>Total · {{ number(fabricYarnTotals(row).total) }} Kg</strong></div>
				</div>
			</template>

			<template v-else-if="isCloseMode">
				<div class="work-order-action-panel__fields">
					<label><span>Close reason *</span><Select v-model="draft.close_reason" :options="closeContext.reason_options || []" fluid /></label>
					<label v-if="draft.close_reason === 'Others'"><span>Other reason *</span><InputText v-model="draft.close_other_reason" fluid /></label>
					<label class="work-order-action-panel__wide"><span>Remarks</span><Textarea v-model="draft.close_remarks" rows="3" auto-resize fluid /></label>
					<label v-if="closeContext.can_create_debit" class="work-order-action-panel__check"><Checkbox v-model="draft.with_debit" binary /><span>Create a debit while closing</span></label>
					<template v-if="draft.with_debit"><label><span>Debit number</span><InputText v-model="draft.debit_no" fluid /></label><label><span>Debit value</span><InputNumber v-model="draft.debit_value" :min="0" fluid /></label><label class="work-order-action-panel__wide"><span>Debit reason</span><Textarea v-model="draft.debit_reason" rows="2" auto-resize fluid /></label></template>
				</div>
				<section v-if="closeContext.debits?.length" class="work-order-action-panel__existing"><h3>Existing debits</h3><div v-for="debit in closeContext.debits" :key="debit.name"><span>{{ debit.name }}</span><strong>{{ debit.status || number(debit.debit_value) }}</strong><Button v-if="closeContext.can_approve_debit && debit.status !== 'Approved'" label="Approve" size="small" severity="secondary" outlined :loading="acting === `approve_debit:${debit.name}`" @click="approveDebit(debit.name)" /></div></section>
			</template>

			<template v-else-if="mode === 'create_debit'">
				<div class="work-order-action-panel__fields">
					<label><span>Debit No *</span><InputText v-model="draft.debit_no" fluid /></label>
					<label><span>Debit Value *</span><InputNumber v-model="draft.debit_value" :min="0" :min-fraction-digits="0" :max-fraction-digits="2" fluid /></label>
					<label class="work-order-action-panel__wide"><span>Reason *</span><Textarea v-model="draft.reason" rows="3" auto-resize fluid /></label>
					<label class="work-order-action-panel__wide">
						<span>Debit Document</span>
						<input ref="debitDocumentInput" type="file" hidden :disabled="busy" @change="attachDebitDocument" />
						<div class="work-order-action-panel__check">
							<Button :label="draft.debit_document ? 'Replace' : 'Attach'" size="small" severity="secondary" outlined :loading="uploading" :disabled="busy" @click.prevent="debitDocumentInput?.click()" />
							<span v-if="draft.debit_document">{{ debitDocumentName }}</span>
							<Button v-if="draft.debit_document" label="Clear" size="small" severity="secondary" text :disabled="busy" @click.prevent="draft.debit_document = ''" />
						</div>
					</label>
				</div>
			</template>

			<template v-else-if="mode === 'create_rework'">
				<div class="work-order-action-panel__fields"><label><span>Supplier type</span><Select v-model="draft.supplier_type" :options="['Same Supplier', 'Different Supplier']" fluid /></label><LinkField v-if="draft.supplier_type === 'Different Supplier'" v-model="draft.supplier" label="Supplier *" doctype="Supplier" :show-open-button="false" /></div>
				<Message v-if="!reworkRows.length && !error" severity="secondary" :closable="false">No rework items. Rework rows come from this Work Order's submitted GRNs received in a rework type such as Printing Mistake.</Message>
				<div v-else class="work-order-action-panel__table-wrap" role="region" tabindex="0" aria-label="Rework quantities"><table class="erp-data-table"><thead><tr><th>Source</th><th>Item</th><th>Stock context</th><th class="erp-number">Available</th><th class="erp-number">Rework quantity</th></tr></thead><tbody><tr v-for="(row, rowIndex) in reworkRows" :key="row.source_key"><td>{{ row.source_label || row.source_key }}</td><td>{{ row.item_variant }}</td><td>{{ reworkContext(row) }}</td><td class="erp-number">{{ number(row.available_qty) }}</td><td><InputNumber v-model="row.qty" :aria-label="`Rework quantity for ${row.item_variant || row.source_label || `row ${rowIndex + 1}`}`" :min="0" :max="Number(row.available_qty || 0)" :max-fraction-digits="3" fluid /></td></tr></tbody></table></div>
			</template>

			<template v-else-if="mode === 'create_recut'">
				<Message v-if="!recutGroups.length" severity="secondary" :closable="false">This Work Order has no calculated SKU rows available for recut.</Message>
				<div v-else class="work-order-recut-groups">
					<section v-for="(group, groupIndex) in recutGroups" :key="groupIndex" class="work-order-recut-group">
						<div v-for="(row, rowIndex) in group.items || []" :key="row.item_variant || row.name || rowIndex" class="work-order-recut-row">
							<div><strong>{{ row.item_variant || row.name }}</strong><small>{{ attributeText(row.attributes) }}</small></div>
							<label v-for="value in primaryValues(group)" :key="value"><span>{{ value === 'default' ? 'Quantity' : value }}</span><InputNumber v-model="row.values[value].qty" :aria-label="`${value === 'default' ? 'Quantity' : value} for ${row.item_variant || row.name || `recut row ${rowIndex + 1}`}`" :min="0" :max-fraction-digits="3" fluid /></label>
						</div>
					</section>
				</div>
				<label v-if="recutCanSubmit" class="work-order-action-panel__check"><Checkbox v-model="draft.submit_recut" binary /><span>Submit the Recut immediately</span></label>
			</template>

			<template v-else-if="mode === 'create_sewing_plan'">
				<p class="work-order-action-panel__copy">Create the Sewing Plan for this Work Order now? The Work Order will stay open and refresh after creation.</p>
			</template>

			<template v-else-if="mode === 'change_delivery_date'">
				<div class="work-order-action-panel__fields"><DateField v-model="draft.expected_date" label="Delivery date *" required /><label class="work-order-action-panel__wide"><span>Reason *</span><Textarea v-model="draft.reason" rows="3" auto-resize fluid /></label></div>
			</template>

			<template v-else-if="mode === 'change_item'">
				<Message v-if="changeItemContext.message" severity="secondary" :closable="false">{{ changeItemContext.message }}</Message>
				<div class="work-order-change-items"><label v-for="item in changeItemContext.items || []" :key="item.row_name"><Checkbox v-model="draft.selected" :value="item.row_name" @change="changeItemPreview = {}" /><span><strong>{{ item.item_variant || item.item }}</strong><small>{{ item.branch }} · {{ number(item.qty) }} {{ item.uom }}</small></span></label></div>
				<section v-if="changeItemPreview.changes?.length" class="work-order-action-panel__existing"><h3>Preview</h3><div v-for="change in changeItemPreview.changes" :key="change.selection_id"><span>{{ change.old_variant }}</span><strong>{{ change.new_variant || change.reason }}</strong></div></section>
			</template>

			<template v-else-if="mode === 'calculate_pieces'">
				<p class="work-order-action-panel__copy">Rebuild delivered and received piece quantities from the submitted Work Order documents?</p>
			</template>
		</div>

		<template #footer>
			<Button label="Cancel" severity="secondary" text :disabled="busy" @click="requestVisibility(false)" />
			<Button v-if="mode === 'change_item'" label="Preview" severity="secondary" outlined :disabled="!draft.selected?.length || busy" :loading="acting === 'preview_change_item'" @click="previewChangeItem" />
			<Button :label="submitLabel" icon="pi pi-check" :disabled="!canSubmit || busy" :loading="Boolean(acting && acting !== 'preview_change_item')" @click="submit" />
		</template>
	</Dialog>
	<DocumentErrorDialog :message="error" :title="`${title} could not be completed`" @dismiss="error = ''" />
	<Dialog v-model:visible="discardVisible" class="erp-dialog--sm" modal header="Discard action changes?" :closable="false">
		<p class="work-order-action-panel__copy">This action has unsaved changes. Close it and discard those values?</p>
		<template #footer><Button label="Keep Editing" severity="secondary" text @click="discardVisible = false" /><Button label="Discard Changes" severity="danger" @click="discardAction" /></template>
	</Dialog>
</template>

<script setup>
import Button from "primevue/button"
import Checkbox from "primevue/checkbox"
import Dialog from "primevue/dialog"
import InputNumber from "primevue/inputnumber"
import InputText from "primevue/inputtext"
import Message from "primevue/message"
import Select from "primevue/select"
import Skeleton from "primevue/skeleton"
import Textarea from "primevue/textarea"
import { computed, reactive, ref, watch } from "vue"

import { executeWorkOrderCommand, getWorkOrderFabricCalculationContext } from "../../api/fabricStore.js"
import { uploadFile } from "../../api/frappe.js"
import DateField from "../../components/common/DateField.vue"
import LinkField from "../../components/common/LinkField.vue"
import DocumentErrorDialog from "../../components/documents/DocumentErrorDialog.vue"
import {
	buildFabricPayload, canCalculateFabric, fabricColourError, fabricEntryError, fabricEntryLabel,
	fabricPlanningHint, fabricSourceProcess, fabricUnavailableMessage, fabricWarnings, fabricYarnTotals,
	hydrateFabricRows, setFabricClothQuantity,
} from "./fabricCalculate.js"

const props = defineProps({
	visible: { type: Boolean, default: false },
	mode: { type: String, default: "" },
	workOrder: { type: Object, default: () => ({}) },
	editor: { type: Object, default: () => ({}) },
})
const emit = defineEmits(["update:visible", "changed"])
const error = ref("")
const loading = ref(false)
const acting = ref("")
const uploading = ref(false)
const debitDocumentInput = ref(null)
const draft = reactive({})
const debitDocumentName = computed(() => String(draft.debit_document || "").split("/").pop())
const garmentRows = ref([])
const garmentMatrixRows = ref([])
const garmentPrimaryValues = ref([])
const garmentDisplayAttributes = ref([])
const fabricRows = ref([])
const fabricContext = ref({})
const fabricUnavailable = computed(() => fabricUnavailableMessage(fabricContext.value))
const fabricQuantityWarnings = computed(() => fabricWarnings(fabricRows.value))
const closeContext = ref({})
const reworkRows = ref([])
const recutGroups = ref([])
const recutCanSubmit = ref(false)
const changeItemContext = ref({})
const changeItemPreview = ref({})
const baselinePayload = ref("")
const baselineFabricEntries = ref("")
const discardVisible = ref(false)
const recutQuantity = computed(() => recutGroups.value.reduce((total, group) => total + (group.items || []).reduce((rowTotal, row) => rowTotal + Object.values(row.values || {}).reduce((cellTotal, value) => cellTotal + Number(value?.qty || 0), 0), 0), 0))
const garmentGrandTotal = computed(() => garmentPrimaryValues.value.reduce((total, value) => total + garmentColumnTotal(value), 0))
const dirty = computed(() => Boolean(baselinePayload.value && (JSON.stringify(buildPayload()) !== baselinePayload.value || JSON.stringify(fabricRows.value.map((row) => row.entries)) !== baselineFabricEntries.value)))

const titles = {
	calculate_garment: "Calculate Work Order Items", calculate_fabric: "Calculate Fabric Deliverables",
	close: "Close Work Order", request_close: "Request Work Order Close", approve_close: "Approve Work Order Close",
	create_debit: "Create Debit", create_rework: "Create Rework Work Order", calculate_pieces: "Calculate Pieces",
	create_recut: "Create Work Order Recut", create_sewing_plan: "Create Sewing Plan",
	change_delivery_date: "Change Delivery Date", change_item: "Change Item",
}
const title = computed(() => titles[props.mode] || "Work Order Action")
const largePanel = computed(() => ["calculate_garment", "calculate_fabric", "create_rework", "change_item"].includes(props.mode))
const busy = computed(() => loading.value || uploading.value || Boolean(acting.value))
const isCloseMode = computed(() => ["close", "request_close", "approve_close"].includes(props.mode))
const actionLabels = {
	close: "Close Work Order", request_close: "Request Close", approve_close: "Approve Close",
	create_debit: "Create Debit", calculate_pieces: "Calculate Pieces",
	change_delivery_date: "Change Delivery Date", change_item: "Apply Changes",
	create_recut: "Create Recut", create_sewing_plan: "Create Sewing Plan",
}
const submitLabel = computed(() => props.mode === "create_rework" ? "Create Work Order" : props.mode.startsWith("calculate_") ? "Calculate" : actionLabels[props.mode] || "Continue")
const canSubmit = computed(() => {
	if (props.mode === "calculate_garment") return garmentMatrixRows.value.some((row) => row.selected && garmentRowTotal(row) > 0)
	if (props.mode === "calculate_fabric") return canCalculateFabric(fabricContext.value, fabricRows.value)
	if (isCloseMode.value) return Boolean(String(draft.close_reason || "").trim()) && (draft.close_reason !== "Others" || Boolean(String(draft.close_other_reason || "").trim())) && (!draft.with_debit || Boolean(String(draft.debit_no || "").trim()) && Number(draft.debit_value || 0) > 0 && Boolean(String(draft.debit_reason || "").trim()))
	if (props.mode === "create_debit") return !uploading.value && Boolean(String(draft.debit_no || "").trim()) && Number(draft.debit_value || 0) > 0 && Boolean(String(draft.reason || "").trim())
	if (props.mode === "create_rework") return reworkRows.value.some((row) => Number(row.qty || 0) > 0) && (draft.supplier_type !== "Different Supplier" || Boolean(draft.supplier))
	if (props.mode === "create_recut") return recutQuantity.value > 0
	if (props.mode === "change_delivery_date") return Boolean(draft.expected_date && String(draft.reason || "").trim())
	if (props.mode === "change_item") return Boolean(draft.selected?.length && changeItemPreview.value.changes?.some((change) => change.action === "replace" && change.eligible))
	return true
})

function clone(value) { return JSON.parse(JSON.stringify(value ?? {})) }
function resetDraft() {
	for (const key of Object.keys(draft)) delete draft[key]
	Object.assign(draft, { supplier_type: "Same Supplier", supplier: "", selected: [], expected_date: props.workOrder.expected_delivery_date || "", close_reason: "", close_other_reason: "", close_remarks: "", with_debit: false, debit_no: "", debit_value: null, debit_document: "", debit_reason: "", reason: "", source_process: "", submit_recut: false })
	const garment = props.editor.calculation_contexts?.garment || {}
	garmentRows.value = clone(garment.rows || [])
	garmentPrimaryValues.value = clone(garment.primary_values?.length ? garment.primary_values : ["default"])
	garmentDisplayAttributes.value = clone(garment.display_attributes || [])
	garmentMatrixRows.value = hydrateGarmentMatrix(garment)
	fabricContext.value = clone(props.editor.calculation_contexts?.fabric || {})
	draft.source_process = fabricSourceProcess(fabricContext.value)
	fabricRows.value = hydrateFabricRows(fabricContext.value)
	baselineFabricEntries.value = JSON.stringify(fabricRows.value.map((row) => row.entries))
	closeContext.value = {}; reworkRows.value = []; recutGroups.value = []; recutCanSubmit.value = false; changeItemContext.value = {}; changeItemPreview.value = {}; error.value = ""
}
async function attachDebitDocument(event) {
	const file = event.target.files?.[0]
	if (!file) return
	uploading.value = true; error.value = ""
	try {
		const uploaded = await uploadFile(file, { isPrivate: 1 })
		draft.debit_document = uploaded.file_url
	} catch (reason) { error.value = reason?.message || "Unable to upload the Debit Document." }
	finally { uploading.value = false; event.target.value = "" }
}
async function refreshFabricSource() {
	const previousSourceProcess = fabricSourceProcess(fabricContext.value)
	loading.value = true; error.value = ""
	try {
		fabricContext.value = await getWorkOrderFabricCalculationContext(props.workOrder.name, draft.source_process) || {}
		draft.source_process = fabricSourceProcess(fabricContext.value)
		fabricRows.value = hydrateFabricRows(fabricContext.value)
	} catch (reason) {
		draft.source_process = previousSourceProcess
		error.value = reason?.message || "Unable to fill quantities from the selected source process."
	}
	finally { loading.value = false }
}
async function initialise() {
	resetDraft()
	const contextCommand = isCloseMode.value ? "get_close_context" : props.mode === "create_rework" ? "get_rework_context" : props.mode === "create_recut" ? "prepare_recut" : props.mode === "change_item" ? "get_change_item_context" : ""
	if (!contextCommand) { baselinePayload.value = JSON.stringify(buildPayload()); return }
	loading.value = true
	try {
		const result = await executeWorkOrderCommand(props.workOrder.name, contextCommand, {}, props.workOrder.modified)
		if (isCloseMode.value) {
			closeContext.value = result || {}
			Object.assign(draft, {
				close_reason: result?.close_reason || "",
				close_other_reason: result?.close_other_reason || "",
				close_remarks: result?.close_remarks || "",
			})
		}
		if (props.mode === "create_rework") reworkRows.value = clone(result?.rows || []).map((row) => ({ ...row, qty: 0 }))
		if (props.mode === "create_recut") { recutGroups.value = clone(result?.item_details || []); recutCanSubmit.value = Boolean(result?.can_submit); draft.submit_recut = Boolean(result?.can_submit) }
		if (props.mode === "change_item") changeItemContext.value = result || {}
	} catch (reason) { error.value = reason?.message || "Unable to load this Work Order action." }
	finally { loading.value = false; baselinePayload.value = JSON.stringify(buildPayload()) }
}
function buildPayload() {
	if (props.mode === "calculate_garment") return { rows: garmentMatrixRows.value.filter((row) => row.selected).flatMap((row) => garmentPrimaryValues.value.map((value) => row.values?.[value]).filter((cell) => cell?.source_row && Number(cell.qty || 0) > 0).map((cell) => ({ source_row: cell.source_row, qty: Number(cell.qty) }))) }
	if (props.mode === "calculate_fabric") return buildFabricPayload(fabricContext.value, fabricRows.value)
	if (props.mode === "create_rework") return { supplier_type: draft.supplier_type, supplier: draft.supplier, rows: reworkRows.value.filter((row) => Number(row.qty || 0) > 0).map((row) => ({ source_key: row.source_key, qty: Number(row.qty) })) }
	if (props.mode === "create_recut") return { item_details: clone(recutGroups.value), submit: Boolean(draft.submit_recut && recutCanSubmit.value) }
	if (props.mode === "change_item") return { selected: [...draft.selected] }
	return clone(draft)
}
async function previewChangeItem() {
	acting.value = "preview_change_item"; error.value = ""
	try { changeItemPreview.value = await executeWorkOrderCommand(props.workOrder.name, "preview_change_item", { selected: [...draft.selected] }, props.workOrder.modified) || {} }
	catch (reason) { error.value = reason?.message || "Unable to preview the Item changes." }
	finally { acting.value = "" }
}
async function approveDebit(debit) {
	acting.value = `approve_debit:${debit}`; error.value = ""
	try { const result = await executeWorkOrderCommand(props.workOrder.name, "approve_debit", { debit }, props.workOrder.modified); emit("changed", result); close() }
	catch (reason) { error.value = reason?.message || `Unable to approve ${debit}.` }
	finally { acting.value = "" }
}
async function submit() {
	if (!canSubmit.value || busy.value) return
	acting.value = props.mode; error.value = ""
	try {
		const result = await executeWorkOrderCommand(props.workOrder.name, props.mode, buildPayload(), props.workOrder.modified)
		emit("changed", result); close()
	} catch (reason) { error.value = reason?.message || `Unable to ${title.value.toLowerCase()}.` }
	finally { acting.value = "" }
}
function requestVisibility(value) {
	if (value || busy.value) return
	if (dirty.value) { discardVisible.value = true; return }
	close()
}
function discardAction() { discardVisible.value = false; close() }
function close() { emit("update:visible", false) }
function hydrateGarmentMatrix(context) {
	if (context.matrix_rows?.length) return clone(context.matrix_rows).map((row, index) => ({ ...row, key: row.key || `matrix-${index}`, selected: true }))
	return (context.rows || []).map((source, index) => ({ key: source.source_row || `row-${index}`, selected: true, attributes: source.attributes || {}, values: { default: { source_row: source.source_row, item_variant: source.item_variant, available_qty: source.available_qty, qty: source.qty } } }))
}
function setAllGarmentRows(selected) { for (const row of garmentMatrixRows.value) row.selected = selected }
function garmentRowTotal(row) { if (!row.selected) return 0; return garmentPrimaryValues.value.reduce((total, value) => total + Number(row.values?.[value]?.qty || 0), 0) }
function garmentColumnTotal(value) { return garmentMatrixRows.value.reduce((total, row) => total + (row.selected ? Number(row.values?.[value]?.qty || 0) : 0), 0) }
function sourcePreview(entry) {
	if (!entry.source_grn && !entry.source_stock_available && !entry.source_shared) return ""
	const demand = Number(entry.qty || 0) * Number(entry.source_stock_per_output || 1)
	return `${entry.source_grn || "Shared source"} · Required ${number(demand)} · Available ${number(entry.source_stock_available)}${entry.source_shared ? " · Shared availability: allocate across rows" : ""}`
}
function attributeText(attributes) { return Object.entries(attributes || {}).map(([key, value]) => `${key}: ${value}`).join(" · ") || "—" }
function reworkContext(row) { return [...new Set([row.role, row.received_type, ...Object.values(row.dimensions || {})].filter(Boolean))].join(" · ") || "—" }
function primaryValues(group) { return group.primary_attribute_values?.length ? group.primary_attribute_values : ["default"] }
function number(value) { return Number(value || 0).toLocaleString("en-IN", { maximumFractionDigits: 3 }) }

watch(() => props.visible, (value, previous) => { if (value && !previous) initialise() })
</script>

<style scoped>
.work-order-action-panel__body, .work-order-action-panel__loading { display: grid; gap: var(--erp-space-3); padding: 2px 1px; }
.work-order-action-panel__fields { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: var(--erp-space-3); }
.work-order-action-panel__fields > label, .work-order-action-panel__field, .work-order-fabric-row__quantities label { display: grid; gap: 6px; color: var(--erp-text); font-size: var(--erp-font-size-caption); font-weight: 650; }
.work-order-action-panel__wide { grid-column: 1 / -1; }
.work-order-action-panel__check { display: flex !important; align-items: center; gap: var(--erp-space-2); grid-column: 1 / -1; }
.work-order-action-panel__table-wrap { overflow-x: auto; overflow-y: visible; border: 1px solid var(--erp-border); border-radius: var(--erp-control-radius); box-shadow: 0 5px 16px rgb(28 61 45 / 4%); }
.work-order-action-panel__table-wrap:focus-visible { outline: 2px solid var(--erp-accent-dark); outline-offset: 2px; }
.work-order-action-panel__table-wrap table { min-width: 720px; }
.work-order-garment-calculation { display: grid; gap: var(--erp-space-2); }
.work-order-garment-calculation__toolbar { display: flex; align-items: center; justify-content: space-between; gap: 12px; color: var(--erp-text-muted); font-size: var(--erp-font-size-caption); }
.work-order-garment-calculation__toolbar > div { display: flex; gap: 6px; }
.work-order-calculation-table__use { width: 54px; }
.work-order-calculation-table__quantity { min-width: 116px; }
.work-order-calculation-table__quantity small { display: block; margin-top: 3px; color: var(--erp-text-muted); font-size: var(--erp-font-size-min); }
.work-order-calculation-table__quantity :deep(.p-inputnumber-input) { height: 32px; padding: 5px 8px; text-align: right; }
.work-order-calculation-table__row--disabled { opacity: .55; }
.work-order-calculation-table__total { color: var(--erp-accent-dark); font-weight: 800; }
.work-order-recut-groups { display: grid; gap: var(--erp-space-3); }
.work-order-recut-group { display: grid; overflow: hidden; border: 1px solid var(--erp-border); border-radius: var(--erp-control-radius); box-shadow: 0 4px 14px rgb(28 61 45 / 3%); }
.work-order-recut-row { display: grid; grid-template-columns: minmax(180px, 1fr) repeat(auto-fit, minmax(110px, 150px)); align-items: end; gap: var(--erp-space-3); padding: var(--erp-space-3); border-bottom: 1px solid var(--erp-border); }
.work-order-recut-row:last-child { border-bottom: 0; }
.work-order-recut-row > div, .work-order-recut-row label { display: grid; gap: 4px; }
.work-order-recut-row small, .work-order-recut-row label span { color: var(--erp-text-muted); font-size: var(--erp-font-size-min); }
.work-order-fabric-row { display: grid; gap: var(--erp-space-3); padding: var(--erp-space-3); border-left: 3px solid color-mix(in srgb, var(--erp-accent) 54%, white); background: color-mix(in srgb, var(--erp-surface-soft) 70%, white); border-radius: 0 var(--erp-control-radius) var(--erp-control-radius) 0; }
.work-order-fabric-row > header { display: flex; justify-content: space-between; gap: 12px; }
.work-order-fabric-row > header div { display: grid; gap: 2px; }
.work-order-fabric-row > header span { color: var(--erp-text-muted); font-size: var(--erp-font-size-min); }
.work-order-fabric-row__quantities { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: var(--erp-space-3); }
.work-order-fabric-row__routes { display: grid; gap: var(--erp-space-3); }
.work-order-fabric-row__route { display: grid; gap: var(--erp-space-2); padding: var(--erp-space-3); border: 1px solid var(--erp-border); border-radius: var(--erp-control-radius); background: var(--erp-surface); }
.work-order-fabric-row__hint, .work-order-fabric-row__quantities small { color: var(--erp-text-muted); font-size: var(--erp-font-size-min); }
.work-order-fabric-row__error { color: var(--erp-danger); }
.work-order-fabric-row__yarns { display: flex; gap: 8px 14px; color: var(--erp-text-muted); font-size: var(--erp-font-size-min); flex-wrap: wrap; }
.work-order-action-panel__existing { display: grid; gap: 6px; padding: var(--erp-space-3); border-left: 3px solid var(--erp-border-strong); background: var(--erp-surface-soft); }
.work-order-action-panel__existing h3 { margin: 0 0 4px; font-size: var(--erp-font-size-section); }
.work-order-action-panel__existing div { display: flex; justify-content: space-between; gap: 10px; font-size: var(--erp-font-size-caption); }
.work-order-change-items { display: grid; gap: 7px; }
.work-order-change-items label { display: flex; align-items: center; gap: 9px; padding: 9px 10px; border-bottom: 1px solid var(--erp-border); background: var(--erp-surface); transition: background-color 160ms ease; }
.work-order-change-items label:hover { background: color-mix(in srgb, var(--erp-accent-soft) 40%, white); }
.work-order-change-items label > span { display: grid; gap: 2px; }
.work-order-change-items small { color: var(--erp-text-muted); }
.work-order-action-panel__copy { margin: 0; color: var(--erp-text-muted); line-height: 1.55; }
@media (max-width: 700px) { .work-order-action-panel__fields, .work-order-fabric-row__quantities { grid-template-columns: 1fr; } .work-order-action-panel__wide { grid-column: auto; } }
@media (max-width: 1024px), (pointer: coarse) {
	.work-order-garment-calculation__toolbar :deep(.p-button), .work-order-action-panel__existing :deep(.p-button), .work-order-action-panel__check :deep(.p-button) { min-height: 44px; }
	.work-order-action-panel__body :deep(.p-inputnumber-input) { height: 44px; min-height: 44px; }
}
</style>
