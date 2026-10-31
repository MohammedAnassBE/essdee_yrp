<template>
	<LotMainTab :sections="sections" :expanded="expanded" :scroll-to="scrollTo" @update:expanded="emit('update:expanded', $event)">
		<template #header>
			<DocumentOverview v-if="headerGroups.length" :fields="fields" :definitions="LOT_HEADER_GROUPS" id-prefix="lot-header" aria-label="Lot details" :include-empty="includeEmpty" />
		</template>
		<template #quantities>
			<slot name="quantities-actions" />
			<LotOrderItemsTab v-if="workspace.order_items" :order-items="workspace.order_items" />
			<LotEmptyState v-else title="No order quantities" reason="Choose an Item Production Detail to load box quantities." />
		</template>
		<template #order-details>
			<div class="lot-tab-stack">
				<slot name="order-details-actions" />
				<LotFacts :facts="workspaceFacts(fields, LOT_ORDER_DETAIL_FIELDS, includeEmpty)" aria-label="Order detail facts" />
				<LotOrderDetailsTab :order-details="workspace.order_details" />
			</div>
		</template>
		<template #fabric-details>
			<div class="erp-table-wrap lot-table-wrap" role="region" tabindex="0" aria-label="Fabric details">
				<table class="erp-data-table lot-table">
					<thead><tr><th>S.No</th><th>Cloth Item</th><th>Item Production Detail</th><th>Plan Status</th></tr></thead>
					<tbody>
						<tr v-for="(fabric, index) in workspace.fabrics" :key="fabric.cloth_item || index">
							<td>{{ index + 1 }}</td>
							<td><DocumentLink doctype="Item" :name="fabric.cloth_item" /></td>
							<td><DocumentLink doctype="YRP Item Production Detail" :name="fabric.production_detail" /></td>
							<td>{{ fabric.plan_status || "—" }}</td>
						</tr>
					</tbody>
				</table>
			</div>
		</template>
		<template #ipd><LotFacts :facts="workspaceFacts(fields, LOT_IPD_FIELDS, includeEmpty)" aria-label="Facts from Item Production Detail" /></template>
		<template #ppo><slot name="ppo" /></template>
		<template #transfer><LotFacts :facts="workspaceFacts(fields, LOT_TRANSFER_FIELDS, true)" aria-label="Transfer facts" /></template>
		<template #ocr><LotOcrTable :payload="workspace.ocr" linked /></template>
	</LotMainTab>
</template>
<script setup>
import { computed } from "vue"
import DocumentLink from "../../../components/common/DocumentLink.vue"
import DocumentOverview from "../../../components/documents/DocumentOverview.vue"
import { buildDocumentOverviewGroups } from "../../../utils/documentOverview.js"
import LotOcrTable from "../../sales/LotOcrTable.vue"
import LotEmptyState from "./LotEmptyState.vue"
import LotFacts from "./LotFacts.vue"
import LotMainTab from "./LotMainTab.vue"
import LotOrderDetailsTab from "./LotOrderDetailsTab.vue"
import LotOrderItemsTab from "./LotOrderItemsTab.vue"
import {
	LOT_HEADER_GROUPS, LOT_IPD_FIELDS, LOT_ORDER_DETAIL_FIELDS, LOT_TRANSFER_FIELDS,
	hasLotOcr, hasLotTransfer, lotSections, orderDetailRowCount, workspaceFacts, workspaceValues,
} from "./lotLayout.js"
/** Read-only Lot tab for the Purchase, Planning and Merch Lot pages. */
const props = defineProps({
	workspace: { type: Object, required: true },
	expanded: { type: Array, default: () => [] },
	scrollTo: { type: String, default: "" },
	includeEmpty: Boolean,
	hasPpo: Boolean,
})
const emit = defineEmits(["update:expanded"])
const fields = computed(() => [...(props.workspace.header || []), ...(props.workspace.details || []), ...(props.workspace.ipd_facts || [])])
const headerGroups = computed(() => buildDocumentOverviewGroups(fields.value, LOT_HEADER_GROUPS, { includeEmpty: props.includeEmpty }))
const sections = computed(() => {
	const workspace = props.workspace
	const orderGroups = workspace.order_details?.groups || []
	return lotSections({
		"order-details": Boolean(workspace.order_details),
		"fabric-details": Boolean(workspace.fabrics?.length),
		ipd: true,
		ppo: props.hasPpo,
		transfer: hasLotTransfer(workspaceValues(fields.value)),
		ocr: hasLotOcr(workspace.ocr),
	}, {
		"order-details": orderDetailRowCount(orderGroups),
		"fabric-details": workspace.fabrics?.length || 0,
	})
})
</script>
