<template>
	<div class="goods-received-note-workspace" :class="`goods-received-note-workspace--${presentation}`">
		<FabricDocumentWorkspace
			doctype="YRP Goods Received Note"
			title="Goods Received Note"
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
			<template #header="{ record, headingId }">
				<div class="goods-received-note-header__identity" :class="{ 'goods-received-note-header__identity--embedded': presentation === 'embedded' }">
					<div v-if="presentation !== 'embedded'" class="goods-received-note-header__title"><h1 :id="headingId">Goods Received Note</h1><span>{{ record.name || duplicateLabel || (loading && name ? "Loading…" : error && name ? name : "New document") }}</span></div>
					<DocumentStatusBadge v-if="hasWorkspace && presentation !== 'embedded'" :docstatus="record.docstatus" :label="record.status || statusLabel(record.docstatus)" />
					<div v-if="headerFacts.length" class="goods-received-note-header__facts" role="region" aria-label="Goods Received Note context" tabindex="0">
						<div v-for="fact in headerFacts" :key="fact.label"><span>{{ fact.label }}</span><strong :title="String(fact.value)">{{ fact.value }}</strong></div>
					</div>
				</div>
			</template>

			<template #header-actions>
				<DocumentActionStrip :actions="goodsReceivedNoteActions" />
			</template>

			<template #fields>
				<DocumentFieldGroupGrid
					v-if="canEdit && visibleFields.length"
					:groups="primaryFieldGroups"
					:facts="!canEdit"
					aria-label="Goods Received Note fields"
					root-class="goods-received-note-fields"
					card-class="goods-received-note-field-group"
					content-class="goods-received-note-field-group__grid"
				>
					<template #default="{ group }">
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
							<div v-for="field in group.fields" :key="`fact-${field.fieldname}`" class="goods-received-note-field-fact">
								<span>{{ field.label }}</span><strong :title="String(formatFieldValue(field))">{{ formatFieldValue(field) }}</strong>
							</div>
						</template>
					</template>
				</DocumentFieldGroupGrid>
				<Tabs v-else-if="hasWorkspace" v-model:value="activeTab" class="goods-received-note-tabs erp-tabs">
					<TabList><Tab value="overview">Overview</Tab><Tab value="receivables">Receivables <span v-if="logicalRowCount(itemGroups)">{{ logicalRowCount(itemGroups) }}</span></Tab></TabList>
					<TabPanels>
						<TabPanel value="overview"><DocumentOverview :fields="overviewFields" :definitions="overviewDefinitions" include-unclaimed :unclaimed-definition="overviewAdditionalDefinition" aria-label="Goods Received Note overview" id-prefix="goods-received-note-overview" /></TabPanel>
						<TabPanel value="receivables">
							<div class="goods-received-note-tab-matrices">
								<section v-for="block in matrixBlocks" :key="`readonly-${block.key}`" class="goods-received-note-tab-matrix">
									<header><div><span>{{ block.kind === 'items' ? 'Receivables' : 'Corrections' }}</span><h2>{{ block.title }}</h2></div><strong>{{ logicalRowCount(block.groups) }} rows</strong></header>
									<StockItemMatrix :groups="block.groups" doctype="YRP Goods Received Note" group-by-item show-lot-column show-availability show-pricing show-amount :currency="workspace.record?.currency || ''" />
								</section>
								<div v-if="!matrixBlocks.length" class="goods-received-note-matrix__empty"><i class="pi pi-inbox" /><span>No Goods Received Note item rows are available.</span></div>
							</div>
						</TabPanel>
					</TabPanels>
				</Tabs>
			</template>

			<template #secondary-fields>
				<DocumentFieldGroupGrid
					v-if="canEdit && secondaryFieldGroups.length"
					:groups="secondaryFieldGroups"
					:facts="!canEdit"
					wide-last-odd
					aria-label="Additional Goods Received Note fields"
					root-class="goods-received-note-fields goods-received-note-fields--secondary"
					card-class="goods-received-note-field-group"
					content-class="goods-received-note-field-group__grid"
				>
					<template #default="{ group }">
						<template v-if="canEdit">
							<FormField v-for="field in group.fields" :key="fieldKey(field)" :field="field" :model-value="form[field.fieldname]" :form="form" :required="Boolean(field.reqd || field.mandatory)" compact :search-handler="linkSearchHandler(field)" @update:model-value="setField(field.fieldname, $event)" />
						</template>
						<template v-else>
							<div v-for="field in group.fields" :key="`fact-${field.fieldname}`" class="goods-received-note-field-fact"><span>{{ field.label }}</span><strong :title="String(formatFieldValue(field))">{{ formatFieldValue(field) }}</strong></div>
						</template>
					</template>
				</DocumentFieldGroupGrid>
			</template>

			<template #matrix>
				<template v-if="canEdit">
				<section
					v-for="block in matrixBlocks"
					:key="block.key"
					class="goods-received-note-matrix"
					:class="`goods-received-note-matrix--${block.kind}`"
				>
					<header class="goods-received-note-matrix__header">
						<div><span>{{ block.kind === "items" ? "Receivables" : "Corrections" }}</span><h2>{{ block.title }}</h2></div>
						<strong>{{ logicalRowCount(block.groups) }} rows</strong>
					</header>
					<div class="goods-received-note-matrix__stack">
						<article v-for="section in itemSections(block.groups)" :key="section.key" class="goods-received-note-matrix__group">
							<header><div><strong>{{ section.name || "Unspecified item" }}</strong><small v-if="section.lot && !canEditLots">{{ section.lot }}</small></div></header>
							<div class="erp-table-wrap goods-received-note-matrix__scroll" tabindex="0" role="region" :aria-label="`Receipt quantities for ${section.name || 'item'}`">
								<table class="erp-data-table">
									<thead><tr>
										<th v-for="column in identityColumns(section.group)" :key="column.key">{{ column.label }}</th>
										<th v-if="hasActualDia && block.kind === 'items'">Actual Dia</th>
										<th v-if="hasActualDia && block.kind === 'items'">Balance</th>
										<th v-if="canEditLots && block.kind === 'items'">Lot</th>
									<template v-if="hasPrimaryAttribute(section.group)">
										<th v-for="value in primaryValues(section.group)" :key="value" class="erp-number goods-received-note-matrix__quantity-heading">{{ value }}</th>
									</template>
									<template v-else>
										<th class="erp-number goods-received-note-matrix__available-heading">Available</th>
										<th class="erp-number goods-received-note-matrix__quantity-heading">Receive</th>
										<th v-if="hasSecondaryQuantity(section.group)" class="erp-number">Secondary</th>
									</template>
										<th class="erp-number">Total qty</th><th class="erp-number">Value</th><th>UOM</th>
									</tr></thead>
									<tbody>
										<tr v-for="(row, rowIndex) in section.items" :key="rowKey(row, rowIndex)">
											<td v-for="column in identityColumns(section.group)" :key="column.key">{{ identityValue(row, column) }}</td>
											<td v-if="hasActualDia && block.kind === 'items'">
												<Select :model-value="row.attributes?.[actualDia.attribute]" :options="unusedDias(section.group, row, actualDia, true)" aria-label="Actual Dia" :invalid="Boolean(row.actual_dia_error)" @update:model-value="changeDia(row, $event)" />
												<div v-if="diaSiblings(section.group, row)[0] === row && unusedDias(section.group, row, actualDia).length">
													<Select v-model="row.actual_dia_selection" :options="unusedDias(section.group, row, actualDia)" placeholder="Choose Dia" aria-label="Dia to add" />
													<Button label="Add Dia" text size="small" :disabled="!row.actual_dia_selection" @click="addDia(section.group, row)" />
												</div>
												<Button v-if="canRemoveActualDia(row)" icon="pi pi-trash" aria-label="Remove Dia" text size="small" @click="removeLot(section.group, row)" />
												<small v-if="row.actual_dia_error" class="grn-dia-error" role="alert">{{ row.actual_dia_error }}</small>
											</td>
											<td v-if="hasActualDia && block.kind === 'items'" class="erp-number">{{ formatQty(receivableBalance(section.group, row)) }}</td>
											<td v-if="canEditLots && block.kind === 'items'">
												<Select v-if="canEditLotForEntry(row, workspace.lot_options, lotFieldname)" v-model="row.dimensions[lotFieldname]" :options="lotChoicesForEntry(row, workspace.lot_options, lotFieldname)" option-label="label" option-value="value" option-disabled="disabled" placeholder="Choose lot" aria-label="Receipt lot" @update:model-value="markDirty" />
												<span v-else>{{ row.dimensions?.[lotFieldname] }}</span>
												<Button v-if="unusedLots(section.group, row).length" label="Add lot" text size="small" @click="addLot(section.group, row)" />
												<Button v-if="canRemoveLot(section.group, row)" label="Remove" text size="small" @click="removeLot(section.group, row)" />
											</td>
										<template v-if="hasPrimaryAttribute(section.group)">
											<td v-for="value in primaryValues(section.group)" :key="value" class="erp-number goods-received-note-matrix__quantity goods-received-note-matrix__primary-cell">
												<InputNumber v-model="row.values[value].qty" :aria-label="matrixInputLabel('Receive', section, row, value)" :min="0" :max-fraction-digits="3" :disabled="!canEditMatrixBlock(block.kind)" fluid @update:model-value="markDirty" />
												<small>Available {{ formatQty(availableQuantity(row.values[value])) }}</small>
												<div v-if="secondaryUom(row, value)" class="goods-received-note-matrix__secondary-inline"><InputNumber v-model="row.values[value].secondary_qty" :aria-label="matrixInputLabel('Secondary quantity for', section, row, value, secondaryUom(row, value))" :min="0" :max-fraction-digits="3" :disabled="!canEditMatrixBlock(block.kind)" fluid @update:model-value="markDirty" /><span>{{ secondaryUom(row, value) }}</span></div>
											</td>
										</template>
										<template v-else>
											<td class="erp-number goods-received-note-matrix__available">{{ formatQty(availableQuantity(row.values.default)) }}</td>
											<td class="erp-number goods-received-note-matrix__quantity"><InputNumber v-model="row.values.default.qty" :aria-label="matrixInputLabel('Receive', section, row, 'default')" :min="0" :max-fraction-digits="3" :disabled="!canEditMatrixBlock(block.kind)" fluid @update:model-value="markDirty" /></td>
											<td v-if="hasSecondaryQuantity(section.group)" class="erp-number goods-received-note-matrix__secondary">
												<InputNumber v-model="row.values.default.secondary_qty" :aria-label="matrixInputLabel('Secondary quantity for', section, row, 'default', secondaryUom(row, 'default'))" :min="0" :max-fraction-digits="3" :disabled="!canEditMatrixBlock(block.kind)" fluid @update:model-value="markDirty" />
												<small>{{ secondaryUom(row, "default") }}</small>
											</td>
										</template>
											<td class="erp-number goods-received-note-matrix__total">{{ formatQty(rowTotal(row)) }}</td>
											<td class="erp-number goods-received-note-matrix__value">{{ formatMoney(rowValue(row)) }}</td>
											<td>{{ row.default_uom || row.uom || "—" }}</td>
										</tr>
									</tbody>
								</table>
							</div>
						</article>
					</div>
				</section>
					<div v-if="!matrixBlocks.length" class="goods-received-note-matrix__empty"><i class="pi pi-inbox" /><span>No Goods Received Note item rows are available.</span></div>
				</template>
			</template>

			<template #after-matrix>
				<div v-if="canEdit && afterMatrixFields.length" class="goods-received-note-after-matrix" aria-label="Goods Received Note final details">
					<template v-if="canEdit">
						<FormField v-for="field in afterMatrixFields" :key="`after-${fieldKey(field)}`" :class="{ 'goods-received-note-after-matrix__wide': field.fieldname === 'comments' }" :field="field" :model-value="form[field.fieldname]" :form="form" :required="Boolean(field.reqd || field.mandatory)" compact :search-handler="linkSearchHandler(field)" @update:model-value="setField(field.fieldname, $event)" />
					</template>
					<template v-else>
						<div v-for="field in afterMatrixFields" :key="`after-fact-${field.fieldname}`" class="goods-received-note-after-matrix__fact" :class="{ 'goods-received-note-after-matrix__wide': field.fieldname === 'comments' }"><span>{{ field.label }}</span><strong>{{ formatFieldValue(field) }}</strong></div>
					</template>
				</div>
			</template>

			<template #rail>
				<div class="goods-received-note-totals fabric-document-workspace__metric-group">
				<div
					v-for="total in visibleTotals"
					:key="total.fieldname"
					class="goods-received-note-total"
					:class="{ 'goods-received-note-total--primary': primaryTotals.has(total.fieldname) && totalIsPositive(total) }"
				>
					<span>{{ total.label }}</span><strong>{{ formatTotal(total) }}</strong>
				</div>
				</div>
				<div v-if="workspace.record?.is_internal_unit" class="goods-received-note-transfer-progress">
					<span>Internal transfer</span><strong>{{ transferPercent }}%</strong>
					<div><i :style="{ width: `${transferPercent}%` }" /></div>
					<small>{{ workspace.record.transfer_complete ? "Transfer complete" : "Completion pending" }}</small>
				</div>
			</template>

			<template #panel>
				<section v-if="workspace.special_source?.active" class="goods-received-note-special-context" aria-label="Source-managed Goods Received Note context">
					<header><span>Source-managed mode</span><strong>Prepared by the originating workflow</strong></header>
					<div><span v-for="mode in workspace.special_source.modes || []" :key="mode">{{ titleCase(mode) }}</span></div>
				</section>
				<section v-if="inspectionEntries.length && !inspectionOpen" class="goods-received-note-related">
					<header><span>Inspection Entries</span><strong>{{ inspectionEntries.length }}</strong></header>
					<div><span v-for="entry in inspectionEntries" :key="entry.name"><strong>{{ entry.name }}</strong><small>{{ entry.status || statusLabel(entry.docstatus) }}</small></span></div>
				</section>
			</template>
		</FabricDocumentWorkspace>

		<Dialog v-model:visible="calculationOpen" modal header="Calculate Goods Received Note" class="fabric-action-dialog fabric-action-dialog--wide erp-dialog--lg" :closable="!acting">
			<GrnCalculatePanel :context="calculationContext" :acting="acting" :error="panelError" @apply="calculate" @close="closeCalculation" />
		</Dialog>
		<Dialog v-model:visible="inspectionOpen" modal header="Create Inspection Entry" class="fabric-action-dialog fabric-action-dialog--wide erp-dialog--lg" :closable="!acting">
			<InspectionEntryPanel :context="workspace.inspection || {}" :acting="acting" :error="panelError" @save="saveInspection" @close="closeInspection" />
		</Dialog>
		<FabricStockOperationDialog v-model:visible="completionEntryOpen" operation="stock_entry" :name="completionEntryName" @changed="completionEntryChanged" />
		<DocumentConfirmationDialog v-model:visible="lifecycleConfirmVisible" :title="lifecycleConfirmTitle" :message="lifecycleConfirmMessage" :confirm-label="lifecycleConfirmLabel" :busy="Boolean(acting)" @confirm="confirmLifecycleAction" />
	</div>
