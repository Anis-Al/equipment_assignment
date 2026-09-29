from odoo import api, fields, models
from odoo.exceptions import ValidationError


class EquipmentCategory(models.Model):
    _name = 'equipment.category'
    _description = 'Equipment Category'
    _parent_store = True
    _rec_names_search = ['name', 'complete_name']
    _order = 'sequence, complete_name'

    name = fields.Char(required=True, translate=True)
    complete_name = fields.Char(compute='_compute_complete_name', recursive=True, store=True)
    parent_id = fields.Many2one('equipment.category', string='Parent Category', index=True, ondelete='restrict')
    parent_path = fields.Char(index=True)
    sequence = fields.Integer(default=10)
    color = fields.Integer()
    active = fields.Boolean(default=True)
    item_count = fields.Integer(string='Equipment', compute='_compute_item_count')

    @api.depends('name', 'parent_id.complete_name')
    def _compute_complete_name(self):
        for category in self:
            if category.parent_id:
                category.complete_name = f'{category.parent_id.complete_name} / {category.name}'
            else:
                category.complete_name = category.name

    @api.depends('name', 'parent_id.display_name')
    @api.depends_context('lang')
    def _compute_display_name(self):
        for category in self:
            category.display_name = (
                f'{category.parent_id.display_name} / {category.name}' if category.parent_id else category.name
            )

    def _compute_item_count(self):
        groups = self.env['equipment.item']._read_group(
            [('category_id', 'child_of', self.ids)], ['category_id'], ['__count'],
        )
        for category in self:
            category.item_count = sum(
                count for sub, count in groups if sub.parent_path.startswith(category.parent_path or '/')
            )

    @api.constrains('parent_id')
    def _check_parent_id(self):
        if self._has_cycle():
            raise ValidationError(self.env._('You cannot create recursive categories.'))

    def action_view_items(self):
        self.ensure_one()
        action = self.env['ir.actions.act_window']._for_xml_id('equipment_assignment.equipment_item_action')
        action['domain'] = [('category_id', 'child_of', self.id)]
        action['context'] = {'default_category_id': self.id}
        return action
