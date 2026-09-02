# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
import base64

from odoo import _, fields, models
from odoo.exceptions import UserError

from . import import_utils

# Directory column header -> field on commission.account (group_code is
# handled separately since it targets commission.account.group).
HEADER_FIELD_MAP = {
    "ACC ID": "acc_id",
    "NAME": "name",
    "MERCH CODE": "merch_code",
    "INN": "inn",
    "OGRN": "ogrn",
    "Enabled": "enabled",
}
GROUP_HEADER = "Group|COMPANY ID"
ALL_HEADERS = set(HEADER_FIELD_MAP) | {GROUP_HEADER}
BOOL_FIELDS = {"enabled"}


class CommissionAccountImport(models.TransientModel):
    _name = "commission.account.import"
    _description = "Import Accounts Directory"

    state = fields.Selection(
        selection=[("choose", "Choose file"), ("done", "Done")],
        default="choose",
    )
    file = fields.Binary(string="Directory file (xlsx or csv)", required=True)
    filename = fields.Char()

    created_count = fields.Integer(readonly=True)
    updated_count = fields.Integer(readonly=True)
    error_count = fields.Integer(readonly=True)
    log = fields.Text(readonly=True)

    def action_import(self):
        self.ensure_one()
        if not self.filename:
            raise UserError(_("Please select a file."))
        data = base64.b64decode(self.file)
        try:
            rows, col_map = import_utils.read_rows(
                self.filename, data, ALL_HEADERS
            )
        except (ImportError, ValueError) as exc:
            raise UserError(str(exc)) from exc

        log_lines = []
        missing = sorted(ALL_HEADERS - set(col_map))
        if missing:
            log_lines.append(
                _("Columns not found in the file (ignored): %s")
                % ", ".join(missing)
            )
        if GROUP_HEADER not in col_map:
            raise UserError(
                _("Required column '%s' not found in the file.") % GROUP_HEADER
            )
        if "ACC ID" not in col_map:
            raise UserError(_("Required column 'ACC ID' not found in the file."))

        Group = self.env["commission.account.group"]
        Account = self.env["commission.account"]
        existing_groups = {g.code: g for g in Group.search([])}
        existing_accounts = {a.acc_id: a for a in Account.search([])}

        created = 0
        updated = 0
        errors = 0
        for line_no, row in enumerate(rows, start=2):
            acc_id = row.get("ACC ID")
            acc_id = str(acc_id).strip() if acc_id not in (None, "") else ""
            if not acc_id:
                errors += 1
                log_lines.append(_("Line %s: missing ACC ID, skipped.") % line_no)
                continue

            group_code = row.get(GROUP_HEADER)
            group_code = (
                str(group_code).strip() if group_code not in (None, "") else ""
            )
            group = None
            if group_code and group_code != "0":
                group = existing_groups.get(group_code)
                if not group:
                    group = Group.create({"code": group_code})
                    existing_groups[group_code] = group

            vals = {"group_id": group.id if group else False}
            for header, field_name in HEADER_FIELD_MAP.items():
                if field_name == "acc_id":
                    continue
                value = row.get(header)
                if field_name in BOOL_FIELDS:
                    vals[field_name] = import_utils.to_bool(value)
                else:
                    vals[field_name] = (
                        str(value).strip() if value not in (None, "") else False
                    )

            account = existing_accounts.get(acc_id)
            if account:
                account.write(vals)
                updated += 1
            else:
                vals["acc_id"] = acc_id
                account = Account.create(vals)
                existing_accounts[acc_id] = account
                created += 1

            # Give the group a name from its own head account, if this row
            # is it and the group has none yet.
            if group and not group.name and acc_id == group_code:
                group.name = vals.get("name") or False

        log_lines.append(
            _("Created: %(created)s, updated: %(updated)s, errors: %(errors)s.")
            % {"created": created, "updated": updated, "errors": errors}
        )
        self.write(
            {
                "state": "done",
                "created_count": created,
                "updated_count": updated,
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