</template>

<script setup>
import Button from "primevue/button"
import Dialog from "primevue/dialog"
import InputNumber from "primevue/inputnumber"
import Select from "primevue/select"
import Tab from "primevue/tab"
import TabList from "primevue/tablist"
import TabPanel from "primevue/tabpanel"
import TabPanels from "primevue/tabpanels"
import Tabs from "primevue/tabs"
import { useToast } from "primevue/usetoast"
import { computed, onMounted, reactive, ref, watch } from "vue"
import { useRouter } from "vue-router"

import {
	calculateGoodsReceivedNote,
	executeGoodsReceivedNoteCommand,
	getGoodsReceivedNoteCalculation,
	getGoodsReceivedNoteDeliveryAddress,
	getGoodsReceivedNoteSupplierAddress,
	getGoodsReceivedNoteWorkspace,
	saveGoodsReceivedNote,
	saveGoodsReceivedNoteInspection,
} from "../../api/fabricStore.js"
import { searchLink, searchLinkedDocument } from "../../api/frappe.js"
import FormField from "../../components/common/FormField.vue"
import DocumentActionStrip from "../../components/documents/DocumentActionStrip.vue"
import DocumentConfirmationDialog from "../../components/documents/DocumentConfirmationDialog.vue"
import DocumentFieldGroupGrid from "../../components/documents/DocumentFieldGroupGrid.vue"
import DocumentOverview from "../../components/documents/DocumentOverview.vue"
import DocumentStatusBadge from "../../components/documents/DocumentStatusBadge.vue"
import StockItemMatrix from "../../components/stock/StockItemMatrix.vue"
import { hasDocumentDisplayValue, plainTextFromHtml } from "../../utils/documentValues.js"
import FabricDocumentWorkspace from "./FabricDocumentWorkspace.vue"
import FabricStockOperationDialog from "./FabricStockOperationDialog.vue"
import { addActualDia, canRemoveActualDia, changeActualDia, diaSiblings, prepareActualDiaGroups, receivableBalance, setActualDiaRowError, unusedDias } from "./grnActualDia.js"
import { canEditLotForEntry, itemsNeedLotEditor, lotChoicesForEntry, unusedLotsForEntry } from "./grnLotOptions.js"
import GrnCalculatePanel from "./GrnCalculatePanel.vue"
import InspectionEntryPanel from "./InspectionEntryPanel.vue"

