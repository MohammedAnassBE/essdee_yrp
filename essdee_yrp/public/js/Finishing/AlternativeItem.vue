<template>
    <div>
        <div class="form-group" style="max-width: 220px;" v-if="items && Object.keys(items).length > 0">
            <label class="control-label">Pieces per Box</label>
            <input type="number" min="0" class="form-control" :value="pieces_per_box ?? ''" @input="set_pieces_per_box($event.target.value)"/>
        </div>
        <table class="table table-sm table-sm-bordered bordered-table" v-if="items && Object.keys(items).length > 0">
            <thead class="dark-border">
                <tr>
                    <th style="width:20px;">S.No</th>
                    <th style="width:20px;">Colour</th>
                    <th style="width:20px;" v-if="items.is_set_item">{{ items['set_attr'] }}</th>
                    <th style="width:150px;">Type</th>
                    <th v-for="size in items.primary_values" :key="size">{{ size }}</th>
                    <th>Total</th>
                </tr>
            </thead>
            <tbody class="dark-border">
                <tr>
                    <td :colspan="items.is_set_item ? 3 : 2"></td>
                    <td><strong>Box Qty</strong></td>
                    <td v-for="size in items.primary_values" :key="size">
                        <input type="number" min="0" class="form-control" :value="box_qty[size] ?? ''" @input="set_box_qty(size, $event.target.value)"/>
                    </td>
                    <td></td>
                </tr>
            </tbody>
            <tbody class="dark-border" v-for="(colour, idx) in Object.keys(items['data']['data'])" :key="colour">
                <tr>
                    <td :rowspan="4">
                        {{ idx + 1 }}
                        <input type="checkbox" v-model="items['data']['data'][colour]['check_value']"/>
                    </td>
                    <td :rowspan="4">{{ colour.split("@")[0] }}</td>
                    <td :rowspan="4" v-if="items.is_set_item">{{ items['data']['data'][colour]['part'] }}</td>
                    <td> Qty </td>
                    <td v-for="size in items.primary_values" :key="size">
                        {{
                            items['data']['data'][colour]["values"][size]['balance'] ?? 0
                        }}
                    </td>
                    <td><strong>{{ items['data']['data'][colour]['colour_total']['balance'] ?? 0 }}</strong></td>
                </tr>
                <tr>
                    <td>Conversion Qty</td>
                    <td v-for="size in items.primary_values" :key="size">
                        <div v-if="items['data']['data'][colour]['check_value']">
                            <input type="number" v-model="items['data']['data'][colour]['values'][size]['conversion_qty']"
                            class="form-control"/>
                        </div>
                        <div v-else>
                            0
                        </div>
                    </td>
                    <td></td>
                </tr>
            </tbody>
        </table>
    </div>
</template>

<script setup>

import { ref } from 'vue';
import { applyBoxQuantity } from '../../../../frontend/src/departments/finishing/plan/finishingBoxQuantities.js';

let items = ref({})
let pieces_per_box = ref(null)
let box_qty = ref({})

function apply_box(size) {
    const rows = items.value['data']['data']
    const entry = Object.fromEntries(Object.entries(rows).map(([colour, row]) => [colour, {
        checked: row['check_value'],
        sizes: Object.fromEntries(Object.entries(row['values']).map(([key, value]) => [key, value['conversion_qty']])),
    }]))
    const ratio = items.value['box_packing']?.['colour_ratio']
    if (!applyBoxQuantity({ payload: items.value, entry, size, boxes: box_qty.value[size], piecesPerBox: pieces_per_box.value, ratio, checkable: true })) return
    Object.entries(entry).forEach(([colour, row]) => {
        if (size in row.sizes) rows[colour]['values'][size]['conversion_qty'] = row.sizes[size]
    })
}

function set_box_qty(size, value) {
    box_qty.value[size] = value
    apply_box(size)
}

function set_pieces_per_box(value) {
    pieces_per_box.value = value
    Object.keys(box_qty.value).forEach(apply_box)
}

function load_data(data) {
    Object.keys(data['data']['data']).forEach((colour)=> {
        Object.keys(data['data']['data'][colour]['values']).forEach((size)=> {
            data['data']['data'][colour]['values'][size]['conversion_qty'] = 0
        })
    })
    items.value = data
    pieces_per_box.value = Number(data['box_packing']?.['pieces_per_box']) || null
    box_qty.value = {}
}

function get_items(){
    return items.value
}

defineExpose({
    load_data,
    get_items
})
</script>

<style scoped>
.bordered-table {
    width: 100%;
    border: 1px solid #ccc;
    border-collapse: collapse;
}

.bordered-table th,
.bordered-table td {
    border: 1px solid #ccc;
    padding: 6px 8px;
    text-align: center;
}

.bordered-table thead {
    background-color: #f8f9fa;
    font-weight: bold;
}

.dark-border{
    border: 2px solid black;
}
</style>
