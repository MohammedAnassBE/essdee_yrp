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
        v-for="(e, i) in entries"
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

        <section v-if="false" class="cp-colour-recipes">
          <label v-if="i > 0" class="cp-main-recipe-toggle">
            <input
              type="checkbox"
              :checked="e.useMainFabricRecipes"
              @change="setUseMainFabricRecipes(e, $event.target.checked)"
            />
            <span>
              <strong>Use Main Fabric Yarn Recipes</strong>
              <small>
                Reuse Main Fabric's recipe for each matching finished colour.
                Main Fabric changes are followed automatically.
              </small>
            </span>
          </label>
          <div class="cp-section-head">
            <div>
              <strong>Colour-wise yarn selection</strong>
              <small>Choose the simplest entry mode. Every colour recipe must total exactly 100%.</small>
            </div>
            <div
              v-if="!e.useMainFabricRecipes"
              class="cp-mode-switch"
              role="group"
              aria-label="Yarn entry mode"
            >
              <button
                v-for="option in RECIPE_MODES"
                :key="option.value"
                type="button"
                :class="{ active: e.recipeMode === option.value }"
                :aria-pressed="e.recipeMode === option.value"
                @click="setRecipeMode(e, option.value)"
              >
                {{ option.label }}
              </button>
            </div>
          </div>

          <div v-if="e.useMainFabricRecipes" class="cp-main-recipe-summary">
            <strong>Following Main Fabric</strong>
            <span
              v-for="colour in e.requiredColours"
              :key="colour"
              :class="{ invalid: !!validateYarnRows(effectiveRecipeForColour(e, colour)) }"
            >
              {{ colour }}:
              {{ effectiveRecipeForColour(e, colour).map((row) => `${row.yarn_item || "Missing yarn"} ${formatRatio(row.ratio)}%`).join(" + ") }}
            </span>
          </div>

          <div v-else-if="e.recipeMode === 'same'" class="cp-shared-recipe">
            <div class="cp-colour-title">
              <span>One recipe for all: {{ e.requiredColours.join(", ") || "uncoloured cloth" }}</span>
              <strong :class="{ invalid: !!validateYarnRows(e.sharedYarns) }">
                {{ formatRatio(rowsTotal(e.sharedYarns)) }}%
              </strong>
            </div>
            <div class="cp-yarn-head" aria-hidden="true">
              <span>Yarn Item</span><span>Ratio %</span><span></span>
            </div>
            <div v-for="(yarn, yarnIndex) in e.sharedYarns" :key="yarnIndex" class="cp-yarn-row">
              <LinkField
                :modelValue="yarn.yarn_item || ''"
                @update:modelValue="(v) => onColourYarnChange(e, yarn, v)"
                target-doctype="YRP Item"
                placeholder="Select yarn item"
              />
              <InputNumber v-model="yarn.ratio" :min="0" :max="100" :maxFractionDigits="3" suffix="%" />
              <Button
                icon="pi pi-trash"
                text
                rounded
                severity="danger"
                :disabled="e.sharedYarns.length === 1"
                :aria-label="`Remove yarn row ${yarnIndex + 1}`"
                @click="removeRecipeYarn(e.sharedYarns, yarnIndex)"
              />
            </div>
            <Button label="Add yarn" icon="pi pi-plus" size="small" text @click="addRecipeYarn(e.sharedYarns)" />
          </div>

          <div v-else-if="e.recipeMode === 'group'" class="cp-profile-list">
            <div
              v-for="(profile, profileIndex) in e.recipeGroups"
              :key="profile.id"
              class="cp-colour-recipe cp-profile-card"
            >
              <div class="cp-profile-head">
                <div>
                  <strong>Recipe {{ profileIndex + 1 }}</strong>
                  <small>
                    {{ profile.colours.length
                      ? profile.colours.join(", ")
                      : "Assign at least one finished colour" }}
                  </small>
                </div>
                <div class="cp-profile-actions">
                  <strong :class="{ invalid: !!validateYarnRows(profile.yarns) }">
                    {{ formatRatio(rowsTotal(profile.yarns)) }}%
                  </strong>
                  <Button
                    icon="pi pi-trash"
                    text
                    rounded
                    severity="danger"
                    :disabled="e.recipeGroups.length === 1 || profile.colours.length > 0"
                    title="Unassign this profile's colours before removing it"
                    :aria-label="`Remove recipe ${profileIndex + 1}`"
                    @click="removeRecipeGroup(e, profileIndex)"
                  />
                </div>
              </div>
              <div class="cp-profile-colours">
                <label
                  v-for="colour in e.requiredColours"
                  :key="colour"
                  :class="{ assigned: profile.colours.includes(colour) }"
                >
                  <input
                    type="checkbox"
                    :checked="profile.colours.includes(colour)"
                    @change="assignGroupColour(e, profileIndex, colour, $event.target.checked)"
                  />
                  {{ colour }}
                </label>
              </div>
              <div v-for="(yarn, yarnIndex) in profile.yarns" :key="yarnIndex" class="cp-mini-yarn">
                <LinkField
                  :modelValue="yarn.yarn_item || ''"
                  @update:modelValue="(v) => onColourYarnChange(e, yarn, v)"
                  target-doctype="YRP Item"
                  placeholder="Yarn item"
                />
                <InputNumber v-model="yarn.ratio" :min="0" :max="100" :maxFractionDigits="3" suffix="%" />
                <Button
                  icon="pi pi-trash"
                  text
                  rounded
                  severity="danger"
                  :disabled="profile.yarns.length === 1"
                  :aria-label="`Remove yarn row ${yarnIndex + 1} from recipe ${profileIndex + 1}`"
                  @click="removeRecipeYarn(profile.yarns, yarnIndex)"
                />
              </div>
              <Button
                label="Add yarn"
                icon="pi pi-plus"
                size="small"
                text
                @click="addRecipeYarn(profile.yarns)"
              />
            </div>
            <Button
              label="Add recipe profile"
              icon="pi pi-plus"
              size="small"
              outlined
              @click="addRecipeGroup(e)"
            />
          </div>

          <div v-else class="cp-colour-recipe-grid">
              <div v-for="colour in e.requiredColours" :key="colour" class="cp-colour-recipe">
                <div class="cp-colour-title">
                  <span>{{ colour }}</span>
                  <strong :class="{ invalid: !!validateYarnRows(e.recipesByColour[colour]) }">
                    {{ formatRatio(rowsTotal(e.recipesByColour[colour])) }}%
                  </strong>
                </div>
                <div v-for="(yarn, yarnIndex) in e.recipesByColour[colour]" :key="yarnIndex" class="cp-mini-yarn">
                  <LinkField
                    :modelValue="yarn.yarn_item || ''"
                    @update:modelValue="(v) => onColourYarnChange(e, yarn, v)"
                    target-doctype="YRP Item"
                    placeholder="Yarn item"
                  />
                  <InputNumber v-model="yarn.ratio" :min="0" :max="100" :maxFractionDigits="3" suffix="%" />
                  <Button
                    icon="pi pi-trash"
                    text
                    rounded
                    severity="danger"
                    :disabled="e.recipesByColour[colour].length === 1"
                    :aria-label="`Remove yarn row ${yarnIndex + 1} from ${colour}`"
                    @click="removeRecipeYarn(e.recipesByColour[colour], yarnIndex)"
                  />
                </div>
                <Button
                  label="Add yarn"
                  icon="pi pi-plus"
                  size="small"
                  text
                  @click="addRecipeYarn(e.recipesByColour[colour])"
                />
              </div>
          </div>
          <small class="cp-yarn-constraint">
            Yarn Items must be attribute-less. Colour and Dia begin on the cloth received from Knitting.
          </small>
          <small v-if="recipeError(e)" class="cp-recipe-error">{{ recipeError(e) }}</small>
        </section>

        <section v-if="e.requiredColours.length" class="cp-output-colours">
          <div class="cp-section-head">
            <div>
              <strong>Knitting output colour</strong>
            </div>
          </div>
          <div class="cp-output-grid">
            <div
              v-for="colour in e.requiredColours"
              :key="colour"
              class="cp-output-card"
            >
              <div class="cp-output-summary">
                <div>
                  <small>Finished Colour</small>
                  <strong>{{ colour }}</strong>
                </div>
                <i class="pi pi-arrow-right" aria-hidden="true"></i>
                <label class="cp-output-summary-field">
                  <small>Knitting Output</small>
                  <LinkField
                    :modelValue="commonOutputColour(e, colour)"
                    @update:modelValue="(v) => setOutputColourForAllDias(e, colour, v)"
                    target-doctype="YRP Item Attribute Value"
                    :filters="{ attribute_name: 'Colour' }"
                    :placeholder="outputColourLabel(e, colour)"
                  />
                </label>
                <span>{{ routesForColour(e, colour).length }} routes · {{ formatWeight(colourTotal(e, colour)) }} kg</span>
                <Button
                  :label="isEditingRoutes(e, colour) ? 'Done' : 'Edit'"
                  :icon="isEditingRoutes(e, colour) ? 'pi pi-check' : 'pi pi-pencil'"
                  size="small"
                  outlined
                  @click="toggleRouteEditor(e, colour)"
                />
              </div>
              <div v-if="isEditingRoutes(e, colour)" class="cp-output-editor">
                <div
                  v-for="route in routesForColour(e, colour)"
                  :key="`${route.dia}-${route.colour}`"
                  class="cp-route-row"
                >
                  <div class="cp-route-finished">
                    <strong>{{ route.dia }}</strong>
                    <small>
                      {{ formatWeight(route.weight) }} kg required ·
                      {{ formatWeight(routeProgramWeight(route)) }} kg program
                      <template v-if="route.additional_weight">
                        (+{{ formatWeight(route.additional_weight) }} kg added)
                      </template>
                    </small>
                    <small
                      :class="route.knitting_output_colour === colour ? 'direct' : 'dye'"
                    >
                      {{ route.knitting_output_colour === colour ? "Direct colour" : "Needs dyeing" }}
                    </small>
                  </div>
                  <label>
                    Knitting output Dia
                    <LinkField
                      :modelValue="route.knitting_output_dia || ''"
                      @update:modelValue="(v) => (route.knitting_output_dia = v || '')"
                      target-doctype="YRP Item Attribute Value"
                      :filters="{ attribute_name: 'Dia' }"
                      placeholder="Physical Dia after knitting"
                    />
                  </label>
                  <label>
                    Knitting output Colour
                    <LinkField
                      :modelValue="route.knitting_output_colour || ''"
                      @update:modelValue="(v) => (route.knitting_output_colour = v || '')"
                      target-doctype="YRP Item Attribute Value"
                      :filters="{ attribute_name: 'Colour' }"
                      placeholder="Physical colour after knitting"
                    />
                    <Button
                      v-if="route.knitting_output_colour !== colour"
                      label="Use finished colour"
                      icon="pi pi-check"
                      size="small"
                      text
                      @click="route.knitting_output_colour = colour"
                    />
                  </label>
                </div>
              </div>
            </div>
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
              target-doctype="YRP Process"
              placeholder="Select knitting"
            />
          </label>
          <label>
            Dyeing Process {{ requiresDyeing(e) ? "(required)" : "(not required)" }}
            <LinkField
              :modelValue="e.dyeing_process || ''"
              @update:modelValue="(v) => (e.dyeing_process = v || '')"
              target-doctype="YRP Process"
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
const editingRouteGroups = ref({})
const initialSnapshot = ref("")
let recipeGroupCounter = 0
const RECIPE_MODES = Object.freeze([
  { value: "same", label: "Same for all" },
  { value: "group", label: "Colour groups" },
  { value: "individual", label: "Individual" },
])

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
  editingRouteGroups.value = {}
  try {
    const r = await callMethod("essdee_yrp.api.cloth_program.get_cloth_program_context", { lot: props.lot })
    const defaults = (r && r.defaults) || {}
    entries.value = ((r && r.cloths) || []).map((c) => ({
      ...normaliseColourRecipes(c, defaults),
      cloth_item: c.cloth_item,
      label: c.label,
      production_detail: c.production_detail || "",
      useMainFabricRecipes: false,
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

function normaliseColourRecipes(cloth, defaults = {}) {
  const itemYarns = cloneRows(cloth.item_yarns || [])
  const storedColourYarns = cloth.colour_yarn_recipes || []
  const requiredColours = (cloth.required_colours || []).filter(Boolean)
  const fallback = cloneRows(itemYarns)
  const recipesByColour = {}
  for (const colour of requiredColours) {
    const stored = cloneRows(
      storedColourYarns.filter((row) => row.colour === colour),
    )
    recipesByColour[colour] = stored.length ? stored : cloneRows(fallback)
  }
  const signatures = requiredColours.map((colour) => recipeSignature(recipesByColour[colour]))
  const uniqueSignatures = new Set(signatures)
  const same = uniqueSignatures.size <= 1
  const recipeGroups = buildRecipeGroups(requiredColours, recipesByColour)
  const firstColour = requiredColours[0] || ""
  const storedOutputs = cloth.profile?.knitting_output_colours || {}
  const storedRoutes = cloth.profile?.fabric_routes || []
  const defaultOutput = defaults.knitting_output_colour || ""
  const legacyOutput = cloth.profile?.greige_colour || ""
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
        weight: Number(route.weight) || 0,
        knitting_output_dia: existing?.knitting_output_dia || route.dia || "",
        knitting_output_colour:
          existing?.knitting_output_colour ||
          defaultOutput ||
          storedOutputs[route.colour] ||
          legacyOutput ||
          "",
      }
    })
    .sort((a, b) => diaSortValue(a.dia) - diaSortValue(b.dia))
  return {
    itemYarns,
    requiredColours,
    requiredRoutes,
    recipesByColour,
    recipeGroups,
    sharedYarns: cloneRows(recipesByColour[firstColour] || fallback),
    recipeMode: same
      ? "same"
      : (uniqueSignatures.size < requiredColours.length ? "group" : "individual"),
  }
}

function cloneRows(rows) {
  return (rows || []).map((row) => ({
    yarn_item: row.yarn_item || "",
    ratio: Number(row.ratio) || 0,
  }))
}

function recipeSignature(rows) {
  return JSON.stringify(
    cloneRows(rows)
      .sort((a, b) => a.yarn_item.localeCompare(b.yarn_item))
      .map((row) => [row.yarn_item, Number(row.ratio || 0)]),
  )
}

function diaSortValue(value) {
  const number = Number.parseFloat(String(value || "").match(/-?\d+(?:\.\d+)?/)?.[0])
  return Number.isFinite(number) ? number : Number.MAX_SAFE_INTEGER
}

function buildRecipeGroups(colours, recipesByColour) {
  const groups = []
  const bySignature = new Map()
  for (const colour of colours) {
    const rows = cloneRows(recipesByColour[colour] || [])
    const signature = recipeSignature(rows)
    let group = bySignature.get(signature)
    if (!group) {
      group = {
        id: `recipe-${++recipeGroupCounter}`,
        colours: [],
        yarns: rows.length ? rows : [{ yarn_item: "", ratio: 0 }],
      }
      bySignature.set(signature, group)
      groups.push(group)
    }
    group.colours.push(colour)
  }
  return groups.length
    ? groups
    : [{
        id: `recipe-${++recipeGroupCounter}`,
        colours: [...colours],
        yarns: [{ yarn_item: "", ratio: 0 }],
      }]
}

function firstProfileYarn(entry) {
  if (entry.recipeMode === "same") return entry.sharedYarns?.[0]?.yarn_item || ""
  if (entry.recipeMode === "group") return entry.recipeGroups?.[0]?.yarns?.[0]?.yarn_item || ""
  return entry.recipesByColour?.[entry.requiredColours?.[0]]?.[0]?.yarn_item || ""
}

function recipeModeLabel(mode) {
  return RECIPE_MODES.find((option) => option.value === mode)?.label || mode
}

function setRecipeMode(entry, mode) {
  if (entry.recipeMode === mode) return

  if (mode === "same") {
    const signatures = new Set(
      entry.requiredColours.map((colour) =>
        recipeSignature(recipeForColour(entry, colour))),
    )
    if (
      signatures.size > 1 &&
      !window.confirm(
        "These colours currently use different yarn recipes. Use the first colour's recipe for every colour?",
      )
    ) {
      return
    }
    entry.sharedYarns = cloneRows(
      recipeForColour(entry, entry.requiredColours[0]) || entry.sharedYarns,
    )
  }

  if (entry.recipeMode === "group" && mode === "individual") {
    syncGroupsToIndividual(entry)
  }

  if (entry.recipeMode === "same" && mode === "individual") {
    for (const colour of entry.requiredColours) {
      entry.recipesByColour[colour] = cloneRows(entry.sharedYarns)
    }
  }

  if (mode === "group") {
    if (entry.recipeMode === "same") {
      entry.recipeGroups = [{
        id: `recipe-${++recipeGroupCounter}`,
        colours: [...entry.requiredColours],
        yarns: cloneRows(entry.sharedYarns),
      }]
    } else if (entry.recipeMode === "individual") {
      entry.recipeGroups = buildRecipeGroups(
        entry.requiredColours, entry.recipesByColour)
    } else if (!entry.recipeGroups?.length) {
      entry.recipeGroups = [{
        id: `recipe-${++recipeGroupCounter}`,
        colours: [...entry.requiredColours],
        yarns: cloneRows(entry.sharedYarns),
      }]
    }
  }
  entry.recipeMode = mode
}

function recipeForColour(entry, colour) {
  if (entry.recipeMode === "same") return entry.sharedYarns
  if (entry.recipeMode === "group") {
    return entry.recipeGroups.find((group) => group.colours.includes(colour))?.yarns || []
  }
  return entry.recipesByColour[colour] || []
}

function effectiveRecipeForColour(entry, colour) {
  if (entry.useMainFabricRecipes && entries.value[0] && entries.value[0] !== entry) {
    return recipeForColour(entries.value[0], colour)
  }
  return recipeForColour(entry, colour)
}

function setUseMainFabricRecipes(entry, checked) {
  entry.useMainFabricRecipes = Boolean(checked)
}

function syncGroupsToIndividual(entry) {
  for (const colour of entry.requiredColours) {
    const group = entry.recipeGroups.find((candidate) =>
      candidate.colours.includes(colour))
    if (group) entry.recipesByColour[colour] = cloneRows(group.yarns)
  }
}

function assignGroupColour(entry, groupIndex, colour, checked) {
  for (const group of entry.recipeGroups) {
    const index = group.colours.indexOf(colour)
    if (index !== -1) group.colours.splice(index, 1)
  }
  if (checked) entry.recipeGroups[groupIndex].colours.push(colour)
}

function addRecipeGroup(entry) {
  entry.recipeGroups.push({
    id: `recipe-${++recipeGroupCounter}`,
    colours: [],
    yarns: [{ yarn_item: "", ratio: 0 }],
  })
}

function removeRecipeGroup(entry, index) {
  const group = entry.recipeGroups[index]
  if (!group || group.colours.length || entry.recipeGroups.length === 1) return
  entry.recipeGroups.splice(index, 1)
}

function addRecipeYarn(rows) {
  rows.push({ yarn_item: "", ratio: 0 })
}

function removeRecipeYarn(rows, index) {
  if (rows.length > 1) rows.splice(index, 1)
}

function rowsTotal(rows) {
  return (rows || []).reduce((sum, row) => sum + (Number(row.ratio) || 0), 0)
}

function formatRatio(value) {
  return Number(value || 0).toLocaleString(undefined, { maximumFractionDigits: 3 })
}

function formatWeight(value) {
  return Number(value || 0).toLocaleString(undefined, { maximumFractionDigits: 3 })
}

function roundProgramWeight(value) {
  const number = Number(value || 0)
  const floor = Math.floor(number)
  return number - floor > 0.5 ? Math.ceil(number) : floor
}

function routeProgramWeight(route) {
  const percentage = Math.max(0, Number(excessPercentage.value || 0))
  return roundProgramWeight(Number(route.weight || 0) * (1 + percentage / 100))
    + Number(route.additional_weight || 0)
}

function routesForColour(entry, colour) {
  return entry.requiredRoutes.filter((route) => route.colour === colour)
}

function commonOutputColour(entry, colour) {
  const values = [...new Set(
    routesForColour(entry, colour)
      .map((route) => route.knitting_output_colour)
      .filter(Boolean),
  )]
  return values.length === 1 ? values[0] : ""
}

function outputColourLabel(entry, colour) {
  const values = [...new Set(
    routesForColour(entry, colour)
      .map((route) => route.knitting_output_colour)
      .filter(Boolean),
  )]
  if (values.length === 1) return values[0]
  return values.length ? "Mixed by Dia" : "Not set"
}

function routeEditorKey(entry, colour) {
  return `${entry.cloth_item}::${colour}`
}

function isEditingRoutes(entry, colour) {
  return Boolean(editingRouteGroups.value[routeEditorKey(entry, colour)])
}

function toggleRouteEditor(entry, colour) {
  const key = routeEditorKey(entry, colour)
  editingRouteGroups.value = {
    ...editingRouteGroups.value,
    [key]: !editingRouteGroups.value[key],
  }
}

function setOutputColourForAllDias(entry, colour, value) {
  for (const route of routesForColour(entry, colour)) {
    route.knitting_output_colour = value || ""
  }
}

function colourTotal(entry, colour) {
  return routesForColour(entry, colour).reduce(
    (total, route) => total + (Number(route.weight) || 0), 0)
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
  if (!e.requiredColours.length) return validateYarnRows(e.sharedYarns)
  if (e.useMainFabricRecipes) {
    for (const colour of e.requiredColours) {
      const rows = effectiveRecipeForColour(e, colour)
      if (!rows.length) {
        return `Main Fabric has no yarn recipe for ${colour}.`
      }
      const error = validateYarnRows(rows)
      if (error) return `Main Fabric / ${colour}: ${error}`
    }
    return ""
  }
  if (e.recipeMode === "same") return validateYarnRows(e.sharedYarns)
  if (e.recipeMode === "group") {
    const assigned = e.recipeGroups.flatMap((group) => group.colours)
    const missing = e.requiredColours.filter((colour) => !assigned.includes(colour))
    if (missing.length) return `Assign a recipe profile to: ${missing.join(", ")}.`
    for (const [index, group] of e.recipeGroups.entries()) {
      if (!group.colours.length) continue
      const error = validateYarnRows(group.yarns)
      if (error) return `Recipe ${index + 1}: ${error}`
    }
    return ""
  }
  for (const colour of e.requiredColours) {
    const error = validateYarnRows(e.recipesByColour[colour])
    if (error) return `${colour}: ${error}`
  }
  return ""
}

function outputError(entry) {
  const missing = entry.requiredRoutes.filter(
    (route) => !route.knitting_output_colour || !route.knitting_output_dia)
  return missing.length
    ? `Complete the knitting output Colour and Dia for ${missing[0].colour} / ${missing[0].dia}.`
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
  return entry.requiredRoutes.some(
    (route) =>
      route.knitting_output_colour &&
      route.knitting_output_colour !== route.colour,
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
    knitting_output_colour: route.knitting_output_colour || "",
    knitting_output_dia: route.knitting_output_dia || "",
  }))
}

