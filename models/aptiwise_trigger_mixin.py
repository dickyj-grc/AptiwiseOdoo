from odoo import models


class AptiwiseTriggerMixin(models.AbstractModel):
    """Optional convenience mixin for record-level Aptiwise triggering.

    Inherit it on any model to get short helpers, e.g.::

        class PurchaseOrder(models.Model):
            _inherit = ["purchase.order", "aptiwise.trigger.mixin"]

            def action_send_po_approval(self):
                return self._aptiwise_trigger(
                    "po_approval",
                    {"po_number": self.name, "amount": self.amount_total},
                )
    """

    _name = "aptiwise.trigger.mixin"
    _description = "Aptiwise Trigger Mixin"

    def _aptiwise_trigger(self, workflow, payload=None):
        """Trigger on behalf of the current user (interactive buttons/menus)."""
        self.ensure_one()
        return self.env["aptiwise.client"].trigger(workflow, payload)

    def _aptiwise_trigger_as_service(self, workflow, payload=None):
        """Trigger as the integration itself (cron / background)."""
        self.ensure_one()
        return self.env["aptiwise.client"].trigger_as_service(workflow, payload)
