from . import models
from . import wizards


def post_init_hook(env):
    """Sensible defaults for a fresh install of this module, since it was
    built for a Russian-language, RUB business: Russian UI active (and
    used by the users that already exist at install time) and RUB as
    every company's currency.

    Runs once, right after install only - never on a module upgrade - so
    it won't fight you if you (or someone) later set these to something
    else on purpose.
    """
    ru_lang = env["res.lang"].search([("code", "=", "ru_RU")], limit=1)
    if not ru_lang or not ru_lang.active:
        env["res.lang"]._activate_lang("ru_RU")

    env["res.users"].search([]).write({"lang": "ru_RU"})

    # Currencies are inactive by default until used - a plain search()
    # filters those out, so RUB (normally inactive on a fresh db) would
    # never be found without this.
    rub = env["res.currency"].with_context(active_test=False).search(
        [("name", "=", "RUB")], limit=1
    )
    if rub:
        if not rub.active:
            rub.active = True
        env["res.company"].search([]).write({"currency_id": rub.id})
