<!-- home-greeting block — greeting bar + primary-create split CTA.

     Extracted 1:1 from views/home/HomePage.vue (build step 4). Today's DOM
     folds quick-create into the hero: primary CTA = first creatable
     quick-create doctype, the rest sit in the overflow menu. The list comes
     from store.quickCreate (spec §8.3) — the Default layout seeds today's
     literal ["Lot","Work Order","Delivery Challan"].

     Knobs (spec §6.4 — defaults reproduce today's behavior exactly):
       greetingName : String — name shown after "Good morning/…". Default:
                      first word of the session user's full name (today).
       sub          : String — the sub-line under the greeting.
       newCta       : { primary: "<DocType>", menu: ["<DocType>", …] } —
                      explicit CTA arrangement. Default: store.quickCreate
                      order (first creatable = primary, rest = menu).
     Every entry stays gated by canCreate() at render — arrangement never
     grants capability (spec §15). -->
<template>
	<header class="home-head">
		<div class="home-head__text">
			<h1 class="home-title">{{ greeting }}</h1>
			<p class="home-sub">{{ sub }}</p>
		</div>

		<div
			v-if="primaryCreate"
			class="home-cta"
			:class="{ split: moreCreates.length }"
			@keydown.esc="moreOpen = false"
		>
			<button class="cta-primary" @click="goCreate(primaryCreate)">
				<i class="pi pi-plus" />
				<span>New {{ primaryCreate.label }}</span>
			</button>
			<button
				v-if="moreCreates.length"
				class="cta-more"
				aria-label="More create options"
				:aria-expanded="moreOpen"
				@click="moreOpen = !moreOpen"
			>
				<i class="pi pi-chevron-down" />
			</button>
			<div v-if="moreOpen" class="cta-backdrop" @click="moreOpen = false" />
			<div v-if="moreOpen" class="cta-menu">
				<button
					v-for="qc in moreCreates"
					:key="qc.doctype"
					class="cta-menu__item"
					@click="goCreate(qc)"
				>
					<i :class="qc.icon" />
					<span>New {{ qc.label }}</span>
				</button>
			</div>
		</div>
	</header>
</template>

<script setup>
import { computed, ref, watch } from "vue"
import { useRouter, useRoute } from "vue-router"
import { useUiConfigStore } from "@yrp/web-engine"
import { useAuth } from "@/composables/useAuth"
import { usePermissions } from "@/composables/usePermissions"
import { getRegistryByDoctype } from "@/config/doctypes"

defineOptions({ inheritAttrs: false })

const props = defineProps({
	// null → today's behavior (session user's first name / no name).
	greetingName: { type: String, default: null },
	sub: { type: String, default: "Here's your floor today." },
	// null → today's behavior (store.quickCreate order decides primary + menu).
	newCta: { type: Object, default: null },
})

const router = useRouter()
const route = useRoute()
const { fullName } = useAuth()
const { canCreate } = usePermissions()
const ui = useUiConfigStore()

const greeting = computed(() => {
	const h = new Date().getHours()
	const part = h < 12 ? "Good morning" : h < 17 ? "Good afternoon" : "Good evening"
	const name = props.greetingName ?? (fullName.value || "").split(" ")[0]
	return name ? `${part}, ${name}` : `${part}`
})

// ── Primary create CTA + overflow (folds in the old Quick Create list) ──
// Ordered doctype list: explicit newCta knob when given, else the layout's
// quickCreate list from the store. Same canCreate + catalog-route gate either
// way, so a knob can never surface a doctype the user cannot create.
const ctaDoctypes = computed(() => {
	if (props.newCta && typeof props.newCta === "object") {
		const list = [props.newCta.primary, ...(props.newCta.menu || [])]
		return list.filter((dt) => typeof dt === "string" && dt)
	}
	return ui.quickCreate
})

const quickCreates = computed(() =>
	ctaDoctypes.value
		.filter((dt) => canCreate(dt))
		.map((dt) => {
			const reg = getRegistryByDoctype(dt)
			return { doctype: dt, label: dt, icon: reg?.icon || "pi pi-plus", route: reg?.route || "" }
		})
		.filter((qc) => qc.route)
)
const primaryCreate = computed(() => quickCreates.value[0] || null)
const moreCreates = computed(() => quickCreates.value.slice(1))
const moreOpen = ref(false)
// Close the overflow menu on any route change (cheap insurance).
watch(() => route.fullPath, () => { moreOpen.value = false })

function goCreate(qc) {
	moreOpen.value = false
	router.push(`/${qc.route}/new`)
}
</script>

<style scoped>
/* Styles lifted verbatim from HomePage.vue. The old `margin-bottom: 18px` is
   gone: vertical rhythm between home blocks now comes from the ScreenRenderer
   grid gap (HomePage shell pins it to the same 18px). */
.home-head {
	display: flex;
	align-items: flex-start;
	justify-content: space-between;
	gap: 16px;
	flex-wrap: wrap;
}

.home-title {
	font-size: 20px;
	font-weight: 800;
	margin: 0;
	letter-spacing: -0.02em;
}

.home-sub {
	margin: 4px 0 0;
	font-size: 13px;
	color: var(--esd-muted);
}

.home-cta {
	position: relative;
	display: flex;
	flex-shrink: 0;
}

.cta-primary {
	display: inline-flex;
	align-items: center;
	gap: 7px;
	background: var(--esd-accent);
	color: #fff;
	border: 0;
	border-radius: var(--radius-sm);
	padding: 9px 15px;
	font-size: 13px;
	font-weight: 600;
	cursor: pointer;
	font-family: inherit;
	transition: filter 0.14s;
}
.cta-primary:hover {
	filter: brightness(1.07);
}
.home-cta.split .cta-primary {
	border-radius: var(--radius-sm) 0 0 var(--radius-sm);
}

.cta-more {
	background: var(--esd-accent);
	color: #fff;
	border: 0;
	border-left: 1px solid rgba(255, 255, 255, 0.25);
	border-radius: 0 var(--radius-sm) var(--radius-sm) 0;
	padding: 0 11px;
	cursor: pointer;
	font-size: 12px;
}
.cta-more:hover {
	filter: brightness(1.07);
}

.cta-backdrop {
	position: fixed;
	inset: 0;
	z-index: 40;
}
.cta-menu {
	position: absolute;
	top: calc(100% + 6px);
	right: 0;
	z-index: 41;
	min-width: 210px;
	background: var(--esd-card);
	border: 1px solid var(--esd-line);
	border-radius: var(--radius);
	box-shadow: var(--esd-shadow-pop);
	padding: 6px;
}
.cta-menu__item {
	display: flex;
	align-items: center;
	gap: 9px;
	width: 100%;
	background: transparent;
	border: 0;
	border-radius: var(--radius-sm);
	padding: 8px 10px;
	font-size: 13px;
	font-weight: 500;
	color: var(--esd-ink-2);
	cursor: pointer;
	font-family: inherit;
	text-align: left;
}
.cta-menu__item:hover {
	background: var(--esd-slate-50);
}
.cta-menu__item i {
	color: var(--esd-accent);
	font-size: 13px;
}

@media (max-width: 768px) {
	.home-cta {
		width: 100%;
	}
	.cta-primary {
		flex: 1;
		justify-content: center;
	}
}
</style>