const props = defineProps({
	presentation: { type: String, default: "page" },
	name: { type: String, default: "" },
	sourceContext: { type: Object, default: () => ({}) },
	duplicateRouteName: { type: String, default: "fabric-goods-received-note-new" },
})
const emit = defineEmits(["changed", "closed"])
const router = useRouter()
const toast = useToast()

const loading = ref(true)
const acting = ref("")
const error = ref("")
const panelError = ref("")
const dirty = ref(false)
const editingSubmitted = ref(false)
const workspace = ref({})
const currentName = ref("")
const itemGroups = ref([])
const correctionGroups = ref([])
const calculationOpen = ref(false)
const calculationContext = ref({})
const inspectionOpen = ref(false)
const activeTab = ref("overview")
const completionEntryOpen = ref(false)
const completionEntryName = ref("")
const lifecycleConfirmVisible = ref(false)
const pendingLifecycleCommand = ref("")
const form = reactive({})
let loadSequence = 0
let actionSequence = 0
const addressDefaults = reactive({
	delivery_address: { sequence: 0, pending: false },
	supplier_address: { sequence: 0, pending: false },
})
const addressPending = computed(() => Object.values(addressDefaults).some((state) => state.pending))
const primaryTotals = new Set(["total_received_quantity", "total", "grand_total", "total_receivable_cost"])
const headerFieldnames = new Set(["against", "against_id", "delivery_challan", "process_name", "item", "supplier", "supplier_name"])
const sourceFieldnames = new Set(["against", "against_id", "delivery_challan"])
const fieldLabelOverrides = { against: "Source Type", against_id: "Source Document" }
const sourceOwnedFieldnames = new Set(["is_return", "is_rework", "additional_grn", "allow_non_bundle", "includes_packing", "cutting_laysheet", "cut_panel_movement", "from_closed_wo_sewing_details", "from_finishing", "is_manual_entry", "is_pack", "avoid_sewing_plan_qty"])
const presentationHiddenFieldnames = new Set(["against", "against_id", "delivery_challan", "production_detail"])
const afterMatrixFieldnames = new Set(["freight_charges", "comments", "is_internal_unit", "transfer_complete", "ste_transferred", "ste_transferred_percent"])

