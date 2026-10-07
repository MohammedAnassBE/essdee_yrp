<template>
	<div class="delivery-challan-workspace" :class="`delivery-challan-workspace--${presentation}`">
		<FabricDocumentWorkspace
			doctype="YRP Delivery Challan"
			title="Delivery Challan"
			:workspace="workspace"
			:presentation="presentation"
			:loading="loading"
			:error="error"
			:dirty="dirty"
			:acting="acting"
			:show-lifecycle-actions="false"
			:compact-mobile-rail="Boolean(workspace.record?.name)"
			@reload="load(true)"
			@action="runWorkspaceAction"
			@close="emit('closed')"
		>
			<template #header="{ record }">
				<div class="delivery-challan-header__identity" :class="{ 'delivery-challan-header__identity--embedded': presentation === 'embedded' }">
					<div v-if="presentation !== 'embedded'" class="delivery-challan-header__title"><h1>Delivery Challan</h1><span>{{ record.name || duplicateLabel || (loading && name ? "Loading…" : error && name ? name : "New document") }}</span></div>
					<Tag v-if="hasWorkspace && presentation !== 'embedded'" :value="record.status || statusLabel(record.docstatus)" :severity="statusSeverity" rounded />
					<div v-if="headerFacts.length" class="delivery-challan-header__facts" role="region" aria-label="Delivery Challan context" tabindex="0">
						<div v-for="fact in headerFacts" :key="fact.label"><span>{{ fact.label }}</span><strong :title="String(fact.value)">{{ fact.value }}</strong></div>
					</div>
				</div>
			</template>

			<template #header-actions>
				<DocumentActionStrip :actions="deliveryChallanActions" />
			</template>

			<template #fields>
				<section v-if="visibleFields.length" class="delivery-challan-fields" aria-label="Delivery Challan fields">
					<section v-for="group in primaryFieldGroups" :key="group.key" class="delivery-challan-field-group" :data-group="group.key">
						<header><span>{{ group.eyebrow }}</span><h2>{{ group.label }}</h2></header>
						<div class="delivery-challan-field-group__grid" :class="{ 'delivery-challan-field-group__grid--facts': !canEdit }">
							<template v-if="canEdit">
								<FormField
									v-for="field in group.fields"
									:key="fieldKey(field)"
									:field="field"
									:model-value="form[field.fieldname]"
									:form="form"
									:required="Boolean(field.reqd || field.mandatory)"
									compact
									:search-handler="linkSearchHandler(field)"
									@update:model-value="setField(field.fieldname, $event)"
								/>
							</template>
							<template v-else>
								<div v-for="field in group.fields" :key="`fact-${field.fieldname}`" class="delivery-challan-field-fact">
									<span>{{ field.label }}</span><strong :title="String(formatFieldValue(field))">{{ formatFieldValue(field) }}</strong>
								</div>
							</template>
						</div>
					</section>
				</section>
			</template>

			<template #secondary-fields>
				<section v-if="secondaryFieldGroups.length" class="delivery-challan-fields delivery-challan-fields--secondary" aria-label="Additional Delivery Challan fields">
					<section v-for="group in secondaryFieldGroups" :key="group.key" class="delivery-challan-field-group" :data-group="group.key">
						<header><span>{{ group.eyebrow }}</span><h2>{{ group.label }}</h2></header>
						<div class="delivery-challan-field-group__grid" :class="{ 'delivery-challan-field-group__grid--facts': !canEdit }">
							<template v-if="canEdit">
								<FormField v-for="field in group.fields" :key="fieldKey(field)" :field="field" :model-value="form[field.fieldname]" :form="form" :required="Boolean(field.reqd || field.mandatory)" compact :search-handler="linkSearchHandler(field)" @update:model-value="setField(field.fieldname, $event)" />
							</template>
							<template v-else>
								<div v-for="field in group.fields" :key="`fact-${field.fieldname}`" class="delivery-challan-field-fact"><span>{{ field.label }}</span><strong :title="String(formatFieldValue(field))">{{ formatFieldValue(field) }}</strong></div>
							</template>
						</div>
					</section>
				</section>
			</template>

			<template #matrix>
				<section
					v-for="block in matrixBlocks"
					:key="block.key"
					class="delivery-challan-matrix"
					:class="`delivery-challan-matrix--${block.kind}`"
				>
					<header class="delivery-challan-matrix__header">
						<div><span>{{ block.kind === "items" ? "Deliverables" : "Corrections" }}</span><h2>{{ block.title }}</h2></div>
						<strong>{{ logicalRowCount(block.groups) }} rows</strong>
					</header>
					<div class="delivery-challan-matrix__stack">
						<article v-for="section in itemSections(block.groups)" :key="section.key" class="delivery-challan-matrix__group">
							<header><div><strong>{{ section.name || "Unspecified item" }}</strong></div></header>
							<div class="erp-table-wrap delivery-challan-matrix__scroll" tabindex="0" role="region" :aria-label="`Delivery quantities for ${section.name || 'item'}`">
								<table class="erp-data-table">
									<thead><tr>
										<th v-for="column in identityColumns(section.group)" :key="column.key">{{ column.label }}</th>
									<template v-if="hasPrimaryAttribute(section.group)"><th v-for="value in primaryValues(section.group)" :key="value" class="erp-number delivery-challan-matrix__quantity-heading">{{ value }}</th></template>
									<template v-else><th class="erp-number delivery-challan-matrix__pending-heading">Pending</th><th class="erp-number delivery-challan-matrix__quantity-heading">Deliver</th><th v-if="hasSecondaryQuantity(section.group)" class="erp-number">Secondary</th></template>
										<th class="erp-number">Total</th><th>UOM</th>
									</tr></thead>
									<tbody>
										<tr v-for="(row, rowIndex) in section.items" :key="rowKey(row, rowIndex)">
											<td v-for="column in identityColumns(section.group)" :key="column.key">{{ identityValue(row, column) }}</td>
										<template v-if="hasPrimaryAttribute(section.group)">
											<td v-for="value in primaryValues(section.group)" :key="value" class="erp-number delivery-challan-matrix__quantity delivery-challan-matrix__primary-cell">
												<InputNumber v-model="row.values[value].qty" :aria-label="matrixInputLabel('Deliver', section, row, value)" :min="0" :max-fraction-digits="3" :disabled="!canEditMatrix" fluid @update:model-value="markDirty" />
												<small>Pending {{ formatQty(pendingQuantity(row.values[value])) }}</small>
												<div v-if="secondaryUom(row, value)" class="delivery-challan-matrix__secondary-inline"><InputNumber v-model="row.values[value].secondary_qty" :aria-label="matrixInputLabel('Secondary quantity for', section, row, value, secondaryUom(row, value))" :min="0" :max-fraction-digits="3" :disabled="!canEditMatrix" fluid @update:model-value="markDirty" /><span>{{ secondaryUom(row, value) }}</span></div>
											</td>
										</template>
										<template v-else>
											<td class="erp-number delivery-challan-matrix__pending">{{ formatQty(pendingQuantity(row.values.default)) }}</td>
											<td class="erp-number delivery-challan-matrix__quantity"><InputNumber v-model="row.values.default.qty" :aria-label="matrixInputLabel('Deliver', section, row, 'default')" :min="0" :max-fraction-digits="3" :disabled="!canEditMatrix" fluid @update:model-value="markDirty" /></td>
											<td v-if="hasSecondaryQuantity(section.group)" class="erp-number delivery-challan-matrix__secondary">
												<InputNumber v-model="row.values.default.secondary_qty" :aria-label="matrixInputLabel('Secondary quantity for', section, row, 'default', secondaryUom(row, 'default'))" :min="0" :max-fraction-digits="3" :disabled="!canEditMatrix" fluid @update:model-value="markDirty" /><small>{{ secondaryUom(row, "default") }}</small>
											</td>
										</template>
											<td class="erp-number delivery-challan-matrix__total">{{ formatQty(rowTotal(row)) }}</td>
											<td>{{ row.default_uom || row.uom || "—" }}</td>
										</tr>
									</tbody>
								</table>
							</div>
						</article>
					</div>
				</section>
					<div v-if="!matrixBlocks.length" class="delivery-challan-matrix__empty"><i class="pi pi-inbox" /><span>No Delivery Challan item rows are available.</span></div>
			</template>

			<template #after-matrix>
				<div v-if="afterMatrixFields.length" class="delivery-challan-after-matrix" aria-label="Delivery Challan final details">
					<template v-if="canEdit">
						<FormField v-for="field in afterMatrixFields" :key="`after-${fieldKey(field)}`" :field="field" :model-value="form[field.fieldname]" :form="form" :required="Boolean(field.reqd || field.mandatory)" compact :search-handler="linkSearchHandler(field)" @update:model-value="setField(field.fieldname, $event)" />
					</template>
					<template v-else>
						<div v-for="field in afterMatrixFields" :key="`after-fact-${field.fieldname}`" class="delivery-challan-after-matrix__fact"><span>{{ field.label }}</span><strong>{{ formatFieldValue(field) }}</strong></div>
					</template>
				</div>
			</template>

			<template #rail>
				<div
					v-for="total in visibleTotals"
					:key="total.fieldname"
					class="delivery-challan-total"
					:class="{ 'delivery-challan-total--primary': primaryTotals.has(total.fieldname) && totalIsPositive(total) }"
				>
					<span>{{ total.label }}</span><strong>{{ formatTotal(total) }}</strong>
				</div>
				<div v-if="workspace.record?.is_internal_unit" class="delivery-challan-transfer-progress">
					<span>Internal transfer</span><strong>{{ transferPercent }}%</strong>
					<div><i :style="{ width: `${transferPercent}%` }" /></div>
					<small>{{ workspace.record.transfer_complete ? "Transfer complete" : "Completion pending" }}</small>
				</div>
			</template>

			<template #panel>
				<section v-if="workspace.special_source?.active" class="delivery-challan-special-context" aria-label="Source-managed Delivery Challan context">
					<header><span>Source-managed mode</span><strong>Prepared by the originating workflow</strong></header>
					<div><span v-for="mode in workspace.special_source.modes || []" :key="mode">{{ titleCase(mode) }}</span></div>
				</section>
			</template>
		</FabricDocumentWorkspace>

		<Dialog v-model:visible="returnOpen" modal header="Return Delivery Challan" class="fabric-action-dialog" :closable="!acting" :style="{ width: 'min(980px, calc(100vw - 24px))' }">
			<DeliveryChallanReturnPanel :context="workspace.return_context || {}" :acting="acting" :error="returnError" @create="createReturn" @close="closeReturn" />
		</Dialog>
		<Dialog :visible="Boolean(notificationPreparation)" modal header="Send supplier notification" class="fabric-action-dialog" :closable="!acting" :style="{ width: 'min(760px, calc(100vw - 24px))' }" @update:visible="handleNotificationVisibility">
			<SupplierNotificationPanel v-if="notificationPreparation" :preparation="notificationPreparation" :document-values="notificationValues" :acting="acting" :error="notificationError" @send="sendNotification" @close="closeNotification" />
		</Dialog>
		<FabricStockOperationDialog v-model:visible="completionEntryOpen" operation="stock_entry" :name="completionEntryName" @changed="completionEntryChanged" />
		<RelatedDocumentWorkspaceDialog v-model:visible="createdReturnOpen" doctype="YRP Goods Received Note" :name="createdReturnName" @changed="createdReturnChanged" @closed="createdReturnOpen = false" />
		<DocumentConfirmationDialog v-model:visible="lifecycleConfirmVisible" :title="lifecycleConfirmTitle" :message="lifecycleConfirmMessage" :confirm-label="lifecycleConfirmLabel" :busy="Boolean(acting)" @confirm="confirmLifecycleAction" />
		<DocumentConfirmationDialog v-model:visible="sourceConfirmVisible" title="Change Work Order?" message="Changing the Work Order replaces the current source defaults and delivery quantities. Values entered for the current source will be discarded." cancel-label="Keep Current Work Order" confirm-label="Replace Source" :busy="acting === 'preview_source'" return-focus-selector="[id^='field-work_order-']" @update:visible="sourceConfirmationVisibilityChanged" @confirm="confirmSourceChange" />
	</div>
