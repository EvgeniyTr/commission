# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
from datetime import timedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError

PAYER_TYPE_SELECTION = [
    ("client", "Commission on top (paid by the client)"),
    ("partner", "Commission inside (paid by the partner)"),
]


class CommissionAgreement(models.Model):
    """A commercial agreement with a partner (management company, developer,
    insurer...) that defines how partner commission is calculated on top of
    an imported transaction registry.

    Each agreement corresponds to what used to be one sheet of the manual
    spreadsheet: one partner, one commission scheme, one or more rates
    depending on the payment method.
    """

    _name = "commission.agreement"
    _description = "Partner Commission Agreement"
    _order = "name"

    name = fields.Char(required=True, help="Free label, e.g. 'ЖКУ 0.45%'.")
    partner_id = fields.Many2one(
        comodel_name="res.partner",
        string="Partner",
        required=True,
        help="Counterparty of the agreement (management company, developer, "
        "insurer...).",
    )
    payer_type = fields.Selection(
        selection=PAYER_TYPE_SELECTION,
        required=True,
        default="partner",
        help="Who effectively bears the commission by default for accounts "
        "assigned to this agreement:\n"
        "* Commission on top: the client pays the transaction amount plus "
        "the commission; the partner receives the full amount.\n"
        "* Commission inside: the client pays only the transaction amount; "
        "the commission is deducted from what the partner receives.\n"
        "A specific account can override this on the accounts directory "
        "when a group mixes both schemes.",
    )
    vat_rate = fields.Float(
        string="VAT rate on NKO fee (%)",
        default=22.0,
        help="VAT rate used to split the processing fee (NKO fee) into its "
        "VAT and VAT-free parts.",
    )
    currency_id = fields.Many2one(
        comodel_name="res.currency",
        default=lambda self: self.env.company.currency_id,
        required=True,
    )
    company_id = fields.Many2one(
        comodel_name="res.company", default=lambda self: self.env.company
    )
    active = fields.Boolean(default=True)
    notes = fields.Text()

    group_id = fields.Many2one(
        comodel_name="commission.account.group",
        string="Account group",
        help="Default 'Group / Company ID' from the accounts directory "
        "this agreement's accounts are picked from. Used by the "
        "'Assign accounts' action and to browse the group's accounts; "
        "an agreement can still hold accounts from other groups if "
        "assigned manually.",
    )
    account_ids = fields.One2many(
        comodel_name="commission.account",
        inverse_name="agreement_id",
        string="Assigned accounts",
    )
    account_count = fields.Integer(compute="_compute_account_count")

    rate_line_ids = fields.One2many(
        comodel_name="commission.agreement.rate",
        inverse_name="agreement_id",
        string="Rates by payment method",
    )
    transaction_ids = fields.One2many(
        comodel_name="commission.transaction",
        inverse_name="agreement_id",
        string="Transactions",
    )
    transaction_count = fields.Integer(compute="_compute_transaction_stats")
    total_amount = fields.Monetary(compute="_compute_transaction_stats")
    total_nko_fee = fields.Monetary(compute="_compute_transaction_stats")
    total_partner_commission = fields.Monetary(compute="_compute_transaction_stats")
    total_amount_last_month = fields.Monetary(
        compute="_compute_transaction_stats",
        string="Total Amount (last month)",
        help="Sum over the previous full calendar month (e.g. all of "
        "August, if today is in September).",
    )
    total_nko_fee_last_month = fields.Monetary(
        compute="_compute_transaction_stats", string="Total NKO Fee (last month)"
    )
    total_partner_commission_last_month = fields.Monetary(
        compute="_compute_transaction_stats",
        string="Total Partner Commission (last month)",
    )

    @api.depends("account_ids")
    def _compute_account_count(self):
        for agreement in self:
            agreement.account_count = len(agreement.account_ids)

    @api.depends(
        "transaction_ids.amount",
        "transaction_ids.nko_fee",
        "transaction_ids.partner_commission",
        "transaction_ids.date",
    )
    def _compute_transaction_stats(self):
        today = fields.Date.context_today(self)
        last_month_end = today.replace(day=1) - timedelta(days=1)
        last_month_start = last_month_end.replace(day=1)
        for agreement in self:
            transactions = agreement.transaction_ids
            agreement.transaction_count = len(transactions)
            agreement.total_amount = sum(transactions.mapped("amount"))
            agreement.total_nko_fee = sum(transactions.mapped("nko_fee"))
            agreement.total_partner_commission = sum(
                transactions.mapped("partner_commission")
            )

            last_month_txns = transactions.filtered(
                lambda t: t.date
                and last_month_start <= t.date.date() <= last_month_end
            )
            agreement.total_amount_last_month = sum(
                last_month_txns.mapped("amount")
            )
            agreement.total_nko_fee_last_month = sum(
                last_month_txns.mapped("nko_fee")
            )
            agreement.total_partner_commission_last_month = sum(
                last_month_txns.mapped("partner_commission")
            )

    def action_view_transactions(self):
        self.ensure_one()
        action = self.env["ir.actions.act_window"]._for_xml_id(
            "partner_commission.action_commission_transaction"
        )
        action["domain"] = [("agreement_id", "=", self.id)]
        action["context"] = {"default_agreement_id": self.id}
        return action

    def action_view_accounts(self):
        """Browse every account of this agreement's group (assigned here,
        assigned elsewhere, unassigned, or excluded) so the user can triage
        them: assign to an agreement, override the scheme, or exclude."""
        self.ensure_one()
        action = self.env["ir.actions.act_window"]._for_xml_id(
            "partner_commission.action_commission_account"
        )
        if self.group_id:
            action["domain"] = [("group_id", "=", self.group_id.id)]
        else:
            action["domain"] = [("agreement_id", "=", self.id)]
        action["context"] = {
            "default_group_id": self.group_id.id,
            "default_agreement_id": self.id,
        }
        return action

    def action_assign_group_accounts(self):
        """Bulk-assign every not-yet-assigned, not-excluded account of
        this agreement's group to this agreement. Accounts already
        assigned elsewhere or marked excluded are left untouched -
        review/fix those individually from 'Accounts'."""
        for agreement in self:
            if not agreement.group_id:
                raise UserError(
                    _("Set an account group on the agreement first.")
                )
            unassigned = agreement.group_id.account_ids.filtered(
                lambda a: not a.excluded and not a.agreement_id
            )
            unassigned.write({"agreement_id": agreement.id})
