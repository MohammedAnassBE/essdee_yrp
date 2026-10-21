<template>
	<dl v-if="header" class="quality-header-facts">
		<div v-for="fact in facts" :key="fact.fieldname">
			<dt>{{ fact.label }}</dt>
			<dd><DocumentLink v-if="fact.doctype" :doctype="fact.doctype" :name="fact.value" :label="fact.display" current-path="/web/quality/inspections" /><template v-else>{{ fact.display }}</template></dd>
		</div>
	</dl>
	<div v-else class="quality-inspection-summary">
		<InspectionStatTiles :record="record" />
		<dl v-if="facts.length" class="quality-header-facts quality-inspection-facts">
			<div v-for="fact in facts" :key="fact.fieldname">
				<dt>{{ fact.label }}</dt>
				<dd><DocumentLink v-if="fact.doctype" :doctype="fact.doctype" :name="fact.value" :label="fact.display" current-path="/web/quality/inspections" /><template v-else>{{ fact.display }}</template></dd>
			</div>
		</dl>
		<div v-if="chips.length" class="quality-selections">
			<div v-for="group in chips" :key="group.key" class="quality-selection">
				<span class="quality-selection__label">{{ group.label }}</span>
				<span v-for="value in group.values" :key="value" class="quality-chip">{{ value }}</span>
			</div>
		</div>
		<section v-if="notes.length" class="quality-notes" aria-labelledby="inspection-notes">
			<h2 id="inspection-notes"><i class="pi pi-align-left" aria-hidden="true" /> Notes</h2>
			<dl><div v-for="note in notes" :key="note.fieldname"><dt>{{ note.label }}</dt><dd>{{ note.value }}</dd></div></dl>
		</section>
	</div>
</template>

<script setup>
import { computed } from "vue"
import DocumentLink from "../../../components/common/DocumentLink.vue"
import { documentOverviewHasValue } from "../../../utils/documentOverview.js"
import { INSPECTION_FIELDS } from "../inspectionFields.js"
import { inspectionHeaderFacts, inspectionSummaryFacts, inspectionSelectedChips } from "../qualityViews.js"
import InspectionStatTiles from "./InspectionStatTiles.vue"
const props = defineProps({
	record: { type: Object, default: () => ({}) }, selection: { type: Object, default: () => ({}) }, header: Boolean,
})
const facts = computed(() => props.header ? inspectionHeaderFacts(props.record) : inspectionSummaryFacts(props.record))
const chips = computed(() => inspectionSelectedChips(props.selection))
const notes = computed(() => ["measurement_deviation", "remarks_and_suggestions"]
	.filter((key) => documentOverviewHasValue(props.record[key])).map((key) => ({ ...INSPECTION_FIELDS[key], value: props.record[key] })))
</script>
