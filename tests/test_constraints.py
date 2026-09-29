from psycopg2.errors import CheckViolation, UniqueViolation

from odoo.exceptions import UserError
from odoo.tests import tagged
from odoo.tools import SQL, mute_logger

from .common import EquipmentCase


@tagged('post_install', '-at_install')
class TestConstraints(EquipmentCase):

    @mute_logger('odoo.sql_db')
    def test_db_check_assigned_iff_holder(self):
        with self.assertRaises(CheckViolation), self.env.cr.savepoint():
            self.env.cr.execute(SQL(
                "UPDATE equipment_item SET state = 'assigned' WHERE id = %s", self.items[0].id,
            ))
        self.assign(self.items[1], self.employee_a)
        with self.assertRaises(CheckViolation), self.env.cr.savepoint():
            self.env.cr.execute(SQL(
                "UPDATE equipment_item SET state = 'available' WHERE id = %s", self.items[1].id,
            ))

    def test_orm_refuses_lifecycle_writes(self):
        with self.assertRaises(UserError):
            self.items[0].write({'state': 'maintenance'})
        with self.assertRaises(UserError):
            self.items[0].action_archive()
        with self.assertRaises(UserError):
            self._create_items(1, state='assigned')

    @mute_logger('odoo.sql_db')
    def test_one_open_assignment_per_item(self):
        self.assign(self.items[0], self.employee_a)
        with self.assertRaises(UniqueViolation), self.env.cr.savepoint():
            self.env['equipment.assignment']._service().create({
                'equipment_id': self.items[0].id,
                'employee_id': self.employee_b.id,
                'company_id': self.company.id,
                'date_start': self.today,
            })

    @mute_logger('odoo.sql_db')
    def test_concurrent_assign_gives_readable_error(self):
        self.env['equipment.assignment']._service().create({
            'equipment_id': self.items[0].id,
            'employee_id': self.employee_b.id,
            'company_id': self.company.id,
            'date_start': self.today,
        })
        with self.assertRaisesRegex(UserError, 'at the same time'):
            self.assign(self.items[0], self.employee_a)

    @mute_logger('odoo.sql_db')
    def test_return_date_not_before_handover(self):
        assignment = self.assign(self.items[0], self.employee_a, date_start=self.days_ago(2))
        with self.assertRaises(CheckViolation), self.env.cr.savepoint():
            assignment._service().write({'date_end': self.days_ago(5)})
            assignment.flush_recordset()

    @mute_logger('odoo.sql_db')
    def test_unique_reference_and_serial_per_company(self):
        other_company = self.env['res.company'].create({'name': 'Equipment Other Co'})
        self._create_items(2)
        self._create_items(1, serial_number='SN-1')
        with self.assertRaises(UniqueViolation), self.env.cr.savepoint():
            self._create_items(1, serial_number='SN-1')
        with self.assertRaises(UniqueViolation), self.env.cr.savepoint():
            self._create_items(1, reference=self.items[0].reference)
        self._create_items(1, serial_number='SN-1', reference=self.items[0].reference, company_id=other_company.id)

    def test_deletion_rules(self):
        fresh = self._create_items(1)
        fresh.unlink()
        self.assign(self.items[0], self.employee_a, date_start=self.days_ago(5))
        with self.assertRaises(UserError):
            self.items[0].unlink()
        with self.assertRaises(UserError):
            self.items[0].current_assignment_id.unlink()
        old = self.items[0].current_assignment_id
        self.items[0]._return_current(self.days_ago(1))
        old.with_user(self.manager).unlink()
        self.assertFalse(old.exists())

    def test_write_guard_on_history(self):
        assignment = self.assign(self.items[0], self.employee_a, date_start=self.days_ago(10))
        with self.assertRaises(UserError):
            self.env['equipment.assignment'].create({
                'equipment_id': self.items[1].id, 'employee_id': self.employee_a.id,
                'company_id': self.company.id, 'date_start': self.today,
            })
        with self.assertRaises(UserError):
            assignment.with_user(self.manager).write({'date_start': self.days_ago(9)})
        self.items[0]._return_current(self.days_ago(2))
        as_officer = assignment.with_user(self.officer)
        as_officer.write({'note_in': 'Returned with charger'})
        with self.assertRaises(UserError):
            as_officer.write({'date_end': self.days_ago(3)})
        with self.assertRaises(UserError):
            as_officer.write({'employee_id': self.employee_b.id})
        as_manager = assignment.with_user(self.manager)
        as_manager.write({'date_end': self.days_ago(3)})
        self.assertEqual(assignment.duration_days, 7)
        with self.assertRaises(UserError):
            as_manager.write({'date_end': False})

    def test_category_recursion(self):
        child = self.env['equipment.category'].create({'name': 'Child', 'parent_id': self.category.id})
        with self.assertRaises(UserError):
            self.category.parent_id = child
