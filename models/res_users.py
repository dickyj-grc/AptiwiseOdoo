from odoo import fields, models


class ResUsers(models.Model):
    _inherit = "res.users"

    aptiwise_email = fields.Char(
        string="Aptiwise Email",
        groups="base.group_system",
        help="Set only if this user's Aptiwise account email differs from "
             "their Odoo login. Leave blank to use the Odoo login.",
    )
