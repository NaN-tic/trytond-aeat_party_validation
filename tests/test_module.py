# This file is part aeat_party_validation module for Tryton.
# The COPYRIGHT file at the top level of this repository contains
# the full copyright notices and license terms.
from contextlib import nullcontext
from datetime import datetime
from unittest.mock import call, patch

from trytond.pool import Pool
from trytond.tests.test_tryton import ModuleTestCase, with_transaction
from trytond.modules.aeat_party_validation import party as party_module


class AeatPartyValidationTestCase(ModuleTestCase):
    'Test Aeat Party Validation module'
    module = 'aeat_party_validation'

    @with_transaction()
    def test_check_aeat_batches(self):
        pool = Pool()
        Party = pool.get('party.party')
        Certificate = pool.get('certificate')
        Configuration = pool.get('party.configuration')
        certificate, = Certificate.create([{'name': 'AEAT test'}])
        configuration = Configuration(1)
        configuration.aeat_certificate = certificate
        configuration.save()
        parties = Party.create([{
                    'name': name,
                    'identifiers': [('create', [{
                                    'type': 'es_vat', 'code': nif}])],
                    } for name, nif in [
                        ('First', '12345678Z'),
                        ('Second', '87654321X'),
                        ('Third', '12345678Z')]])
        taxpayers = [{'Nif': p.identifiers[0].aeat_nif, 'Nombre': p.name}
            for p in parties]
        results = [dict(t, Resultado=result) for t, result in zip(
                taxpayers, ['IDENTIFICADO', 'NO IDENTIFICADO', 'IDENTIFICADO'])]
        Identifier = pool.get('party.identifier')
        Identifier.write([parties[1].identifiers[0]], {
                'aeat_valid': True,
                'aeat_validated_at': datetime(2026, 1, 1),
                })

        with patch.object(party_module, 'AEAT_BATCH_SIZE', 2), \
                patch.object(Certificate, 'tmp_ssl_credentials',
                    return_value=nullcontext(('test.crt', 'test.key'))), \
                patch.object(party_module, 'Session'), \
                patch.object(party_module, 'Client') as client:
            service = client.return_value.service.VNifV2
            service.side_effect = [results[:2], results[2:]]
            result = Party.check_aeat(parties)
            self.assertEqual(service.call_args_list, [
                    call(Contribuyente=taxpayers[:2]),
                    call(Contribuyente=taxpayers[2:]),
                    ])

        self.assertEqual([p.identifiers[0].aeat_valid for p in parties],
            [True, False, True])
        for record in parties:
            self.assertIsNotNone(record.identifiers[0].aeat_validated_at)
        self.assertEqual([r['party'] for r in result['parties']],
            [p.id for p in parties])
        self.assertEqual([r['result'] for r in result['parties']],
            [r['Resultado'] for r in results])

    @with_transaction()
    def test_party_identifier(self):
        pool = Pool()
        Party = pool.get('party.party')
        Identifier = pool.get('party.identifier')

        party, = Party.create([{'name': 'Example'}])
        identifier, = Identifier.create([{
                    'party': party.id,
                    'type': 'es_vat',
                    'code': '12345678Z',
                    }])
        self.assertEqual(party.identifiers, (identifier,))
        self.assertEqual(identifier.aeat_nif, '12345678Z')
        self.assertFalse(identifier.aeat_valid)
        self.assertIsNone(identifier.aeat_validated_at)

        # Set the validation result directly: no AEAT call or certificate.
        validated = {
            'aeat_valid': True,
            'aeat_validated_at': datetime(2026, 1, 1),
            }
        Identifier.write([identifier], validated)
        Party.write([party], {'name': 'Example'})
        self.assertTrue(identifier.aeat_valid)
        self.assertEqual(identifier.aeat_validated_at,
            validated['aeat_validated_at'])

        Identifier.write([identifier], {
                'party': party.id,
                'code': identifier.code,
                'type': identifier.type,
                'active': identifier.active,
                })
        self.assertTrue(identifier.aeat_valid)
        self.assertEqual(identifier.aeat_validated_at,
            validated['aeat_validated_at'])

        Party.write([party], {'name': 'Updated example'})
        self.assertFalse(identifier.aeat_valid)
        self.assertIsNone(identifier.aeat_validated_at)

        Identifier.write([identifier], validated)
        Identifier.write([identifier], {'code': '87654321X'})
        self.assertFalse(identifier.aeat_valid)
        self.assertIsNone(identifier.aeat_validated_at)

        Identifier.write([identifier], validated)
        copied_party, = Party.copy([party])
        copied_identifier, = copied_party.identifiers
        self.assertNotEqual(copied_identifier, identifier)
        self.assertEqual(copied_identifier.code, identifier.code)
        self.assertFalse(copied_identifier.aeat_valid)
        self.assertIsNone(copied_identifier.aeat_validated_at)
        self.assertTrue(identifier.aeat_valid)
        self.assertEqual(identifier.aeat_validated_at,
            validated['aeat_validated_at'])

        Identifier.write([identifier], {'party': copied_party.id})
        self.assertFalse(identifier.aeat_valid)
        self.assertIsNone(identifier.aeat_validated_at)


del ModuleTestCase
