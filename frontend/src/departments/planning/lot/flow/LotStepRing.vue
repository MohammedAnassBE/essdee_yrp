<template>
	<div class="pf-ring-tile">
		<div class="pf-ring-tile__head">
			<svg class="pf-ring" viewBox="0 0 72 72" role="img" :aria-label="rings.map((ring) => `${ring.kind} ${ring.share}%`).join(', ')">
				<template v-for="(ring, index) in rings" :key="ring.kind">
					<circle class="pf-ring__track" cx="36" cy="36" :r="radius(index)" />
					<circle v-if="ring.share > 0" class="pf-ring__arc" :class="`pf-ring__arc--${tone(ring.kind)}`" cx="36" cy="36" :r="radius(index)" :stroke-dasharray="dash(ring.share, index)" />
				</template>
			</svg>
			<div>
				<div class="pf-ring-tile__big">{{ formatNumber(received) }}%</div>
				<div class="pf-ring-tile__cap">received<template v-if="delivered !== null"> · {{ formatNumber(delivered) }}% delivered</template></div>
			</div>
		</div>
		<dl class="pf-ring-rows">
			<template v-for="meter in meters" :key="`${meter.kind}-${meter.label}`">
				<dt><i class="pf-ring-key" :class="`pf-fill--${tone(meter.kind)}`" />{{ meter.kind }}<small>{{ meter.label }}</small></dt>
				<dd :title="`${meter.kind}: ${formatNumber(meter.value)} of ${formatNumber(meter.total)} ${meter.uom}`">
					<strong>{{ formatNumber(meter.value) }}</strong> / {{ formatNumber(meter.total) }} {{ meter.uom }}<em>{{ percent(meter.value, meter.total) }}%</em><span v-if="percent(meter.value, meter.total) > 100" class="pf-meter__over">+{{ formatNumber(percent(meter.value, meter.total) - 100) }}%</span>
				</dd>
			</template>
		</dl>
	</div>
</template>
<script setup>
import { computed } from "vue"
import { formatNumber, meterRings, percent } from "../../../../utils/lotProcessFlow.js"
/** Step progress tile: concentric rings (delivered outside, received inside) plus the meter rows. */
const props = defineProps({
	meters: { type: Array, required: true },
	status: { type: String, required: true },
})
const rings = computed(() => meterRings(props.meters))
const shareOf = (kind) => rings.value.find((ring) => ring.kind === kind)?.share ?? null
const received = computed(() => shareOf("Received") ?? 0)
const delivered = computed(() => shareOf("Delivered"))
const radius = (index) => 30 - index * 9
const dash = (share, index) => {
	const circumference = 2 * Math.PI * radius(index)
	return `${(share / 100) * circumference} ${circumference}`
}
const tone = (kind) => ({ Delivered: "delivered", Dispatch: "dispatch" })[kind] || props.status
</script>
