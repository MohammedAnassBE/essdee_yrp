<template>
	<section v-if="rows.length" class="purchase-order-production-orders" aria-label="Production Orders">
		<header><span>Production Orders</span><strong>{{ rows.length }}</strong></header>
		<table class="erp-data-table">
			<thead><tr><th>Production Order</th><th>Item Name</th></tr></thead>
			<tbody>
				<tr v-for="row in rows" :key="row.production_order">
					<td><DocumentLink doctype="YRP Production Order" :name="row.production_order" :label="row.production_order" /></td>
					<td>{{ row.item_name || "—" }}</td>
				</tr>
			</tbody>
		</table>
	</section>
</template>

<script setup>
import DocumentLink from "../../components/common/DocumentLink.vue"

defineProps({ rows: { type: Array, default: () => [] } })
</script>

<style scoped>
.purchase-order-production-orders { display: grid; gap: 8px; min-width: 0; }
.purchase-order-production-orders header { display: flex; align-items: center; gap: 8px; color: var(--erp-text-muted); font-size: var(--erp-font-size-caption); font-weight: 600; }
.purchase-order-production-orders table { width: 100%; }
</style>
