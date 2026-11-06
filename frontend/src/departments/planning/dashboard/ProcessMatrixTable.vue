<template>
	<div class="pf-table-wrap pd-matrix">
		<table class="erp-data-table pf-table">
			<thead>
				<tr>
					<th>{{ firstLabel }}</th>
					<th>Type</th>
					<th v-for="column in matrix.columns" :key="column" class="erp-number">{{ column }}</th>
					<th class="erp-number">Total</th>
				</tr>
			</thead>
			<tbody>
				<template v-for="row in matrix.rows" :key="row.key">
					<tr v-for="(line, index) in row.lines" :key="line.key" :data-line="line.key">
						<td v-if="!index" :rowspan="row.lines.length" class="pf-colour"><strong>{{ row.key }}</strong></td>
						<td class="pf-type">{{ line.label }}</td>
						<td v-for="(cell, cellIndex) in line.cells" :key="matrix.columns[cellIndex]" class="erp-number" :class="toneClass(cell.tone)">{{ cell.text }}</td>
						<td class="erp-number pf-total-cell" :class="toneClass(line.total.tone)">{{ line.total.text }}</td>
					</tr>
				</template>
				<tr v-if="!matrix.rows.length"><td :colspan="matrix.columns.length + 3" class="pd-empty">No quantities for this process yet.</td></tr>
			</tbody>
		</table>
	</div>
</template>

<script setup>
/** Toned matrix built by `sizeWiseMatrix()` or `colourWiseMatrix()`. */
defineProps({
	matrix: { type: Object, required: true },
	firstLabel: { type: String, default: "Colour" },
})
const toneClass = (tone) => (tone ? `pf-tone-${tone}` : "")
</script>
