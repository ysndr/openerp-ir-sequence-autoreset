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

from openerp import fields, models,  _
from openerp.exceptions import UserError
from datetime import datetime
import logging

_logger = logging.getLogger(__name__)


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

    _logger.debug("statement (`{}`) executed".format(statement))


def _select_nextval(cr, seq_name):
    cr.execute("SELECT nextval('%s')" % seq_name)
    return cr.fetchone()


def _update_nogap(self, number_increment):
    number_next = self.number_next
    self._cr.execute("SELECT number_next FROM %s WHERE id=%s FOR UPDATE NOWAIT" % (self._table, self.id))
    self._cr.execute("UPDATE %s SET number_next=number_next+%s WHERE id=%s " % (self._table, number_increment, self.id))  # NoQA
    self.invalidate_cache(['number_next'], [self.id])
    return number_next

def _extract_timestamp(reset_time):
    reset_timestamp = None
    try:
        _logger.debug("reset_timestamp: {}".format(reset_time.split(":", 1)[1]))
        reset_timestamp = datetime.strptime(reset_time.split(":", 1)[1], "%Y-%m-%d %H:%M:%S.%f")
    except ValueError:
        reset_timestamp = datetime.min

    return reset_timestamp


def _exeeds_period(current_time, reset_time):
    current_period, _ = current_time
    reset_period, _ = reset_time

    if current_period != reset_period: return True

    _, current_timestamp = current_time
    _, reset_timestamp = reset_time

    _logger.debug("current_timestamp: {}; reset_timestamp {}".format(current_timestamp, reset_timestamp))

    if (current_timestamp.year > reset_timestamp.year) \
    or (current_timestamp.month > reset_timestamp.month and current_period in dict(_reset_periods[1:])) \
    or (current_timestamp.isocalendar()[1] > reset_timestamp.isocalendar()[1] and current_period in dict(_reset_periods[2:])) \
    or (current_timestamp.day > reset_timestamp.day and current_period in dict(_reset_periods[3:])) \
    or (current_timestamp.hour > reset_timestamp.hour and current_period in dict(_reset_periods[4:])) \
    or (current_timestamp.minute > reset_timestamp.minute and current_period in dict(_reset_periods[5:])) \
    or (current_timestamp.second > reset_timestamp.second and current_period in dict(_reset_periods[6:])): return True

_reset_periods = [('year', 'Every Year'), ('month', 'Every Month'), ('woy', 'Every Week'), ('day', 'Every Day'),
 ('h24', 'Every Hour'), ('min', 'Every Minute'), ('sec', 'Every Second')]

class IrSequence(models.Model):
    _inherit = 'ir.sequence'

    auto_reset = fields.Boolean('Auto Reset', default=False)
    reset_period = fields.Selection(
        _reset_periods,
        'Reset Period', required=True, default='month')
    reset_time = fields.Char('Name', size=64, help="")
    reset_init_number = fields.Integer('Reset Number', default=1, required=True, help="Reset number of this sequence")

    def _next_do(self):
        if self.implementation == 'standard':
            if self.auto_reset:
                current_time = (self.reset_period, datetime.today())
                reset_time = (self.reset_time.split(":")[0], _extract_timestamp(self.reset_time))

                _logger.debug("current time {}; reset_time {}".format(current_time, reset_time))

                if _exeeds_period(current_time, reset_time):
                    _logger.debug("saved time: {}".format(':'.join((current_time[0], str(current_time[1])))))
                    self._cr.execute("UPDATE ir_sequence SET reset_time=%s WHERE id=%s ", (':'.join((current_time[0], str(current_time[1]))), self.id))
                    _alter_sequence(self._cr, "ir_sequence_%03d" % self.id, self.number_increment, self.reset_init_number)  # NoQA
                    self._cr.commit()
            number_next = _select_nextval(self._cr, 'ir_sequence_%03d' % self.id)
        else:
            number_next = _update_nogap(self, self.number_increment)
        return self.get_next_char(number_next)


class IrSequenceDateRange(models.Model):
    _inherit = 'ir.sequence.date_range'

    def _next(self):
        if self.sequence_id.implementation == 'standard':
            if self.sequence_id.auto_reset:

                current_time = (self.sequence_id.reset_period, datetime.today())
                reset_time = (self.sequence_id.reset_time.split(":")[0], _extract_timestamp(self.sequence_id.reset_time))

                _logger.debug("current time {}; reset_time {}".format(current_time, reset_time))

                if _exeeds_period(current_time, reset_time):
                    self._cr.execute("UPDATE ir_sequence SET reset_time=%s WHERE id=%s ", (current_time, self.id))
                    _alter_sequence(self._cr, "ir_sequence_%03d" % self.id, self.number_increment, self.reset_init_number)  # NoQA
                    self._cr.commit()
            number_next = _select_nextval(self._cr, 'ir_sequence_%03d_%03d' % (self.sequence_id.id, self.id))
        else:
            number_next = _update_nogap(self, self.sequence_id.number_increment)
        return self.sequence_id.get_next_char(number_next)
