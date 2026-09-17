{
    "name": "Aptiwise Connector",
    "version": "1.0.0",
    "summary": "Trigger Aptiwise workflows from Odoo using per-user, on-behalf-of short-lived tokens",
    "description": """
Aptiwise Connector
==================

A reusable service that lets any Odoo menu, button, server action, or
automation trigger an Aptiwise workflow **as the logged-in user**, with:

* **No per-user secret stored in Odoo.** Only one integration credential
  (client_id / client_secret) lives server-side in ``odoo.conf`` (or the
  environment).
* **No interactive login.** The already-authenticated Odoo user's identity
  is asserted to Aptiwise via OAuth 2.0 Token Exchange (RFC 8693); Aptiwise
  returns a short-lived, scoped token minted on demand.
* **Shared token cache.** One mint per user per token lifetime, reused across
  every button/menu in every module.
* **Audit-friendly.** Each trigger is attributed to the real human plus the
  Odoo integration as delegate (handled on the Aptiwise side).

Usage from any model::

    self.env["aptiwise.client"].trigger("po_approval", {"po_number": self.name})

See README.md for configuration and call-site examples.
""",
    "author": "Aptiwise",
    "website": "https://aptiwise.com",
    "category": "Tools",
    "license": "MIT",
    "depends": ["base"],
    "data": [
        "security/ir.model.access.csv",
        "views/aptiwise_workflow_views.xml",
        "views/aptiwise_user_views.xml",
    ],
    "external_dependencies": {"python": ["requests"]},
    "installable": True,
    "application": False,
}
