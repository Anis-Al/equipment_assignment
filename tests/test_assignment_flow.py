from odoo.exceptions import UserError
from odoo.tests import tagged

from .common import EquipmentCase


@tagged('post_install', '-at_install')
class TestAssignmentFlow(EquipmentCase):

    def test_fr3_assign_single_snapshots_and_pointers(self):
        item = self.items[0]
        assignment = self.assign(item, self.employee_a, date_start=self.days_ago(3), condition_out='new')
        self.assertEqual(item.state, 'assigned')
        self.assertEqual(item.current_assignment_id, assignment)
        self.assertEqual(item.current_employee_id, self.employee_a)
        self.assertEqual(item.current_department_id, self.department)
        self.assertEqual(item.assigned_since, self.days_ago(3))
        self.assertEqual(assignment.department_id, self.department)
        self.assertEqual(assignment.category_id, self.category)
        self.assertEqual(assignment.company_id, item.company_id)
        self.assertEqual(assignment.state, 'ongoing')
        self.assertEqual(assignment.condition_out, 'new')
        self.assertTrue(assignment.name.startswith(f'ASG/{self.days_ago(3).year}/'))

    def test_fr3_assign_bulk_as_officer(self):
        assignments = self.assign(self.items.with_user(self.officer), self.employee_a)
        self.assertEqual(len(assignments), 5)
        self.assertEqual(set(self.items.mapped('state')), {'assigned'})
        self.assertEqual(assignments.assigned_by_id, self.officer)

    def test_fr3_assign_refuses_non_available_and_names_them(self):
        self.assign(self.items[0], self.employee_a)
        with self.assertRaisesRegex(UserError, self.items[0].reference):
            self.assign(self.items[:2], self.employee_b)
        self.assertEqual(self.items[1].state, 'available')

    def test_fr3_assign_refuses_archived_employee(self):
        self.employee_b.action_archive()
        with self.assertRaises(UserError):
            self.assign(self.items[0], self.employee_b)

    def test_fr4_return_to_available_and_maintenance(self):
        self.assign(self.items[:2], self.employee_a, date_start=self.days_ago(10))
        first = self.items[0].current_assignment_id
        self.items[0]._return_current(self.days_ago(2), 'fair', 'available', 'Scratched')
        self.items[1]._return_current(self.days_ago(1), 'damaged', 'maintenance')
        self.assertEqual(self.items.mapped('state')[:2], ['available', 'maintenance'])
        self.assertFalse(self.items[0].current_employee_id)
        self.assertFalse(self.items[0].current_assignment_id)
        self.assertEqual(self.items[0].last_return_date, self.days_ago(2))
        self.assertEqual(first.date_end, self.days_ago(2))
        self.assertEqual(first.state, 'returned')
        self.assertEqual(first.duration_days, 8)
        self.assertEqual(first.condition_in, 'fair')
        self.assertEqual(first.returned_by_id, self.env.user)

    def test_fr4_return_refuses_date_before_handover(self):
        self.assign(self.items[0], self.employee_a, date_start=self.days_ago(2))
        with self.assertRaises(UserError):
            self.items[0]._return_current(self.days_ago(5))

    def test_fr5_transfer_is_contiguous(self):
        self.assign(self.items[0], self.employee_a, date_start=self.days_ago(10))
        old = self.items[0].current_assignment_id
        self.items[0]._transfer_to({'employee_id': self.employee_b.id, 'date_start': self.days_ago(4)})
        new = self.items[0].current_assignment_id
        self.assertNotEqual(old, new)
        self.assertEqual(old.date_end, new.date_start)
        self.assertEqual(self.items[0].state, 'assigned')
        self.assertEqual(self.items[0].current_employee_id, self.employee_b)
        self.assertEqual(self.items[0].assignment_count, 2)

    def test_a5_backdating_rules(self):
        item = self.items[0]
        with self.assertRaises(UserError):
            self.assign(item, self.employee_a, date_start=self.days_ago(-1))
        self.assign(item, self.employee_a, date_start=self.days_ago(20))
        item._return_current(self.days_ago(5))
        with self.assertRaises(UserError):
            self.assign(item, self.employee_b, date_start=self.days_ago(6))
        self.assign(item, self.employee_b, date_start=self.days_ago(5))
        self.assertEqual(item.state, 'assigned')

    def test_state_actions(self):
        item = self.items[0]
        item.action_send_to_maintenance()
        self.assertEqual(item.state, 'maintenance')
        item.action_set_available()
        item.action_retire()
        self.assertEqual(item.state, 'retired')
        self.assertFalse(item.active)
        item.action_set_available()
        self.assertTrue(item.active)
        self.assign(item, self.employee_a)
        with self.assertRaises(UserError):
            item.action_retire()
        with self.assertRaises(UserError):
            item.action_send_to_maintenance()

    def test_overdue_search_and_compute(self):
        self.assign(self.items[0], self.employee_a, date_start=self.days_ago(10), expected_return_date=self.days_ago(1))
        self.assign(self.items[1], self.employee_a, expected_return_date=self.days_ago(-5))
        self.assign(self.items[2], self.employee_a)
        Item = self.env['equipment.item']
        self.assertEqual(Item.search([('id', 'in', self.items.ids), ('is_overdue', '=', True)]), self.items[0])
        self.assertEqual(Item.search([('id', 'in', self.items.ids), ('is_overdue', '=', False)]), self.items[1:])
        self.assertTrue(self.items[0].is_overdue)
        Assignment = self.env['equipment.assignment']
        self.assertEqual(
            Assignment.search([('equipment_id', 'in', self.items.ids), ('is_overdue', '=', True)]),
            self.items[0].current_assignment_id,
        )

    def test_fr9_employee_count_and_wizards(self):
        wizard = self.env['equipment.assign.wizard'].with_context(
            active_model='equipment.item', active_ids=self.items[:3].ids,
        ).create({'employee_id': self.employee_a.id})
        wizard.action_confirm()
        self.assertEqual(self.employee_a.equipment_item_count, 3)
        self.env['equipment.return.wizard'].with_context(
            active_model='equipment.item', active_ids=self.items[:1].ids,
        ).create({'destination_state': 'maintenance'}).action_confirm()
        self.employee_a.invalidate_recordset(['equipment_item_count'])
        self.assertEqual(self.employee_a.equipment_item_count, 2)
        self.assertEqual(self.items[0].state, 'maintenance')

    def test_fr9_departure_returns_held_items(self):
        self.assign(self.items[:2], self.employee_a, date_start=self.days_ago(3))
        wizard = self.env['hr.departure.wizard'].with_context(active_ids=self.employee_a.ids).create({
            'departure_date': self.today,
            'return_equipment_items': True,
        })
        self.assertEqual(wizard.held_equipment_item_ids, self.items[:2])
        wizard.action_register_departure()
        self.assertEqual(set(self.items[:2].mapped('state')), {'available'})
