# This file is part of Tryton.  The COPYRIGHT file at the top level of
# this repository contains the full copyright notices and license terms.
from trytond.pool import Pool
from . import configuration, party

def register():
    Pool.register(
        party.Party,
        party.Identifier,
        configuration.Configuration,
        configuration.ConfigurationAEATCertificate,
        party.ValidateNifNameStart,
        party.ValidateNifNameParty,
        module='aeat_party_validation', type_='model')
    Pool.register(
        party.ValidateNifName,
        module='aeat_party_validation', type_='wizard')
