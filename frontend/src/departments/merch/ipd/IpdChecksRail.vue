<template>
	<div class="ipd-rail" aria-label="IPD checks and usage">
		<section v-if="approval" class="ipd-rail__card" aria-labelledby="ipd-rail-approval">
			<header><h2 id="ipd-rail-approval">Approval</h2><DocumentStatusBadge :label="approval.status || 'Not Approved'" /></header>
			<div class="ipd-rail__body">
				<p v-if="approval.approvedBy">Approved by <strong>{{ approval.approvedBy }}</strong></p>
				<p v-else>Not approved yet.</p>
			</div>
		</section>

		<section v-if="showChecks" id="ipd-checks" class="ipd-rail__card" :aria-busy="running" aria-labelledby="ipd-rail-checks" tabindex="-1">
			<header>
				<h2 id="ipd-rail-checks">Checks</h2>
				<span class="ipd-rail__pill" :class="`ipd-rail__pill--${badge.tone}`">{{ badge.label }}</span>
			</header>
			<div v-for="problem in checks?.problems || []" :key="problem.key || `${problem.section}-${problem.field}-${problem.row_key}-${problem.column}`" class="ipd-rail__problem">
				<i class="pi pi-exclamation-circle" aria-hidden="true" />
				<strong>{{ problemTitle(problem, sections) }}</strong>
				<span>{{ problem.message }}</span>
				<button type="button" class="ipd-rail__link" @click="emit('go-to', problem)">{{ problem.row_key || problem.column ? "Go to cell" : "Go to field" }}</button>
			</div>
			<div v-for="warning in checks?.warnings || []" :key="warning.key" class="ipd-rail__problem ipd-rail__problem--warning">
				<i class="pi pi-exclamation-triangle" aria-hidden="true" />
				<strong>{{ problemTitle(warning, sections) }}</strong>
				<span>{{ warning.message }}</span>
				<button type="button" class="ipd-rail__link" @click="emit('go-to', warning)">{{ warning.row_key || warning.column ? "Go to cell" : "Go to field" }}</button>
			</div>
			<button v-if="passed.length" type="button" class="ipd-rail__passed" :aria-expanded="passedOpen" @click="passedOpen = !passedOpen">
				<i class="pi pi-check-circle" aria-hidden="true" />
				<span>{{ passed.length }} {{ passed.length === 1 ? "check" : "checks" }} passed</span>
				<i :class="passedOpen ? 'pi pi-chevron-up' : 'pi pi-chevron-down'" aria-hidden="true" />
			</button>
			<ul v-if="passedOpen" class="ipd-rail__passed-list">
				<li v-for="entry in passed" :key="`${entry.section}-${entry.rule}`">{{ entry.label }}</li>
			</ul>
			<p v-if="!checks && !running" class="ipd-rail__empty">Run checks to see every problem before saving.</p>
		</section>

		<section class="ipd-rail__card" aria-labelledby="ipd-rail-used-by">
			<header><h2 id="ipd-rail-used-by">Used by</h2><span class="ipd-rail__pill">{{ lotCount }} {{ lotCount === 1 ? "lot" : "lots" }}</span></header>
			<div v-for="entry in visibleUsage" :key="entry.ipd" class="ipd-rail__usage" :class="{ 'is-current': entry.is_current }">
				<strong>Version {{ entry.version }} · {{ entry.lots?.length ? `${entry.lots.length} ${entry.lots.length === 1 ? "lot" : "lots"}` : "no lots yet" }}<span v-if="entry.is_current" class="ipd-rail__this">This version</span></strong>
				<span v-if="entry.lots?.length" class="ipd-rail__lots">
					<RouterLink v-for="lot in entry.lots" :key="lot" :to="lotPath(lot)">{{ lot }}</RouterLink>
				</span>
				<span v-else-if="entry.is_current" class="ipd-rail__muted">Safe to change. Lots pick a version in the lot editor.</span>
			</div>
			<p v-if="hiddenVersions" class="ipd-rail__empty">{{ hiddenVersions }} other {{ hiddenVersions === 1 ? "version has" : "versions have" }} no lots.</p>
			<p v-if="!usedBy.length" class="ipd-rail__empty">No lots use this item yet.</p>
		</section>

		<section v-if="showKeys" class="ipd-rail__card ipd-rail__keys" aria-labelledby="ipd-rail-keys">
			<header><h2 id="ipd-rail-keys">Keys</h2></header>
			<p class="ipd-rail__body">Tab / Enter move · Ctrl+V pastes a block · Ctrl+D fills down · Ctrl+R fills right · ← / → / Home / End focus tabs · Enter / Space opens tab</p>
		</section>
	</div>
</template>

<script setup>
import { computed, ref } from "vue"
import { RouterLink } from "vue-router"

import DocumentStatusBadge from "../../../components/documents/DocumentStatusBadge.vue"
import { checksBadge, problemTitle } from "./ipdEditor.js"

const props = defineProps({
	checks: { type: Object, default: null },
	running: { type: Boolean, default: false },
	sections: { type: Array, default: () => [] },
	usedBy: { type: Array, default: () => [] },
	approval: { type: Object, default: null },
	showChecks: { type: Boolean, default: true },
	showKeys: { type: Boolean, default: false },
})
const emit = defineEmits(["go-to"])
const passedOpen = ref(false)
const badge = computed(() => checksBadge(props.checks, props.running))
const passed = computed(() => props.checks?.passed || [])
const visibleUsage = computed(() => props.usedBy.filter((entry) => entry.is_current || entry.lots?.length))
const hiddenVersions = computed(() => props.usedBy.length - visibleUsage.value.length)
const lotCount = computed(() => props.usedBy.reduce((total, entry) => total + (entry.lots?.length || 0), 0))

function lotPath(lot) { return `/merch/lots/${encodeURIComponent(lot)}` }
</script>
