<template>
	<section class="ocr-summary">
		<div class="ocr-summary__header">
			<div>
				<div class="ocr-summary__title">{{ __("Order completion by process") }}</div>
				<div class="ocr-summary__hint">{{ __("Sent, received and balance quantities across submitted Work Orders.") }}</div>
			</div>
			<span v-if="processNames.length" class="ocr-summary__badge">{{ processNames.length }} {{ __("processes") }}</span>
		</div>

		<div v-if="loading" class="ocr-summary__state">{{ __("Loading order completion…") }}</div>
		<div v-else-if="error" class="ocr-summary__state ocr-summary__state--error">{{ error }}</div>
		<div v-else-if="!processNames.length" class="ocr-summary__state">
			<div class="ocr-summary__empty-title">{{ __("No submitted Work Orders yet") }}</div>
			<div>{{ __("Process-wise progress will appear here once this Lot has submitted Work Orders.") }}</div>
		</div>
		<div v-else class="ocr-summary__table-wrap">
			<table class="ocr-summary__table">
				<thead>
					<tr>
						<th>{{ __("Process") }}</th>
						<th>{{ __("Type") }}</th>
						<th v-for="size in sizes" :key="size" class="ocr-summary__number">{{ size }}</th>
						<th class="ocr-summary__number">{{ __("Total") }}</th>
					</tr>
				</thead>
				<tbody>
					<template v-for="process in processNames" :key="process">
						<tr>
							<td rowspan="3" class="ocr-summary__process">
								<div class="ocr-summary__process-name">{{ process }}</div>
								<a
									v-for="workOrder in limitedWorkOrders(process)"
									:key="workOrder"
									href="#"
									@click.prevent="openDocument('Work Order', workOrder)"
								>
									{{ workOrder }}
								</a>
								<button v-if="workOrders(process).length > 3" type="button" class="btn btn-link btn-xs" @click="openWorkOrderList(process)">
									+{{ workOrders(process).length - 3 }} {{ __("more") }}
								</button>
							</td>
							<td>{{ __("Sent") }}</td>
							<td v-for="size in sizes" :key="size" class="ocr-summary__number">{{ quantity(process, size, "sent") }}</td>
							<td class="ocr-summary__number ocr-summary__total">{{ processData(process).total_sent || 0 }}</td>
						</tr>
						<tr>
							<td>{{ __("Received") }}</td>
							<td v-for="size in sizes" :key="size" class="ocr-summary__number">{{ quantity(process, size, "received") }}</td>
							<td class="ocr-summary__number ocr-summary__total">{{ processData(process).total_received || 0 }}</td>
						</tr>
						<tr class="ocr-summary__variance-row">
							<td>{{ __("Variance") }}</td>
							<td v-for="size in sizes" :key="size" class="ocr-summary__number">
								<span :class="varianceClass(variance(process, size))">{{ signed(variance(process, size)) }}</span>
							</td>
							<td class="ocr-summary__number ocr-summary__total">
								<span :class="varianceClass(totalVariance(process))">{{ signed(totalVariance(process)) }}</span>
							</td>
						</tr>
					</template>
				</tbody>
			</table>
		</div>
	</section>
</template>

<script setup>
import { computed, onMounted, ref } from "vue";

const items = ref({});
const loading = ref(true);
const error = ref("");
const sizes = computed(() => items.value?.sizes || []);
const processNames = computed(() => Object.keys(items.value?.processes || {}));

onMounted(() => {
	frappe.call({
		method: "essdee_yrp.essdee_yrp.doctype.lot.lot.get_ocr_details",
		args: { lot: cur_frm.doc.name },
		callback(response) {
			items.value = response.message || {};
		},
		error() {
			error.value = __("Unable to load order completion details.");
		},
		always() {
			loading.value = false;
		},
	});
});

function processData(process) {
	return items.value?.processes?.[process] || {};
}
function workOrders(process) {
	return processData(process).wo_list || [];
}
function limitedWorkOrders(process) {
	return workOrders(process).slice(0, 3);
}
function quantity(process, size, type) {
	return Number(processData(process).data?.[size]?.[type] || 0);
}
function variance(process, size) {
	return quantity(process, size, "received") - quantity(process, size, "sent");
}
function totalVariance(process) {
	return Number(processData(process).total_received || 0) - Number(processData(process).total_sent || 0);
}
function signed(value) {
	return value > 0 ? `+${value}` : String(value);
}
function varianceClass(value) {
	return { "ocr-summary__variance": true, "is-positive": value > 0, "is-negative": value < 0 };
}
function openDocument(doctype, name) {
	frappe.set_route("Form", doctype, name);
}
function openWorkOrderList(process) {
	frappe.route_options = { lot: cur_frm.doc.name, process_name: process, docstatus: 1 };
	frappe.set_route("List", "Work Order");
}
</script>

<style scoped>
.ocr-summary { border: 1px solid var(--border-color); border-radius: 8px; overflow: hidden; background: var(--card-bg, var(--fg-color)); }
.ocr-summary__header { display: flex; align-items: center; justify-content: space-between; padding: 14px 16px; background: var(--subtle-fg); border-bottom: 1px solid var(--border-color); }
.ocr-summary__title { font-weight: 600; }
.ocr-summary__hint, .ocr-summary__state { color: var(--text-muted); font-size: 12px; }
.ocr-summary__badge { padding: 3px 8px; border-radius: 999px; background: var(--control-bg); color: var(--text-muted); font-size: 11px; }
.ocr-summary__state { padding: 34px 20px; text-align: center; }
.ocr-summary__state--error { color: var(--red-600); }
.ocr-summary__empty-title { color: var(--text-color); font-size: 13px; font-weight: 600; margin-bottom: 4px; }
.ocr-summary__table-wrap { max-height: 560px; overflow: auto; }
.ocr-summary__table { width: 100%; min-width: 720px; border-collapse: separate; border-spacing: 0; font-size: 12px; }
.ocr-summary__table th, .ocr-summary__table td { padding: 8px 10px; border-right: 1px solid var(--border-color); border-bottom: 1px solid var(--border-color); }
.ocr-summary__table th { position: sticky; top: 0; z-index: 1; background: var(--subtle-fg); color: var(--text-muted); font-size: 11px; font-weight: 600; text-align: left; }
.ocr-summary__table th:last-child, .ocr-summary__table td:last-child { border-right: 0; }
.ocr-summary__process { min-width: 190px; vertical-align: top; background: var(--subtle-fg); }
.ocr-summary__process-name { font-weight: 600; margin-bottom: 5px; }
.ocr-summary__process a { display: block; margin: 2px 0; font-size: 11px; }
.ocr-summary__number { text-align: right !important; font-variant-numeric: tabular-nums; }
.ocr-summary__total { font-weight: 600; }
.ocr-summary__variance-row td { background: var(--subtle-fg); }
.ocr-summary__variance { display: inline-flex; min-width: 34px; justify-content: flex-end; padding: 2px 5px; border-radius: 4px; }
.ocr-summary__variance.is-positive { color: var(--green-700); background: var(--green-100); }
.ocr-summary__variance.is-negative { color: var(--red-700); background: var(--red-100); }
</style>
