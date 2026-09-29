#this is a useful template i use usually x)
from odoo.tests import tagged

from .common import EquipmentCase

QUERY_MARGIN = 3


@tagged('post_install', '-at_install')
class TestPerformance(EquipmentCase):

    def count_queries(self, func):
        self.env.flush_all()
        self.env.invalidate_all()
        before = self.env.cr.sql_log_count
        func()
        self.env.flush_all()
        return self.env.cr.sql_log_count - before

    def bulk_cost(self, size):
        items = self._create_items(size).with_user(self.officer)
        assign = self.count_queries(lambda: self.assign(items, self.employee_a, date_start=self.days_ago(5)))
        back = self.count_queries(lambda: items._return_current(self.days_ago(1)))
        return assign, back

    def test_bulk_assign_and_return_query_count_is_constant(self):
        self.bulk_cost(3)
        assign_10, return_10 = self.bulk_cost(10)
        assign_100, return_100 = self.bulk_cost(100)
        self.assertLessEqual(assign_100 - assign_10, QUERY_MARGIN, f'assign: {assign_10} vs {assign_100}')
        self.assertLessEqual(return_100 - return_10, QUERY_MARGIN, f'return: {return_10} vs {return_100}')

    def test_overdue_search_is_pure_sql(self):
        Item = self.env['equipment.item']
        Item._search([('is_overdue', '=', True)])
        before = self.env.cr.sql_log_count
        query = Item._search([('is_overdue', '=', True)])
        self.assertEqual(self.env.cr.sql_log_count, before)
        self.assertIn('expected_return_date', str(query.select()))

    def test_employee_count_is_one_query(self):
        employees = self.env['hr.employee'].create([{'name': f'Emp {index}'} for index in range(10)])
        self.assign(self.items[:3], employees[0])
        self.env.flush_all()
        self.env.invalidate_all()
        with self.assertQueryCount(1):
            employees.mapped('equipment_item_count')
