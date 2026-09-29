#this is a useful template i use usually x)
from odoo.exceptions import AccessError, UserError
from odoo.tests import tagged, new_test_user

from .common import EquipmentCase


@tagged('post_install', '-at_install')
class TestSecurity(EquipmentCase):

    def test_officer_cannot_delete_retire_or_see_value(self):
        item = self._create_items(1, purchase_value=1000).with_user(self.officer)
        with self.assertRaises(AccessError):
            item.unlink()
        with self.assertRaises(AccessError):
            item.action_retire()
        with self.assertRaises(AccessError):
            item.read(['purchase_value'])
        with self.assertRaises(AccessError):
            self.category.with_user(self.officer).write({'name': 'Renamed'})

    def test_manager_can(self):
        item = self._create_items(1, purchase_value=1000).with_user(self.manager)
        self.assertEqual(item.read(['purchase_value'])[0]['purchase_value'], 1000)
        item.action_retire()
        self.assertEqual(item.state, 'retired')
        self._create_items(1).with_user(self.manager).unlink()

    def test_plain_user_has_no_access(self):
        user = new_test_user(self.env, 'eq_plain', groups='base.group_user')
        with self.assertRaises(AccessError):
            self.items.with_user(user).read(['name'])

    def test_multi_company_isolation(self):
        other_company = self.env['res.company'].create({'name': 'Equipment Isolated Co'})
        other_item = self._create_items(1, company_id=other_company.id)
        Item = self.env['equipment.item'].with_user(self.officer)
        self.assertNotIn(other_item, Item.search([]))
        other_employee = self.env['hr.employee'].create({'name': 'Other', 'company_id': other_company.id})
        with self.assertRaises(UserError):
            self.assign(self.items[0].with_user(self.officer), other_employee)
