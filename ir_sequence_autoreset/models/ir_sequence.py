# -*- coding: utf-8 -*-
##############################################################################
#
#    Auto reset sequence by year,month,day
#    Copyright 2013 wangbuke <wangbuke@gmail.com>
#
#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU Affero General Public License as
#    published by the Free Software Foundation, either version 3 of the
#    License, or (at your option) any later version.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU Affero General Public License for more details.
#
#    You should have received a copy of the GNU Affero General Public License
#    along with this program.  If not, see <http://www.gnu.org/licenses/>.
#
##############################################################################

from odoo import fields, models,  _
from odoo.exceptions import UserError


def _alter_sequence(cr, seq_name, number_increment=None, number_next=None):
    """ Alter a PostreSQL sequence. """
    if number_increment == 0:
        raise UserError(_("Step must not be zero."))
    cr.execute("SELECT relname FROM pg_class WHERE relkind=%s AND relname=%s", ('S', seq_name))
    if not cr.fetchone():
        # sequence is not created yet, we're inside create() so ignore it, will be set later
        return
    statement = "ALTER SEQUENCE %s" % (seq_name, )
    if number_increment is not None:
        statement += " INCREMENT BY %d" % (number_increment, )
    if number_next is not None:
        statement += " RESTART WITH %d" % (number_next, )
    cr.execute(statement)


def _select_nextval(cr, seq_name):
    cr.execute("SELECT nextval('%s')" % seq_name)
    return cr.fetchone()


def _update_nogap(self, number_increment):
    number_next = self.number_next
    self._cr.execute("SELECT number_next FROM %s WHERE id=%s FOR UPDATE NOWAIT" % (self._table, self.id))
    self._cr.execute("UPDATE %s SET number_next=number_next+%s WHERE id=%s " % (self._table, number_increment, self.id))  # NoQA
    self.invalidate_cache(['number_next'], [self.id])
    return number_next


class IrSequence(models.Model):
    _inherit = 'ir.sequence'

    auto_reset = fields.Boolean('Auto Reset', default=False)
    reset_period = fields.Selection(
        [('year', 'Every Year'), ('month', 'Every Month'), ('woy', 'Every Week'), ('day', 'Every Day'),
         ('h24', 'Every Hour'), ('min', 'Every Minute'), ('sec', 'Every Second')],
        'Reset Period', required=True, default='month')
    reset_time = fields.Char('Name', size=64, help="")
    reset_init_number = fields.Integer('Reset Number', default=1, required=True, help="Reset number of this sequence")

    def _next_do(self):
        if self.implementation == 'standard':
            current_time = ':'.join([self.reset_period, self._interpolation_dict().get(self.reset_period)])
            if self.auto_reset and current_time != self.reset_time:
                self._cr.execute("UPDATE ir_sequence SET reset_time=%s WHERE id=%s ", (current_time, self.id))
                _alter_sequence(self._cr, "ir_sequence_%03d" % self.id, self.number_increment, self.reset_init_number)
                self._cr.commit()
            number_next = _select_nextval(self._cr, 'ir_sequence_%03d' % self.id)
        else:
            number_next = _update_nogap(self, self.number_increment)
        return self.get_next_char(number_next)


class IrSequenceDateRange(models.Model):
    _inherit = 'ir.sequence.date_range'

    def _next(self):
        if self.sequence_id.implementation == 'standard':
            current_time = ':'.join([self.reset_period, self._interpolation_dict().get(self.reset_period)])
            if self.auto_reset and current_time != self.reset_time:
                self._cr.execute("UPDATE ir_sequence SET reset_time=%s WHERE id=%s ", (current_time, self.id))
                _alter_sequence(self._cr, "ir_sequence_%03d" % self.id, self.number_increment, self.reset_init_number)
                self._cr.commit()
            number_next = _select_nextval(self._cr, 'ir_sequence_%03d_%03d' % (self.sequence_id.id, self.id))
        else:
            number_next = _update_nogap(self, self.sequence_id.number_increment)
        return self.sequence_id.get_next_char(number_next)
