<template>
  <div ref="root" class="box-container" v-if="Object.keys(lot_wise_detail).length > 0">
    <h3 class="view-title">Lotwise Ordered Detail</h3>
    <div
      v-for="(detail, lot) in lot_wise_detail"
      :key="lot"
      class="lot-section"
    >
      <p class="lot-label">Lot: {{ lot }}</p>
      <table class="styled-table">
        <thead>
          <tr>
            <th>Size</th>
            <th v-for="(value, index) in primary_values" :key="index">
              {{ value }}
            </th>
            <th>Total</th>
          </tr>
        </thead>
        <tbody>
          <tr>
            <td>Qty</td>
            <td v-for="(value, index) in primary_values" :key="index">
              <input
                type="number"
                :value="detail[value] ? detail[value].qty : 0"
                :disabled="true"
                class="styled-input"
              />
            </td>
            <td>{{ lot_totals[lot] }}</td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>

<script setup>
import { ref } from "vue";

const root = ref(null);
const primary_values = ref([]);
const lot_wise_detail = ref({});
const lot_totals = ref({});

function normalizeKey(value) {
  if (value === null || value === undefined) return "";
  return String(value).trim();
}

function getNormalizedItems(items = {}) {
  const normalized = {};
  Object.entries(items || {}).forEach(([key, value]) => {
    const normalizedKey = normalizeKey(key);
    if (!normalizedKey) return;
    normalized[normalizedKey] = value || {};
  });
  return normalized;
}

function load_data(data) {
  const payload = JSON.parse(JSON.stringify(data || {}));
  primary_values.value = (payload.primary_values || [])
    .map(normalizeKey)
    .filter(Boolean);
  lot_wise_detail.value = payload.ordered || {};
  lot_totals.value = {};

  Object.keys(lot_wise_detail.value).forEach((lot) => {
    lot_wise_detail.value[lot] = getNormalizedItems(lot_wise_detail.value[lot]);
    let total = 0;
    primary_values.value.forEach((key) => {
      if (!lot_wise_detail.value[lot][key]) {
        lot_wise_detail.value[lot][key] = { qty: 0 };
      }
      total += Number(lot_wise_detail.value[lot][key].qty || 0);
    });
    lot_totals.value[lot] = total;
  });
}

defineExpose({
  load_data,
});
</script>

<style scoped>
.box-container {
  padding: 10px 0;
  font-family: var(--font-stack);
}

.view-title {
  font-size: 14px;
  font-weight: 700;
  margin: 0 0 10px;
  color: #111827;
}

.lot-section {
  background: #fff;
  border: 1px solid #d1d8dd;
  border-radius: 4px;
  overflow: hidden;
  font-size: 15px;
  font-weight: 600;
  margin-bottom: 15px;
}

.lot-label {
  margin: 0;
  padding: 10px 12px;
  font-size: 13px;
  font-weight: 700;
  color: #111827;
  background-color: #f7fafc;
  border-bottom: 1px solid #d1d8dd;
}

.styled-table {
  width: 100%;
  border-collapse: collapse;
  margin-bottom: 0;
  font-size: 13px;
  color: #1f2937;
}

.styled-table th {
  background-color: #f7fafc;
  color: #64748b;
  font-weight: 700;
  padding: 8px 12px;
  border-bottom: 1px solid #d1d8dd;
  border-right: 1px solid #d1d8dd;
  text-align: center;
}

.styled-table th:last-child {
  border-right: none;
}

.styled-table td {
  padding: 8px 12px;
  border-bottom: 1px solid #d1d8dd;
  border-right: 1px solid #d1d8dd;
  text-align: center;
  vertical-align: middle;
}

.styled-table td:last-child {
  border-right: none;
}

.styled-table tr:last-child td {
  border-bottom: none;
}

.styled-input {
  width: 100%;
  max-width: 80px;
  height: 28px;
  padding: 4px 8px;
  font-size: 13px;
  border: 1px solid #d1d8dd;
  border-radius: 4px;
  text-align: center;
  color: #111827;
  outline: none;
}

.styled-input:disabled {
  background-color: #f3f3f3;
  cursor: not-allowed;
  border-color: #d1d8dd;
}

/* Chrome, Safari, Edge, Opera */
input::-webkit-outer-spin-button,
input::-webkit-inner-spin-button {
  -webkit-appearance: none;
  margin: 0;
}

/* Firefox */
input[type="number"] {
  -moz-appearance: textfield;
  appearance: none;
}
</style>
