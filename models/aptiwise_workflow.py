from odoo import fields, models


class AptiwiseWorkflow(models.Model):
    """Registry mapping a logical workflow key to its Aptiwise trigger URL.

    This holds only non-secret routing data, so storing it in the database is
    fine. Buttons/menus reference the ``key``; the URL lives in exactly one
    place and can be changed by an administrator without touching code.
    """

    _name = "aptiwise.workflow"
    _description = "Aptiwise Workflow Endpoint"
    _order = "name"

    name = fields.Char(required=True, help="Human-readable label.")
    key = fields.Char(
        required=True,
        help="Technical key referenced from code, e.g. self.env['aptiwise.client'].trigger('po_approval', ...).",
    )
    url = fields.Char(
        required=True,
        string="Trigger URL",
        help="Full Aptiwise workflow trigger endpoint, e.g. https://api.aptiwise.com/api/v1/workflows/42/trigger",
    )
    scope = fields.Char(
        default="workflow:trigger",
        help="OAuth scope requested when minting a token for this workflow.",
    )
    active = fields.Boolean(default=True)

    _sql_constraints = [
        ("key_uniq", "unique(key)", "The workflow key must be unique."),
    ]
