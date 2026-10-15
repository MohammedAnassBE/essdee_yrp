<template>
	<section class="lot-section">
		<header>
			<div>
				<span>Order quantities</span>
				<h2>Box quantities ({{ orderItems.uom || "—" }})</h2>
			</div>
			<span class="lot-count">{{ countLabel(matrix.rows.length, "row") }}</span>
		</header>
		<div
			v-if="matrix.rows.length"
			class="erp-table-wrap lot-table-wrap"
			role="region"
			tabindex="0"
			aria-label="Lot order items"
		>
			<table class="erp-data-table lot-table">
				<thead>
					<tr>
						<th>S.No</th>
						<th v-for="attribute in orderItems.attributes" :key="attribute">
							{{ attribute }}
						</th>
						<th>Details</th>
						<th v-for="column in matrix.columns" :key="column" class="erp-number">
							{{ column }}
						</th>
						<th class="erp-number">Total</th>
					</tr>
				</thead>
				<tbody v-for="row in matrix.rows" :key="row.index">
					<tr v-for="(line, lineIndex) in row.lines" :key="line.key">
						<td v-if="!lineIndex" :rowspan="row.lines.length">{{ row.index }}</td>
						<template v-if="!lineIndex">
							<td
								v-for="attribute in orderItems.attributes"
								:key="attribute"
								:rowspan="row.lines.length"
							>
								{{ row.attributes?.[attribute] || "—" }}
							</td>
						</template>
						<td class="lot-stage-label">
							<span>{{ line.label }}</span>
						</td>
						<td v-for="column in matrix.columns" :key="column" class="erp-number">
							{{ formatQuantity(line.values[column]) }}
						</td>
						<td class="erp-number lot-total">
							{{ line.total === null ? "" : quantityTotal(line.total) }}
						</td>
					</tr>
				</tbody>
			</table>
		</div>
		<LotEmptyState
			v-else
			title="No order items"
			reason="No box quantities are recorded for this Lot."
		/>
	</section>
</template>

<script setup>
import { computed } from "vue"
import LotEmptyState from "./LotEmptyState.vue"
import { countLabel, formatQuantity, orderItemRows, quantityTotal } from "./lotViews.js"

const props = defineProps({ orderItems: { type: Object, required: true } })
const matrix = computed(() => orderItemRows(props.orderItems))
</script>
