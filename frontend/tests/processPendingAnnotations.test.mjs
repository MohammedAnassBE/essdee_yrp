import test from 'node:test'
import assert from 'node:assert/strict'
import { pendingAnnotation } from '../src/departments/planning/reports/processPendingAnnotations.js'

test('pending supplier cells show age and last submitted DC; zero and totals stay empty', () => {
  const row = { supplier_0: 6400, others: 2, supplier_pending_days: { Unit: 6, Others: null }, supplier_last_dc_dates: { Unit: '2026-10-14' } }
  assert.deepEqual(pendingAnnotation({ fieldname: 'supplier_0', label: 'Unit' }, row), { label: '6 days pending', title: 'Last DC: 14-10-2026' })
  assert.deepEqual(pendingAnnotation({ fieldname: 'others', label: 'Others' }, row), { label: 'No DC', title: 'No submitted DC found' })
  assert.equal(pendingAnnotation({ fieldname: 'received', label: 'Received' }, row), null)
  assert.equal(pendingAnnotation({ fieldname: 'supplier_0', label: 'Unit' }, { ...row, supplier_0: 0 }), null)
  assert.equal(pendingAnnotation({ fieldname: 'supplier_0', label: 'Unit' }, { ...row, is_total_row: true }), null)
  assert.equal(pendingAnnotation({ fieldname: 'supplier_0', label: 'Unit' }, { ...row, supplier_pending_days: { Unit: 1 } }).label, '1 day pending')
})
