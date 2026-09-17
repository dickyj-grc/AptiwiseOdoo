from odoo import fields, models


class ResUsers(models.Model):
    _inherit = "res.users"

    aptiwise_email = fields.Char(
        string="Aptiwise Email",
        help="Set only if this user's Aptiwise account email differs from "
             "their Odoo email/login. Leave blank to use the Odoo email.",
    )

    # Allow a user to see/set their own mapping without broad res.users access.
    @property
    def SELF_READABLE_FIELDS(self):
        return super().SELF_READABLE_FIELDS + ["aptiwise_email"]

    @property
    def SELF_WRITEABLE_FIELDS(self):
        return super().SELF_WRITEABLE_FIELDS + ["aptiwise_email"]
