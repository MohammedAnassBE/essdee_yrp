<template>
    <div @keydown.capture="select_typed_dia">
        <table class="table table-sm table-bordered" v-if="rows.length > 0"
            v-entry-table="{ add: is_read_only ? null : add_row, isRowBlank: is_row_blank, fixed: false }">
            <thead>
                <tr>
                    <th v-if="!is_read_only" class="row-select"><input type="checkbox" data-row-select aria-label="Select all rows"
                        :checked="selection.isAllSelected.value" :indeterminate="selection.isPartlySelected.value"
                        @change="selection.toggleAll($event.target.checked)"></th>
                    <th style="width: 30%;">Name</th>
                    <th>Dia</th>
                </tr>
            </thead>
            <tbody>
                <tr v-for="(row, index) in rows" :key="row.id">
                    <td v-if="!is_read_only" class="row-select"><input type="checkbox" data-row-select tabindex="-1" aria-label="Select row"
                        :checked="selection.isSelected(index)" @change="selection.toggle(index, $event.target.checked)"></td>
                    <td>
                        <input type="text" class="form-control form-control-sm" v-model="row.name1" @input="make_dirty" placeholder="Enter name" />
                    </td>
                    <td>
                        <div class="dia-cell">
                            <div class="dia-pills">
                                <span class="dia-pill" v-for="d in row.dia" :key="d">
                                    {{ d }}
                                    <span class="dia-pill-remove" @click="removeDia(index, d)">&times;</span>
                                </span>
                            </div>
                            <div class="dia-search-wrap" ref="searchWraps">
                                <input
                                    type="text"
                                    class="form-control form-control-sm dia-search-input"
                                    v-model="row.search"
                                    @input="onSearchInput(index)"
                                    @focus="openDropdown(index)"
                                    :data-dia-row="index"
                                    placeholder="Type to search Dia..."
                                />
                                <div class="dia-dropdown" v-if="activeRow === index && filteredOptions(index).length > 0">
                                    <div
                                        class="dia-dropdown-item"
                                        v-for="opt in filteredOptions(index)"
                                        :key="opt"
                                        @mousedown.prevent="selectDia(index, opt)"
                                    >
                                        {{ opt }}
                                    </div>
                                </div>
                            </div>
                        </div>
                    </td>
                </tr>
            </tbody>
        </table>
        <SelectionFooter :count="selection.selected.value.length" @delete="delete_selected" />
        <button class="btn btn-xs btn-secondary" @click="add_row" style="margin-top: 5px;">Add Row</button>
    </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted } from 'vue';
import { SelectionFooter, useRowSelection, vEntryTable } from "yrp/public/js/utils/entryGrid.js";

const rows = ref([]);
const is_read_only = computed(() => cur_frm.doc.docstatus > 0 || !cur_frm.has_perm("write"));
const selection = useRowSelection(() => is_read_only.value ? [] : rows.value.map((_, index) => index));
const allDiaValues = ref([]);
const activeRow = ref(null);
let nextId = 0;

onMounted(() => {
    fetch_dia_options();
    document.addEventListener('click', handleClickOutside);
});

onUnmounted(() => {
    document.removeEventListener('click', handleClickOutside);
});

function handleClickOutside(e) {
    if (!e.target.closest('.dia-search-wrap')) {
        activeRow.value = null;
    }
}

function fetch_dia_options() {
    frappe.call({
        method: 'yrp.yrp.doctype.yrp_item.yrp_item.search_item_attribute_values',
        args: { attribute: essdee_yrp.get_dia_attribute() },
        callback: function(r) {
            if (r.message) {
                allDiaValues.value = r.message;
            }
        }
    });
}

function filteredOptions(index) {
    const row = rows.value[index];
    const search = (row.search || '').toLowerCase();
    return allDiaValues.value.filter(v =>
        !frappe.yrp.attribute_value(row.dia).includes(v) && v.toLowerCase().includes(search)
    );
}

function openDropdown(index) {
    activeRow.value = index;
}

function onSearchInput(index) {
    activeRow.value = index;
}

function selectDia(index, val) {
    if (!frappe.yrp.attribute_value(rows.value[index].dia).includes(val)) {
        frappe.yrp.attribute_value(rows.value[index].dia).push(val);
    }
    rows.value[index].search = '';
    activeRow.value = null;
    make_dirty();
}

/** Enter in a Dia search with typed text picks the first match instead of moving to the next cell. */
function select_typed_dia(event) {
    const index = Number(event.target.dataset?.diaRow);
    if (event.key !== 'Enter' || Number.isNaN(index) || !rows.value[index].search) return;
    event.preventDefault();
    event.stopPropagation();
    const opts = filteredOptions(index);
    if (opts.length > 0) {
        selectDia(index, opts[0]);
    }
}

function is_row_blank(index) {
    const row = rows.value[index];
    return !row.name1 && !frappe.yrp.attribute_value(row.dia).length;
}

function removeDia(index, val) {
    rows.value[index].dia = frappe.yrp.attribute_value(rows.value[index].dia).filter(d => d !== val);
    make_dirty();
}

function add_row() {
    rows.value.push({
        id: nextId++,
        name1: '',
        dia: [],
        search: '',
    });
    make_dirty();
}

function delete_row(index) {
    rows.value.splice(index, 1);
    make_dirty();
}

function delete_selected() {
    selection.removeSelected(delete_row, () => !is_read_only.value);
}

function make_dirty() {
    if (cur_frm && !cur_frm.is_dirty()) {
        cur_frm.dirty();
    }
}

function load_data(data) {
    if (!data || !Array.isArray(data)) {
        rows.value = [];
        return;
    }
    rows.value = data.map(item => ({
        id: nextId++,
        name1: item.name1 || '',
        dia: frappe.yrp.attribute_value(item.dia) || [],
        search: '',
    }));
}

function get_data() {
    return rows.value.map(row => ({
        name1: row.name1,
        dia: frappe.yrp.attribute_value(row.dia),
    }));
}

defineExpose({
    load_data,
    get_data,
});
</script>

<style scoped>
.row-select {
    width: 32px;
    text-align: center;
    vertical-align: middle;
}
.dia-cell {
    display: flex;
    flex-direction: column;
    gap: 4px;
}
.dia-pills {
    display: flex;
    flex-wrap: wrap;
    gap: 4px;
}
.dia-pill {
    display: inline-flex;
    align-items: center;
    background: #e8f0fe;
    color: #1a73e8;
    border-radius: 12px;
    padding: 2px 8px;
    font-size: 12px;
    white-space: nowrap;
}
.dia-pill-remove {
    margin-left: 4px;
    cursor: pointer;
    font-weight: bold;
    font-size: 14px;
    line-height: 1;
    color: #1a73e8;
}
.dia-pill-remove:hover {
    color: #d93025;
}
.dia-search-wrap {
    position: relative;
}
.dia-search-input {
    width: 100%;
}
.dia-dropdown {
    position: absolute;
    top: 100%;
    left: 0;
    right: 0;
    max-height: 200px;
    overflow-y: auto;
    background: #fff;
    border: 1px solid #d0d0d0;
    border-radius: 4px;
    z-index: 1050;
    box-shadow: 0 2px 8px rgba(0,0,0,0.15);
}
.dia-dropdown-item {
    padding: 6px 10px;
    cursor: pointer;
    font-size: 13px;
}
.dia-dropdown-item:hover {
    background: #e8f0fe;
}
</style>
