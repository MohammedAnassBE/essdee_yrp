<template>
	<div class="lot-page__identity">
		<div class="lot-page__title-row">
			<div class="lot-page__title">
				<div class="lot-page__meta">
					<span>{{ name ? `Lot · ${name}` : "New Lot" }}</span>
					<span v-if="editing" class="lot-page__editing">· Editing</span>
					<span v-if="deliveryDate" class="lot-page__date"><span>Delivery</span><strong>{{ formatLotDate(deliveryDate) }}</strong></span>
				</div>
				<h1 :id="headingId" :aria-label="[name || draftName || 'New Lot', item].filter(Boolean).join(' · ')">
					<span class="lot-page__lot">{{ name || draftName || "New Lot" }}</span>
					<template v-if="item"><span class="lot-page__title-separator" aria-hidden="true">·</span><span>{{ item }}</span></template>
				</h1>
			</div>
			<DocumentStatusBadge :label="status || 'Open'" />
		</div>
	</div>
</template>
<script setup>
import DocumentStatusBadge from "../../../components/documents/DocumentStatusBadge.vue"
import { formatLotDate } from "./lotViews.js"
defineProps({
	name: { type: String, default: "" },
	draftName: { type: String, default: "" },
	item: { type: String, default: "" },
	deliveryDate: { type: String, default: "" },
	status: { type: String, default: "Open" },
	headingId: { type: String, required: true },
	editing: { type: Boolean, default: false },
})
</script>
