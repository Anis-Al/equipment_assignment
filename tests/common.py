from datetime import timedelta

from odoo import fields
from odoo.tests.common import TransactionCase, new_test_user


class EquipmentCase(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.today = fields.Date.context_today(cls.env['equipment.item'])
        cls.company = cls.env.company
        cls.officer = new_test_user(
            cls.env, 'eq_officer', groups='base.group_user,equipment_assignment.group_equipment_officer',
        )
        cls.manager = new_test_user(
            cls.env, 'eq_manager', groups='base.group_user,equipment_assignment.group_equipment_manager',
        )
        cls.department = cls.env['hr.department'].create({'name': 'IT Support'})
        cls.employee_a, cls.employee_b = cls.env['hr.employee'].create([
            {'name': 'Alice Holder', 'department_id': cls.department.id},
            {'name': 'Bob Holder'},
        ])
        cls.category = cls.env['equipment.category'].create({'name': 'Test Laptops'})
        cls.items = cls._create_items(5)

    @classmethod
    def _create_items(cls, count, **vals):
        return cls.env['equipment.item'].create([
            {'name': f'Laptop {index}', 'category_id': cls.category.id, **vals} for index in range(count)
        ])

    def days_ago(self, days):
        return self.today - timedelta(days=days)

    def assign(self, items, employee, **vals):
        return items._assign_to({'employee_id': employee.id, **vals})