</template>

<script setup>
import Button from "primevue/button"
import Dialog from "primevue/dialog"
import InputNumber from "primevue/inputnumber"
import Tag from "primevue/tag"
import { useToast } from "primevue/usetoast"
import { computed, onMounted, reactive, ref, watch } from "vue"
import { useRouter } from "vue-router"

import {
	executeDeliveryChallanCommand,
	getDeliveryChallanWorkspace,
	previewDeliveryChallanSource,
	saveDeliveryChallan,
} from "../../api/fabricStore.js"
import { searchLinkedDocument } from "../../api/frappe.js"
import FormField from "../../components/common/FormField.vue"
import DocumentActionStrip from "../../components/documents/DocumentActionStrip.vue"
import DocumentConfirmationDialog from "../../components/documents/DocumentConfirmationDialog.vue"
import { hasDocumentDisplayValue, plainTextFromHtml } from "../../utils/documentValues.js"
import DeliveryChallanReturnPanel from "./DeliveryChallanReturnPanel.vue"
import FabricDocumentWorkspace from "./FabricDocumentWorkspace.vue"
import FabricStockOperationDialog from "./FabricStockOperationDialog.vue"
import RelatedDocumentWorkspaceDialog from "./RelatedDocumentWorkspaceDialog.vue"
import SupplierNotificationPanel from "./SupplierNotificationPanel.vue"