const capabilities = computed(() => workspace.value.capabilities || {})
const goodsReceivedNoteActions = computed(() => {
	const busy = Boolean(acting.value) || addressPending.value
	const actions = []
	const add = (key, fallback, icon, command, options = {}) => {
		if (!capabilities.value[key]) return
		actions.push({
			key, label: capabilityLabel(key, fallback), icon, command,
			disabled: busy || Boolean(options.disabled), disabledReason: options.disabledReason || "",
			loading: acting.value === (options.loadingKey || key), menuOnly: Boolean(options.menuOnly),
		})
	}
	if (editingSubmitted.value) {
		actions.push({ key: "cancel_edit", label: "Cancel Edit", icon: "pi pi-times", command: cancelSubmittedEdit, disabled: busy })
		if (dirty.value) actions.push({ key: "save", label: "Save", icon: "pi pi-save", command: () => save(false), disabled: busy, loading: acting.value === "save", primary: true })
		return actions
	}
	add("complete_transfer", "Complete Transfer", "pi pi-check-circle", completeTransfer)
	add("calculate", "Calculate", "pi pi-calculator", openCalculation, { disabled: dirty.value, disabledReason: dirty.value ? "Save the Goods Received Note before calculating." : "", loadingKey: "load_calculation" })
	add("create_inspection", "Create Inspection Entry", "pi pi-search", () => { inspectionOpen.value = true })
	if (canOfferSubmittedEdit.value) actions.push({ key: "edit", label: "Edit", icon: "pi pi-pencil", command: startSubmittedEdit, disabled: busy })
	if (!currentName.value || dirty.value) add("save", "Save", "pi pi-save", () => runWorkspaceAction("save"))
	if (currentName.value && !dirty.value) add("submit", "Submit", "pi pi-check", () => runWorkspaceAction("submit"))
	add("cancel", "Cancel Document", "pi pi-ban", () => runWorkspaceAction("cancel"), { menuOnly: true })
	add("amend", "Amend", "pi pi-copy", () => runWorkspaceAction("amend"), { menuOnly: true })
	if (currentName.value && workspace.value.permissions?.can_create && !workspace.value.special_source?.active) {
		actions.push({ key: "duplicate", label: "Duplicate", icon: "pi pi-clone", command: duplicateGoodsReceivedNote, disabled: busy, loading: acting.value === "duplicate", menuOnly: true })
	}
	const primaryKey = capabilities.value.complete_transfer ? "complete_transfer" : actions.some((action) => action.key === "calculate") ? "calculate" : actions.some((action) => action.key === "submit") ? "submit" : actions.some((action) => action.key === "save") ? "save" : actions.some((action) => action.key === "amend") ? "amend" : ""
	return actions.map((action) => ({ ...action, primary: action.key === primaryKey }))
})
const hasWorkspace = computed(() => Boolean(Object.keys(workspace.value || {}).length))
const duplicateLabel = computed(() => props.sourceContext?.duplicate_from ? `Duplicate of ${props.sourceContext.duplicate_from}` : "")
const visibleTotals = computed(() => (workspace.value.totals || []).filter((total) => primaryTotals.has(total.fieldname) || totalIsPositive(total)))
const canEditDraft = computed(() => Boolean(
	Number(workspace.value.record?.docstatus || 0) === 0
	&& (currentName.value ? workspace.value.permissions?.can_write : workspace.value.permissions?.can_create),
))
const allowOnSubmitFields = computed(() => new Set(workspace.value.allow_on_submit_fields || []))
const canOfferSubmittedEdit = computed(() => Boolean(
	Number(workspace.value.record?.docstatus || 0) === 1
	&& workspace.value.permissions?.can_update_after_submit
	&& allowOnSubmitFields.value.size
	&& !workspace.value.special_source?.read_only,
))
const canEdit = computed(() => canEditDraft.value || editingSubmitted.value)
const actualDia = computed(() => workspace.value.actual_dia || { enabled: false, dia_options: [] })
const hasActualDia = computed(() => canEditDraft.value && actualDia.value.enabled)
const lotFieldname = computed(() => workspace.value.lot_fieldname || "lot")
const canEditLots = computed(() => canEditDraft.value && form.against === "Purchase Order" && !form.is_return && itemsNeedLotEditor(itemGroups.value, workspace.value.lot_options, lotFieldname.value))
function canEditMatrixBlock(kind) {
	if (!canEdit.value || workspace.value.special_source?.read_only) return false
	if (!editingSubmitted.value) return true
	return allowOnSubmitFields.value.has(kind === "items" ? "items" : "correction_items")
}
const visibleFields = computed(() => {
	const result = new Map()
	for (const source of workspace.value.fields || []) {
		if (!source?.fieldname || source.hidden || sourceOwnedFieldnames.has(source.fieldname) || presentationHiddenFieldnames.has(source.fieldname)) continue
		if (source.depends_on && !evaluateCondition(source.depends_on, true)) continue
		if (headerFieldnames.has(source.fieldname) && (!sourceFieldnames.has(source.fieldname) || currentName.value)) continue
		if (result.has(source.fieldname)) continue
		const field = {
			...source,
			label: fieldLabelOverrides[source.fieldname] || source.label,
			reqd: Boolean(source.reqd || source.mandatory || evaluateCondition(source.mandatory_depends_on)),
			read_only: Boolean(source.read_only || evaluateCondition(source.read_only_depends_on)),
		}
		if (!canEdit.value && !hasDocumentDisplayValue(form[source.fieldname] ?? source.value)) continue
		result.set(source.fieldname, field)
	}
	return [...result.values()].sort((left, right) => fieldOrder(left.fieldname) - fieldOrder(right.fieldname))
})
const fieldGroups = computed(() => {
	const groups = new Map(grnFieldGroups.map((group) => [group.key, { ...group, fields: [] }]))
	for (const field of visibleFields.value) {
		if (afterMatrixFieldnames.has(field.fieldname)) continue
		;(groups.get(fieldGroupKey(field.fieldname)) || groups.get("additional")).fields.push(field)
	}
	return [...groups.values()].filter((group) => group.fields.length)
})
const primaryFieldGroups = computed(() => fieldGroups.value.filter((group) => ["posting", "movement"].includes(group.key)))
const secondaryFieldGroups = computed(() => fieldGroups.value.filter((group) => !["posting", "movement"].includes(group.key)))
const afterMatrixFields = computed(() => visibleFields.value.filter((field) => afterMatrixFieldnames.has(field.fieldname)))
const overviewDefinitions = [
	{ key: "identity", label: "Receipt identity", description: "Source and production references", icon: "pi pi-id-card", fields: ["naming_series", "against", "against_id", "delivery_challan", "production_detail", "is_return", "is_rework"] },
	{ key: "movement", label: "Movement", description: "Supplier and stock destination", icon: "pi pi-truck", fields: ["supplier", "supplier_name", "delivery_location", "delivery_location_name", "from_warehouse", "to_warehouse", "billing_address", "delivery_address"] },
	{ key: "schedule", label: "Supplier reference", description: "Posting and transport information", icon: "pi pi-calendar", fields: ["posting_date", "posting_time", "actual_date", "supplier_document_no", "supplier_document_date", "dc_no", "vehicle_no"] },
	{ key: "status", label: "Status & notes", description: "Receipt controls, charges and comments", icon: "pi pi-clipboard", fields: ["status", "freight_charges", "purchase_invoice_name", "includes_packing", "is_internal_unit", "transfer_complete", "letter_head", "comments"] },
]
const overviewAdditionalDefinition = { key: "additional", label: "Additional details", description: "Other receipt information", icon: "pi pi-ellipsis-h", wide: true }
const overviewFields = computed(() => {
	const sources = workspace.value.fields || []
	const fields = visibleFields.value.map((field) => ({ ...field, value: form[field.fieldname] ?? field.value }))
	const existing = new Set(fields.map((field) => field.fieldname))
	for (const fieldname of overviewDefinitions.flatMap((definition) => definition.fields)) {
		if (existing.has(fieldname)) continue
		const source = sources.find((field) => field.fieldname === fieldname)
		const value = form[fieldname] ?? source?.value ?? workspace.value.record?.[fieldname]
		if (!source || source.hidden || !hasDocumentDisplayValue(value)) continue
		fields.push({ ...source, value })
		existing.add(fieldname)
	}
	if (!existing.has("status")) fields.push({ fieldname: "status", label: "Status", fieldtype: "Data", value: workspace.value.record?.status || statusLabel(workspace.value.record?.docstatus) })
	return fields
})
const matrixBlocks = computed(() => {
	const blocks = []
	if (itemGroups.value.length) blocks.push({ key: "items", kind: "items", title: "Received quantities", groups: itemGroups.value })
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
	["Source", workspace.value.record?.against_id || form.against_id],
	["Process", workspace.value.record?.process_name || form.process_name],
	["Item", workspace.value.record?.item || form.item],
	["Supplier", workspace.value.record?.supplier_name || workspace.value.record?.supplier || form.supplier],
].filter(([, value]) => value).map(([label, value]) => ({ label, value })))
const transferPercent = computed(() => Math.max(0, Math.min(100, Number(workspace.value.record?.ste_transferred_percent || (workspace.value.record?.transfer_complete ? 100 : 0)))))
const inspectionEntries = computed(() => workspace.value.inspection?.entries || workspace.value.related?.inspection_entries || [])

async function load(refresh = false) {
	const sequence = ++loadSequence
	actionSequence += 1
	const requestedName = props.name || currentName.value
	const requestedRouteName = props.name
	const requestedSource = JSON.stringify(props.sourceContext || {})
	const requestedContext = clone(props.sourceContext || {})
	if (refresh) acting.value = "reload"
	else {
		loading.value = true
		clearWorkspaceState(requestedName)
	}
	error.value = ""
	try {
		const nextWorkspace = await getGoodsReceivedNoteWorkspace(requestedName, requestedContext) || {}
		if (loadIsStale(sequence, requestedName, requestedRouteName, requestedSource)) return
		applyWorkspace(nextWorkspace)
	} catch (reason) {
		if (loadIsStale(sequence, requestedName, requestedRouteName, requestedSource)) return
		clearWorkspaceState(requestedName)
		error.value = reason?.message || "Unable to load this Goods Received Note."
	} finally {
		if (!loadIsStale(sequence, requestedName, requestedRouteName, requestedSource)) {
			loading.value = false
			acting.value = ""
		}
	}
}

function loadIsStale(sequence, requestedName, requestedRouteName, requestedSource) {
	return sequence !== loadSequence
		|| requestedRouteName !== props.name
		|| (Boolean(requestedRouteName) && requestedName !== props.name)
		|| requestedSource !== JSON.stringify(props.sourceContext || {})
}

function actionIsStale(sequence, requestedRouteName) {
	return sequence !== actionSequence || requestedRouteName !== props.name
}

function clearWorkspaceState(name = "") {
	invalidateAddresses()
	workspace.value = {}
	currentName.value = name
	for (const key of Object.keys(form)) delete form[key]
	itemGroups.value = []
	correctionGroups.value = []
	dirty.value = false
	editingSubmitted.value = false
	calculationOpen.value = false
	calculationContext.value = {}
	inspectionOpen.value = false
	activeTab.value = "overview"
	panelError.value = ""
}

function applyWorkspace(nextWorkspace) {
	invalidateAddresses()
	workspace.value = nextWorkspace || {}
	currentName.value = workspace.value.record?.name || ""
	for (const key of Object.keys(form)) delete form[key]
	Object.assign(form, clone(workspace.value.values || {}))
	for (const field of workspace.value.fields || []) if (!(field.fieldname in form)) form[field.fieldname] = field.value
	if (!workspace.value.record?.name) {
		const defaults = currentPostingDefaults()
		if (!form.posting_date) form.posting_date = defaults.date
		if (!form.posting_time) form.posting_time = defaults.time
	}
	itemGroups.value = prepareActualDiaGroups(normalizeGroups(workspace.value.matrices?.items || workspace.value.item_groups || []), actualDia.value)
	correctionGroups.value = clone(workspace.value.matrices?.correction_items || workspace.value.correction_item_groups || [])
	for (const correction of correctionGroups.value) correction.item_details = normalizeGroups(correction.item_details || [])
	if (!workspace.value.capabilities?.calculate) calculationOpen.value = false
	if (!workspace.value.capabilities?.create_inspection) inspectionOpen.value = false
	activeTab.value = "overview"
	dirty.value = false
	editingSubmitted.value = false
	error.value = ""
	panelError.value = ""
}