function flattenColourRecipes(entry) {
  if (entry.useMainFabricRecipes) {
    return entry.requiredColours.flatMap((colour) =>
      cloneRows(effectiveRecipeForColour(entry, colour)).map((row) => ({
        colour,
        ...row,
      })),
    )
  }
  if (entry.recipeMode === "same") {
    return entry.requiredColours.flatMap((colour) =>
      cloneRows(entry.sharedYarns).map((row) => ({ colour, ...row })),
    )
  }
  if (entry.recipeMode === "group") {
    return entry.requiredColours.flatMap((colour) =>
      cloneRows(recipeForColour(entry, colour)).map((row) => ({ colour, ...row })),
    )
  }
  return entry.requiredColours.flatMap((colour) =>
    cloneRows(entry.recipesByColour[colour]).map((row) => ({ colour, ...row })),
  )
}

function primaryRecipe(entry) {
  if (entry.useMainFabricRecipes && entry.requiredColours.length) {
    return cloneRows(effectiveRecipeForColour(entry, entry.requiredColours[0]))
  }
  if (entry.recipeMode === "same" || !entry.requiredColours.length) {
    return cloneRows(entry.sharedYarns)
  }
  if (entry.recipeMode === "group") {
    return cloneRows(recipeForColour(entry, entry.requiredColours[0]))
  }
  return cloneRows(entry.recipesByColour[entry.requiredColours[0]] || [])
}