const props = defineProps({
	presentation: { type: String, default: "page" },
	name: { type: String, default: "" },
	sourceContext: { type: Object, default: () => ({}) },
})
const emit = defineEmits(["changed", "closed"])
const router = useRouter()
const toast = useToast()

const loading = ref(true)
const acting = ref("")
const error = ref("")
const dirty = ref(false)
const workspace = ref({})
const currentName = ref("")
const itemGroups = ref([])
const correctionGroups = ref([])
const returnOpen = ref(false)
const returnError = ref("")
const notificationPreparation = ref(null)
const notificationError = ref("")
const completionEntryOpen = ref(false)
const completionEntryName = ref("")
const createdReturnOpen = ref(false)
const createdReturnName = ref("")
const sourceFieldRevision = ref(0)
const lifecycleConfirmVisible = ref(false)
const pendingLifecycleCommand = ref("")
const sourceConfirmVisible = ref(false)
const pendingSourceWorkOrder = ref(null)
const form = reactive({})
const primaryTotals = new Set(["total_delivered_qty", "stock_value", "total_value"])
const headerFieldnames = new Set(["process_name", "item", "lot", "supplier_name", "from_location_name"])
const sourceOwnedFieldnames = new Set(["from_finishing", "cutting_bulk_lay_sheet", "cutting_bulk_lay_sheet_detail", "cut_panel_movement", "loose_piece_dc", "pack_piece_dc"])
const presentationHiddenFieldnames = new Set(["received_type"])
const afterMatrixFieldnames = new Set(["is_internal_unit", "includes_packing", "additional_goods_value", "ste_transferred", "ste_transferred_percent", "is_rework"])

const capabilities = computed(() => workspace.value.capabilities || {})
const deliveryChallanActions = computed(() => {
	const busy = Boolean(acting.value)
	const actions = []
	const add = (key, fallback, icon, command, menuOnly = false) => {
		if (!capabilities.value[key]) return
		actions.push({ key, label: capabilityLabel(key, fallback), icon, command, disabled: busy, loading: acting.value === key, menuOnly })
	}
	add("complete_transfer", "Complete Transfer", "pi pi-check-circle", completeTransfer)
	add("return", "Return", "pi pi-replay", () => { returnOpen.value = true })
	if (!currentName.value || dirty.value) add("save", "Save", "pi pi-save", () => runWorkspaceAction("save"))
	if (currentName.value && !dirty.value) add("submit", "Submit", "pi pi-check", () => runWorkspaceAction("submit"))
	add("cancel", "Cancel Document", "pi pi-ban", () => runWorkspaceAction("cancel"), true)
	add("amend", "Amend", "pi pi-copy", () => runWorkspaceAction("amend"), true)
	if (currentName.value && workspace.value.permissions?.can_create && !workspace.value.special_source?.active) {
		actions.push({ key: "duplicate", label: "Duplicate", icon: "pi pi-clone", command: duplicateDeliveryChallan, disabled: busy, loading: acting.value === "duplicate", menuOnly: true })
	}
	add("prepare_sms", "Send SMS", "pi pi-envelope", () => prepareNotification("prepare_sms"), true)
	add("prepare_whatsapp", "Send WhatsApp", "pi pi-comments", () => prepareNotification("prepare_whatsapp"), true)
	const primaryKey = capabilities.value.complete_transfer ? "complete_transfer" : actions.some((action) => action.key === "submit") ? "submit" : actions.some((action) => action.key === "save") ? "save" : actions.some((action) => action.key === "amend") ? "amend" : ""
	return actions.map((action) => ({ ...action, primary: action.key === primaryKey }))
})
const hasWorkspace = computed(() => Boolean(Object.keys(workspace.value || {}).length))
const duplicateLabel = computed(() => props.sourceContext?.duplicate_from ? `Duplicate of ${props.sourceContext.duplicate_from}` : "")
const visibleTotals = computed(() => (workspace.value.totals || []).filter((total) => primaryTotals.has(total.fieldname) || totalIsPositive(total)))
const canEdit = computed(() => Boolean(
	Number(workspace.value.record?.docstatus || 0) === 0
	&& (currentName.value ? workspace.value.permissions?.can_write : workspace.value.permissions?.can_create),
))
const canEditMatrix = computed(() => canEdit.value && !workspace.value.special_source?.read_only)
const visibleFields = computed(() => {
	const result = new Map()
	for (const source of [...(workspace.value.fields || []), ...(workspace.value.dimensions || [])]) {
		if (!source?.fieldname || source.hidden || sourceOwnedFieldnames.has(source.fieldname) || presentationHiddenFieldnames.has(source.fieldname)) continue
		if (source.depends_on && !evaluateCondition(source.depends_on, true)) continue
		if (headerFieldnames.has(source.fieldname)) continue
		if (source.fieldname === "work_order" && currentName.value) continue
		if (result.has(source.fieldname)) continue
		const field = {
			...source,
			reqd: Boolean(source.reqd || source.mandatory || evaluateCondition(source.mandatory_depends_on)),
			read_only: Boolean(source.read_only || source.locked || evaluateCondition(source.read_only_depends_on)),
		}
		field.dependency_locked = Boolean(
			(["from_warehouse", "from_address"].includes(source.fieldname) && !form.from_location)
			|| (["to_warehouse", "supplier_address"].includes(source.fieldname) && !form.supplier),
		)
		field.read_only ||= field.dependency_locked
		if (source.fieldname === "from_warehouse") field.link_filters = { disabled: 0, supplier: form.from_location || "__unselected__" }
		if (source.fieldname === "to_warehouse") field.link_filters = { disabled: 0, supplier: form.supplier || "__unselected__" }
		if ((!canEdit.value || (field.read_only && !field.dependency_locked)) && !hasDocumentDisplayValue(form[source.fieldname] ?? source.value)) continue
		result.set(source.fieldname, field)
	}
	return [...result.values()].sort((left, right) => fieldOrder(left.fieldname) - fieldOrder(right.fieldname))
})
const fieldGroups = computed(() => {
	const groups = new Map(dcFieldGroups.map((group) => [group.key, { ...group, fields: [] }]))
	for (const field of visibleFields.value) {
		if (afterMatrixFieldnames.has(field.fieldname)) continue
		;(groups.get(fieldGroupKey(field.fieldname)) || groups.get("additional")).fields.push(field)
	}
	return [...groups.values()].filter((group) => group.fields.length)
})
const primaryFieldGroups = computed(() => fieldGroups.value.filter((group) => ["document", "movement"].includes(group.key)))
const secondaryFieldGroups = computed(() => fieldGroups.value.filter((group) => !["document", "movement"].includes(group.key)))
const afterMatrixFields = computed(() => visibleFields.value.filter((field) => afterMatrixFieldnames.has(field.fieldname)))
const matrixBlocks = computed(() => {
	const blocks = []
	if (itemGroups.value.length) blocks.push({ key: "items", kind: "items", title: "Delivery quantities", groups: itemGroups.value })
	for (const [index, correction] of correctionGroups.value.entries()) {
		blocks.push({
			key: correction.work_order_correction || `correction-${index}`,
			kind: "corrections",
			title: correction.title || correction.work_order_correction || "Correction quantities",
			groups: correction.item_details || [],
		})
	}
	return blocks
})
const headerFacts = computed(() => [
	["Source", workspace.value.record?.work_order || form.work_order],
	["Process", workspace.value.record?.process_name || form.process_name],
	["Item", workspace.value.record?.item || form.item],
	["Lot", workspace.value.record?.lot || form.lot],
].filter(([, value]) => value).map(([label, value]) => ({ label, value })))
const statusSeverity = computed(() => {
	const record = workspace.value.record || {}
	if (Number(record.docstatus) === 2 || record.status === "Cancelled") return "danger"
	if (record.transfer_complete) return "success"
	return Number(record.docstatus) === 1 ? "info" : "secondary"
})
const transferPercent = computed(() => Math.max(0, Math.min(100, Number(workspace.value.record?.ste_transferred_percent || (workspace.value.record?.transfer_complete ? 100 : 0)))))
const notificationValues = computed(() => ({ ...(workspace.value.record || {}), ...form }))