async function setField(fieldname, value) {
	if (editingSubmitted.value && !allowOnSubmitFields.value.has(fieldname)) return
	form[fieldname] = value
	if (fieldname === "supplier") { form.contact_person = ""; form.billing_address = "" }
	if (fieldname in addressDefaults) invalidateAddress(fieldname)
	if (["posting_date", "posting_time"].includes(fieldname)) form.edit_posting_date_and_time = 1
	markDirty()
	if (fieldname === "delivery_location") await defaultAddress("delivery_address", value)
	if (fieldname === "supplier") await defaultAddress("supplier_address", value)
}

function invalidateAddress(fieldname) { addressDefaults[fieldname].sequence += 1; addressDefaults[fieldname].pending = false }
function invalidateAddresses() { for (const fieldname of Object.keys(addressDefaults)) invalidateAddress(fieldname) }
async function defaultAddress(fieldname, party) {
	invalidateAddress(fieldname)
	const state = addressDefaults[fieldname]
	const sequence = state.sequence
	const requestedLoad = loadSequence
	const isCurrent = () => sequence === state.sequence && requestedLoad === loadSequence
	form[fieldname] = ""
	if (!party) return
	state.pending = true
	try {
		const address = await (fieldname === "supplier_address"
			? getGoodsReceivedNoteSupplierAddress(party)
			: getGoodsReceivedNoteDeliveryAddress(party))
		if (isCurrent() && !form[fieldname]) form[fieldname] = address || ""
	} catch (reason) {
		if (isCurrent()) error.value = reason?.message || `Unable to default the ${fieldname === "supplier_address" ? "Supplier" : "Delivery"} Address.`
	} finally {
		if (isCurrent()) state.pending = false
	}
}

async function runWorkspaceAction(action) {
	if (action === "save") return save(false)
	if (action === "submit") return save(true)
	if (["cancel", "amend"].includes(action)) return requestLifecycleAction(action)
}

function startSubmittedEdit() {
	if (!canOfferSubmittedEdit.value) return
	editingSubmitted.value = true
	dirty.value = false
}

function cancelSubmittedEdit() {
	const snapshot = workspace.value
	applyWorkspace(snapshot)
}

function submittedUpdateValues() {
	const values = {}
	for (const fieldname of allowOnSubmitFields.value) {
		if (fieldname in form) values[fieldname] = clone(form[fieldname])
	}
	if (allowOnSubmitFields.value.has("items")) values.item_details = clone(itemGroups.value)
	if (allowOnSubmitFields.value.has("correction_items")) values.correction_item_details = clone(correctionGroups.value)
	return values
}

async function duplicateGoodsReceivedNote() {
	if (!currentName.value || !workspace.value.permissions?.can_create) return
	if (props.presentation === "page") {
		await router.push({ name: props.duplicateRouteName, query: { duplicate_from: currentName.value } })
		return
	}
	acting.value = "duplicate"
	error.value = ""
	const sequence = ++actionSequence
	const requestedRouteName = props.name
	const duplicateFrom = currentName.value
	try {
		const nextWorkspace = await getGoodsReceivedNoteWorkspace("", { duplicate_from: duplicateFrom }) || {}
		if (actionIsStale(sequence, requestedRouteName)) return
		applyWorkspace(nextWorkspace)
		dirty.value = true
		emit("changed", workspace.value)
	} catch (reason) {
		if (actionIsStale(sequence, requestedRouteName)) return
		error.value = reason?.message || "Unable to duplicate this Goods Received Note."
	} finally {
		if (!actionIsStale(sequence, requestedRouteName)) acting.value = ""
	}
}

async function save(submit) {
	const sequence = ++actionSequence
	const requestedRouteName = props.name
	const requestedName = currentName.value
	acting.value = submit ? "submit" : "save"
	error.value = ""
	try {
		const values = editingSubmitted.value
			? submittedUpdateValues()
			: {
				...clone(form),
				item_details: clone(itemGroups.value),
				correction_item_details: clone(correctionGroups.value),
			}
		const saved = await saveGoodsReceivedNote(values, {
			name: requestedName,
			submit,
			expectedModified: workspace.value.record?.modified,
		})
		if (actionIsStale(sequence, requestedRouteName)) return
		applyWorkspace(saved || {})
		toast.add({ severity: "success", summary: submit ? "Goods Received Note submitted" : "Goods Received Note saved", detail: workspace.value.record?.name || "Your changes are saved.", life: 3500 })
		emit("changed", workspace.value)
	} catch (reason) {
		if (actionIsStale(sequence, requestedRouteName)) return
		const message = reason?.message || `Unable to ${submit ? "submit" : "save"} this Goods Received Note.`
		if (!hasActualDia.value || !setActualDiaRowError(itemGroups.value, message)) error.value = message
	} finally { if (!actionIsStale(sequence, requestedRouteName)) acting.value = "" }
}

async function runCommand(command, payload = {}, destructive = false) {
	if (!currentName.value) return null
	const sequence = ++actionSequence
	const requestedRouteName = props.name
	const requestedName = currentName.value
	acting.value = command
	error.value = ""
	try {
		const result = await executeGoodsReceivedNoteCommand(requestedName, command, payload, workspace.value.record?.modified)
		if (actionIsStale(sequence, requestedRouteName)) return null
		const updated = result?.workspace || result
		if (updated?.record) { applyWorkspace(updated); emit("changed", workspace.value) }
		return result
	} catch (reason) {
		if (actionIsStale(sequence, requestedRouteName)) return null
		error.value = reason?.message || `Unable to ${command.replaceAll("_", " ")} this Goods Received Note.`
		return null
	} finally { if (!actionIsStale(sequence, requestedRouteName)) acting.value = "" }
}
const lifecycleConfirmTitle = computed(() => pendingLifecycleCommand.value === "cancel" ? "Cancel Goods Received Note?" : "Amend Goods Received Note?")
const lifecycleConfirmLabel = computed(() => pendingLifecycleCommand.value === "cancel" ? "Cancel GRN" : "Create Amendment")
const lifecycleConfirmMessage = computed(() => pendingLifecycleCommand.value === "cancel" ? `Cancel ${currentName.value}? This keeps the receipt for audit and reverses its submitted effect.` : `Create a new draft amendment from ${currentName.value}?`)
function requestLifecycleAction(command) { pendingLifecycleCommand.value = command; lifecycleConfirmVisible.value = true }
async function confirmLifecycleAction() { const command = pendingLifecycleCommand.value; lifecycleConfirmVisible.value = false; pendingLifecycleCommand.value = ""; if (command) await runCommand(command) }

