# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
from odoo import api, fields, models
from odoo.exceptions import ValidationError


class CommissionAccountRate(models.Model):
    """Per-account override of the NKO fee / partner commission rate for
    one payment method. If an account has no override row for a given
    payment method, the agreement's own rate line applies as usual.

    Mirrors commission.agreement.rate on purpose: a row's mere existence
    means "overridden for this payment method", so there is no ambiguity
    between "not set" and "explicitly set to 0%"."""

    _name = "commission.account.rate"
    _description = "Partner Commission Account Rate Override"
    _order = "account_id, pay_method"

    account_id = fields.Many2one(
        comodel_name="commission.account",
        required=True,
        ondelete="cascade",
    )
    pay_method = fields.Selection(
        selection=[("card", "Card"), ("sbp", "SBP (Faster Payments)")],
        required=True,
    )
    nko_rate = fields.Float(
        string="NKO fee rate (%)",
        required=True,
        help="Overrides the agreement's NKO fee rate for this account and "
        "payment method.",
    )
    partner_rate = fields.Float(
        string="Partner commission rate (%)",
        required=True,
        help="Overrides the agreement's partner commission rate for this "
        "account and payment method.",
    )

    _sql_constraints = [
        (
            "account_pay_method_uniq",
            "unique(account_id, pay_method)",
            "There is already a rate override for this payment method on "
            "this account.",
        ),
    ]

    @api.constrains("nko_rate", "partner_rate")
    def _check_rates(self):
        for rate in self:
            if rate.nko_rate < 0 or rate.partner_rate < 0:
                raise ValidationError(self.env._("Rates cannot be negative."))
