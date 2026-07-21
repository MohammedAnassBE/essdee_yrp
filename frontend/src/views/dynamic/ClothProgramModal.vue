<template>
  <Dialog
    :visible="visible"
    modal
    class="cloth-program-dialog"
    :style="{ width: 'min(920px, calc(100vw - 32px))' }"
    header="Build Cloth Programs"
    @update:visible="(v) => emit('update:visible', v)"
    @show="loadContext"
  >
    <div v-if="loading" class="cp-loading">Loading cloths…</div>
    <div v-else-if="!entries.length" class="cp-empty">
      This lot's garment has no cloth items to build.
    </div>
    <div v-else class="cp-list">
      <div v-for="(e, i) in entries" :key="e.cloth_item" class="cp-card">
        <div class="cp-card-title">{{ e.label }} — {{ e.cloth_item }}</div>
        <div class="cp-grid">
          <label>Yarn Item
            <LinkField
              :modelValue="e.yarn_item || ''"
              @update:modelValue="(v) => onYarnChange(e, v)"
              target-doctype="Item"
              placeholder="Select yarn"
            />
          </label>
          <label>Cloth Kgs / 1 Kg Yarn
            <InputNumber v-model="e.cloth_per_kg_yarn" :minFractionDigits="0" :maxFractionDigits="3" />
          </label>
          <label>Knitting Process
            <LinkField
              :modelValue="e.knitting_process || ''"
              @update:modelValue="(v) => (e.knitting_process = v || '')"
              target-doctype="Process"
              placeholder="Select knitting"
            />
          </label>
          <label>Dyeing Process
            <LinkField
              :modelValue="e.dyeing_process || ''"
              @update:modelValue="(v) => (e.dyeing_process = v || '')"
              target-doctype="Process"
              placeholder="Select dyeing"
            />
          </label>
          <label>Compacting Process
            <LinkField
              :modelValue="e.compacting_process || ''"
              @update:modelValue="(v) => (e.compacting_process = v || '')"
              target-doctype="Process"
              placeholder="Optional"
            />
            <small class="cp-hint">Recorded on the CPD; not auto-chained in v1.</small>
          </label>
          <label>Greige Colour
            <LinkField
              :modelValue="e.greige_colour || ''"
              @update:modelValue="(v) => (e.greige_colour = v || '')"
              target-doctype="Item Attribute Value"
              :filters="{ attribute_name: 'Colour' }"
              placeholder="Select greige"
            />
          </label>
        </div>
      </div>
    </div>
    <template #footer>
      <Button label="Cancel" severity="secondary" text :disabled="applying" @click="emit('update:visible', false)" />
      <Button v-if="entries.length" label="Build" icon="pi pi-th-large" :loading="applying" @click="onApply" />
    </template>
  </Dialog>
</template>

<script setup>
import { ref } from "vue"
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
})
const emit = defineEmits(["update:visible", "built"])
const toast = useAppToast()

const loading = ref(false)
const applying = ref(false)
const entries = ref([])

async function loadContext() {
  loading.value = true
  entries.value = []
  try {
    const r = await callMethod("essdee_yrp.api.cloth_program.get_cloth_program_context", { lot: props.lot })
    entries.value = ((r && r.cloths) || []).map((c) => ({
      cloth_item: c.cloth_item,
      label: c.label,
      yarn_item: c.default_yarn || "",
      cloth_per_kg_yarn: null,
      knitting_process: "",
      dyeing_process: "",
      compacting_process: "",
      greige_colour: "",
    }))
    // Spec prefill: derive each cloth's profile from its default (picked) yarn.
    await Promise.all(entries.value.map((e) => (e.yarn_item ? applyYarnProfile(e) : null)))
  } catch (e) {
    toast.error("Couldn't load cloths", e.message)
    emit("update:visible", false)
  } finally {
    loading.value = false
  }
}

async function onYarnChange(e, v) {
  e.yarn_item = v || ""
  await applyYarnProfile(e)
}

async function applyYarnProfile(e) {
  if (!e.yarn_item) return
  try {
    const p = (await callMethod("essdee_yrp.api.cloth_program.get_yarn_profile", { yarn_item: e.yarn_item })) || {}
    if (p.knitting_process) e.knitting_process = p.knitting_process
    if (p.dyeing_process) e.dyeing_process = p.dyeing_process
    if (p.compacting_process) e.compacting_process = p.compacting_process
    if (p.cloth_per_kg_yarn) e.cloth_per_kg_yarn = p.cloth_per_kg_yarn
    if (p.greige_colour) e.greige_colour = p.greige_colour
  } catch (err) {
    // non-fatal: leave the fields for manual entry
  }
}

async function onApply() {
  const rows = entries.value
    .filter((e) => e.yarn_item && e.knitting_process && e.cloth_per_kg_yarn > 0 && e.dyeing_process && e.greige_colour)
    .map((e) => ({
      cloth_item: e.cloth_item,
      yarn_item: e.yarn_item,
      cloth_per_kg_yarn: e.cloth_per_kg_yarn,
      knitting_process: e.knitting_process,
      dyeing_process: e.dyeing_process || null,
      compacting_process: e.compacting_process || null,
      greige_colour: e.greige_colour || null,
    }))
  if (!rows.length) {
    toast.warn("Nothing to build", "Fill yarn, knitting + dyeing process, cloth-per-kg and greige colour for at least one cloth.")
    return
  }
  applying.value = true
  try {
    const res = await callMethod("essdee_yrp.api.cloth_program.build_cloth_programs", {
      lot: props.lot,
      selections: JSON.stringify(rows),
      modified: props.modified,
    })
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
.cp-list { display: flex; flex-direction: column; gap: 16px; }
.cp-card { border: 1px solid var(--p-content-border-color, #e5e7eb); border-radius: 8px; padding: 12px; }
.cp-card-title { font-weight: 600; margin-bottom: 8px; }
.cp-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 10px; }
.cp-grid label { display: flex; flex-direction: column; gap: 4px; font-size: 0.85rem; }
.cp-hint { font-size: 0.72rem; opacity: 0.6; }
.cp-loading, .cp-empty { padding: 24px; text-align: center; opacity: 0.7; }
</style>