async function openCalculation() {
	if (!currentName.value || !capabilities.value.calculate || dirty.value) return
	const sequence = ++actionSequence
	const requestedRouteName = props.name
	const requestedName = currentName.value
	acting.value = "load_calculation"
	panelError.value = ""
	try {
		const context = await getGoodsReceivedNoteCalculation(requestedName) || {}
		if (actionIsStale(sequence, requestedRouteName)) return
		calculationContext.value = context; calculationOpen.value = true; inspectionOpen.value = false
	} catch (reason) {
		if (!actionIsStale(sequence, requestedRouteName)) error.value = reason?.message || "Unable to load the Goods Received Note calculation."
	} finally { if (!actionIsStale(sequence, requestedRouteName)) acting.value = "" }
}
async function calculate(payload) {
	if (!capabilities.value.calculate || dirty.value) {
		panelError.value = dirty.value
			? "Save the Goods Received Note before calculating."
			: "Calculate is no longer available for this Goods Received Note."
		return
	}
	const sequence = ++actionSequence
	const requestedRouteName = props.name
	const requestedName = currentName.value
	const expectedModified = calculationContext.value.modified
	acting.value = "calculate"
	panelError.value = ""
	error.value = ""
	try {
		const result = await calculateGoodsReceivedNote(requestedName, payload.rows, payload.received_type, expectedModified)
		if (actionIsStale(sequence, requestedRouteName)) return
		applyWorkspace(result?.workspace || result || {})
		calculationOpen.value = false
		emit("changed", workspace.value)
	} catch (reason) { if (!actionIsStale(sequence, requestedRouteName)) error.value = reason?.message || "Unable to calculate this Goods Received Note." }
	finally { if (!actionIsStale(sequence, requestedRouteName)) acting.value = "" }
}
function closeCalculation() { calculationOpen.value = false; panelError.value = "" }
function closeInspection() { inspectionOpen.value = false; panelError.value = "" }
async function saveInspection({ values, submit }) {
	const sequence = ++actionSequence
	const requestedRouteName = props.name
	const requestedName = currentName.value
	const expectedModified = workspace.value.record?.modified
	acting.value = submit ? "inspection_submit" : "inspection_save"
	panelError.value = ""
	error.value = ""
	try {
		const result = await saveGoodsReceivedNoteInspection(requestedName, values, { submit, expectedModified })
		if (actionIsStale(sequence, requestedRouteName)) return
		applyWorkspace(result?.workspace || result || {})
		inspectionOpen.value = false
		emit("changed", workspace.value)
	} catch (reason) { if (!actionIsStale(sequence, requestedRouteName)) error.value = reason?.message || "Unable to save this Inspection Entry." }
	finally { if (!actionIsStale(sequence, requestedRouteName)) acting.value = "" }
}
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
function fieldKey(field) { return `${field.fieldname}-${field.idx || "value"}` }
const grnFieldGroups = [
	{ key: "source", eyebrow: "Source", label: "Receipt source", description: "Source document and production references." },
	{ key: "posting", eyebrow: "Receipt", label: "Posting details", description: "Series, posting date and receipt timing." },
	{ key: "movement", eyebrow: "Movement", label: "Stock movement", description: "Warehouses and delivery destination." },
	{ key: "supplier-document", eyebrow: "Reference", label: "Supplier document & transport", description: "Supplier reference and vehicle details." },
	{ key: "addresses", eyebrow: "Parties", label: "Addresses & contact", description: "Billing, supplier and delivery contacts." },
	{ key: "charges", eyebrow: "Commercial", label: "Charges & notes", description: "Receipt charges and operational notes." },
	{ key: "transfer", eyebrow: "Status", label: "Internal transfer", description: "Internal transfer completion state." },
	{ key: "additional", eyebrow: "Additional", label: "Additional details", description: "Other permitted Goods Received Note fields." },
]
const grnGroupFields = {
	source: ["against", "against_id", "delivery_challan", "production_detail"],
	posting: ["naming_series", "posting_date", "posting_time", "edit_posting_date_and_time", "actual_date"],
	movement: ["from_warehouse", "billing_address", "contact_person", "delivery_location", "to_warehouse", "delivery_address", "delivery_location_name"],
	"supplier-document": ["supplier_document_no", "supplier_document_date", "dc_no", "vehicle_no"],
	addresses: ["billing_address_display", "supplier_address", "supplier_address_display", "contact_display", "contact_mobile", "delivery_address_display"],
	charges: ["freight_charges", "comments", "purchase_invoice"],
	transfer: ["is_internal_unit", "transfer_complete", "ste_transferred", "ste_transferred_percent", "total_delivered_qty"],
}
const grnFieldOrder = Object.values(grnGroupFields).flat()
function fieldOrder(fieldname) { const index = grnFieldOrder.indexOf(fieldname); return index === -1 ? grnFieldOrder.length + 1 : index }
function fieldGroupKey(fieldname) { return Object.entries(grnGroupFields).find(([, fields]) => fields.includes(fieldname))?.[0] || "additional" }
function linkSearchHandler(field) {
	if (field.fieldname === "supplier_address" || field.fieldname === "billing_address") return (text) => searchLinkedDocument("Address", "Supplier", form.supplier, text)
	if (field.fieldname === "delivery_address") return (text) => searchLink("Address", text, { disabled: 0 })
	if (field.fieldname === "contact_person") return (text) => searchLinkedDocument("Contact", "Supplier", form.supplier, text)
	return null
}
function markDirty() { if (!loading.value) dirty.value = true }
function capabilityLabel(name, fallback) { return name === "save" ? fallback : capabilities.value[name]?.label || fallback }
function statusLabel(docstatus) { return Number(docstatus) === 1 ? "Submitted" : Number(docstatus) === 2 ? "Cancelled" : "Draft" }
function evaluateCondition(condition, fallback = false) {
	if (!condition) return fallback
	const expression = String(condition).replace(/^eval:/, "").trim()
	const direct = expression.match(/^(!)?doc\.([A-Za-z0-9_]+)$/)
	if (direct) { const value = Boolean(conditionValue(direct[2])); return direct[1] ? !value : value }
	const comparison = expression.match(/^doc\.([A-Za-z0-9_]+)\s*(===|==|!==|!=)\s*['"]?([^'"]+)['"]?$/)
	if (!comparison) return fallback
	const equal = String(conditionValue(comparison[1]) ?? "") === comparison[3]
	return comparison[2].includes("!") ? !equal : equal
}
function conditionValue(fieldname) { return Object.prototype.hasOwnProperty.call(form, fieldname) ? form[fieldname] : workspace.value.record?.[fieldname] }
function primaryValues(group) { return group.primary_attribute_values?.length ? group.primary_attribute_values : ["default"] }
function hasPrimaryAttribute(group) { return Boolean(group.primary_attribute && primaryValues(group).some((value) => value !== "default")) }
function availableQuantity(value) { return value?.max_receivable_quantity ?? value?.pending_qty ?? value?.pending_quantity ?? 0 }
function secondaryUom(row, value) { return String(row.values?.[value]?.secondary_uom || row.secondary_uom || "").trim() }
function hasSecondaryQuantity(group) { return (group.items || []).some((row) => primaryValues(group).some((value) => Boolean(secondaryUom(row, value)))) }
function logicalRowCount(groups) { return (groups || []).reduce((total, group) => total + (group.items?.length || 0), 0) }
function rowTotal(row) { return Object.values(row.values || {}).reduce((total, value) => total + Number(value?.qty || 0), 0) }
function rowValue(row) { return Object.values(row.values || {}).reduce((total, value) => total + Number(value?.amount ?? (Number(value?.qty || 0) * Number(value?.rate || row.rate || 0))), 0) }
function rowKey(row, index) { return [row.item_variant || row.name, row.row_index, row.received_type || row.dimensions?.received_type, row.delivery_challan_item, index].filter((value) => value !== undefined && value !== "").join("-") }
function matrixInputLabel(action, section, row, value, uom = "") {
	const item = section.name || row.item_variant || row.name || "item"
	const context = [...Object.values(row.attributes || {}), value === "default" ? "" : value].filter(Boolean)
	return `${action} ${item}${context.length ? `, ${context.join(", ")}` : ""}${uom ? ` in ${uom}` : ""}`
}
function formatQty(value) { return Number(value || 0).toLocaleString("en-IN", { maximumFractionDigits: 3 }) }
function formatMoney(value) { return Number(value || 0).toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 }) }
function formatTotal(total) { return Number(total.value || 0).toLocaleString("en-IN", { maximumFractionDigits: ["total", "grand_total", "total_tax", "freight_charges", "total_receivable_cost"].includes(total.fieldname) ? 2 : 3 }) }
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
	for (const group of normalized) for (const row of group.items || []) { row.values ||= {}; for (const value of primaryValues(group)) row.values[value] ||= { qty: 0 } }
	return normalized
}
function itemSections(groups) {
	return (groups || []).flatMap((group, groupIndex) => {
		const sections = new Map()
		for (const row of group.items || []) {
			const name = row.name || row.item || row.item_variant || ""
			const lot = row.dimensions?.[lotFieldname.value] || row.lot || ""
			const key = `${groupIndex}-${name || "item"}-${canEditLots.value ? '' : lot}`
			if (!sections.has(key)) sections.set(key, { group, name, lot, key, items: [] })
			sections.get(key).items.push(row)
		}
		return [...sections.values()]
	})
}
function changeDia(row, dia) { changeActualDia(row, actualDia.value.attribute, dia); markDirty() }
function addDia(group, row) {
	if (addActualDia(group, row, actualDia.value, row.actual_dia_selection)) { row.actual_dia_selection = null; markDirty() }
}
function lotSiblingKey(row) {
	return JSON.stringify([row.name, row.attributes, row.set_combination, row.dimensions?.received_type,
		Object.entries(row.values || {}).map(([key, value]) => [key, value.ref_docname])])
}
function lotSiblings(group, row) { return group.items.filter((entry) => lotSiblingKey(entry) === lotSiblingKey(row)) }
function unusedLots(group, row) {
	const used = new Set(lotSiblings(group, row).map((entry) => entry.dimensions?.[lotFieldname.value]))
	return unusedLotsForEntry(row, workspace.value.lot_options, used)
}
function addLot(group, row) {
	const entry = clone(row)
	entry.dimensions[lotFieldname.value] = unusedLots(group, row)[0]
	for (const value of Object.values(entry.values || {})) { value.qty = 0; value.secondary_qty = 0; value.freight_amount = 0 }
	group.items.push(entry)
	markDirty()
}
function canRemoveLot(group, row) {
	return lotSiblings(group, row).length > 1 && Object.values(row.values || {}).every((value) => !Number(value.qty) && !Number(value.secondary_qty))
}
function removeLot(group, row) { group.items.splice(group.items.indexOf(row), 1); markDirty() }
function identityColumns(group) {
	const columns = (group.attributes || []).map((key) => ({ key, label: titleCase(key), source: "attributes" }))
	const dimensions = []
	for (const row of group.items || []) for (const key of Object.keys(row.dimensions || {})) if (key !== "lot" && !dimensions.includes(key)) dimensions.push(key)
	for (const key of dimensions) columns.push({ key, label: titleCase(key), source: "dimensions" })
	return columns.filter((column, index, values) => values.findIndex((entry) => entry.key === column.key) === index)
}
function identityValue(row, column) {
	const value = column.source === "dimensions" ? row.dimensions?.[column.key] : (row.attributes?.[column.key] ?? row[column.key])
	return value === null || value === undefined || value === "" ? "—" : String(value)
}
function currentPostingDefaults() {
	const now = new Date()
	const pad = (value) => String(value).padStart(2, "0")
	return {
		date: `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}`,
		time: `${pad(now.getHours())}:${pad(now.getMinutes())}:${pad(now.getSeconds())}`,
	}
}

