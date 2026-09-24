<template>
 <ItemDimensionFetcher :items="items" :edit="frm.doc.docstatus === 0"
  :show-dimensions="false" :other-inputs="otherInputs" :table-fields="tableFields"
  :validate-qty="true" :args="args"
  @itemadded="dirty" @itemupdated="dirty" @itemremoved="dirty" />
</template>
<script setup>
import {ref} from 'vue';
import ItemDimensionFetcher from '../../../../yrp/yrp/public/js/Stock/components/ItemDimensionFetch.vue';
const props = defineProps({frm: Object});
const items = ref([]);
const fields = [
 ['from_lot', 'From Lot', 'SD YRP Lot'],
 ['to_lot', 'To Lot', 'SD YRP Lot'],
 ['warehouse', 'Warehouse', 'Warehouse'],
 ['received_type', 'Received Type', 'YRP Received Type'],
];
const otherInputs = fields.map(([name, label, options]) => ({
 name, parent: 'transfer-fields', df: {fieldname: name, label, options, fieldtype: 'Link', reqd: 1},
}));
const tableFields = fields.map(([name, label]) => ({name, label}));
tableFields.push({name: 'rate', label: 'Rate', uses_primary_attribute: 1});
const args = {item_query: () => ({filters: {is_stock_item: 1}})};
const dirty = () => props.frm.dirty();
function load(data) {
 items.value = JSON.parse(JSON.stringify(data || []));
 // Transfer fields are edited through otherInputs, not the stock-dimension controls.
 for (const group of items.value) {
  for (const entry of group.items) entry.dimensions = {};
 }
}
function get_items() { return items.value; }
defineExpose({load, get_items});
</script>
