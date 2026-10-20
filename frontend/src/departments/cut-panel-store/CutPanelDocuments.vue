<template>
	<ListView :doctype="capability.doctype" :title="title" :search-placeholder="`Search ${title}…`" :name-column-label="label" :row-mark="isDelivery ? 'DC' : 'GRN'" :filters="filters" :default-columns="columns" viewport-bounded clickable @row-click="openDocument" />
</template>

<script setup>
import { computed } from "vue"
import { useRouter } from "vue-router"
import ListView from "../../components/common/ListView.vue"
import { openListDocument } from "../../router/listDocumentNavigation.js"

const props = defineProps({ capability: { type: Object, required: true } })
const router = useRouter()
const isDelivery = computed(() => props.capability.doctype === "YRP Delivery Challan")
const label = computed(() => isDelivery.value ? "Delivery Challan" : "Goods Received Note")
const title = computed(() => isDelivery.value ? "Delivery Challans" : "Goods Received Notes")
const columns = ["posting_date", "supplier", "cut_panel_movement", "docstatus"]
const filters = [["cut_panel_movement", "is", "set"]]
function openDocument(row, snapshot) {
	return openListDocument(router, row, snapshot, {
		routeName: isDelivery.value ? "cut-panel-delivery-challan" : "cut-panel-goods-received-note",
		paramName: isDelivery.value ? "deliveryChallanId" : "goodsReceivedNoteId",
	})
}
</script>
