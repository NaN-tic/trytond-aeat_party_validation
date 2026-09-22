# This file is part of Tryton.  The COPYRIGHT file at the top level of
# this repository contains the full copyright notices and license terms.
from trytond.pool import PoolMeta


class Cron(metaclass=PoolMeta):
    __name__ = 'ir.cron'

    @classmethod
    def __setup__(cls):
        super().__setup__()
        cls.method.selection.append(
            ('party.identifier|check_aeat', 'Check Tax Identifier/Name with AEAT'))
        cls.methods_company_needed.add('party.identifier|check_aeat')
        cls._notifications.add('party.identifier|check_aeat')
