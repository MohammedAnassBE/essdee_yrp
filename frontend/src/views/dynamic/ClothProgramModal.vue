<template>
  <Dialog
    :visible="visible"
    modal
    class="cloth-program-dialog"
    :style="{ width: 'min(920px, calc(100vw - 32px))' }"
    header="Build Cloth Programs"
    @update:visible="requestClose"
    @show="loadContext"
  >
    <div v-if="loading" class="cp-loading">Loading cloths…</div>
    <div v-else-if="!entries.length" class="cp-empty">
      This lot's garment has no cloth items to build.
    </div>
    <div v-else class="cp-list">
      <label class="cp-excess">
        <strong>Cloth Excess Percentage</strong>
        <InputNumber
          v-model="excessPercentage"
          :min="0"
          :minFractionDigits="0"
          :maxFractionDigits="3"
          suffix="%"
        />
      </label>
      <div
        v-for="e in entries"
        :key="e.cloth_item"
        class="cp-card"
        :class="{ 'cp-card--invalid': !!entryError(e) }"
      >
        <div class="cp-card-head">
          <div>
            <div class="cp-card-title">{{ e.label }}</div>
            <div class="cp-cloth-item">{{ e.cloth_item }}</div>
          </div>
        </div>

        <section class="cp-yarn-recipe">
          <strong>Item Yarn Recipe:</strong>
          <div class="cp-item-yarns">
            <span v-for="row in e.itemYarns" :key="row.yarn_item">
              {{ row.yarn_item }} {{ formatRatio(row.ratio) }}%
            </span>
            <span v-if="!e.itemYarns.length" class="invalid">
              Configure a Yarn Ratio totalling 100% on the Cloth Item.
            </span>
          </div>
        </section>

        <section v-if="e.requiredColours.length" class="cp-output-colours">
          <div class="cp-colour-row cp-colour-head">
            <span>Finished Colour</span>
            <span>Is Dyed Yarn</span>
            <span>Same Finished Colour</span>
          </div>
          <div
            v-for="colour in e.requiredColours"
            :key="colour"
            class="cp-colour-row"
          >
            <strong>{{ colour }}</strong>
            <label class="cp-dyed-yarn-toggle">
              <input
                type="checkbox"
                :checked="isDyedYarnColour(e, colour)"
                @change="setDyedYarnColour(e, colour, $event.target.checked)"
              />
              <span>{{ isDyedYarnColour(e, colour) ? "Yes" : "No" }}</span>
            </label>
            <label class="cp-dyed-yarn-toggle">
              <input
                type="checkbox"
                :checked="isSameFinishedColour(e, colour)"
                :disabled="isDyedYarnColour(e, colour)"
                @change="setSameFinishedColour(e, colour, $event.target.checked)"
              />
              <span>{{ isSameFinishedColour(e, colour) ? "Yes" : "No" }}</span>
            </label>
          </div>
          <small v-if="outputError(e)" class="cp-recipe-error">{{ outputError(e) }}</small>
        </section>

        <div class="cp-grid">
          <label>Cloth Kgs / 1 Kg Yarn
            <InputNumber
              v-model="e.cloth_per_kg_yarn"
              :min="0.001"
              :minFractionDigits="0"
              :maxFractionDigits="3"
            />
          </label>
          <label>Knitting Process
            <LinkField
              :modelValue="e.knitting_process || ''"
              @update:modelValue="(v) => (e.knitting_process = v || '')"
              target-doctype="Process"
              placeholder="Select knitting"
            />
          </label>
          <label>
            Dyeing Process {{ requiresDyeing(e) ? "(required)" : "(not required)" }}
            <LinkField
              :modelValue="e.dyeing_process || ''"
              @update:modelValue="(v) => (e.dyeing_process = v || '')"
              target-doctype="Process"
              placeholder="Select dyeing"
            />
          </label>
        </div>
      </div>
    </div>
    <template #footer>
      <Button label="Cancel" severity="secondary" text :disabled="applying" @click="requestClose(false)" />
      <Button v-if="entries.length" label="Build" icon="pi pi-th-large" :loading="applying" @click="onApply" />
    </template>
  </Dialog>
