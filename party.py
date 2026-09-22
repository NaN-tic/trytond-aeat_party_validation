# This file is part of Tryton.  The COPYRIGHT file at the top level of
# this repository contains the full copyright notices and license terms.
from datetime import datetime

from trytond.pool import Pool, PoolMeta
from trytond.model import ModelView, fields
from trytond.wizard import Wizard, StateView, StateTransition, Button
from trytond.i18n import gettext
from trytond.exceptions import UserError
from trytond.tools import grouped_slice

from requests import Session
from requests.exceptions import RequestException
from zeep.transports import Transport
from zeep.exceptions import Error as ZeepError
from zeep import Client


AEAT_WSDL_URL = (
    'https://www2.agenciatributaria.gob.es/static_files/common/internet/'
    'dep/aplicaciones/es/aeat/burt/jdit/ws/VNifV2.wsdl')

# Keep SOAP requests below the AEAT limit of 20,000 taxpayers.
AEAT_BATCH_SIZE = 1000


def _aeat_values_changed(record, values, names):
    "Check written values against the record, comparing relations by ID."
    for name in names:
        if name in values:
            current = getattr(record, name)
            if values[name] != getattr(current, 'id', current):
                return True
    return False


class Party(metaclass=PoolMeta):
    __name__ = 'party.party'

    @classmethod
    def write(cls, *args):
        Identifier = Pool().get('party.identifier')
        changed = {record for records, values in zip(args[::2], args[1::2])
            for record in records
            if _aeat_values_changed(record, values, ('name',))}
        super().write(*args)
        # AEAT validates the NIF together with the party name. A name change
        # invalidates the previous validation of all the party's identifiers.
        identifiers = [i for record in changed for i in record.identifiers]
        if identifiers:
            Identifier.write(identifiers, {
                'aeat_valid': False,
                'aeat_validated_at': None,
                })

    @classmethod
    def check_aeat(cls, parties):
        pool = Pool()
        Identifier = pool.get('party.identifier')
        Configuration = pool.get('party.configuration')

        certificate = Configuration(1).aeat_certificate
        if not certificate:
            raise UserError(gettext(
                'aeat_party_validation.msg_missing_certificate'))

        with certificate.tmp_ssl_credentials() as (crt, key), Session() as session:
            session.cert = (crt, key)
            transport = Transport(session=session)
            client = Client(wsdl=AEAT_WSDL_URL, transport=transport)

            default = {}
            default['parties'] = []
            identifiers = [identifier for party in parties
                for identifier in party.identifiers
                if identifier.active and identifier.aeat_nif]
            for batch in grouped_slice(identifiers, AEAT_BATCH_SIZE):
                batch = list(batch)
                taxpayers = [{'Nif': i.aeat_nif, 'Nombre': i.party.name}
                    for i in batch]
                try:
                    response = client.service.VNifV2(Contribuyente=taxpayers)
                    if response is None or len(response) != len(batch):
                        raise ZeepError('Unexpected number of AEAT results')
                except (ZeepError, RequestException) as e:
                    raise UserError(
                        gettext('aeat_party_validation.msg_wsdl_unexpected_error',
                        error=str(e)))
                checked_at = datetime.now()
                for identifier, taxpayer, result in zip(
                        batch, taxpayers, response):
                    valid = ((result['Resultado'] or '').strip().casefold()
                        == 'identificado')
                    Identifier.write([identifier], {
                        'aeat_valid': valid,
                        'aeat_validated_at': checked_at if valid else None,
                        })
                    default['parties'].append({
                        'party': identifier.party.id,
                        'orig_name': taxpayer['Nombre'],
                        'orig_nif': taxpayer['Nif'],
                        'aeat_name': result['Nombre'],
                        'aeat_nif': result['Nif'],
                        'result': result['Resultado'],
                        })
        return default


class Identifier(metaclass=PoolMeta):
    __name__ = 'party.identifier'

    aeat_valid = fields.Boolean('AEAT NIF/Name Valid', readonly=True)
    aeat_validated_at = fields.DateTime('AEAT NIF/Name Checked At', readonly=True)

    @property
    def aeat_nif(self):
        # CIF, DNI, NIE and Spanish VAT identifiers can be used as a NIF.
        # EU VAT identifiers are supported only for Spain, without the ES
        # prefix. es_cae identifies an activity/establishment, not a taxpayer.
        if self.type in {'es_cif', 'es_dni', 'es_nie', 'es_vat'}:
            return self.code
        if self.type == 'eu_vat' and self.code.startswith('ES'):
            return self.code[2:]
        return None

    @classmethod
    def write(cls, *args):
        actions = []
        for records, values in zip(args[::2], args[1::2]):
            for record in records:
                changes = values.copy()
                if _aeat_values_changed(record, values,
                        ('code', 'type', 'active', 'party')):
                    changes.update(aeat_valid=False, aeat_validated_at=None)
                actions.extend(([record], changes))
        if actions:
            super().write(*actions)

    @classmethod
    def copy(cls, identifiers, default=None):
        default = dict(default or {}, aeat_valid=False, aeat_validated_at=None)
        return super().copy(identifiers, default=default)


class ValidateNifName(Wizard):
    'Validate NIF/Name'
    __name__ = 'party.validate_nif_name'
    start = StateView(
        'party.validate_nif_name.start',
        'aeat_party_validation.validate_nif_name_start_view_form', [
            Button('Update Names', 'update_name', 'tryton-forward'),
            Button('Close', 'end', 'tryton-ok', True),
            ])
    update_name = StateTransition()

    def default_start(self, fields):
        Party = Pool().get('party.party')
        return Party.check_aeat(self.records)

    def transition_update_name(self):
        pool = Pool()
        Party = pool.get('party.party')
        to_save = []
        identified_results = {
            'identificado', 'no identificado-similar',
            'identificado-baja', 'identificado-revocado',
            }
        for party in self.start.parties:
            if ((party.result or '').strip().casefold()
                    in identified_results
                    and party.aeat_name and party.aeat_name.strip()
                    and party.aeat_name != party.party.name):
                party.party.name = party.aeat_name
                to_save.append(party.party)
        Party.save(to_save)
        if to_save:
            Party.check_aeat(to_save)
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
    # Known AEAT results (casing may vary):
    # Identificado: taxpayer identified with the supplied data.
    # No identificado: taxpayer could not be identified.
    # No identificado-similar: minor name differences for a natural person;
    #     AEAT returns the census name.
    # Identificado-Baja: identified entity that has been deregistered.
    # Identificado-Revocado: identified entity whose NIF has been revoked.
    # No procesado: request exceeds the taxpayer limit.
    # Keep the original text so new AEAT results can also be displayed.
    result = fields.Char('Result', readonly=True)
