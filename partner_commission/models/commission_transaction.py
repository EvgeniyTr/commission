# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
from decimal import ROUND_HALF_UP, Decimal

from odoo import api, fields, models

from .commission_agreement import PAYER_TYPE_SELECTION


def _round2(value):
    """Round to 2 decimals the way Excel's ROUND() does (half away from
    zero on the decimal value), instead of Python's banker's rounding on
    the binary float (e.g. 12.825 -> 12.83, not 12.82). This keeps the
    calculation consistent with the source spreadsheets."""
    return float(Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


class CommissionTransaction(models.Model):
    """One line of the transaction registry imported from the payment
    gateway, enriched with the partner commission calculation for its
    agreement.

    All fields prefixed with nothing and taken "as is" below come straight
    from the registry file uploaded by the user; the computed block is what
    this module adds on top of it.
    """

    _name = "commission.transaction"
    _description = "Partner Commission Transaction"
    _order = "date desc, id desc"

    # ------------------------------------------------------------------
    # Link to the agreement that defines the applicable rates and scheme
    # ------------------------------------------------------------------
    agreement_id = fields.Many2one(
        comodel_name="commission.agreement",
        required=True,
        ondelete="restrict",
        index=True,
    )
    partner_id = fields.Many2one(
        related="agreement_id.partner_id", store=True, string="Partner"
    )
    account_id = fields.Many2one(
        comodel_name="commission.account",
        string="Directory account",
        index=True,
        help="The accounts-directory entry matched by 'Id Account' on "
        "import, if any. Used to resolve the agreement and to apply a "
        "per-account scheme override.",
    )
    payer_type = fields.Selection(
        selection=PAYER_TYPE_SELECTION,
        compute="_compute_amounts",
        store=True,
        help="account_id's scheme override if set, otherwise the "
        "agreement's default scheme.",
    )
    currency_id = fields.Many2one(
        related="agreement_id.currency_id", store=True, readonly=True
    )
    company_id = fields.Many2one(related="agreement_id.company_id", store=True)

    # ------------------------------------------------------------------
    # Raw registry fields (as uploaded)
    # ------------------------------------------------------------------
    ref_no = fields.Char(string="RefNo", required=True, index=True)
    amount = fields.Monetary(string="Amount", required=True)
    currency_name = fields.Char(string="Currency (raw)")
    gw_commission = fields.Monetary(string="Commission")
    gw_commission_vat = fields.Monetary(string="Commission VAT")
    gw_commission_wo_vat = fields.Monetary(string="Commission without VAT")
    cops = fields.Monetary(string="COPS")
    cops_vat = fields.Monetary(string="COPS VAT")
    cops_wo_vat = fields.Monetary(string="COPS without VAT")
    gross_profit_raw = fields.Monetary(string="GrossProfit (raw)")
    bank_ref = fields.Char(string="BankRef (RRN)")
    auth_code = fields.Char(string="Auth Code")
    company_name = fields.Char(string="Company Name")
    id_account = fields.Char(string="Id Account")
    erp_id = fields.Char(string="Unique Accounting ERP identifier")
    date = fields.Datetime(string="Date")
    confirmation_date = fields.Datetime(string="Confirmation Date")
    terminal = fields.Char(string="Terminal")
    status = fields.Char(string="Status", index=True)
    pay_method_raw = fields.Char(string="Pay Method")
    pay_method_bank = fields.Char(string="PayMethod Bank")
    identity_card = fields.Char(string="Identity Card")
    rc = fields.Char(string="RC")
    card_info = fields.Char(string="Card Info")
    order_pinfo = fields.Text(string="order_pinfo")

    # ------------------------------------------------------------------
    # Payment method classification (drives which rate line applies)
    # ------------------------------------------------------------------
    pay_method = fields.Selection(
        selection=[
            ("card", "Card"),
            ("sbp", "SBP (Faster Payments)"),
            ("other", "Other / not recognized"),
        ],
        string="Payment method",
        help="Derived from the raw 'Pay Method' field on import. Can be "
        "corrected manually if the automatic match is wrong.",
    )

    # ------------------------------------------------------------------
    # Calculation block
    # ------------------------------------------------------------------
    nko_rate = fields.Float(
        string="NKO fee rate (%)", compute="_compute_amounts", store=True
    )
    nko_fee = fields.Monetary(
        string="NKO fee", compute="_compute_amounts", store=True
    )
    nko_vat = fields.Monetary(
        string="NKO fee VAT", compute="_compute_amounts", store=True
    )
    nko_fee_wo_vat = fields.Monetary(
        string="NKO fee without VAT", compute="_compute_amounts", store=True
    )
    partner_rate = fields.Float(
        string="Partner commission rate (%)",
        compute="_compute_amounts",
        store=True,
    )
    partner_commission = fields.Monetary(
        string="Partner commission", compute="_compute_amounts", store=True
    )
    client_pays = fields.Monetary(
        string="Client pays", compute="_compute_amounts", store=True
    )
    partner_receives = fields.Monetary(
        string="Partner receives", compute="_compute_amounts", store=True
    )

    _sql_constraints = [
        (
            "agreement_ref_no_uniq",
            "unique(agreement_id, ref_no)",
            "This transaction (RefNo) has already been imported for this "
            "agreement.",
        ),
    ]

    @api.model
    def _pay_method_from_raw(self, raw):
        """Classify the raw 'Pay Method' registry value into card/sbp/other."""
        raw = (raw or "").lower()
        if "fasterpayments" in raw.replace(" ", "").replace("_", ""):
            return "sbp"
        if "visa" in raw or "mastercard" in raw or "eurocard" in raw:
            return "card"
        return "other"

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get("pay_method") and vals.get("pay_method_raw"):
                vals["pay_method"] = self._pay_method_from_raw(
                    vals["pay_method_raw"]
                )
        return super().create(vals_list)

    def _get_rate_line(self):
        """The rate to apply: the account's own override for this payment
        method if one exists, otherwise the agreement's rate line for it."""
        self.ensure_one()
        override = self.account_id.rate_override_ids.filtered(
            lambda line: line.pay_method == self.pay_method
        )[:1]
        if override:
            return override
        return self.agreement_id.rate_line_ids.filtered(
            lambda line: line.pay_method == self.pay_method
        )[:1]

    @api.depends(
        "amount",
        "pay_method",
        "account_id.payer_type_override",
        "account_id.rate_override_ids.nko_rate",
        "account_id.rate_override_ids.partner_rate",
        "agreement_id.payer_type",
        "agreement_id.vat_rate",
        "agreement_id.rate_line_ids.nko_rate",
        "agreement_id.rate_line_ids.partner_rate",
    )
    def _compute_amounts(self):
        for rec in self:
            rate_line = rec._get_rate_line()
            rec.nko_rate = rate_line.nko_rate if rate_line else 0.0
            rec.partner_rate = rate_line.partner_rate if rate_line else 0.0

            rec.nko_fee = _round2(rec.amount * rec.nko_rate / 100.0)
            vat_rate = rec.agreement_id.vat_rate or 0.0
            if rec.pay_method == "sbp":
                vat_rate = 0.0
            nko_vat_raw = (
                rec.nko_fee * vat_rate / (100.0 + vat_rate) if vat_rate else 0.0
            )
            # NKO fee VAT is rounded for display (matches the legacy
            # export), but "NKO fee without VAT" is kept at full precision,
            # computed from the *unrounded* VAT - also matching the legacy
            # export, where that column is never rounded.
            rec.nko_vat = _round2(nko_vat_raw)
            rec.nko_fee_wo_vat = rec.nko_fee - nko_vat_raw

            rec.partner_commission = _round2(
                rec.amount * rec.partner_rate / 100.0
            )

            # A specific account can override the agreement's default
            # scheme, for groups that mix both (e.g. most accounts pay
            # "on top" but a handful are configured "inside").
            rec.payer_type = (
                rec.account_id.payer_type_override
                or rec.agreement_id.payer_type
            )
            if rec.payer_type == "client":
                # Commission on top: the client pays amount + commission,
                # the partner receives the full amount.
                rec.client_pays = rec.amount + rec.partner_commission
                rec.partner_receives = rec.amount
            else:
                # Commission inside: the client pays only the amount,
                # the commission is deducted from the partner's share.
                rec.client_pays = rec.amount
                rec.partner_receives = rec.amount - rec.partner_commission

    def action_recompute(self):
        """Recompute amounts for the current recordset (safe batched commits).

        Can be called from a button on the form/list to recompute selected
        transactions without holding a huge transaction open.
        """
        limit = 200
        ids = list(self.ids)
        for i in range(0, len(ids), limit):
            chunk = self.browse(ids[i : i + limit])
            chunk._compute_amounts()
            # commit between chunks to avoid long-running transactions
            self.env.cr.commit()
        return True

    @api.model
    def action_recompute_all(self):
        """Recompute all commission.transaction records in the database.

        Use with caution; this runs in batches and commits between them.
        Intended to be invoked from a server action/menu item.
        """
        Tx = self.env["commission.transaction"]
        limit = 200
        offset = 0
        while True:
            chunk = Tx.search([], offset=offset, limit=limit)
            if not chunk:
                break
            chunk._compute_amounts()
            self.env.cr.commit()
            offset += limit
        return True
