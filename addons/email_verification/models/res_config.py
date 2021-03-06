#  -*- coding: utf-8 -*-
#################################################################################
#
#   Copyright (c) 2018-Present Webkul Software Pvt. Ltd. (<https://webkul.com/>)
#   See LICENSE URL <https://store.webkul.com/license.html/> for full copyright and licensing details.
#################################################################################


from odoo import api, models, fields, exceptions

import logging
_logger = logging.getLogger(__name__)


class EmailVerificationConfig (models.TransientModel):
	_name = 'email.verification.config'
	_inherit = 'webkul.website.addons'


	token_validity = fields.Integer(
		string='Token Validity In Days',
		help="Validity of the token in days sent in email. If validity is 0 it means infinite.",

	  )
	restrict_unverified_users = fields.Boolean(
		string='Restrict Unverified Users From Checkout',
		help="If enabled unverified users can not proceed to checkout untill they verify their emails")

	@api.multi
	def set_values(self):
		super(EmailVerificationConfig, self).set_values()
		IrDefault = self.env['ir.default'].sudo()
		if self.token_validity <= 0:
			raise exceptions.UserError('Token Validity can not be 0 or negative, Please update another value!')
		IrDefault.set('email.verification.config','token_validity', self.token_validity)
		IrDefault.set('email.verification.config','restrict_unverified_users', self.restrict_unverified_users)

	@api.multi
	def get_values(self):
		res = super(EmailVerificationConfig, self).get_values()
		IrDefault = self.env['ir.default'].sudo()
		token_validity = IrDefault.get('email.verification.config','token_validity', False)
		restrict_unverified_users = IrDefault.get('email.verification.config', 'restrict_unverified_users')
		res.update({
			'token_validity': token_validity if token_validity else 2,
			'restrict_unverified_users': True if restrict_unverified_users == None else restrict_unverified_users
		})
		return res