async function load(refresh = false) {
	if (refresh) acting.value = "reload"
	else loading.value = true
	error.value = ""
	const requestedName = props.name || currentName.value
	try {
		currentName.value = requestedName
		applyWorkspace(await getDeliveryChallanWorkspace(currentName.value, props.sourceContext) || {})
	} catch (reason) {
		clearWorkspaceState(requestedName)
		error.value = reason?.message || "Unable to load this Delivery Challan."
	} finally {
		loading.value = false
		acting.value = ""
	}
}

function clearWorkspaceState(name = "") {
	workspace.value = {}
	currentName.value = name
	for (const key of Object.keys(form)) delete form[key]
	itemGroups.value = []
	correctionGroups.value = []
	dirty.value = false
	returnOpen.value = false
	returnError.value = ""
	notificationPreparation.value = null
	notificationError.value = ""
}

function applyWorkspace(nextWorkspace) {
	workspace.value = nextWorkspace || {}
	currentName.value = workspace.value.record?.name || ""
	for (const key of Object.keys(form)) delete form[key]
	Object.assign(form, clone(workspace.value.values || {}))
	for (const field of workspace.value.fields || []) {
		if (!(field.fieldname in form)) form[field.fieldname] = field.value
	}
	for (const dimension of workspace.value.dimensions || []) {
		if (!(dimension.fieldname in form)) form[dimension.fieldname] = dimension.value
	}
	if (!form.from_location) {
		form.from_warehouse = ""
		form.from_address = ""
		form.from_address_details = ""
	}
	if (!form.supplier) {
		form.to_warehouse = ""
		form.supplier_address = ""
		form.supplier_address_details = ""
	}
	itemGroups.value = normalizeGroups(workspace.value.matrices?.items || workspace.value.item_groups || [])
	correctionGroups.value = clone(workspace.value.matrices?.correction_items || workspace.value.correction_item_groups || [])
	for (const correction of correctionGroups.value) correction.item_details = normalizeGroups(correction.item_details || [])
	dirty.value = false
	error.value = ""
	returnOpen.value = false
	returnError.value = ""
	notificationPreparation.value = null
	notificationError.value = ""
}

async function setField(fieldname, value) {
	if (fieldname === "work_order" && !currentName.value && value !== form.work_order) {
		if (dirty.value) {
			pendingSourceWorkOrder.value = value
			sourceConfirmVisible.value = true
			return
		}
		await applySourceChange(value)
		return
	}
	form[fieldname] = value
	if (fieldname === "supplier") {
		form.to_warehouse = ""
		form.supplier_address = ""
		form.supplier_address_details = ""
	}
	if (fieldname === "from_location") {
		form.from_warehouse = ""
		form.from_address = ""
		form.from_address_details = ""
	}
	if (["posting_date", "posting_time"].includes(fieldname)) form.edit_posting_date_and_time = 1
	markDirty()
}
async function applySourceChange(value) {
	if (value) {
		await previewSource(value)
		return
	}
	for (const fieldname of [
		"work_order", "production_detail", "process_name", "item", "lot",
		"supplier", "supplier_name", "supplier_address", "supplier_address_details",
		"from_location", "from_location_name", "from_warehouse", "from_address", "from_address_details",
		"to_warehouse",
	]) form[fieldname] = ""
	itemGroups.value = []
	correctionGroups.value = []
	sourceFieldRevision.value += 1
	markDirty()
}
async function previewSource(value) {
	acting.value = "preview_source"
	error.value = ""
	try {
		const preview = await previewDeliveryChallanSource(value, { ...form, work_order: value })
		applyWorkspace(preview || {})
	} catch (reason) {
		error.value = reason?.message || "Unable to refresh Delivery Challan defaults."
		sourceFieldRevision.value += 1
	} finally {
		acting.value = ""
	}
}
async function confirmSourceChange() {
	const value = pendingSourceWorkOrder.value
	pendingSourceWorkOrder.value = null
	sourceConfirmVisible.value = false
	if (value !== null) await applySourceChange(value)
}
function sourceConfirmationVisibilityChanged(visible) {
	sourceConfirmVisible.value = visible
	if (visible || pendingSourceWorkOrder.value === null) return
	pendingSourceWorkOrder.value = null
	sourceFieldRevision.value += 1
}

