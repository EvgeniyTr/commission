# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
from odoo import api, fields, models
from odoo.exceptions import ValidationError


class CommissionAgreementRate(models.Model):
    """Rate of NKO processing fee and partner commission for one payment
    method within an agreement (e.g. a different rate for cards and for
    SBP/Faster Payments)."""

    _name = "commission.agreement.rate"
    _description = "Partner Commission Agreement Rate"
    _order = "agreement_id, pay_method"

    agreement_id = fields.Many2one(
        comodel_name="commission.agreement",
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
        help="Processing fee rate charged by the settlement organization "
        "(NKO), as a percentage of the transaction amount.",
    )
    partner_rate = fields.Float(
        string="Partner commission rate (%)",
        required=True,
        help="Partner commission rate, as a percentage of the transaction "
        "amount.",
    )

    _sql_constraints = [
        (
            "agreement_pay_method_uniq",
            "unique(agreement_id, pay_method)",
            "There is already a rate defined for this payment method on "
            "this agreement.",
        ),
    ]

    @api.constrains("nko_rate", "partner_rate")
    def _check_rates(self):
        for rate in self:
            if rate.nko_rate < 0 or rate.partner_rate < 0:
                raise ValidationError(
                    self.env._("Rates cannot be negative.")
                )