onMounted(() => load())
watch(() => [props.name, JSON.stringify(props.sourceContext || {})], ([name, source], previous) => {
	if (!previous || name === previous[0] && source === previous[1]) return
	loadSequence += 1
	actionSequence += 1
	clearWorkspaceState(name || "")
	load()
})
</script>

<style scoped>
.grn-dia-error { display: block; color: var(--p-red-600, #dc2626); max-width: 280px; white-space: normal; }
.goods-received-note-workspace { width: 100%; min-width: 0; }
.goods-received-note-tabs :deep(.p-tabpanels) { padding: 12px 0 0; background: transparent; }
.goods-received-note-tabs :deep(.p-tablist-tab-list) { padding-inline: 2px; }
.goods-received-note-tabs :deep(.p-tab span) { margin-left: 5px; padding: 2px 6px; color: var(--erp-text-muted); background: var(--erp-surface-muted); border-radius: var(--erp-pill-radius); font-size: var(--erp-font-size-min); }
.goods-received-note-tab-matrices { display: grid; gap: var(--erp-space-3); }
.goods-received-note-tab-matrix { display: grid; gap: 8px; min-width: 0; }
.goods-received-note-tab-matrix > header { display: flex; align-items: end; justify-content: space-between; gap: 12px; padding: 0 2px; }
.goods-received-note-tab-matrix > header div { display: grid; gap: 2px; }
.goods-received-note-tab-matrix > header span { color: var(--erp-text-muted); font-size: var(--erp-font-size-min); font-weight: 750; letter-spacing: .035em; text-transform: uppercase; }
.goods-received-note-tab-matrix > header h2 { margin: 0; color: var(--erp-text); font-size: var(--erp-font-size-section); }
.goods-received-note-tab-matrix > header > strong { color: var(--erp-accent); font-size: var(--erp-font-size-min); }
.goods-received-note-after-matrix { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); align-items: end; gap: 10px 14px; padding: 2px; }
.goods-received-note-after-matrix__wide { grid-column: span 2; }
.goods-received-note-after-matrix__fact { display: grid; min-width: 0; gap: 3px; padding: 8px 2px; border-bottom: 1px solid var(--erp-border); }
.goods-received-note-after-matrix__fact span { color: var(--erp-text-muted); font-size: var(--erp-font-size-min); font-weight: 750; letter-spacing: .035em; text-transform: uppercase; }
.goods-received-note-after-matrix__fact strong { color: var(--erp-text); font-size: var(--erp-font-size-caption); line-height: 1.4; white-space: pre-line; overflow-wrap: anywhere; }
@media (max-width: 1000px) { .goods-received-note-after-matrix { grid-template-columns: repeat(2, minmax(0, 1fr)); } }
@media (max-width: 560px) { .goods-received-note-after-matrix { grid-template-columns: 1fr; } .goods-received-note-after-matrix__wide { grid-column: auto; } }
.goods-received-note-workspace--page { padding-bottom: var(--erp-space-3); }
.goods-received-note-header__identity { display: flex; min-width: 0; align-items: center; gap: 12px; }
.goods-received-note-header__title { display: grid; min-width: 0; gap: 2px; }
.goods-received-note-header__identity h1 { margin: 0; color: var(--erp-text); font-size: 19px; line-height: 1.15; letter-spacing: -.018em; }
.goods-received-note-header__title > span { color: var(--erp-text-muted); font-size: var(--erp-font-size-caption); font-weight: 700; }
.goods-received-note-header__facts { display: flex; min-width: 0; flex: 1; align-items: center; gap: 16px; padding-left: 13px; border-left: 1px solid var(--erp-border); }
.goods-received-note-header__facts > div { display: grid; min-width: 0; gap: 2px; flex: 0 1 auto; }
.goods-received-note-header__facts span, .goods-received-note-total span, .goods-received-note-transfer-progress > span, .goods-received-note-matrix__header span, .goods-received-note-special-context header span, .goods-received-note-related header span { color: var(--erp-text-muted); font-size: var(--erp-font-size-min); font-weight: 750; letter-spacing: .035em; text-transform: uppercase; }
.goods-received-note-header__facts strong { overflow: hidden; max-width: 180px; color: var(--erp-text); font-size: var(--erp-font-size-caption); text-overflow: ellipsis; white-space: nowrap; }
.goods-received-note-header__identity--embedded { width: 100%; overflow: hidden; }
.goods-received-note-header__identity--embedded .goods-received-note-header__facts { overflow-x: auto; flex-wrap: nowrap; padding-left: 0; border-left: 0; scrollbar-width: thin; }
.goods-received-note-header__identity--embedded .goods-received-note-header__facts > div { flex: 0 0 auto; }
.goods-received-note-field-fact { display: grid; min-height: 50px; align-content: center; gap: 4px; padding: 7px 10px; border-bottom: 1px solid color-mix(in srgb, var(--erp-border) 76%, white); }
.goods-received-note-field-fact span { color: var(--erp-text-muted); font-size: var(--erp-font-size-min); font-weight: 750; letter-spacing: .035em; text-transform: uppercase; }
.goods-received-note-field-fact strong { overflow: hidden; color: var(--erp-text); font-size: var(--erp-font-size-caption); text-overflow: ellipsis; white-space: nowrap; }
.goods-received-note-matrix { overflow: hidden; min-width: 0; border: 1px solid var(--erp-border); border-radius: var(--erp-panel-radius); background: var(--erp-surface); box-shadow: none; }
.goods-received-note-matrix__header { display: flex; min-height: 48px; align-items: center; justify-content: space-between; gap: 12px; padding: 8px 12px; border-bottom: 1px solid var(--erp-border); background: var(--erp-surface-soft); }
.goods-received-note-matrix__header > div { display: grid; gap: 2px; }
.goods-received-note-matrix__header h2 { margin: 0; font-size: var(--erp-font-size-section); }
.goods-received-note-matrix__header > strong { padding: 3px 8px; color: var(--erp-accent); font-size: var(--erp-font-size-min); background: var(--erp-accent-soft); border-radius: var(--erp-pill-radius); }
.goods-received-note-matrix__stack { display: grid; gap: var(--erp-space-3); padding: var(--erp-space-3); background: color-mix(in srgb, var(--erp-surface-soft) 66%, white); }
.goods-received-note-matrix__group { overflow: hidden; min-width: 0; border: 1px solid var(--erp-border); border-radius: var(--erp-control-radius); background: var(--erp-surface); box-shadow: none; }
.goods-received-note-matrix__group > header { display: flex; min-height: 40px; align-items: center; padding: 7px 10px; border-bottom: 1px solid var(--erp-border); }
.goods-received-note-matrix__group > header div { display: grid; gap: 2px; }
.goods-received-note-matrix__group > header strong { color: var(--erp-text); font-size: var(--erp-font-size-caption); }
.goods-received-note-matrix__group > header span { color: var(--erp-text-muted); font-size: var(--erp-font-size-min); }
.goods-received-note-matrix__scroll table { min-width: 860px; }
.goods-received-note-matrix__available-heading, .goods-received-note-matrix__available { background: var(--erp-attention-soft); }
.goods-received-note-matrix__quantity-heading, .goods-received-note-matrix__quantity { background: var(--erp-accent-soft); }
.goods-received-note-matrix__available { min-width: 82px; color: var(--erp-attention-text); font-weight: 750; }
.goods-received-note-matrix__quantity, .goods-received-note-matrix__secondary { min-width: 106px; }
.goods-received-note-matrix :deep(.p-inputnumber) { min-width: 94px; }
.goods-received-note-matrix :deep(.p-inputnumber-input) { height: 32px; padding: 5px 8px; text-align: right; }
.goods-received-note-matrix__secondary small { display: block; margin-top: 3px; color: var(--erp-text-muted); font-size: var(--erp-font-size-min); }
.goods-received-note-matrix__primary-cell > small { display: block; margin-top: 3px; color: var(--erp-attention-text); font-size: var(--erp-font-size-min); text-align: right; }
.goods-received-note-matrix__secondary-inline { display: grid; grid-template-columns: minmax(72px, 1fr) auto; align-items: center; gap: 5px; margin-top: 5px; }
.goods-received-note-matrix__secondary-inline span { color: var(--erp-text-muted); font-size: var(--erp-font-size-min); }
.goods-received-note-matrix__total, .goods-received-note-matrix__value { color: var(--erp-accent-dark); font-weight: 800; }
.goods-received-note-matrix__empty { display: grid; min-height: 140px; place-items: center; align-content: center; gap: 6px; color: var(--erp-text-muted); border: 1px solid var(--erp-border); border-radius: var(--erp-control-radius); background: var(--erp-surface); }
.goods-received-note-total, .goods-received-note-transfer-progress { display: grid; min-height: 58px; align-content: center; gap: 2px; padding: 9px 12px; border: 0; border-bottom: 1px solid var(--erp-border); border-radius: 0; background: var(--erp-surface); }
.goods-received-note-totals { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 1px; background: var(--erp-border); }
.goods-received-note-totals .goods-received-note-total { min-height: 56px; border-bottom: 0; }
.goods-received-note-total:last-child, .goods-received-note-transfer-progress:last-child { border-bottom: 0; }
.goods-received-note-total strong, .goods-received-note-transfer-progress strong { color: var(--erp-text); font-size: 18px; font-weight: 780; font-variant-numeric: tabular-nums; }
.goods-received-note-total--primary { background: color-mix(in srgb, var(--erp-accent-soft) 76%, white); box-shadow: inset 3px 0 0 color-mix(in srgb, var(--erp-accent) 76%, white); }
.goods-received-note-total--primary strong { color: var(--erp-accent-hover); font-size: 21px; }
.goods-received-note-transfer-progress > div { overflow: hidden; height: 6px; background: var(--erp-border); border-radius: var(--erp-pill-radius); }
.goods-received-note-transfer-progress > div i { display: block; height: 100%; background: var(--erp-accent); transition: width .2s ease; }
.goods-received-note-transfer-progress small { color: var(--erp-text-muted); font-size: var(--erp-font-size-min); }
.goods-received-note-special-context, .goods-received-note-related { display: grid; overflow: hidden; border: 1px solid var(--erp-border); border-radius: var(--erp-control-radius); background: var(--erp-surface); }
.goods-received-note-special-context header, .goods-received-note-related header { display: flex; min-height: 42px; align-items: center; justify-content: space-between; gap: 12px; padding: 8px 12px; border-bottom: 1px solid var(--erp-border); background: var(--erp-surface-soft); }
.goods-received-note-special-context header strong { color: var(--erp-text-muted); font-size: var(--erp-font-size-caption); }
.goods-received-note-special-context > div, .goods-received-note-related > div { display: flex; gap: 7px; padding: var(--erp-space-3); flex-wrap: wrap; }
.goods-received-note-special-context > div span { padding: 5px 9px; color: var(--erp-accent); font-size: var(--erp-font-size-caption); font-weight: 750; border: 1px solid var(--erp-accent-border); border-radius: var(--erp-pill-radius); background: var(--erp-accent-soft); }
.goods-received-note-related > div span { display: grid; gap: 2px; padding: 6px 9px; border: 1px solid var(--erp-border); border-radius: var(--erp-control-radius); }
.goods-received-note-related small { color: var(--erp-text-muted); }
@media (max-width: 1100px) { .goods-received-note-header__facts { overflow-x: auto; padding-right: 18px; flex-wrap: nowrap; scrollbar-width: thin; -webkit-mask-image: linear-gradient(to right, #000 0, #000 calc(100% - 18px), transparent 100%); mask-image: linear-gradient(to right, #000 0, #000 calc(100% - 18px), transparent 100%); } .goods-received-note-header__facts:focus-visible { outline: 2px solid var(--erp-accent); outline-offset: 2px; } .goods-received-note-header__facts > div { flex: 0 0 auto; } }
@media (max-width: 760px) { .goods-received-note-header__identity { align-items: flex-start; flex-wrap: wrap; } .goods-received-note-header__facts { width: 100%; flex: 1 0 100%; gap: 8px 14px; padding: 8px 18px 0 0; border-top: 1px solid var(--erp-border); border-left: 0; } .goods-received-note-header__identity--embedded { align-items: center; flex-wrap: nowrap; } .goods-received-note-header__identity--embedded .goods-received-note-header__facts { width: auto; padding-top: 0; border-top: 0; flex: 1 1 auto; } }
@media (max-width: 620px) { .goods-received-note-field-fact { min-height: 46px; padding: 6px 8px; } .goods-received-note-matrix__stack { padding: var(--erp-space-2); } }
:global(.fabric-action-dialog .p-dialog-content) { min-height: 0; }
@media (max-width: 620px) { :global(.fabric-action-dialog) { width: 100vw !important; height: 100dvh !important; max-height: 100dvh !important; margin: 0; border-radius: 0; } :global(.fabric-action-dialog .p-dialog-content) { flex: 1; overflow-y: auto; } }
</style>