async function runWorkspaceAction(action) {
	if (action === "save") return save(false)
	if (action === "submit") return save(true)
	if (["cancel", "amend"].includes(action)) return requestLifecycleAction(action)
}

async function duplicateDeliveryChallan() {
	if (!currentName.value || !workspace.value.permissions?.can_create) return
	if (props.presentation === "page") {
		await router.push({ name: "fabric-delivery-challan-new", query: { duplicate_from: currentName.value } })
		return
	}
	acting.value = "duplicate"
	error.value = ""
	try {
		applyWorkspace(await getDeliveryChallanWorkspace("", { duplicate_from: currentName.value }) || {})
		dirty.value = true
		emit("changed", workspace.value)
	} catch (reason) {
		error.value = reason?.message || "Unable to duplicate this Delivery Challan."
	} finally {
		acting.value = ""
	}
}

async function save(submit) {
	acting.value = submit ? "submit" : "save"
	error.value = ""
	try {
		const saved = await saveDeliveryChallan({
			...clone(form),
			item_details: clone(itemGroups.value),
			correction_item_details: clone(correctionGroups.value),
		}, {
			name: currentName.value,
			submit,
			expectedModified: workspace.value.record?.modified,
		})
		applyWorkspace(saved || {})
		toast.add({ severity: "success", summary: submit ? "Delivery Challan submitted" : "Delivery Challan saved", detail: workspace.value.record?.name || "Your changes are saved.", life: 3500 })
		emit("changed", workspace.value)
	} catch (reason) {
		error.value = reason?.message || `Unable to ${submit ? "submit" : "save"} this Delivery Challan.`
	} finally {
		acting.value = ""
	}
}

async function runCommand(command, payload = {}, destructive = false) {
	if (!currentName.value) return
	acting.value = command
	error.value = ""
	try {
		const result = await executeDeliveryChallanCommand(currentName.value, command, payload, workspace.value.record?.modified)
		const updated = result?.workspace || result
		if (updated?.record) {
			applyWorkspace(updated)
			emit("changed", workspace.value)
		}
		return result
	} catch (reason) {
		error.value = reason?.message || `Unable to ${command.replaceAll("_", " ")} this Delivery Challan.`
		return null
	} finally {
		acting.value = ""
	}
}
const lifecycleConfirmTitle = computed(() => pendingLifecycleCommand.value === "cancel" ? "Cancel Delivery Challan?" : "Amend Delivery Challan?")
const lifecycleConfirmLabel = computed(() => pendingLifecycleCommand.value === "cancel" ? "Cancel Delivery Challan" : "Create Amendment")
const lifecycleConfirmMessage = computed(() => pendingLifecycleCommand.value === "cancel" ? `Cancel ${currentName.value}? This keeps the document for audit and reverses its submitted effect.` : `Create a new draft amendment from ${currentName.value}?`)
function requestLifecycleAction(command) { pendingLifecycleCommand.value = command; lifecycleConfirmVisible.value = true }
async function confirmLifecycleAction() { const command = pendingLifecycleCommand.value; lifecycleConfirmVisible.value = false; pendingLifecycleCommand.value = ""; if (command) await runCommand(command) }

async function createReturn(payload) {
	returnError.value = ""
	const result = await runCommand("return", payload)
	if (result?.workspace) {
		returnOpen.value = false
		if (result.created?.doctype === "YRP Goods Received Note" && result.created.name) {
			createdReturnName.value = result.created.name
			createdReturnOpen.value = true
		}
	}
	else returnError.value = error.value || "Unable to create the return Goods Received Note."
}
function closeReturn() { returnOpen.value = false; returnError.value = "" }
async function completeTransfer() {
	const result = await runCommand("complete_transfer")
	if (result?.created?.doctype === "YRP Stock Entry" && result.created.name) {
		completionEntryName.value = result.created.name
		completionEntryOpen.value = true
	}
}
async function completionEntryChanged() {
	completionEntryOpen.value = false
	await load(true)
	emit("changed", workspace.value)
}
async function createdReturnChanged() {
	await load(true)
	emit("changed", workspace.value)
}
async function prepareNotification(command) {
	const result = await runCommand(command)
	if (result?.context) { notificationPreparation.value = result; notificationError.value = "" }
}
async function sendNotification({ channel, payload }) {
	notificationError.value = ""
	const result = await runCommand(`send_${channel}`, payload)
	if (!result) return
	if (result.result?.ok) notificationPreparation.value = null
	else error.value = result.result?.error || `Unable to send ${channel === "sms" ? "SMS" : "WhatsApp"}.`
}
function closeNotification() { notificationPreparation.value = null; notificationError.value = "" }
function handleNotificationVisibility(visible) { if (!visible) closeNotification() }