</template>

<script setup>
import { computed, ref } from "vue"
import Dialog from "primevue/dialog"
import InputNumber from "primevue/inputnumber"
import Button from "primevue/button"
import LinkField from "@/components/LinkField.vue"
import { callMethod } from "@/api/client"
import { useAppToast } from "@/composables/useToast"

const props = defineProps({
  visible: { type: Boolean, default: false },
  lot: { type: String, required: true },
  productionDetail: { type: String, default: null },
  modified: { type: String, default: null },
  syncedExcessPercentage: { type: [Number, String], default: 0 },
})
// "applying" fires right BEFORE the server write so the host can open its
// realtime local-write suppression window (markLocalWrite) in time — the
// doc_update echo can arrive mid-request, before "built" resolves, and would
// otherwise raise a false "modified by another user" notice.
const emit = defineEmits(["update:visible", "built", "applying"])
const toast = useAppToast()

const loading = ref(false)
const applying = ref(false)
const entries = ref([])
const excessPercentage = ref(0)
const initialSnapshot = ref("")

function requestClose(nextVisible) {
  if (!nextVisible && applying.value) return
  if (!nextVisible && isDirty.value) {
    const discard = window.confirm(
      "Discard the cloth-program changes entered in this window?",
    )
    if (!discard) return
  }
  emit("update:visible", nextVisible)
}

const isDirty = computed(
  () => Boolean(initialSnapshot.value) &&
    JSON.stringify(entries.value) !== initialSnapshot.value,
)

async function loadContext() {
  loading.value = true
  entries.value = []
  excessPercentage.value = Number(props.syncedExcessPercentage || 0)
  try {
    const r = await callMethod("essdee_yrp.api.cloth_program.get_cloth_program_context", { lot: props.lot })
    const defaults = (r && r.defaults) || {}
    entries.value = ((r && r.cloths) || []).map((c) => ({
      ...normaliseColourSelection(c, defaults),
      cloth_item: c.cloth_item,
      label: c.label,
      production_detail: c.production_detail || "",
      cloth_per_kg_yarn:
        c.profile?.cloth_per_kg_yarn ||
        defaults.cloth_per_kg_yarn ||
        1,
      knitting_process:
        c.profile?.knitting_process ||
        defaults.knitting_process ||
        "",
      dyeing_process:
        c.profile?.dyeing_process ||
        defaults.dyeing_process ||
        "",
      compacting_process:
        c.profile?.compacting_process ||
        defaults.compacting_process ||
        "",
    }))
    // A cloth's own CPD profile wins. For a new/legacy cloth without one,
    // derive process defaults from its first selected yarn.
    await Promise.all(entries.value.map((e) => (
      !e.knitting_process && firstProfileYarn(e)
        ? applyYarnProfile(e, firstProfileYarn(e))
        : null
    )))
    initialSnapshot.value = JSON.stringify(entries.value)
  } catch (e) {
    toast.error("Couldn't load cloths", e.message)
    emit("update:visible", false)
  } finally {
    loading.value = false
  }
}

