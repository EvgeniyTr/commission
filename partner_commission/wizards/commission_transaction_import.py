# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
import base64

from odoo import _, fields, models
from odoo.exceptions import UserError

from . import import_utils

# Registry column header (as produced by the payment gateway export) ->
# field on commission.transaction.
HEADER_FIELD_MAP = {
    "RefNo": "ref_no",
    "Amount": "amount",
    "Currency": "currency_name",
    "Commission": "gw_commission",
    "Commission VAT": "gw_commission_vat",
    "Commission without VAT": "gw_commission_wo_vat",
    "COPS": "cops",
    "COPS VAT": "cops_vat",
    "COPS without VAT": "cops_wo_vat",
    "GrossProfit": "gross_profit_raw",
    "BankRef (RRN)": "bank_ref",
    "Auth Code": "auth_code",
    "Company Name": "company_name",
    "Id Account": "id_account",
    "Unique Accounting ERP identifier": "erp_id",
    "Date": "date",
    "Confirmation Date": "confirmation_date",
    "Terminal": "terminal",
    "Status": "status",
    "Pay Method": "pay_method_raw",
    "PayMethod Bank": "pay_method_bank",
    "Identity Card": "identity_card",
    "RC": "rc",
    "Card Info": "card_info",
    "order_pinfo": "order_pinfo",
}

FLOAT_FIELDS = {
    "amount",
    "gw_commission",
    "gw_commission_vat",
    "gw_commission_wo_vat",
    "cops",
    "cops_vat",
    "cops_wo_vat",
    "gross_profit_raw",
}
DATETIME_FIELDS = {"date", "confirmation_date"}