function onColourYarnChange(e, yarn, v) {
  yarn.yarn_item = v || ""
}

async function applyYarnProfile(e, yarnItem) {
  if (!yarnItem) return
  try {
    const p = (await callMethod("essdee_yrp.api.cloth_program.get_yarn_profile", { yarn_item: yarnItem })) || {}
    if (p.knitting_process) e.knitting_process = p.knitting_process
    if (p.dyeing_process) e.dyeing_process = p.dyeing_process
    if (p.compacting_process) e.compacting_process = p.compacting_process
    if (p.cloth_per_kg_yarn) e.cloth_per_kg_yarn = p.cloth_per_kg_yarn
    const outputs = p.knitting_output_colours || {}
    const routes = p.fabric_routes || []
    for (const route of e.requiredRoutes) {
      const existing = routes.find(
        (row) =>
          row.finished_colour === route.colour &&
          row.finished_dia === route.dia,
      )
      if (!route.knitting_output_colour) {
        route.knitting_output_colour =
          existing?.knitting_output_colour ||
          outputs[route.colour] ||
          p.greige_colour ||
          ""
      }
      if (!route.knitting_output_dia) {
        route.knitting_output_dia = existing?.knitting_output_dia || route.dia
      }
    }
  } catch (err) {
    // non-fatal: leave the fields for manual entry
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
    colour_yarn_recipes: flattenColourRecipes(e),
    fabric_routes: flattenFabricRoutes(e),
    yarns: primaryRecipe(e),
    yarn_item: primaryRecipe(e)[0]?.yarn_item || null,
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
.cp-card { display: flex; flex-direction: column; border: 1px solid var(--p-content-border-color, #e5e7eb); border-radius: 12px; padding: 16px; }
.cp-card--invalid { border-color: color-mix(in srgb, var(--p-red-500, #ef4444) 42%, var(--p-content-border-color)); }
.cp-card-head { order: 0; }
.cp-output-colours { order: 1; }
.cp-colour-recipes { order: 2; }
.cp-grid { order: 3; }
.cp-card-head,
.cp-section-head { display: flex; align-items: center; justify-content: space-between; gap: 12px; }
.cp-card-title { font-weight: 700; font-size: 1rem; }
.cp-cloth-item { margin-top: 2px; font-size: 0.78rem; opacity: 0.68; }
.cp-yarn-recipe { margin: 14px 0; padding: 12px; border-radius: 10px; background: var(--p-content-hover-background, #f8fafc); }
.cp-colour-recipes,
.cp-output-colours { margin: 14px 0; padding: 12px; border-radius: 10px; background: var(--p-content-hover-background, #f8fafc); }
.cp-main-recipe-toggle { display: flex; align-items: flex-start; gap: 8px; margin-bottom: 10px; padding: 10px; border: 1px solid color-mix(in srgb, var(--esd-accent, var(--p-primary-color)) 35%, var(--p-content-border-color)); border-radius: 9px; background: color-mix(in srgb, var(--esd-accent, var(--p-primary-color)) 7%, var(--p-content-background)); cursor: pointer; }
.cp-main-recipe-toggle input { margin-top: 3px; accent-color: var(--esd-accent, var(--p-primary-color)); }
.cp-main-recipe-toggle span { display: flex; flex-direction: column; gap: 2px; }
.cp-main-recipe-toggle small { opacity: 0.68; }
.cp-main-recipe-summary { display: flex; flex-wrap: wrap; gap: 6px; padding: 10px; border: 1px solid var(--p-content-border-color, #e5e7eb); border-radius: 9px; background: var(--p-content-background, #fff); }
.cp-main-recipe-summary strong { width: 100%; }
.cp-main-recipe-summary span { padding: 5px 7px; border-radius: 7px; font-size: 0.72rem; background: var(--p-content-hover-background, #f3f4f6); }
.cp-main-recipe-summary span.invalid { color: var(--p-red-600, #dc2626); }
.cp-colour-recipe-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 8px; }
.cp-colour-recipe { border: 1px solid var(--p-content-border-color, #e5e7eb); border-radius: 8px; padding: 9px 10px; background: var(--p-content-background, #fff); }
.cp-colour-title { display: flex; justify-content: space-between; gap: 12px; }
.cp-colour-title { font-weight: 700; margin-bottom: 6px; }
.cp-colour-title strong { color: var(--esd-accent, var(--p-primary-color)); font-size: 0.75rem; }
.cp-colour-title strong.invalid { color: var(--p-red-600, #dc2626); }
.cp-section-head { align-items: flex-start; margin-bottom: 10px; }
.cp-section-head > div { display: flex; flex-direction: column; gap: 2px; }
.cp-section-head small { opacity: 0.65; }
.cp-mode-switch { display: flex !important; flex-direction: row !important; gap: 3px !important; padding: 3px; border: 1px solid var(--p-content-border-color, #e5e7eb); border-radius: 9px; background: var(--p-content-background, #fff); }
.cp-mode-switch button { border: 0; border-radius: 7px; padding: 6px 9px; color: var(--esd-muted, inherit); background: transparent; font: inherit; font-size: 0.75rem; font-weight: 650; cursor: pointer; }
.cp-mode-switch button.active { color: var(--p-primary-contrast-color, #fff); background: var(--esd-accent, var(--p-primary-color)); }
.cp-shared-recipe { padding: 10px; border: 1px solid var(--p-content-border-color, #e5e7eb); border-radius: 9px; background: var(--p-content-background, #fff); }
.cp-profile-list { display: flex; flex-direction: column; gap: 9px; }
.cp-profile-card { display: flex; flex-direction: column; gap: 8px; }
.cp-profile-head,
.cp-profile-actions { display: flex; align-items: center; justify-content: space-between; gap: 8px; }
.cp-profile-head > div:first-child { display: flex; flex-direction: column; gap: 2px; }
.cp-profile-head small { opacity: 0.65; }
.cp-profile-actions strong { color: var(--esd-accent, var(--p-primary-color)); font-size: 0.75rem; }
.cp-profile-actions strong.invalid { color: var(--p-red-600, #dc2626); }
.cp-profile-colours { display: flex; flex-wrap: wrap; gap: 5px; }
.cp-profile-colours label { display: inline-flex; align-items: center; gap: 5px; padding: 5px 7px; border: 1px solid var(--p-content-border-color, #e5e7eb); border-radius: 7px; font-size: 0.72rem; cursor: pointer; }
.cp-profile-colours label.assigned { border-color: color-mix(in srgb, var(--esd-accent, var(--p-primary-color)) 45%, var(--p-content-border-color)); background: color-mix(in srgb, var(--esd-accent, var(--p-primary-color)) 8%, var(--p-content-background)); }
.cp-profile-colours input { accent-color: var(--esd-accent, var(--p-primary-color)); }
.cp-group-fill { display: grid; grid-template-columns: minmax(150px, 190px) minmax(240px, 1fr) auto; gap: 10px; align-items: end; margin-bottom: 10px; padding: 10px; border: 1px solid color-mix(in srgb, var(--esd-accent, var(--p-primary-color)) 24%, var(--p-content-border-color)); border-radius: 9px; background: color-mix(in srgb, var(--esd-accent, var(--p-primary-color)) 6%, var(--p-content-background)); }
.cp-group-fill > label { display: flex; flex-direction: column; gap: 4px; font-size: 0.72rem; font-weight: 650; }
.cp-select { width: 100%; min-height: 36px; padding: 6px 8px; border: 1px solid var(--p-content-border-color, #d1d5db); border-radius: 7px; color: inherit; background: var(--p-content-background, #fff); font: inherit; }
.cp-targets { display: flex; flex-wrap: wrap; gap: 5px; }
.cp-target-chip { display: inline-flex; align-items: center; gap: 5px; padding: 5px 7px; border: 1px solid var(--p-content-border-color, #e5e7eb); border-radius: 7px; background: var(--p-content-background, #fff); font-size: 0.72rem; }
.cp-target-chip input { accent-color: var(--esd-accent, var(--p-primary-color)); }
.cp-mini-yarn { display: grid; grid-template-columns: minmax(0, 1fr) 105px 40px; gap: 6px; align-items: center; margin-bottom: 6px; }
.cp-yarn-head,
.cp-yarn-row { display: grid; grid-template-columns: minmax(220px, 1fr) minmax(130px, 180px) 40px; gap: 8px; align-items: center; }
.cp-mini-yarn > *,
.cp-yarn-row > *,
.cp-route-row > *,
.cp-grid > * { min-width: 0; }
.cp-mini-yarn :deep(.p-autocomplete),
.cp-mini-yarn :deep(.p-inputnumber),
.cp-yarn-row :deep(.p-autocomplete),
.cp-yarn-row :deep(.p-inputnumber),
.cp-route-row :deep(.p-autocomplete),
.cp-grid :deep(.p-autocomplete),
.cp-grid :deep(.p-inputnumber) {
  width: 100%;
  min-width: 0;
}
.cp-mini-yarn :deep(.p-inputnumber-input),
.cp-mini-yarn :deep(.p-autocomplete-input),
.cp-yarn-row :deep(.p-inputnumber-input),
.cp-yarn-row :deep(.p-autocomplete-input),
.cp-route-row :deep(.p-autocomplete-input),
.cp-grid :deep(.p-inputnumber-input),
.cp-grid :deep(.p-autocomplete-input) {
  width: 100%;
  min-width: 0;
}
.cp-yarn-head { padding: 0 2px 5px; font-size: 0.72rem; font-weight: 600; opacity: 0.65; }
.cp-yarn-row + .cp-yarn-row { margin-top: 8px; }
.cp-recipe-error { display: block; margin-top: 8px; color: var(--p-red-600, #dc2626); }
.cp-yarn-constraint { display: block; margin-top: 7px; opacity: 0.68; }
.cp-output-grid { display: grid; grid-template-columns: minmax(0, 1fr); gap: 8px; }
.cp-output-card { display: flex; flex-direction: column; gap: 6px; padding: 10px; border: 1px solid var(--p-content-border-color, #e5e7eb); border-radius: 9px; background: var(--p-content-background, #fff); }
.cp-output-summary { display: grid; grid-template-columns: minmax(120px, 0.8fr) auto minmax(140px, 1fr) auto auto; gap: 12px; align-items: center; }
.cp-output-summary > div,
.cp-output-summary-field { display: flex; flex-direction: column; gap: 2px; min-width: 0; }
.cp-output-summary small { font-size: 0.68rem; opacity: 0.65; }
.cp-output-summary > span { font-size: 0.72rem; opacity: 0.68; }
.cp-output-summary > i { opacity: 0.5; }
.cp-output-summary-field :deep(.p-autocomplete),
.cp-output-summary-field :deep(.p-autocomplete-input) { width: 100%; min-width: 0; }
.cp-output-editor { display: flex; flex-direction: column; gap: 6px; margin-top: 4px; }
.cp-output-target { display: flex; align-items: center; justify-content: space-between; gap: 6px; font-size: 0.78rem; font-weight: 700; }
.cp-output-target small { padding: 2px 6px; border-radius: 999px; font-size: 0.64rem; white-space: nowrap; }
.cp-output-target small.direct { color: var(--p-green-700, #15803d); background: color-mix(in srgb, var(--p-green-500, #22c55e) 12%, transparent); }
.cp-output-target small.dye { color: var(--p-orange-700, #c2410c); background: color-mix(in srgb, var(--p-orange-500, #f97316) 12%, transparent); }
.cp-output-bulk { display: grid; grid-template-columns: minmax(220px, 1fr) auto; gap: 8px; align-items: end; padding: 8px; border-radius: 8px; background: var(--p-content-hover-background, #f8fafc); }
.cp-output-bulk label { display: flex; flex-direction: column; gap: 4px; min-width: 0; font-size: 0.72rem; }
.cp-output-bulk :deep(.p-autocomplete),
.cp-output-bulk :deep(.p-autocomplete-input) { width: 100%; min-width: 0; }
.cp-route-dias { display: flex; flex-wrap: wrap; gap: 4px; }
.cp-route-dias span { padding: 3px 6px; border-radius: 6px; font-size: 0.68rem; font-weight: 600; color: var(--esd-muted, inherit); background: var(--p-content-hover-background, #f3f4f6); }
.cp-route-row { display: grid; grid-template-columns: minmax(120px, 0.7fr) minmax(180px, 1fr) minmax(210px, 1.2fr); gap: 8px; padding-top: 8px; border-top: 1px solid var(--p-content-border-color, #e5e7eb); }
.cp-route-row label,
.cp-route-finished { display: flex; flex-direction: column; gap: 4px; font-size: 0.72rem; }
.cp-route-finished small { opacity: 0.7; }
.cp-route-finished small.direct,
.cp-route-finished small.dye { width: fit-content; padding: 2px 6px; border-radius: 999px; opacity: 1; }
.cp-route-finished small.direct { color: var(--p-green-700, #15803d); background: color-mix(in srgb, var(--p-green-500, #22c55e) 12%, transparent); }
.cp-route-finished small.dye { color: var(--p-orange-700, #c2410c); background: color-mix(in srgb, var(--p-orange-500, #f97316) 12%, transparent); }
.cp-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 10px; }
.cp-grid label { display: flex; flex-direction: column; gap: 4px; font-size: 0.85rem; }
.cp-loading, .cp-empty { padding: 24px; text-align: center; opacity: 0.7; }
@media (max-width: 620px) {
  .cp-card-head,
  .cp-section-head { align-items: stretch; flex-direction: column; }
  .cp-mode-switch { align-self: stretch; overflow-x: auto; }
  .cp-group-fill { grid-template-columns: 1fr; }
  .cp-yarn-head { display: none; }
  .cp-yarn-row { grid-template-columns: minmax(0, 1fr) 120px 40px; }
  .cp-mini-yarn { grid-template-columns: minmax(0, 1fr) 100px 34px; }
  .cp-colour-recipe-grid,
  .cp-output-grid,
  .cp-grid { grid-template-columns: minmax(0, 1fr); }
  .cp-output-bulk { grid-template-columns: minmax(0, 1fr); }
  .cp-output-summary { grid-template-columns: minmax(90px, 1fr) auto minmax(110px, 1fr) auto; }
  .cp-output-summary > span { display: none; }
  .cp-route-row { grid-template-columns: minmax(0, 1fr); }
}
@media (max-width: 430px) {
  .cp-card { padding: 10px; }
  .cp-colour-recipes,
  .cp-output-colours { padding: 9px; }
  .cp-yarn-row,
  .cp-mini-yarn { grid-template-columns: minmax(0, 1fr) 86px 32px; gap: 4px; }
  .cp-mode-switch button { flex: 1 0 auto; }
}
@container (max-width: 620px) {
  .cp-card-head,
  .cp-section-head { align-items: stretch; flex-direction: column; }
  .cp-mode-switch { align-self: stretch; overflow-x: auto; }
  .cp-mode-switch button { min-height: 44px; }
  .cp-yarn-head { display: none; }
  .cp-yarn-row { grid-template-columns: minmax(0, 1fr) 112px 44px; }
  .cp-mini-yarn { grid-template-columns: minmax(0, 1fr) 96px 44px; }
  .cp-colour-recipe-grid,
  .cp-output-grid,
  .cp-grid,
  .cp-output-bulk,
  .cp-route-row { grid-template-columns: minmax(0, 1fr); }
  .cp-output-summary { grid-template-columns: minmax(90px, 1fr) auto minmax(110px, 1fr) auto; }
  .cp-output-summary > span { display: none; }
}
</style>
