# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
import base64
import csv
import datetime
import io

from odoo import fields, models

# Same column order/names as the legacy manual export ("Итог.csv"):
# Стрим;PayMethod;Bank;IdAccount (head);IdAccount;Вознаграждение НКО;НДС;
# Вознаграждение без НДС;Ставка вознаграждения НКО;Бонус ДМЛ;
# Плательщик комиссии;Наименование контрагента;
# Точка исключение (для пл ФЛ);Есть Услуги - исключения
HEADER = [
    "Стрим",
    "PayMethod",
    "Bank",
    "IdAccount (head)",
    "IdAccount",
    "Вознаграждение НКО",
    "НДС",
    "Вознаграждение без НДС",
    "Ставка вознаграждения НКО",
    "Бонус ДМЛ",
    "Плательщик комиссии",
    "Наименование контрагента",
    "Точка исключение (для пл ФЛ)",
    "Есть Услуги - исключения",
]

# The legacy registry's short PayMethod code, keyed by our normalized value.
PAY_METHOD_CODE = {"card": "CCVISAMC", "sbp": "FASTER_PAYMENTS"}
PAYER_TYPE_RU = {"client": "ФЛ", "partner": "УК"}


def _num(value):
    """Format like the legacy file: comma as decimal separator, no
    thousands separator, no forced rounding (matches its own un-rounded
    'Вознаграждение без НДС'/'Ставка' columns)."""
    if value in (None, False):
        return ""
    return str(value).replace(".", ",")


class CommissionTransactionExport(models.TransientModel):
    _name = "commission.transaction.export"
    _description = "Export Partner Commission Results"

    state = fields.Selection(
        selection=[("choose", "Choose filters"), ("done", "Done")],
        default="choose",
    )
    date_from = fields.Date()
    date_to = fields.Date()
    agreement_ids = fields.Many2many(
        comodel_name="commission.agreement",
        string="Agreements",
        help="Leave empty to export every agreement.",
    )

    file = fields.Binary(readonly=True)
    filename = fields.Char(readonly=True)
    row_count = fields.Integer(readonly=True)

    def _domain(self):
        domain = []
        if self.date_from:
            domain.append(
                ("date", ">=", datetime.datetime.combine(
                    self.date_from, datetime.time.min
                ))
            )
        if self.date_to:
            domain.append(
                ("date", "<=", datetime.datetime.combine(
                    self.date_to, datetime.time.max
                ))
            )
        if self.agreement_ids:
            domain.append(("agreement_id", "in", self.agreement_ids.ids))
        return domain

    def action_export(self):
        self.ensure_one()
        transactions = self.env["commission.transaction"].search(
            self._domain(), order="agreement_id, account_id, date"
        )

        # Group's excluded/service account id(s), for the "Точка исключение"
        # column - constant per group, same as in the legacy file.
        excluded_by_group = {}
        for account in self.env["commission.account"].search(
            [("excluded", "=", True), ("group_id", "!=", False)]
        ):
            excluded_by_group.setdefault(account.group_id.id, []).append(
                account.acc_id
            )

        buffer = io.StringIO()
        writer = csv.writer(buffer, delimiter=";")
        writer.writerow(HEADER)
        for txn in transactions:
            agreement = txn.agreement_id
            group = agreement.group_id
            exclusion_points = excluded_by_group.get(group.id, [])
            writer.writerow(
                [
                    group.name or agreement.name or "",
                    PAY_METHOD_CODE.get(txn.pay_method, ""),
                    txn.pay_method_bank or "",
                    group.code or "",
                    txn.id_account or (txn.account_id.acc_id or ""),
                    _num(txn.nko_fee),
                    _num(txn.nko_vat),
                    _num(txn.nko_fee_wo_vat),
                    _num(txn.nko_rate / 100.0),
                    _num(txn.partner_commission),
                    PAYER_TYPE_RU.get(txn.payer_type, ""),
                    txn.company_name or "",
                    ", ".join(exclusion_points),
                    txn.account_id.services_exception or "",
                ]
            )

        content = buffer.getvalue().encode("utf-8")
        self.write(
            {
                "state": "done",
                "file": base64.b64encode(content),
                "filename": "Итог.csv",
                "row_count": len(transactions),
            }
        )
        return {
            "type": "ir.actions.act_window",
            "res_model": self._name,
            "res_id": self.id,
            "view_mode": "form",
            "target": "new",
        }
