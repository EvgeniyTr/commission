# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
{
    "name": "Partner Commission (Simple)",
    "version": "18.0.1.0.0",
    "summary": "Simple calculation of partner commission from an imported "
    "transaction registry, supporting two schemes: commission on top "
    "(paid by the client) and commission inside (paid by the partner).",
    "category": "Accounting",
    "license": "AGPL-3",
    "depends": ["base"],
    "data": [
        "security/commission_security.xml",
        "security/ir.model.access.csv",
        "views/commission_account_views.xml",
        "views/commission_agreement_views.xml",
        "views/commission_transaction_views.xml",
        "wizards/commission_account_import_views.xml",
        "wizards/commission_transaction_import_views.xml",
        "wizards/commission_transaction_export_views.xml",
        "views/menu.xml",
        "data/recompute_action.xml",
    ],
    "installable": True,
    "application": True,
}
