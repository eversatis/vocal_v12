# -*- coding: utf-8 -*-
#################################################################################
# Author      : Webkul Software Pvt. Ltd. (<https://webkul.com/>)
# Copyright(c): 2015-Present Webkul Software Pvt. Ltd.
# All Rights Reserved.
#
# 
#
# This program is copyright property of the author mentioned above.
# You can`t redistribute it and/or modify it.
#
#
# You should have received a copy of the License along with this program.
# If not, see <https://store.webkul.com/license.html/>
#################################################################################
{
  "name"                 :  "USPS Shipping Integration",
  "summary"              :  "Integrate USPS shipping functionality directly within Odoo ERP applications to deliver increased logistical efficiencies.",
  "category"             :  "Website/Shipping Logistics",
  "version"              :  "1.0.3",
  "author"               :  "Webkul Software Pvt. Ltd.",
  "license"              :  "Other proprietary",
  "website"              :  "https://store.webkul.com/Odoo-Website-USPS-Shipping-Integration.html",
  "description"          :  """http://webkul.com/blog/odoo-website-usps-shipping-integration/
  USPS Shipping API Integration as Odoo USPS Delivery Method .
  Provide Shipping Label Generation and Shipping Rate Calculator For Website as Well Odoo BackEnd.""",
  # "live_test_url"        :  "http://odoodemo.webkul.com/?module=usps_delivery_carrier&version=12.0",
  "depends"              :  ['odoo_shipping_service_apps'],
  "data"                 :  [
                             'security/ir.model.access.csv',
                             'views/usps_delivery_carrier.xml',
                             'views/product_packaging.xml',
                             'data/data.xml',
                             'data/delivery_demo.xml',
                            ],
  "demo"                 :  ['data/demo.xml'],
  "images"               :  ['static/description/Banner.png'],
  "application"          :  True,
  "installable"          :  True,
  "price"                :  149,
  "currency"             :  "EUR",
  "pre_init_hook"        :  "pre_init_check",
  "external_dependencies":  {'python': ['urllib3','requests']},
}
