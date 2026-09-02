# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
from odoo import api, fields, models


class CommissionAccountGroup(models.Model):
    """A 'Group|COMPANY ID' from the payment gateway's accounts directory.
    One group typically bundles a 'head' technical account plus many real
    merchant sub-accounts (Id Account)."""

    _name = "commission.account.group"
    _description = "Payment Gateway Account Group (Company ID)"
    _order = "code"

    code = fields.Char(
        string="Group / Company ID", required=True, index=True
    )
    name = fields.Char(help="Usually taken from the head account's name.")
    account_ids = fields.One2many(
        comodel_name="commission.account", inverse_name="group_id"
    )
    account_count = fields.Integer(compute="_compute_account_stats")
    unassigned_count = fields.Integer(
        compute="_compute_account_stats",
        help="Accounts in this group that are neither excluded nor "
        "assigned to any commission agreement yet.",
    )

    _sql_constraints = [
        ("code_uniq", "unique(code)", "This group already exists."),
    ]

    @api.depends(
        "account_ids.excluded", "account_ids.agreement_id"
    )
    def _compute_account_stats(self):
        for group in self:
            accounts = group.account_ids
            group.account_count = len(accounts)
            group.unassigned_count = len(
                accounts.filtered(
                    lambda a: not a.excluded and not a.agreement_id
                )
            )

    def action_view_accounts(self):
        self.ensure_one()
        action = self.env["ir.actions.act_window"]._for_xml_id(
            "partner_commission.action_commission_account"
        )
        action["domain"] = [("group_id", "=", self.id)]
        action["context"] = {"default_group_id": self.id}
        return action
