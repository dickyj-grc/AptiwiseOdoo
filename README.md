# Aptiwise Connector (Odoo module)

Trigger Aptiwise workflows from any Odoo menu, button, server action, or
automation **as the logged-in user**, with no per-user secret stored in Odoo
and no interactive login.

It uses OAuth 2.0 Token Exchange (RFC 8693): the already-authenticated Odoo
user's identity is asserted to Aptiwise, which mints a short-lived, scoped
token on demand. One integration credential lives server-side; nothing
per-user is stored anywhere.

## Requirements

* Odoo 17 / 18 / 19 (uses the `<list>` view tag; on Odoo 16 change `<list>`
  to `<tree>` and `view_mode` to `tree,form`).
* Python `requests` (bundled with Odoo).
* An Aptiwise `/oauth/token` endpoint and a registered service client
  (`client_id` / `client_secret`).

## Install

1. Copy the `aptiwise_connector/` folder into your addons path
   (e.g. `/mnt/extra-addons/`).
2. Update the apps list and install **Aptiwise Connector**.

## Configure (server-side only)

Add to `odoo.conf` — or inject as environment variables (upper-cased names),
which take precedence and keep the secret out of the config file in
containerised deploys:

```ini
aptiwise_token_url     = https://api.aptiwise.com/api/v1/oauth/token
aptiwise_client_id     = odoo-acme-prod
aptiwise_client_secret = <shown once at registration>
; optional:
aptiwise_default_scope = workflow:trigger
aptiwise_token_skew    = 30
```

Environment equivalents: `APTIWISE_TOKEN_URL`, `APTIWISE_CLIENT_ID`,
`APTIWISE_CLIENT_SECRET`, `APTIWISE_DEFAULT_SCOPE`, `APTIWISE_TOKEN_SKEW`.

The `client_secret` is the only long-lived secret. Keep it out of the
database and out of version control.

## Register workflows

Settings ▸ **Aptiwise ▸ Workflows** (admin only). Each row maps a logical
`key` to a trigger `url`. Buttons then reference the key, so URLs live in one
place:

| Field | Example |
|-------|---------|
| Name  | PO Approval |
| Key   | `po_approval` |
| URL   | `https://api.aptiwise.com/api/v1/workflows/42/trigger` |
| Scope | `workflow:trigger` |

## Use it

### From any model (the service is globally reachable)

```python
self.env["aptiwise.client"].trigger("po_approval", {"po_number": self.name})
```

`trigger()` accepts a registered key **or** a full URL.

### From a button, via the optional mixin

```python
class PurchaseOrder(models.Model):
    _inherit = ["purchase.order", "aptiwise.trigger.mixin"]

    def action_send_po_approval(self):
        return self._aptiwise_trigger(
            "po_approval",
            {"po_number": self.name, "amount": self.amount_total},
        )
```

Add `aptiwise_connector` to the depending module's `__manifest__.py`
`depends` list.

### From a cron / background job (no logged-in user)

```python
self.env["aptiwise.client"].trigger_as_service("nightly_sync", {...})
```

`trigger_as_service()` mints a token for the integration itself and requires
the Aptiwise endpoint to accept the `client_credentials` grant. Prefer
`trigger()` for anything a person initiated so the audit trail names them.

## How it behaves

* **Token cache** is per Odoo worker and shared across all call sites, keyed
  by user + scope — so many buttons for the same user mint at most once per
  token lifetime.
* **401 handling**: a stale cached token (rotated signing key, revoked user)
  is transparently re-minted once and the request retried.
* **User-facing errors**: misconfiguration, an unlinked account, or an
  unreachable Aptiwise surface as clean Odoo notifications, not tracebacks.
* **Identity mapping**: the Aptiwise account is matched by the user's
  `aptiwise_email` (if set on their user record) else Odoo `email` else
  `login`.

## Security notes

* No `ir.model.access` rules are needed for `aptiwise.client` — it is an
  abstract service with no table. Per-user security is enforced by the
  Aptiwise token exchange.
* `aptiwise.workflow` is readable by all internal users (they only see URLs,
  not secrets) and writable only by system administrators.
* Gate access to workflows at the buttons/menus in your own modules as usual.
