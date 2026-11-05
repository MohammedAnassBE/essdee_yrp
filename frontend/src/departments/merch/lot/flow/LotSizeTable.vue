<template>
	<div class="pf-block">
		<h4 v-if="title">{{ title }}<span v-if="hint">{{ hint }}</span></h4>
		<div class="pf-table-wrap">
			<table class="erp-data-table lot-table pf-table">
				<thead>
					<tr>
						<th>S.No</th>
						<th>{{ firstLabel }}</th>
						<th>Type</th>
						<th v-for="size in sizes" :key="size" class="erp-number">{{ size }}</th>
						<th class="erp-number">Total</th>
					</tr>
				</thead>
				<tbody>
					<template v-for="(row, index) in table.rows" :key="`${row.colour}-${row.part}`">
						<tr v-for="(line, lineIndex) in row.lines" :key="line.key">
							<template v-if="!lineIndex">
								<td :rowspan="row.lines.length" class="pf-sno">{{ index + 1 }}</td>
								<td :rowspan="row.lines.length" class="pf-colour"><strong>{{ row.colour || "—" }}</strong><span>{{ row.part }}</span></td>
							</template>
							<td class="pf-type">{{ line.label }}</td>
							<td v-for="(cell, cellIndex) in line.cells" :key="sizes[cellIndex]" class="erp-number" :class="toneClass(cell)">{{ formatCell(line, cell) }}</td>
							<td class="erp-number pf-total-cell" :class="toneClass(line.total)">{{ formatCell(line, line.total) }}</td>
						</tr>
					</template>
					<tr v-for="(line, lineIndex) in table.footer || []" :key="`total-${line.key}`" class="pf-total">
						<td v-if="!lineIndex" colspan="2" :rowspan="table.footer.length">Total</td>
						<td class="pf-type">{{ line.label }}</td>
						<td v-for="(cell, cellIndex) in line.cells" :key="sizes[cellIndex]" class="erp-number" :class="toneClass(cell)">{{ formatCell(line, cell) }}</td>
						<td class="erp-number pf-total-cell" :class="toneClass(line.total)">{{ formatCell(line, line.total) }}</td>
					</tr>
				</tbody>
			</table>
		</div>
	</div>
</template>
<script setup>
import { formatNumber } from "../../../../utils/lotProcessFlow.js"
/** Toned colour × size table built by `sizeTable()`. */
defineProps({
	table: { type: Object, required: true },
	sizes: { type: Array, required: true },
	title: { type: String, default: "" },
	hint: { type: String, default: "" },
	firstLabel: { type: String, default: "Colour · Part" },
})
const toneClass = (cell) => (cell.tone ? `pf-tone-${cell.tone}` : "")
function formatCell(line, cell) {
	if (line.key !== "difference" || cell.value <= 0) return formatNumber(cell.value)
	return `+${formatNumber(cell.value)}`
}
</script>