class CommissionTransactionImport(models.TransientModel):
    _name = "commission.transaction.import"
    _description = "Import Partner Commission Transaction Registry"

    state = fields.Selection(
        selection=[("choose", "Choose file"), ("done", "Done")],
        default="choose",
    )
    agreement_id = fields.Many2one(
        comodel_name="commission.agreement",
        string="Fallback agreement",
        help="Used only for rows whose 'Id Account' is not found in the "
        "accounts directory, or found but not yet assigned to any "
        "agreement. Leave empty to reject such rows instead, so you "
        "notice and fix the directory.",
    )
    file = fields.Binary(string="Registry file (xlsx or csv)", required=True)
    filename = fields.Char()

    imported_count = fields.Integer(readonly=True)
    skipped_count = fields.Integer(readonly=True)
    excluded_count = fields.Integer(readonly=True)
    error_count = fields.Integer(readonly=True)
    log = fields.Text(readonly=True)

    def _read_rows(self):
        self.ensure_one()
        if not self.filename:
            raise UserError(_("Please select a file."))
        data = base64.b64decode(self.file)
        try:
            return import_utils.read_rows(
                self.filename, data, set(HEADER_FIELD_MAP)
            )
        except (ImportError, ValueError) as exc:
            raise UserError(str(exc)) from exc

    def _resolve_account_and_agreement(self, id_account, account_by_acc_id):
        """Return (account_or_None, agreement_or_None, note_or_None) for a
        row's raw 'Id Account' value, using the accounts directory first
        and falling back to self.agreement_id if set."""
        account = account_by_acc_id.get(id_account) if id_account else None
        if account:
            if account.excluded:
                return account, None, "excluded"
            if account.agreement_id:
                return account, account.agreement_id, None
            if self.agreement_id:
                return account, self.agreement_id, "unassigned_fallback"
            return account, None, "unassigned"
        # Not found in the directory at all.
        if self.agreement_id:
            return None, self.agreement_id, "not_in_directory_fallback"
        return None, None, "not_in_directory"

    def action_import(self):
        self.ensure_one()
        rows, col_map = self._read_rows()
        missing = sorted(set(HEADER_FIELD_MAP) - set(col_map))
        log_lines = []
        if missing:
            log_lines.append(
                _("Columns not found in the file (ignored): %s")
                % ", ".join(missing)
            )
        if not rows:
            self.write(
                {
                    "state": "done",
                    "imported_count": 0,
                    "skipped_count": 0,
                    "excluded_count": 0,
                    "error_count": 0,
                    "log": "\n".join(
                        log_lines + [_("No data rows found in the file.")]
                    ),
                }
            )
            return self._reopen()

        Account = self.env["commission.account"]
        Transaction = self.env["commission.transaction"]
        account_by_acc_id = {a.acc_id: a for a in Account.search([])}

        existing_ref_nos_by_agreement = {}
        seen_in_file = set()
        to_create = []
        skipped = 0
        excluded = 0
        errors = 0
        scheme_mismatch = 0
        not_in_directory_ids = set()
        unassigned_notes = {}

        for line_no, row in enumerate(rows, start=2):
            ref_no = row.get("RefNo")
            ref_no = str(ref_no).strip() if ref_no not in (None, "") else ""
            if not ref_no:
                errors += 1
                log_lines.append(_("Line %s: missing RefNo, skipped.") % line_no)
                continue

            id_account_raw = row.get("Id Account")
            id_account = (
                str(id_account_raw).strip()
                if id_account_raw not in (None, "")
                else ""
            )
            account, agreement, note = self._resolve_account_and_agreement(
                id_account, account_by_acc_id
            )

            if note == "excluded":
                excluded += 1
                continue
            if note in ("unassigned", "not_in_directory"):
                errors += 1
                not_in_directory_ids.add(id_account or "(empty)")
                unassigned_notes[id_account or "(empty)"] = note
                continue
            if not agreement:
                errors += 1
                log_lines.append(
                    _("Line %s: could not resolve an agreement, skipped.")
                    % line_no
                )
                continue

            dup_key = (agreement.id, ref_no)
            if agreement.id not in existing_ref_nos_by_agreement:
                existing_ref_nos_by_agreement[agreement.id] = set(
                    Transaction.search(
                        [("agreement_id", "=", agreement.id)]
                    ).mapped("ref_no")
                )
            if (
                ref_no in existing_ref_nos_by_agreement[agreement.id]
                or dup_key in seen_in_file
            ):
                skipped += 1
                continue
            seen_in_file.add(dup_key)

            vals = {
                "agreement_id": agreement.id,
                "account_id": account.id if account else False,
            }
            try:
                for header, field_name in HEADER_FIELD_MAP.items():
                    value = row.get(header)
                    if field_name in FLOAT_FIELDS:
                        vals[field_name] = import_utils.to_float(value)
                    elif field_name in DATETIME_FIELDS:
                        dt_value = import_utils.to_datetime(value)
                        vals[field_name] = (
                            fields.Datetime.to_string(dt_value)
                            if dt_value
                            else False
                        )
                    else:
                        vals[field_name] = (
                            str(value).strip() if value not in (None, "") else False
                        )
            except Exception as exc:  # noqa: BLE001
                errors += 1
                log_lines.append(_("Line %s: %s") % (line_no, exc))
                continue

            # Plausibility check, not a decision: in the observed
            # registries a non-zero 'Commission' means the gateway
            # deducted the fee from the settlement (scheme: commission
            # inside), a zero 'Commission' means it didn't (scheme:
            # commission on top).
            expected_payer_type = (
                account.payer_type_override if account else None
            ) or agreement.payer_type
            is_nonzero_commission = abs(vals.get("gw_commission") or 0.0) > 0.01
            expects_nonzero = expected_payer_type == "partner"
            if is_nonzero_commission != expects_nonzero:
                scheme_mismatch += 1

            to_create.append(vals)

        if to_create:
            Transaction.create(to_create)

        if not_in_directory_ids:
            sample = sorted(not_in_directory_ids)[:20]
            more = len(not_in_directory_ids) - len(sample)
            reasons = {"not_in_directory", "unassigned"}
            if unassigned_notes and set(unassigned_notes.values()) & reasons:
                log_lines.append(
                    _(
                        "%(n)s row(s) skipped: their 'Id Account' is either "
                        "missing from the accounts directory, or present "
                        "but not assigned to any agreement yet. Import/"
                        "update the directory and assign these accounts, "
                        "or set a 'Fallback agreement' on this wizard and "
                        "re-import. Affected Id Account(s): %(sample)s%(more)s"
                    )
                    % {
                        "n": len(not_in_directory_ids),
                        "sample": ", ".join(sample),
                        "more": _(" and %s more") % more if more > 0 else "",
                    }
                )

        log_lines.append(
            _(
                "Imported: %(imported)s, skipped duplicates: %(skipped)s, "
                "excluded accounts: %(excluded)s, errors: %(errors)s."
            )
            % {
                "imported": len(to_create),
                "skipped": skipped,
                "excluded": excluded,
                "errors": errors,
            }
        )
        if scheme_mismatch:
            log_lines.append(
                _(
                    "⚠ Warning: %(n)s of %(total)s imported rows look "
                    "inconsistent with their resolved scheme. A non-zero "
                    "'Commission' in the registry usually means commission "
                    "inside (partner pays), a zero 'Commission' means "
                    "commission on top (client pays). Please double-check "
                    "the 'Payer type' on the relevant agreement(s) or the "
                    "'Scheme override' on the relevant account(s)."
                )
                % {"n": scheme_mismatch, "total": len(to_create)}
            )
        self.write(
            {
                "state": "done",
                "imported_count": len(to_create),
                "skipped_count": skipped,
                "excluded_count": excluded,
                "error_count": errors,
                "log": "\n".join(log_lines),
            }
        )
        return self._reopen()

    def _reopen(self):
        return {
            "type": "ir.actions.act_window",
            "res_model": self._name,
            "res_id": self.id,
            "view_mode": "form",
            "target": "new",
        }

    def action_view_transactions(self):
        self.ensure_one()
        action = self.env["ir.actions.act_window"]._for_xml_id(
            "partner_commission.action_commission_transaction"
        )
        if self.agreement_id:
            action["domain"] = [("agreement_id", "=", self.agreement_id.id)]
        return action