function fieldKey(field) { return `${field.fieldname}-${field.fieldname === "work_order" ? sourceFieldRevision.value : field.idx || "value"}` }
const dcFieldGroups = [
	{ key: "document", eyebrow: "Document", label: "Document & posting" },
	{ key: "movement", eyebrow: "Route", label: "Source & receiver" },
	{ key: "logistics", eyebrow: "Dispatch", label: "Transport details" },
	{ key: "controls", eyebrow: "Options", label: "Dispatch controls" },
	{ key: "transfer", eyebrow: "Status", label: "Internal transfer" },
	{ key: "additional", eyebrow: "Additional", label: "Additional details" },
]
const dcGroupFields = {
	document: ["naming_series", "work_order", "purchase_order", "posting_date", "posting_time", "edit_posting_date_and_time", "actual_date", "production_detail", "allow_non_bundle"],
	movement: ["from_location", "from_warehouse", "from_address", "from_address_details", "supplier", "to_warehouse", "supplier_address", "supplier_address_details"],
	logistics: ["vehicle_no", "supplier_document_no", "letter_head", "comments"],
	controls: ["includes_packing", "additional_goods_value"],
	transfer: ["is_internal_unit", "transfer_complete", "ste_transferred", "ste_transferred_percent"],
}
const dcFieldOrder = Object.values(dcGroupFields).flat()
function fieldOrder(fieldname) { const index = dcFieldOrder.indexOf(fieldname); return index === -1 ? dcFieldOrder.length + 1 : index }
function fieldGroupKey(fieldname) { return Object.entries(dcGroupFields).find(([, fields]) => fields.includes(fieldname))?.[0] || "additional" }
function linkSearchHandler(field) {
	if (field.fieldname === "from_address") return (text) => searchLinkedDocument("Address", "Supplier", form.from_location, text)
	if (field.fieldname === "supplier_address") return (text) => searchLinkedDocument("Address", "Supplier", form.supplier, text)
	return null
}
function markDirty() { if (!loading.value) dirty.value = true }
function capabilityLabel(name, fallback) { return name === "save" ? fallback : capabilities.value[name]?.label || fallback }
function statusLabel(docstatus) { return Number(docstatus) === 1 ? "Submitted" : Number(docstatus) === 2 ? "Cancelled" : "Draft" }
function evaluateCondition(condition, fallback = false) {
	if (!condition) return fallback
	const expression = String(condition).replace(/^eval:/, "").trim()
	const direct = expression.match(/^(!)?doc\.([A-Za-z0-9_]+)$/)
	if (direct) {
		const value = Boolean(conditionValue(direct[2]))
		return direct[1] ? !value : value
	}
	const comparison = expression.match(/^doc\.([A-Za-z0-9_]+)\s*(===|==|!==|!=)\s*['"]?([^'"]+)['"]?$/)
	if (!comparison) return fallback
	const equal = String(conditionValue(comparison[1]) ?? "") === comparison[3]
	return comparison[2].includes("!") ? !equal : equal
}
function conditionValue(fieldname) {
	return Object.prototype.hasOwnProperty.call(form, fieldname)
		? form[fieldname]
		: workspace.value.record?.[fieldname]
}
function primaryValues(group) { return group.primary_attribute_values?.length ? group.primary_attribute_values : ["default"] }
function hasPrimaryAttribute(group) { return Boolean(group.primary_attribute && primaryValues(group).some((value) => value !== "default")) }
function pendingQuantity(value) { return value?.pending_qty ?? value?.pending_quantity ?? 0 }
function secondaryUom(row, value) { return String(row.values?.[value]?.secondary_uom || row.secondary_uom || "").trim() }
function hasSecondaryQuantity(group) { return (group.items || []).some((row) => primaryValues(group).some((value) => Boolean(secondaryUom(row, value)))) }
function logicalRowCount(groups) { return (groups || []).reduce((total, group) => total + (group.items?.length || 0), 0) }
function rowTotal(row) { return Object.values(row.values || {}).reduce((total, value) => total + Number(value?.qty || 0), 0) }
function rowKey(row, index) { return [row.item_variant || row.name, row.row_index, row.received_type, row.delivery_challan_item, index].filter((value) => value !== undefined && value !== "").join("-") }
function matrixInputLabel(action, section, row, value, uom = "") {
	const item = section.name || row.item_variant || row.name || "item"
	const context = [...Object.values(row.attributes || {}), value === "default" ? "" : value].filter(Boolean)
	return `${action} ${item}${context.length ? `, ${context.join(", ")}` : ""}${uom ? ` in ${uom}` : ""}`
}
function formatQty(value) { return Number(value || 0).toLocaleString("en-IN", { maximumFractionDigits: 3 }) }
function formatTotal(total) { return Number(total.value || 0).toLocaleString("en-IN", { maximumFractionDigits: total.fieldname?.includes("value") ? 2 : 3 }) }
function totalIsPositive(total) { return Number(total?.value || 0) > 0 }
function formatFieldValue(field) {
	const value = form[field.fieldname] ?? field.value
	if (["Date", "Datetime"].includes(field.fieldtype)) {
		const match = String(value || "").match(/^(\d{4})-(\d{2})-(\d{2})(.*)$/)
		if (match) return `${match[3]}-${match[2]}-${match[1]}${field.fieldtype === "Datetime" ? match[4] : ""}`
	}
	if (field.fieldtype === "Check") return Number(value) ? "Yes" : "No"
	if (["Currency", "Float", "Int", "Percent"].includes(field.fieldtype)) return Number(value || 0).toLocaleString("en-IN", { maximumFractionDigits: 3 })
	return value === null || value === undefined || value === "" ? "—" : plainTextFromHtml(value)
}
function titleCase(value) { return String(value || "").replaceAll("_", " ").replace(/\b\w/g, (character) => character.toUpperCase()) }
function clone(value) { return JSON.parse(JSON.stringify(value || {})) }
function normalizeGroups(groups) {
	const normalized = clone(groups || [])
	for (const group of normalized) {
		for (const row of group.items || []) {
			row.values ||= {}
			for (const value of primaryValues(group)) row.values[value] ||= { qty: 0 }
		}
	}
	return normalized
}
function itemSections(groups) {
	return (groups || []).flatMap((group, groupIndex) => {
		const sections = new Map()
		for (const row of group.items || []) {
			const name = row.name || row.item || row.item_variant || ""
			const lot = row.dimensions?.lot || row.lot || ""
			const key = `${groupIndex}-${name || "item"}-${lot}`
			if (!sections.has(key)) sections.set(key, { group, name, lot, key, items: [] })
			sections.get(key).items.push(row)
		}
		return [...sections.values()]
	})
}
function identityColumns(group) {
	const columns = (group.attributes || []).map((key) => ({ key, label: key, source: "attributes" }))
	const dimensions = []
	for (const row of group.items || []) {
		for (const key of Object.keys(row.dimensions || {})) if (key !== "lot" && !dimensions.includes(key)) dimensions.push(key)
	}
	for (const key of dimensions) columns.push({ key, label: titleCase(key), source: "dimensions" })
	return columns.filter((column, index, values) => values.findIndex((entry) => entry.key === column.key) === index)
}
function identityValue(row, column) {
	const value = column.source === "dimensions" ? row.dimensions?.[column.key] : row.attributes?.[column.key]
	return value === null || value === undefined || value === "" ? "—" : String(value)
}

onMounted(() => load())
watch(() => [props.name, JSON.stringify(props.sourceContext || {})], ([name, source], previous) => {
	if (!previous || name === previous[0] && source === previous[1]) return
	currentName.value = name || ""
	load()
})
</script>

