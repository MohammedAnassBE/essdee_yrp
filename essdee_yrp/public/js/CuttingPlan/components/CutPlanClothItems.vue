<template>
    <div ref="root">
        <div v-if="type">
            <h4>{{ type == 'cloth' ? 'Cloth Details' : 'Accessory Details' }}</h4>
        </div>
        <table v-if='docstatus !== 0' class="table table-sm table-bordered">
            <tr>
                <th>S.No.</th>
                <th v-if='type=="accessory"'>Accessory</th>
                <th>Cloth</th>
                <th>Cloth Type</th>
                <th>Colour</th>
                <th>Dia</th>
                <th>Required Weight</th>
                <th v-if='type=="cloth"'>Received Weight</th>
                <th>Used Weight</th>
                <th v-if='type=="cloth"'>Balance Weight</th>
            </tr>
            <tr v-for="(i, item1_index) in items" :key="item1_index">
                <td>{{item1_index + 1}}</td>
                <td v-if="type=='accessory'">{{i.accessory}}</td>
                <td>{{ i.cloth_item_variant }}</td>
                <td>{{ i.cloth_type }}</td>
                <td>{{ i.colour }}</td>
                <td>{{ i.dia }}</td>
                <td>{{ i.required_weight }}</td>
                <td v-if="type=='cloth'">{{ i.weight }}</td>
                <td>{{i.used_weight}}</td>
                <td v-if='type=="cloth"'>{{i.balance_weight}}</td>
            </tr>
            <tr v-if="!items || items.length === 0">
                <td :colspan="type == 'cloth' ? 9 : 8" class="text-center text-muted">
                    {{ type == 'cloth'
                        ? 'No cloth requirements generated. Use Generate or Fetch Received Cloth.'
                        : 'No accessory cloth requirements.' }}
                </td>
            </tr>
        </table>
        <table v-else class="table table-sm table-bordered">
            <tr>
                <th>S.No.</th>
                <th v-if='type=="accessory"'>Accessory</th>
                <th>Cloth</th>
                <th>Cloth Type</th>
                <th>Colour</th>
                <th>Dia</th>
                <th>Required Weight</th>
                <th v-if='type=="cloth"'>Received Weight</th>
                <th>Used Weight</th>
                <th v-if='type=="cloth"'>Balance Weight</th>
            </tr>
            <tr v-for="(i, item1_index) in items" :key="item1_index">
                <td>{{item1_index + 1}}</td>
                <td v-if="type=='accessory'">{{i.accessory}}</td>
                <td>{{ i.item }}</td>
                <td>{{ i.cloth_type }}</td>
                <td>{{ i.colour }}</td>
                <td>{{ i.dia }}</td>
                <td>{{ i.required_weight }}</td>
                <td v-if="type=='cloth'">
                    <form>
                        <input class="form-control" type="number" v-model.number="i.weight" min="0" step="0.001" @blur="update_doc()"/>
                    </form>
                </td>
                <td>{{i.used_weight}}</td>
                <td v-if='type=="cloth"'>{{i.balance_weight}}</td>
            </tr>
            <tr v-if="!items || items.length === 0">
                <td :colspan="type == 'cloth' ? 9 : 8" class="text-center text-muted">
                    No requirements generated yet.
                </td>
            </tr>
        </table>
    </div>
</template>

<script setup>
import {ref} from 'vue';

let items = ref(null)
let docstatus = ref(0)
let type = ref(null)
function load_data(item,types){
    docstatus.value = cur_frm.doc.docstatus
    items.value = item;
    type.value = types
}
function update_doc(){
    cur_frm.dirty()
}
function get_items(){
    return items.value
}

defineExpose({
    load_data,
    get_items,
})
</script>
