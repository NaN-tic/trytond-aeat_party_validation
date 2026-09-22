# This file is part of Tryton.  The COPYRIGHT file at the top level of
# this repository contains the full copyright notices and license terms.
from trytond.i18n import gettext
from trytond.pool import Pool, PoolMeta
from trytond.modules.account_invoice.exceptions import (
    InvoiceTaxIdentifierError, InvoiceTaxIdentifierWarning)


class Invoice(metaclass=PoolMeta):
    __name__ = 'account.invoice'

    @classmethod
    def _check_tax_identifiers(cls, invoices):
        super()._check_tax_identifiers(invoices)
        Warning = Pool().get('res.user.warning')
        for invoice in invoices:
            for identifier in [
                    invoice.tax_identifier,
                    invoice.party_tax_identifier,
                    ]:
                if (identifier
                        and identifier.aeat_nif
                        and not identifier.aeat_valid):
                    msg = gettext(
                        'aeat_party_validation.'
                        'msg_invoice_tax_identifier_invalid',
                        invoice=invoice.rec_name,
                        identifier=identifier.rec_name)
                    if not identifier.aeat_validated_at:
                        key = Warning.format(
                            'account.invoice aeat valid', [identifier])
                        if Warning.check(key):
                            raise InvoiceTaxIdentifierWarning(key, msg)
                    else:
                        raise InvoiceTaxIdentifierError(msg)
