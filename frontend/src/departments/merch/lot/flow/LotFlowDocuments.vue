<template>
	<p v-if="!groups.length && !packing" class="pf-modal__none">No Delivery Challan or GRN yet.</p>
	<div v-else class="pf-docs">
		<section v-for="group in groups" :key="group.supplier || 'none'" class="pf-supplier">
			<h4><i class="pi pi-building" aria-hidden="true" /> {{ group.supplier_name || "—" }}</h4>
			<div class="pf-supplier__cols">
				<div v-for="column in columns(group)" :key="column.label">
					<h5>{{ column.label }} <em>{{ column.rows.length }}</em></h5>
					<ul v-if="column.rows.length">
						<li v-for="row in column.rows" :key="row.name">
							<a :href="documentHref(column.doctype, row.name)" target="_blank" rel="noopener">{{ row.name }}{{ row.is_return ? " (return)" : "" }}</a>
							<span>{{ formatDisplayDate(row.date) }}</span>
							<b>{{ formatNumber(row.qty) }}</b>
						</li>
					</ul>
					<p v-else class="pf-modal__none">None yet</p>
				</div>
			</div>
		</section>
		<section v-if="packing" class="pf-supplier">
			<h4><i class="pi pi-box" aria-hidden="true" /> Finishing</h4>
			<p class="pf-supplier__plan">
				Finishing Plan
				<template v-if="packing.finishing_plans.length">
					<a v-for="plan in packing.finishing_plans" :key="plan" :href="documentHref('SD YRP Finishing Plan', plan)" target="_blank" rel="noopener">{{ plan }} </a>
				</template>
				<span v-else>— none yet</span>
			</p>
			<h5>Dispatches <em>{{ packing.dispatches.length }}</em></h5>
			<ul v-if="packing.dispatches.length">
				<li v-for="row in packing.dispatches" :key="row.name">
					<a :href="documentHref('SD YRP Finishing Plan Dispatch', row.name)" target="_blank" rel="noopener">{{ row.name }}</a>
					<span>{{ formatDisplayDate(row.date) }}</span>
					<b>{{ formatNumber(row.qty) }}</b>
				</li>
			</ul>
			<p v-else class="pf-modal__none">None yet</p>
		</section>
	</div>
</template>
<script setup>
import { formatDisplayDate } from "../../../../utils/dateFormat.js"
import { documentHref, formatNumber } from "../../../../utils/lotProcessFlow.js"
/** Delivery Challans and GRNs per supplier; packing adds the Finishing Plan and its dispatches. */
defineProps({
	groups: { type: Array, default: () => [] },
	packing: { type: Object, default: null },
})
function columns(group) {
	return [
		{ label: "Delivery Challans", doctype: "YRP Delivery Challan", rows: group.dcs },
		{ label: "Goods Received Notes", doctype: "YRP Goods Received Note", rows: group.grns },
	]
}
</script>