function normaliseColourSelection(cloth, defaults = {}) {
  const itemYarns = (cloth.item_yarns || []).map((row) => ({
    yarn_item: row.yarn_item || "",
    ratio: Number(row.ratio) || 0,
  }))
  const requiredColours = (cloth.required_colours || []).filter(Boolean)
  const dyedYarnColours = (cloth.dyed_yarn_colours || [])
    .filter((colour) => requiredColours.includes(colour))
  const greyKnittingOutputColour =
    defaults.grey_knitting_output_colour ||
    defaults.knitting_output_colour ||
    "Greige"
  const storedRoutes = cloth.profile?.fabric_routes || []
  const sameFinishedColours = (cloth.same_finished_colours || [])
    .filter(
      (colour) =>
        requiredColours.includes(colour)
        && !dyedYarnColours.includes(colour),
    )
  const requiredRoutes = (cloth.required_routes || [])
    .map((route) => {
      const existing = storedRoutes.find(
        (row) =>
          row.finished_colour === route.colour &&
          row.finished_dia === route.dia,
      )
      return {
        dia: route.dia || "",
        colour: route.colour || "",
        knitting_output_dia: existing?.knitting_output_dia || route.dia || "",
      }
    })
    .sort((a, b) => diaSortValue(a.dia) - diaSortValue(b.dia))
  return {
    itemYarns,
    requiredColours,
    requiredRoutes,
    dyedYarnColours,
    sameFinishedColours,
    greyKnittingOutputColour,
  }
}

function diaSortValue(value) {
  const number = Number.parseFloat(String(value || "").match(/-?\d+(?:\.\d+)?/)?.[0])
  return Number.isFinite(number) ? number : Number.MAX_SAFE_INTEGER
}

function firstProfileYarn(entry) {
  return entry.itemYarns?.[0]?.yarn_item || ""
}

function rowsTotal(rows) {
  return (rows || []).reduce((sum, row) => sum + (Number(row.ratio) || 0), 0)
}

function formatRatio(value) {
  return Number(value || 0).toLocaleString(undefined, { maximumFractionDigits: 3 })
}

function isDyedYarnColour(entry, colour) {
  return entry.dyedYarnColours.includes(colour)
}

function setDyedYarnColour(entry, colour, checked) {
  const selected = new Set(entry.dyedYarnColours)
  if (checked) selected.add(colour)
  else selected.delete(colour)
  entry.dyedYarnColours = entry.requiredColours.filter((value) => selected.has(value))
  if (checked) setSameFinishedColour(entry, colour, false)
}

function isSameFinishedColour(entry, colour) {
  return entry.sameFinishedColours.includes(colour)
}

function setSameFinishedColour(entry, colour, checked) {
  const selected = new Set(entry.sameFinishedColours)
  if (checked) selected.add(colour)
  else selected.delete(colour)
  entry.sameFinishedColours = entry.requiredColours.filter(
    (value) => selected.has(value),
  )
}

function knittingOutputColour(entry, colour) {
  return (
    isDyedYarnColour(entry, colour)
    || isSameFinishedColour(entry, colour)
  )
    ? colour
    : entry.greyKnittingOutputColour
}

function validateYarnRows(rows) {
  if (!rows?.length) return "Add at least one yarn."
  const names = new Set()
  for (const [index, row] of rows.entries()) {
    if (!row.yarn_item) return `Yarn row ${index + 1}: select a Yarn Item.`
    if (!(Number(row.ratio) > 0)) return `Yarn row ${index + 1}: enter a ratio greater than zero.`
    if (names.has(row.yarn_item)) return `Yarn row ${index + 1}: this Yarn Item is duplicated.`
    names.add(row.yarn_item)
  }
  const total = rowsTotal(rows)
  if (Math.abs(total - 100) > 0.001) return `Ratio total is ${formatRatio(total)}%. Adjust it to exactly 100%.`
  return ""
}

function recipeError(e) {
  return validateYarnRows(e.itemYarns)
}

function outputError(entry) {
  const missing = entry.requiredRoutes.filter(
    (route) => !route.knitting_output_dia)
  return missing.length
    ? `Configure the Knitting Output Dia in Item Production Detail for ${missing[0].colour} / ${missing[0].dia}.`
    : ""
}

