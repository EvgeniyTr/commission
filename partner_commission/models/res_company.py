# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
from odoo import fields, models


class ResCompany(models.Model):
    _inherit = "res.company"

    partner_commission_nko_vat_rate = fields.Float(
        string="NKO fee VAT rate (%)",
        default=22.0,
        help="VAT rate used to split the processing fee (NKO fee) into its "
        "VAT and VAT-free parts. One value for all commission agreements. "
        "The VAT on the partner's own reward is set per agreement instead "
        "(e.g. 0 for a partner on the simplified tax system).",
    )
