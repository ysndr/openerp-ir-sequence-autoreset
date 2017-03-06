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

from datetime import datetime
from odoo import fields, models,  _
from odoo.exceptions import UserError
import pytz


def _update_nogap(self, number_increment):
    number_next = self.number_next
    self._cr.execute("SELECT number_next FROM %s WHERE id=%s FOR UPDATE NOWAIT" % (self._table, self.id))
    self._cr.execute("UPDATE %s SET number_next=number_next+%s WHERE id=%s " % (self._table, number_increment, self.id))  # NoQA
    self.invalidate_cache(['number_next'], [self.id])
    return number_next


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


class IrSequence(models.Model):
    _inherit = 'ir.sequence'

    auto_reset = fields.Boolean('Auto Reset', default=False)
    reset_period = fields.Selection(
        [('year', 'Every Year'), ('month', 'Every Month'), ('woy', 'Every Week'), ('day', 'Every Day'),
         ('h24', 'Every Hour'), ('min', 'Every Minute'), ('sec', 'Every Second')],
        'Reset Period', required=True, default='month')
    reset_time = fields.Char('Name', size=64, help="")
    reset_init_number = fields.Integer('Reset Number', default=1, required=True, help="Reset number of this sequence")

    def _interpolation_dict(self):
        now = range_date = effective_date = datetime.now(pytz.timezone(self._context.get('tz') or 'UTC'))
        if self._context.get('ir_sequence_date'):
            effective_date = datetime.strptime(self._context.get('ir_sequence_date'), '%Y-%m-%d')
        if self._context.get('ir_sequence_date_range'):
            range_date = datetime.strptime(self._context.get('ir_sequence_date_range'), '%Y-%m-%d')

        sequences = {
            'year': '%Y', 'month': '%m', 'day': '%d', 'y': '%y', 'doy': '%j', 'woy': '%W',
            'weekday': '%w', 'h24': '%H', 'h12': '%I', 'min': '%M', 'sec': '%S'
        }
        res = {}
        for key, format in sequences.iteritems():
            res[key] = effective_date.strftime(format)
            res['range_' + key] = range_date.strftime(format)
            res['current_' + key] = now.strftime(format)

        return res

    def _next(self):
        if not self.ids:
            return False
        force_company = self.env.context.get('force_company')
        if not force_company:
            force_company = self.env.user.company_id.id
        sequences = self.browse(self.ids)
        preferred_sequences = [s for s in sequences if s.company_id and s.company_id.id == force_company]
        seq = preferred_sequences[0] if preferred_sequences else sequences[0]
        if seq.implementation == 'standard':
            current_time = ':'.join([seq.reset_period, self._interpolation_dict().get(seq.reset_period)])
            if seq.auto_reset and current_time != seq.reset_time:
                self._cr.execute("UPDATE ir_sequence SET reset_time=%s WHERE id=%s ", (current_time, seq.id))
                _alter_sequence(self._cr, "ir_sequence_%03d" % seq.id,
                                seq.number_increment, seq.reset_init_number)
                self._cr.commit()

            self._cr.execute("SELECT nextval('ir_sequence_%03d')" % seq.id)
            number_next = self._cr.fetchone()[0]
        else:
            number_next = _update_nogap(self, self.sequence_id.number_increment)

        return seq.get_next_char(number_next)

# vim:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4:
