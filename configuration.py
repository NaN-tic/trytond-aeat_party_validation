# This file is part of Tryton.  The COPYRIGHT file at the top level of
# this repository contains the full copyright notices and license terms.
from trytond.model import ModelSQL, fields
from trytond.pool import PoolMeta
from trytond.modules.company.model import CompanyValueMixin


class Configuration(metaclass=PoolMeta):
    __name__ = 'party.configuration'

    aeat_certificate = fields.MultiValue(fields.Many2One(
        'certificate', 'AEAT Certificate'))


class ConfigurationAEATCertificate(ModelSQL, CompanyValueMixin):
    "Party Configuration AEAT Certificate"
    __name__ = 'party.configuration.aeat_certificate'

    aeat_certificate = fields.Many2One('certificate', 'AEAT Certificate')
