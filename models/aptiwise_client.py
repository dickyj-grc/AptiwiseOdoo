import os
import time
import base64
import logging
import threading

import requests

from odoo import models, tools
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

# Per-worker in-memory token cache: { cache_key: (token, expiry_epoch) }.
# Module-level so it is shared by every call site within one Odoo worker.
_TOKEN_CACHE = {}
_CACHE_LOCK = threading.Lock()

TOKEN_EXCHANGE_GRANT = "urn:ietf:params:oauth:grant-type:token-exchange"
EMAIL_SUBJECT_TYPE = "urn:aptiwise:params:oauth:token-type:email"


def _cfg(key, default=None):
    """Read configuration from the environment first, then odoo.conf.

    Environment wins so containerised deploys can inject the secret without
    baking it into odoo.conf. Env var names are the upper-cased key, e.g.
    ``APTIWISE_CLIENT_SECRET``.
    """
    return os.environ.get(key.upper()) or tools.config.get(key) or default


class AptiwiseClient(models.AbstractModel):
    """Stateless, reusable service for triggering Aptiwise workflows.

    Reach it from anywhere with ``self.env["aptiwise.client"]`` — it has no
    table and needs no access rules; per-user security is enforced by the
    Aptiwise token exchange, not by Odoo ACLs.
    """

    _name = "aptiwise.client"
    _description = "Aptiwise on-behalf-of token exchange and workflow trigger"

    # ------------------------------------------------------------------ #
    # Configuration
    # ------------------------------------------------------------------ #
    def _token_url(self):
        url = _cfg("aptiwise_token_url")
        if not url:
            raise UserError(
                "Aptiwise integration is not configured "
                "(aptiwise_token_url is missing). Contact your administrator."
            )
        return url

    def _client_credentials(self):
        cid = _cfg("aptiwise_client_id")
        secret = _cfg("aptiwise_client_secret")
        if not cid or not secret:
            raise UserError(
                "Aptiwise integration is not configured "
                "(client id/secret missing). Contact your administrator."
            )
        return cid, secret

    def _default_scope(self):
        return _cfg("aptiwise_default_scope", "workflow:trigger")

    def _skew_seconds(self):
        try:
            return int(_cfg("aptiwise_token_skew", 30))
        except (TypeError, ValueError):
            return 30

    def _basic_auth_header(self):
        cid, secret = self._client_credentials()
        raw = f"{cid}:{secret}".encode()
        return "Basic " + base64.b64encode(raw).decode()

    # ------------------------------------------------------------------ #
    # Token minting
    # ------------------------------------------------------------------ #
    def _post_token(self, data):
        try:
            resp = requests.post(
                self._token_url(),
                headers={"Authorization": self._basic_auth_header()},
                data=data,
                timeout=15,
            )
        except requests.RequestException:
            _logger.exception("Aptiwise token request failed")
            raise UserError("Could not reach Aptiwise to authenticate. Please try again later.")

        if resp.status_code == 401:
            raise UserError(
                "Aptiwise integration credentials are invalid. Contact your administrator."
            )
        if resp.status_code == 400 and "invalid_target" in resp.text:
            raise UserError(
                "Your account isn't linked to Aptiwise. Ask an administrator to add you."
            )
        if resp.status_code >= 400:
            _logger.error("Aptiwise token error %s: %s", resp.status_code, resp.text[:500])
            raise UserError("Aptiwise refused the authentication request (%s)." % resp.status_code)

        body = resp.json()
        token = body.get("access_token")
        if not token:
            raise UserError("Aptiwise returned no access token.")
        expires_in = int(body.get("expires_in", 600))
        return token, time.time() + expires_in

    def _mint_user_token(self, email, scope):
        return self._post_token({
            "grant_type": TOKEN_EXCHANGE_GRANT,
            "subject_token": email,
            "subject_token_type": EMAIL_SUBJECT_TYPE,
            "scope": scope,
        })

    def _mint_service_token(self, scope):
        # Requires the Aptiwise /oauth/token endpoint to also accept the
        # standard client_credentials grant (no subject user). Used for cron
        # / background triggers that do not act on behalf of a person.
        return self._post_token({
            "grant_type": "client_credentials",
            "scope": scope,
        })

    # ------------------------------------------------------------------ #
    # Cache
    # ------------------------------------------------------------------ #
    def _get_cached(self, cache_key):
        now = time.time()
        with _CACHE_LOCK:
            cached = _TOKEN_CACHE.get(cache_key)
            if cached and cached[1] - self._skew_seconds() > now:
                return cached[0]
        return None

    def _store_cache(self, cache_key, token, expiry):
        with _CACHE_LOCK:
            _TOKEN_CACHE[cache_key] = (token, expiry)

    def _invalidate(self, cache_key):
        with _CACHE_LOCK:
            _TOKEN_CACHE.pop(cache_key, None)

    # ------------------------------------------------------------------ #
    # Token accessors (cache-aware)
    # ------------------------------------------------------------------ #
    def _current_email(self):
        user = self.env.user
        email = user.aptiwise_email or user.email or user.login
        if not email:
            raise UserError("Your Odoo user has no email to map to an Aptiwise account.")
        return email.strip().lower()

    def get_user_token(self, email=None, scope=None):
        """Return (token, cache_key) for the given (or current) user."""
        scope = scope or self._default_scope()
        email = (email or self._current_email()).strip().lower()
        cache_key = "user:%s:%s" % (email, scope)
        token = self._get_cached(cache_key)
        if token:
            return token, cache_key
        token, expiry = self._mint_user_token(email, scope)
        self._store_cache(cache_key, token, expiry)
        return token, cache_key

    def get_service_token(self, scope=None):
        """Return (token, cache_key) for the integration itself (no user)."""
        scope = scope or self._default_scope()
        cache_key = "service:%s" % scope
        token = self._get_cached(cache_key)
        if token:
            return token, cache_key
        token, expiry = self._mint_service_token(scope)
        self._store_cache(cache_key, token, expiry)
        return token, cache_key

    def _remint(self, cache_key):
        """Force-mint a fresh token for a cache key after a 401."""
        self._invalidate(cache_key)
        kind, _, rest = cache_key.partition(":")
        if kind == "service":
            token, _ = self.get_service_token(scope=rest)
        else:  # "user:<email>:<scope>"
            email, _, scope = rest.partition(":")
            token, _ = self.get_user_token(email=email, scope=scope)
        return token

    # ------------------------------------------------------------------ #
    # Workflow resolution
    # ------------------------------------------------------------------ #
    def _resolve_url(self, workflow):
        """Accept either a full URL or a registered workflow key.

        Returns (url, scope).
        """
        if not workflow:
            raise UserError("No Aptiwise workflow specified.")
        if workflow.startswith(("http://", "https://")):
            return workflow, self._default_scope()
        rec = self.env["aptiwise.workflow"].sudo().search(
            [("key", "=", workflow), ("active", "=", True)], limit=1
        )
        if not rec:
            raise UserError("Unknown Aptiwise workflow key: %s" % workflow)
        return rec.url, (rec.scope or self._default_scope())

    # ------------------------------------------------------------------ #
    # Trigger
    # ------------------------------------------------------------------ #
    def _do_trigger(self, url, token, cache_key, payload):
        headers = {"Authorization": "Bearer %s" % token}
        resp = None
        try:
            resp = requests.post(url, headers=headers, json=payload or {}, timeout=30)
            if resp.status_code == 401:
                # Token stale (rotated signing key / revoked user); mint once and retry.
                token = self._remint(cache_key)
                headers["Authorization"] = "Bearer %s" % token
                resp = requests.post(url, headers=headers, json=payload or {}, timeout=30)
            resp.raise_for_status()
        except requests.HTTPError:
            detail = resp.text[:500] if resp is not None else ""
            code = resp.status_code if resp is not None else "?"
            _logger.error("Aptiwise trigger failed %s: %s", code, detail)
            raise UserError("Aptiwise rejected the request (%s)." % code)
        except requests.RequestException:
            _logger.exception("Aptiwise trigger request failed")
            raise UserError("Could not reach Aptiwise. Please try again later.")
        try:
            return resp.json()
        except ValueError:
            return {"status_code": resp.status_code, "text": resp.text}

    def trigger(self, workflow, payload=None):
        """Trigger a workflow on behalf of the current Odoo user.

        ``workflow`` may be a registered key (see aptiwise.workflow) or a full
        URL. Use this from interactive buttons and menus.
        """
        url, scope = self._resolve_url(workflow)
        token, cache_key = self.get_user_token(scope=scope)
        return self._do_trigger(url, token, cache_key, payload)

    def trigger_as_service(self, workflow, payload=None):
        """Trigger a workflow as the integration itself (no acting user).

        Use this from cron jobs / background automations where there is no
        logged-in human. Requires the Aptiwise token endpoint to accept the
        client_credentials grant.
        """
        url, scope = self._resolve_url(workflow)
        token, cache_key = self.get_service_token(scope=scope)
        return self._do_trigger(url, token, cache_key, payload)
