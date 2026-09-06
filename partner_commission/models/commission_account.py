# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
from odoo import api, fields, models

from .commission_agreement import PAYER_TYPE_SELECTION


class CommissionAccount(models.Model):
    """One 'Id Account' from the payment gateway's accounts directory.

    Fields coming from the directory file (name, merch_code, inn, ogrn,
    enabled, group_id) are refreshed on every re-import; excluded,
    payer_type_override and agreement_id are set by the user in Odoo and
    are never touched by the directory import.
    """

    _name = "commission.account"
    _description = "Payment Gateway Account (Id Account)"
    _order = "acc_id"

    acc_id = fields.Char(string="Id Account", required=True, index=True)
    group_id = fields.Many2one(
        comodel_name="commission.account.group", string="Group / Company ID"
    )
    name = fields.Char(string="Merchant name")
    merch_code = fields.Char(string="Merchant code")
    inn = fields.Char(string="INN")
    ogrn = fields.Char(string="OGRN")
    enabled = fields.Boolean(help="'Enabled' flag from the directory.")
    is_head = fields.Boolean(
        compute="_compute_is_head",
        store=True,
        help="This account's id is the group's own id: usually the "
        "platform's own technical/service account for the group, not a "
        "real merchant.",
    )

    excluded = fields.Boolean(
        string="Excluded from calculation",
        help="Transactions on this account are imported for the record "
        "but never counted towards any agreement's commission.",
    )
    payer_type_override = fields.Selection(
        selection=PAYER_TYPE_SELECTION,
        string="Scheme override",
        help="Leave empty to use the agreement's default scheme. Set this "
        "only when a single account group mixes both schemes.",
    )
    agreement_id = fields.Many2one(
        comodel_name="commission.agreement",
        string="Agreement",
        ondelete="set null",
        help="Commission agreement this account's transactions are booked "
        "against. Leave empty until you know which agreement it belongs "
        "to - unassigned accounts are rejected on registry import.",
    )
    effective_payer_type = fields.Selection(
        selection=PAYER_TYPE_SELECTION,
        string="Applied scheme",
        compute="_compute_effective_payer_type",
        help="The scheme actually used to compute commission on this "
        "account's transactions: the override above if set, otherwise "
        "the agreement's default. Empty if not assigned to any agreement.",
    )
    services_exception = fields.Char(
        string="Services exception",
        help="Free-text note for a services-based exception on this "
        "account (e.g. a contractual MCC exclusion). Informational only "
        "- not used in the commission calculation - but carried through "
        "to the transaction export as-is.",
    )
    rate_override_ids = fields.One2many(
        comodel_name="commission.account.rate",
        inverse_name="account_id",
        string="Rate overrides",
        help="Optional per-account rate, by payment method. If there is "
        "no override row for a payment method, the agreement's own rate "
        "for it applies.",
    )

    _sql_constraints = [
        ("acc_id_uniq", "unique(acc_id)", "This Id Account already exists."),
    ]

    @api.depends("acc_id", "group_id.code")
    def _compute_is_head(self):
        for account in self:
            account.is_head = bool(
                account.group_id and account.acc_id == account.group_id.code
            )

    @api.depends("payer_type_override", "agreement_id.payer_type")
    def _compute_effective_payer_type(self):
        for account in self:
            account.effective_payer_type = (
                account.payer_type_override or account.agreement_id.payer_type
            )