function entryError(entry) {
  return (
    recipeError(entry) ||
    outputError(entry) ||
    (!entry.knitting_process ? "Select a Knitting Process." : "") ||
    (requiresDyeing(entry) && !entry.dyeing_process
      ? "Select a Dyeing Process for the colour-changing routes."
      : "") ||
    (requiresCompacting(entry) && !entry.compacting_process
      ? "Set the Default Dia-change Process in IPD Settings."
      : "") ||
    (!(entry.cloth_per_kg_yarn > 0)
      ? "Enter a positive knitted-cloth yield."
      : "")
  )
}

function requiresDyeing(entry) {
  return entry.requiredColours.some(
    (colour) => knittingOutputColour(entry, colour) !== colour,
  )
}

function requiresCompacting(entry) {
  return entry.requiredRoutes.some(
    (route) =>
      route.knitting_output_dia &&
      route.knitting_output_dia !== route.dia,
  )
}

function flattenFabricRoutes(entry) {
  return entry.requiredRoutes.map((route) => ({
    finished_colour: route.colour,
    finished_dia: route.dia,
    knitting_output_colour: knittingOutputColour(entry, route.colour),
    knitting_output_dia: route.knitting_output_dia || "",
    use_dyed_yarn: isDyedYarnColour(entry, route.colour) ? 1 : 0,
  }))
}

async function applyYarnProfile(e, yarnItem) {
  if (!yarnItem) return
  try {
    const p = (await callMethod("essdee_yrp.api.cloth_program.get_yarn_profile", { yarn_item: yarnItem })) || {}
    if (p.knitting_process) e.knitting_process = p.knitting_process
    if (p.dyeing_process) e.dyeing_process = p.dyeing_process
    if (p.compacting_process) e.compacting_process = p.compacting_process
    if (p.cloth_per_kg_yarn) e.cloth_per_kg_yarn = p.cloth_per_kg_yarn
    const routes = p.fabric_routes || []
    for (const route of e.requiredRoutes) {
      const existing = routes.find(
        (row) =>
          row.finished_colour === route.colour &&
          row.finished_dia === route.dia,
      )
      if (!route.knitting_output_dia) {
        route.knitting_output_dia = existing?.knitting_output_dia || route.dia
      }
    }
  } catch (err) {
    // Non-fatal: the build validator reports any required profile value.
  }
}

async function onApply() {
  // Owner decision: builds always cover ALL demanded cloths — a partial list
  // would silently leave some cloths without a Lot Fabric Detail / requirement,
  // so every entry must be complete before we call the server (parity with Desk).
  const incomplete = entries.value.find((entry) => entryError(entry))
  if (incomplete) {
    toast.error(
      `Complete ${incomplete.label || incomplete.cloth_item}`,
      entryError(incomplete),
    )
    document.querySelector(".cp-card--invalid")?.scrollIntoView({
      behavior: "smooth",
      block: "start",
    })
    return
  }
  const rows = entries.value.map((e) => ({
    cloth_item: e.cloth_item,
    production_detail: e.production_detail || null,
    dyed_yarn_colours: [...e.dyedYarnColours],
    same_finished_colours: [...e.sameFinishedColours],
    fabric_routes: flattenFabricRoutes(e),
    yarns: e.itemYarns.map((row) => ({ ...row })),
    yarn_item: e.itemYarns[0]?.yarn_item || null,
    cloth_per_kg_yarn: e.cloth_per_kg_yarn,
    knitting_process: e.knitting_process,
    dyeing_process: e.dyeing_process || null,
    compacting_process: e.compacting_process || null,
  }))
  applying.value = true
  emit("applying") // before the write — see defineEmits note
  try {
    const res = await callMethod("essdee_yrp.api.cloth_program.build_cloth_programs", {
      lot: props.lot,
      selections: JSON.stringify(rows),
      modified: props.modified,
      excess_percentage: excessPercentage.value || 0,
    })
    initialSnapshot.value = JSON.stringify(entries.value)
    emit("update:visible", false)
    emit("built", res || {})
  } catch (e) {
    toast.error("Build failed", e.message)
  } finally {
    applying.value = false
  }
}
</script>

