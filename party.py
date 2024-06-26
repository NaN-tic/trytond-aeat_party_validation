# This file is part of Tryton.  The COPYRIGHT file at the top level of
# this repository contains the full copyright notices and license terms.
from trytond.pool import Pool
from trytond.model import ModelView, fields
from trytond.wizard import Wizard, StateView, StateTransition, Button
from trytond.config import config
from trytond.i18n import gettext
from trytond.exceptions import UserError

from requests import Session
from zeep.transports import Transport
from zeep.exceptions import Error as ZeepError
from zeep import Client


class ValidateNifName(Wizard):
    'Validate NIF/Name'
    __name__ = 'party.validate_nif_name'
    start = StateView(
        'party.validate_nif_name.start',
        'aeat_party_validation.validate_nif_name_start_view_form', [
            Button('Update Similar', 'update_similar', 'tryton-forward'),
            Button('Close', 'end', 'tryton-ok', True),
            ])
    update_similar = StateTransition()

    def default_start(self, fields):

        CERT = (
            config.get('account_es_sii', 'certificate'),
            config.get('account_es_sii', 'privatekey'))

        wsdl = 'https://www2.agenciatributaria.gob.es/static_files/common/internet/dep/aplicaciones/es/aeat/burt/jdit/ws/VNifV2.wsdl'
        session = Session()
        session.cert = CERT
        transport = Transport(session=session)
        client = Client(wsdl=wsdl, transport=transport)

        default = {}
        default['parties']= []
        for party in self.records:
            if not party.tax_identifier:
                continue
            nif = party.tax_identifier.code
            name = party.name
            try:
                response = client.service.VNifV2({'Nif':nif, 'Nombre':name})
                print(response)
            except ZeepError as e:
                raise UserError(
                    gettext('aeat_party_validation.msg_wsdl_unexpected_error',
                    error=e.message))
            default['parties'].append({
                'party': party.id,
                'orig_name': name,
                'orig_nif': nif,
                'aeat_name': response[0]['Nombre'],
                'aeat_nif': response[0]['Nif'],
                'result': response[0]['Resultado'],
                })
        return default

    def transition_update_similar(self):
        pool = Pool()
        Party = pool.get('party.party')
        to_save = []
        for party in self.start.parties:
            if party.result == 'No identificado-similar':
                party.party.name = party.aeat_name
                to_save.append(party.party)
        Party.save(to_save)
        return 'end'


class ValidateNifNameStart(ModelView):
    "Start Validate NIF/Name"
    __name__ = 'party.validate_nif_name.start'

    parties = fields.One2Many('party.validate_nif_name.start.party', None,
        'Parties')

class ValidateNifNameParty(ModelView):
    "Start Validate NIF/Name Party"
    __name__ = "party.validate_nif_name.start.party"

    party = fields.Many2One('party.party', 'Party', readonly=True)
    orig_name = fields.Char('Original Name', readonly=True)
    orig_nif = fields.Char('Original NIF', readonly=True)
    aeat_name = fields.Char('AEAT Name', readonly=True)
    aeat_nif = fields.Char('AEAT NIF', readonly=True)
    result = fields.Selection([
            ('Identificado', 'Identified'),
            ('No identificado', 'Unidentified'),
            ('No identificado-similar', 'Unidentified-Similar'),
            ('Identificado-Baja', 'Identified-Removed'),
            ('Identificado-Revocado', 'Identified-Revoked'),
            ('No procesado', 'Not Processed'),
            ], 'Result', readonly=True)
