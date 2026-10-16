<template>
	<div class="lot-tab-stack">
		<section
			v-for="(group, groupIndex) in orderDetails.groups"
			:key="groupIndex"
			class="lot-section"
		>
			<header>
				<div>
					<span>Order details</span>
					<h2>{{ group.attributes.join(" · ") }}</h2>
				</div>
				<span class="lot-count">{{ countLabel(group.items.length, "row") }}</span>
			</header>
			<div
				v-if="group.items.length"
				class="erp-table-wrap lot-table-wrap"
				role="region"
				tabindex="0"
				:aria-label="`Lot order detail group ${groupIndex + 1}`"
			>
				<table class="erp-data-table lot-table">
					<thead>
						<tr>
							<th>S.No</th>
							<th v-for="attribute in group.attributes" :key="attribute">
								{{ attribute }}
							</th>
							<th>Details</th>
							<th v-for="size in group.sizes" :key="size" class="erp-number">
								{{ size }}
							</th>
							<th class="erp-number">Total</th>
						</tr>
					</thead>
					<tbody
						v-for="row in orderDetailRows(group, orderDetails.stages)"
						:key="row.index"
					>
						<tr v-for="(line, lineIndex) in row.lines" :key="line.key">
							<td v-if="!lineIndex" :rowspan="row.lines.length">{{ row.index }}</td>
							<template v-if="!lineIndex">
								<td
									v-for="attribute in group.attributes"
									:key="attribute"
									:rowspan="row.lines.length"
								>
									{{ row.attributes[attribute] || "—" }}
									<small
										v-if="
											attribute === orderDetails.colour_attribute &&
											row.colour_note
										"
									>
										{{ row.colour_note }}
									</small>
								</td>
							</template>
							<td class="lot-stage-label">
								<span>{{ line.label }}</span>
							</td>
							<td v-for="size in group.sizes" :key="size" class="erp-number">
								{{ formatQuantity(line.values[size]) }}
							</td>
							<td class="erp-number lot-total">{{ quantityTotal(line.total) }}</td>
						</tr>
					</tbody>
					<tfoot>
						<tr v-for="stage in orderDetails.stages" :key="stage.key">
							<th :colspan="group.attributes.length + 1">Total</th>
							<th>{{ stage.label }}</th>
							<td v-for="size in group.sizes" :key="size" class="erp-number">
								{{ quantityTotal(group.size_totals[stage.key][size]) }}
							</td>
							<td class="erp-number lot-total">
								{{ quantityTotal(group.totals[stage.key]) }}
							</td>
						</tr>
					</tfoot>
				</table>
			</div>
			<LotEmptyState
				v-else
				title="No order details"
				reason="No stage quantities are recorded for this group."
			/>
		</section>
		<LotEmptyState
			v-if="!orderDetails.groups?.length"
			title="No order details"
			reason="No stage quantities are recorded for this Lot."
		/>
	</div>
</template>

<script setup>
import LotEmptyState from "./LotEmptyState.vue"
import { countLabel, formatQuantity, orderDetailRows, quantityTotal } from "./lotViews.js"

defineProps({ orderDetails: { type: Object, required: true } })
</script>