<style scoped>
.delivery-challan-workspace { width: 100%; min-width: 0; }
.delivery-challan-after-matrix { display: grid; grid-template-columns: repeat(5, minmax(0, 1fr)); align-items: end; gap: 10px 14px; padding: 2px; }
.delivery-challan-after-matrix__fact { display: grid; min-width: 0; gap: 3px; padding: 8px 2px; border-bottom: 1px solid var(--erp-border); }
.delivery-challan-after-matrix__fact span { color: var(--erp-text-muted); font-size: var(--erp-font-size-min); font-weight: 750; letter-spacing: .035em; text-transform: uppercase; }
.delivery-challan-after-matrix__fact strong { color: var(--erp-text); font-size: var(--erp-font-size-caption); line-height: 1.4; white-space: pre-line; overflow-wrap: anywhere; }
@media (max-width: 1100px) { .delivery-challan-after-matrix { grid-template-columns: repeat(3, minmax(0, 1fr)); } }
@media (max-width: 700px) { .delivery-challan-after-matrix { grid-template-columns: repeat(2, minmax(0, 1fr)); } }
.delivery-challan-workspace--page { max-width: 1840px; margin: 0 auto; padding: 0 clamp(2px, .7vw, 10px) var(--erp-space-3); }
.delivery-challan-header__identity { display: flex; min-width: 0; align-items: center; gap: 12px; }
.delivery-challan-header__title { display: grid; min-width: 0; gap: 2px; }
.delivery-challan-header__identity h1 { margin: 0; color: var(--erp-text); font-size: 19px; line-height: 1.15; letter-spacing: -.018em; }
.delivery-challan-header__title > span { color: var(--erp-text-muted); font-size: var(--erp-font-size-caption); font-weight: 700; }
.delivery-challan-header__facts { display: flex; min-width: 0; flex: 1; align-items: center; gap: 16px; padding-left: 13px; border-left: 1px solid var(--erp-border); }
.delivery-challan-header__facts > div { display: grid; min-width: 0; gap: 2px; flex: 0 1 auto; }
.delivery-challan-header__facts span, .delivery-challan-total span, .delivery-challan-transfer-progress > span, .delivery-challan-matrix__header span, .delivery-challan-special-context header span { color: var(--erp-text-muted); font-size: var(--erp-font-size-min); font-weight: 750; letter-spacing: .035em; text-transform: uppercase; }
.delivery-challan-header__facts strong { overflow: hidden; max-width: 180px; color: var(--erp-text); font-size: var(--erp-font-size-caption); text-overflow: ellipsis; white-space: nowrap; }
.delivery-challan-header__identity--embedded { width: 100%; overflow: hidden; }
.delivery-challan-header__identity--embedded .delivery-challan-header__facts { overflow-x: auto; flex-wrap: nowrap; padding-left: 0; border-left: 0; scrollbar-width: thin; }
.delivery-challan-header__identity--embedded .delivery-challan-header__facts > div { flex: 0 0 auto; }
.delivery-challan-fields { display: grid; gap: 0; overflow: hidden; border: 1px solid var(--erp-border); border-radius: var(--erp-panel-radius); background: var(--erp-surface); }
.delivery-challan-field-group { overflow: hidden; border: 0; border-bottom: 1px solid var(--erp-border); background: var(--erp-surface); box-shadow: none; }
.delivery-challan-field-group:last-child { border-bottom: 0; }
.delivery-challan-field-group > header { display: flex; min-height: 36px; align-items: center; gap: 10px; padding: 6px 10px; border-bottom: 1px solid var(--erp-border); background: var(--erp-surface-soft); }
.delivery-challan-field-group > header span { color: var(--erp-accent-dark); font-size: var(--erp-font-size-min); font-weight: 800; letter-spacing: .055em; text-transform: uppercase; }
.delivery-challan-field-group > header h2 { margin: 0; color: var(--erp-text); font-size: var(--erp-font-size-section); }
.delivery-challan-field-group__grid { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 8px 10px; padding: 8px 10px 10px; }
.delivery-challan-field-group[data-group="movement"] .delivery-challan-field-group__grid { grid-template-columns: repeat(3, minmax(0, 1fr)); }
.delivery-challan-field-group__grid :deep(.form-field--wide) { grid-column: 1 / -1; }
.delivery-challan-field-fact { display: grid; min-height: 50px; align-content: center; gap: 4px; padding: 7px 10px; border-bottom: 1px solid color-mix(in srgb, var(--erp-border) 76%, white); }
.delivery-challan-field-fact span { color: var(--erp-text-muted); font-size: var(--erp-font-size-min); font-weight: 750; letter-spacing: .035em; text-transform: uppercase; }
.delivery-challan-field-fact strong { overflow: hidden; color: var(--erp-text); font-size: var(--erp-font-size-caption); text-overflow: ellipsis; white-space: nowrap; }
.delivery-challan-matrix { overflow: hidden; min-width: 0; border: 1px solid var(--erp-border); border-radius: var(--erp-panel-radius); background: var(--erp-surface); box-shadow: none; }
.delivery-challan-matrix__header { display: flex; min-height: 48px; align-items: center; justify-content: space-between; gap: 12px; padding: 8px 12px; border-bottom: 1px solid var(--erp-border); background: var(--erp-surface-soft); }
.delivery-challan-matrix__header > div { display: grid; gap: 2px; }
.delivery-challan-matrix__header h2 { margin: 0; font-size: var(--erp-font-size-section); }
.delivery-challan-matrix__header > strong { padding: 3px 8px; color: var(--erp-accent); font-size: var(--erp-font-size-min); background: var(--erp-accent-soft); border-radius: var(--erp-pill-radius); }
.delivery-challan-matrix__stack { display: grid; gap: var(--erp-space-3); padding: var(--erp-space-3); background: color-mix(in srgb, var(--erp-surface-soft) 66%, white); }
.delivery-challan-matrix__group { overflow: hidden; min-width: 0; border: 1px solid var(--erp-border); border-radius: var(--erp-control-radius); background: var(--erp-surface); box-shadow: none; }
.delivery-challan-matrix__group > header { display: flex; min-height: 40px; align-items: center; padding: 7px 10px; border-bottom: 1px solid var(--erp-border); }
.delivery-challan-matrix__group > header div { display: grid; gap: 2px; }
.delivery-challan-matrix__group > header strong { color: var(--erp-text); font-size: var(--erp-font-size-caption); }
.delivery-challan-matrix__group > header span { color: var(--erp-text-muted); font-size: var(--erp-font-size-min); }
.delivery-challan-matrix__scroll table { min-width: 760px; }
.delivery-challan-matrix__pending-heading, .delivery-challan-matrix__pending { background: var(--erp-attention-soft); }
.delivery-challan-matrix__quantity-heading, .delivery-challan-matrix__quantity { background: var(--erp-accent-soft); }
.delivery-challan-matrix__pending { min-width: 78px; color: var(--erp-attention-text); font-weight: 750; }
.delivery-challan-matrix__quantity, .delivery-challan-matrix__secondary { min-width: 106px; }
.delivery-challan-matrix :deep(.p-inputnumber) { min-width: 94px; }
.delivery-challan-matrix :deep(.p-inputnumber-input) { height: 32px; padding: 5px 8px; text-align: right; }
.delivery-challan-matrix__secondary small { display: block; margin-top: 3px; color: var(--erp-text-muted); font-size: var(--erp-font-size-min); }
.delivery-challan-matrix__primary-cell > small { display: block; margin-top: 3px; color: var(--erp-attention-text); font-size: var(--erp-font-size-min); text-align: right; }
.delivery-challan-matrix__secondary-inline { display: grid; grid-template-columns: minmax(72px, 1fr) auto; align-items: center; gap: 5px; margin-top: 5px; }
.delivery-challan-matrix__secondary-inline span { color: var(--erp-text-muted); font-size: var(--erp-font-size-min); }
.delivery-challan-matrix__total { color: var(--erp-accent); font-weight: 800; }
.delivery-challan-matrix__empty { display: grid; min-height: 140px; place-items: center; align-content: center; gap: 6px; color: var(--erp-text-muted); border: 1px solid var(--erp-border); border-radius: var(--erp-control-radius); background: var(--erp-surface); }
.delivery-challan-total, .delivery-challan-transfer-progress { display: grid; min-height: 58px; align-content: center; gap: 2px; padding: 9px 12px; border: 0; border-bottom: 1px solid var(--erp-border); border-radius: 0; background: var(--erp-surface); }
.delivery-challan-total:last-child, .delivery-challan-transfer-progress:last-child { border-bottom: 0; }
.delivery-challan-total strong, .delivery-challan-transfer-progress strong { color: var(--erp-text); font-size: 18px; font-weight: 780; font-variant-numeric: tabular-nums; }
.delivery-challan-total--primary { background: color-mix(in srgb, var(--erp-accent-soft) 76%, white); box-shadow: inset 3px 0 0 color-mix(in srgb, var(--erp-accent) 76%, white); }
.delivery-challan-total--primary strong { color: var(--erp-accent-hover); font-size: 21px; }
.delivery-challan-transfer-progress > div { overflow: hidden; height: 6px; background: var(--erp-border); border-radius: var(--erp-pill-radius); }
.delivery-challan-transfer-progress > div i { display: block; height: 100%; background: var(--erp-accent); transition: width .2s ease; }
.delivery-challan-transfer-progress small { color: var(--erp-text-muted); font-size: var(--erp-font-size-min); }
.delivery-challan-special-context { display: grid; overflow: hidden; border: 1px solid var(--erp-border); border-radius: var(--erp-control-radius); background: var(--erp-surface); }
.delivery-challan-special-context header { display: flex; min-height: 42px; align-items: center; justify-content: space-between; gap: 12px; padding: 8px 12px; border-bottom: 1px solid var(--erp-border); background: var(--erp-surface-soft); }
.delivery-challan-special-context header strong { color: var(--erp-text-muted); font-size: var(--erp-font-size-caption); }
.delivery-challan-special-context > div { display: flex; gap: 7px; padding: var(--erp-space-3); flex-wrap: wrap; }
.delivery-challan-special-context > div span { padding: 5px 9px; color: var(--erp-accent); font-size: var(--erp-font-size-caption); font-weight: 750; border: 1px solid var(--erp-accent-border); border-radius: var(--erp-pill-radius); background: var(--erp-accent-soft); }
@media (min-width: 1201px) {
	.delivery-challan-fields--secondary { grid-template-columns: repeat(2, minmax(0, 1fr)); }
	.delivery-challan-fields--secondary .delivery-challan-field-group:nth-child(odd) { border-right: 1px solid var(--erp-border); }
	.delivery-challan-fields--secondary .delivery-challan-field-group:nth-last-child(-n + 2) { border-bottom: 0; }
	.delivery-challan-fields--secondary .delivery-challan-field-group:last-child:nth-child(odd) { grid-column: 1 / -1; border-right: 0; }
	.delivery-challan-fields--secondary .delivery-challan-field-group__grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
}
@media (max-width: 1100px) { .delivery-challan-header__facts { overflow-x: auto; padding-right: 18px; flex-wrap: nowrap; scrollbar-width: thin; -webkit-mask-image: linear-gradient(to right, #000 0, #000 calc(100% - 18px), transparent 100%); mask-image: linear-gradient(to right, #000 0, #000 calc(100% - 18px), transparent 100%); } .delivery-challan-header__facts:focus-visible { outline: 2px solid var(--erp-accent); outline-offset: 2px; } .delivery-challan-header__facts > div { flex: 0 0 auto; } }
@media (max-width: 760px) { .delivery-challan-header__identity { align-items: flex-start; flex-wrap: wrap; } .delivery-challan-header__facts { width: 100%; flex: 1 0 100%; gap: 8px 14px; padding: 8px 18px 0 0; border-top: 1px solid var(--erp-border); border-left: 0; } .delivery-challan-header__identity--embedded { align-items: center; flex-wrap: nowrap; } .delivery-challan-header__identity--embedded .delivery-challan-header__facts { width: auto; padding-top: 0; border-top: 0; flex: 1 1 auto; } }
@media (max-width: 1200px) { .delivery-challan-field-group__grid { grid-template-columns: repeat(3, minmax(0, 1fr)); } }
@media (max-width: 900px) { .delivery-challan-field-group__grid, .delivery-challan-field-group[data-group="movement"] .delivery-challan-field-group__grid { grid-template-columns: repeat(2, minmax(0, 1fr)); } }
@media (max-width: 620px) { .delivery-challan-workspace--page { padding-right: 0; padding-left: 0; } .delivery-challan-field-group__grid, .delivery-challan-field-group[data-group="movement"] .delivery-challan-field-group__grid { grid-template-columns: 1fr; gap: 4px; padding: 10px; } .delivery-challan-field-group__grid--facts, .delivery-challan-field-group[data-group="movement"] .delivery-challan-field-group__grid--facts { grid-template-columns: repeat(2, minmax(0, 1fr)); } .delivery-challan-field-fact { min-height: 46px; padding: 6px 8px; } .delivery-challan-matrix__stack { padding: var(--erp-space-2); } }
:global(.fabric-action-dialog .p-dialog-content) { min-height: 0; }
@media (max-width: 620px) { :global(.fabric-action-dialog) { width: 100vw !important; height: 100dvh !important; max-height: 100dvh !important; margin: 0; border-radius: 0; } :global(.fabric-action-dialog .p-dialog-content) { flex: 1; overflow-y: auto; } }
</style>