<style scoped>
.cp-list { display: flex; flex-direction: column; gap: 16px; container-type: inline-size; }
.cp-excess { display: flex; align-items: center; justify-content: space-between; gap: 18px; padding: 14px 16px; border: 1px solid var(--p-content-border-color, #e5e7eb); border-radius: 12px; background: var(--p-content-hover-background, #f8fafc); }
.cp-card { display: flex; flex-direction: column; padding: 16px; border: 1px solid var(--p-content-border-color, #e5e7eb); border-radius: 12px; }
.cp-card--invalid { border-color: color-mix(in srgb, var(--p-red-500, #ef4444) 42%, var(--p-content-border-color)); }
.cp-card-head { order: 0; }
.cp-card-title { font-size: 1rem; font-weight: 700; }
.cp-cloth-item { margin-top: 2px; font-size: 0.78rem; opacity: 0.68; }
.cp-yarn-recipe { display: flex; align-items: center; flex-wrap: wrap; gap: 8px; margin: 14px 0 0; padding: 10px 12px; border-radius: 10px; background: var(--p-content-hover-background, #f8fafc); }
.cp-item-yarns { display: flex; flex-wrap: wrap; gap: 6px; }
.cp-item-yarns span { padding: 4px 7px; border: 1px solid var(--p-content-border-color, #e5e7eb); border-radius: 7px; background: var(--p-content-background, #fff); font-size: 0.75rem; }
.cp-item-yarns span.invalid,
.cp-recipe-error { color: var(--p-red-600, #dc2626); }
.cp-output-colours { order: 1; overflow: hidden; margin: 14px 0; border: 1px solid var(--p-content-border-color, #e5e7eb); border-radius: 10px; background: var(--p-content-background, #fff); }
.cp-colour-row { display: grid; grid-template-columns: minmax(160px, 2fr) minmax(120px, 1fr) minmax(160px, 2fr); gap: 12px; align-items: center; min-height: 42px; padding: 8px 12px; }
.cp-colour-row + .cp-colour-row { border-top: 1px solid var(--p-content-border-color, #e5e7eb); }
.cp-colour-head { min-height: auto; color: var(--esd-muted, inherit); background: var(--p-content-hover-background, #f8fafc); font-size: 0.72rem; font-weight: 700; }
.cp-dyed-yarn-toggle { display: flex; align-items: center; justify-self: start; gap: 8px; cursor: pointer; }
.cp-dyed-yarn-toggle input { width: 18px; height: 18px; accent-color: var(--esd-accent, var(--p-primary-color)); }
.cp-recipe-error { display: block; padding: 0 12px 8px; font-size: 0.75rem; }
.cp-grid { order: 3; display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 10px; }
.cp-grid > * { min-width: 0; }
.cp-grid label { display: flex; flex-direction: column; gap: 4px; font-size: 0.85rem; }
.cp-grid :deep(.p-autocomplete),
.cp-grid :deep(.p-inputnumber),
.cp-grid :deep(.p-inputnumber-input),
.cp-grid :deep(.p-autocomplete-input) { width: 100%; min-width: 0; }
.cp-loading,
.cp-empty { padding: 24px; text-align: center; opacity: 0.7; }
@media (max-width: 620px) {
  .cp-grid { grid-template-columns: minmax(0, 1fr); }
  .cp-colour-row { grid-template-columns: minmax(0, 1.2fr) minmax(90px, 0.8fr) minmax(0, 1fr); }
}
@media (max-width: 430px) {
  .cp-card { padding: 10px; }
  .cp-colour-row { gap: 8px; padding: 8px; }
}
@container (max-width: 620px) {
  .cp-grid { grid-template-columns: minmax(0, 1fr); }
  .cp-colour-row { grid-template-columns: minmax(0, 1.2fr) minmax(90px, 0.8fr) minmax(0, 1fr); }
}
</style>
