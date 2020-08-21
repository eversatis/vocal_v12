# -*- coding: utf-8 -*-
#################################################################################
##    Copyright (c) 2018-Present Webkul Software Pvt. Ltd. (<https://webkul.com/>)
#    You should have received a copy of the License along with this program.
#    If not, see <https://store.webkul.com/license.html/>
#################################################################################
import binascii
from collections import defaultdict
import logging
from odoo import api, fields, models
from odoo.exceptions import Warning, ValidationError
_logger = logging.getLogger(__name__)
try:
    from fedex.services.rate_service import FedexRateServiceRequest
    from fedex.services.ship_service import FedexProcessShipmentRequest
    from fedex.services.ship_service import FedexDeleteShipmentRequest
    from fedex.base_service import FedexError, SchemaValidationError, FedexFailure
    from fedex.config import FedexConfig
except Exception as e:
    _logger.error("#WKDEBUG-1  python  fedEx library not installed .")
fedex_provider_tracking_link = "https://www.fedex.com/apps/fedextrack/?action=track&trackingnumber="
INTERNATIONAL = [
    'INTERNATIONAL_ECONOMY',
    'INTERNATIONAL_PRIORITY',
]

class FedexDeliveryCarrier(models.Model):
    _inherit = "delivery.carrier"

    @api.model
    def config_fedex(self):
        config = self._get_config('fedex.config.settings')
        CONFIG_OBJ = FedexConfig(
            key=config['fedex_key'],
            password=config['fedex_password'],
            account_number=config['fedex_account_no'],
            meter_number=config['fedex_meter_no'],
            integrator_id=config['fedex_integration_id'],
            use_test_server=config['fedex_enviroment'] == 'test'
        )
        return CONFIG_OBJ

    @api.model
    def fedex_add_special_service(self,fedex_obj, package, packaging_id):

        if packaging_id.fedex_signature_option:

            package.SpecialServicesRequested.SpecialServiceTypes = "SIGNATURE_OPTION"
            package.SpecialServicesRequested.SignatureOptionDetail.OptionType = packaging_id.fedex_signature_option
        if packaging_id.fedex_priority_alert == 'yes':
            package.SpecialServicesRequested.SpecialServiceTypes = "PRIORITY_ALERT"
            package.SpecialServicesRequested.PriorityAlertDetail.Content = packaging_id.fedex_priority_content
        return package

    @api.model
    def get_fedex_package(self, fedex_obj, weight, length, width, height, packaging_id):
        package_weight = fedex_obj.create_wsdl_object_of_type('Weight')
        package_weight.Value = weight and weight or self.default_product_weight
        package_weight.Units = self.delivery_uom
        package = fedex_obj.create_wsdl_object_of_type(
            'RequestedPackageLineItem')
        package.Weight = package_weight
        package.PhysicalPackaging = 'BOX'
        package=self.fedex_add_special_service(fedex_obj,package, packaging_id)

        package.Dimensions.Length = length and int(round(length)) or 1
        package.Dimensions.Width = width and int(round(width)) or 1
        package.Dimensions.Height = height and int(round(height)) or 1
        package.Dimensions.Units = 'IN' if self.delivery_uom == 'LB' else 'CM'
        package.GroupPackageCount = 1
        return package

    @api.model
    def fedex_customs_clearance_detail(self ,fedex_obj, currency, amount):
        config = self._get_config('fedex.config.settings')
        fedex_obj.RequestedShipment.CustomsClearanceDetail.DutiesPayment.PaymentType='SENDER'
        fedex_obj.RequestedShipment.CustomsClearanceDetail.DutiesPayment.Payor.ResponsibleParty.AccountNumber=config['fedex_account_no']
        fedex_obj.RequestedShipment.CustomsClearanceDetail.DocumentContent='NON_DOCUMENTS'
        fedex_obj.RequestedShipment.CustomsClearanceDetail.ExportDetail.B13AFilingOption='NOT_REQUIRED'
        fedex_obj.RequestedShipment.CustomsClearanceDetail.CustomsValue.Currency=currency
        fedex_obj.RequestedShipment.CustomsClearanceDetail.CustomsValue.Amount= amount
        return fedex_obj

    @api.model
    def fedex_commodity(self ,fedex_obj, packaging_id,
        pickings,package_id):
        domain = [('result_package_id','=',package_id.id)]
        operation_ids =self.env['stock.pack.operation'].search(domain)
        country_code =pickings.picking_type_id.warehouse_id.partner_id.country_id.code
        currency = self.get_shipment_currency(pickings=pickings)
        for operation_id in operation_ids:
            qty_done = operation_id.qty_done
            product_id = operation_id.product_id
            Commodity = fedex_obj.create_wsdl_object_of_type('Commodity')
            Commodity.Name=product_id.name
            Commodity.Description=product_id.description or product_id.name
            Commodity.CountryOfManufacture=country_code
            Commodity.NumberOfPieces=1
            Commodity.Weight.Units=self.delivery_uom
            weight = self._get_api_weight(product_id.weight)
            weight = weight and weight  or self.default_product_weight
            Commodity.Weight.Value=weight

            Commodity.UnitPrice.Currency=currency
            Commodity.UnitPrice.Amount= product_id.list_price
            Commodity.Quantity=qty_done
            Commodity.QuantityUnits='EA'
            Commodity.CustomsValue.Currency= currency
            Commodity.CustomsValue.Amount= product_id.list_price
            fedex_obj.RequestedShipment.CustomsClearanceDetail.Commodities.append(Commodity)
        return fedex_obj

    @api.model
    def fedex_preprocessing(self, fedex_obj, packaging_id,
     order=None, pickings=None,package_id=None):
        config = self._get_config('fedex.config.settings')
        currency = self.get_shipment_currency(order,pickings)
        if order:
            recipient = order.partner_shipping_id if order.partner_shipping_id else order.partner_id
            warehouse = order.warehouse_id.partner_id
        else:
            amount  = package_id.cover_amount
            if self.fedex_servicetype.code in INTERNATIONAL:
                self.fedex_customs_clearance_detail(fedex_obj,currency,amount)
                self.fedex_commodity(fedex_obj,packaging_id,pickings=pickings,package_id=package_id)

            recipient = pickings.partner_id
            warehouse = pickings.picking_type_id.warehouse_id.partner_id
        fedex_obj.RequestedShipment.PreferredCurrency = currency
        fedex_obj.RequestedShipment.DropoffType = self.fedex_dropofftype.code
        fedex_obj.RequestedShipment.ServiceType = self.fedex_servicetype.code
        fedex_obj.RequestedShipment.PackagingType = packaging_id.shipper_package_code
        fedex_obj.RequestedShipment.Shipper.Contact.PersonName = warehouse.name
        fedex_obj.RequestedShipment.Shipper.Contact.PhoneNumber = warehouse.phone
        if warehouse.is_company:
            fedex_obj.RequestedShipment.Shipper.Contact.CompanyName = warehouse.name
            fedex_obj.RequestedShipment.Shipper.Address.Residential = False
        warehouse_street = [warehouse.street]
        if warehouse.street2:warehouse_street+=[warehouse.street2]
        fedex_obj.RequestedShipment.Shipper.Address.StreetLines =warehouse_street

        fedex_obj.RequestedShipment.Recipient.Contact.PersonName = recipient.name
        fedex_obj.RequestedShipment.Recipient.Contact.PhoneNumber = recipient.mobile or recipient.phone
        if recipient.is_company:
            fedex_obj.RequestedShipment.Recipient.Contact.CompanyName = recipient.parent_id and recipient.parent_id.name or recipient.name
            fedex_obj.RequestedShipment.Recipient.Address.Residential = False
        fedex_obj.RequestedShipment.Shipper.Address.City = warehouse.city or None
        fedex_obj.RequestedShipment.Shipper.Address.StateOrProvinceCode = warehouse.state_id and warehouse.state_id.code or None
        fedex_obj.RequestedShipment.Shipper.Address.PostalCode = warehouse.zip
        fedex_obj.RequestedShipment.Shipper.Address.CountryCode = warehouse.country_id.code

        recipient_street = [recipient.street]
        if recipient.street2:recipient_street+=[recipient.street2]
        fedex_obj.RequestedShipment.Recipient.Address.StreetLines = recipient_street

        fedex_obj.RequestedShipment.Recipient.Address.City = recipient.city
        fedex_obj.RequestedShipment.Recipient.Address.StateOrProvinceCode = recipient.state_id and recipient.state_id.code or None
        fedex_obj.RequestedShipment.Recipient.Address.PostalCode = recipient.zip
        fedex_obj.RequestedShipment.Recipient.Address.CountryCode = recipient.country_id.code

        fedex_obj.RequestedShipment.EdtRequestType = packaging_id.fedex_edt_request_type
        fedex_obj.RequestedShipment.ShippingChargesPayment.Payor.ResponsibleParty.AccountNumber = config[
            "fedex_account_no"]
        fedex_obj.RequestedShipment.ShippingChargesPayment.PaymentType = self.fedex_paymentyype

        return fedex_obj

    @api.model
    def fedex_set_shipping_price(self, order=None):
        recipient = order.partner_shipping_id if order.partner_shipping_id else order.partner_id
        currency_id = self.get_shipment_currency_id(order)
        currency_code = currency_id.name
        try:
            CurrencyCode = currency_id.name
            packaging_obj = self.env['product.packaging']
            result = 0.0
            currency_id = order.currency_id
            self.wk_validate_data(order=order)
            package_items = self.wk_get_order_package(order=order)
            items=self.wk_group_by('packaging_id',package_items)

            for order_packaging_id, wk_packaging_ids in items:

                packaging_id = packaging_obj.browse(order_packaging_id)
                rate_request = FedexRateServiceRequest(
                    self.config_fedex())

                rate_request = self.fedex_preprocessing(
                    rate_request, packaging_id, order=order)
                for wk_packaging_id in wk_packaging_ids:
                    weight = int(round(self._get_api_weight(
                        wk_packaging_id.get('weight'))))

                    package = self.get_fedex_package(
                        rate_request, weight, wk_packaging_id.get(
                            'length'), wk_packaging_id.get('width'),
                        wk_packaging_id.get('height'), packaging_id)
                    rate_request.add_package(package)
                rate_request.send_request()
                amount = 0
                for service in rate_request.response.RateReplyDetails:
                    for rate_detail in service.RatedShipmentDetails:
                        CurrencyCode = rate_detail.ShipmentRateDetail.TotalNetFedExCharge.Currency
                        amount += float(
                            rate_detail.ShipmentRateDetail.TotalNetFedExCharge.Amount)
                    result += amount
            return dict(
                currency_id = currency_id,
                price = result,
                currency =CurrencyCode,
                success = True
            )

        except  (FedexError, FedexFailure, SchemaValidationError) as f_err:
            _logger.warning(
                "#1 FEDEX GET RATE ERROR-------%r---------------", f_err.value)
            return dict(
                error_message  = f_err.value,
                success = False
            )
        except Exception as e:
            _logger.warning("#2 FEDEX GET RATE ERROR-------%r---------------", e)
            return dict(
                error_message  = e,
                success = False
            )

    @api.model
    def fedex_rate_shipment(self, order):
        response = self.fedex_set_shipping_price(order)
        _logger.debug("##########11order===%r==%r=="%(order,response))
        if not response.get('error_message'):response['error_message'] = None
        if not response.get('price'):response['price'] = 0
        if not response.get('warning_message'):response['warning_message'] = None
        if not response.get('success'):return response
        price = self.convert_shipment_price(response)
        response['price'] = price
        _logger.debug("##########22order===%r==%r=="%(order,response))
        return response


    @api.one
    def fedex_send_shipping(self, pickings):
        try:

            result = {
                'exact_price': 0,
                'weight': 0,
                'date_delivery': None,
                'tracking_number': '',
                'attachments': []
            }
            packaging_ids = self.wk_group_by_packaging(pickings=pickings)
            MasterTrackingIds = dict()
            product_uom_obj = self.env['uom.uom']
            currency_id = pickings.sale_id.currency_id and pickings.sale_id.currency_id or pickings.company_id.currency_id
            total_package = 0
            for packaging_id, package_ids in packaging_ids.items():
                self.wk_validate_data(pickings=pickings)
                number_of_packages = len(package_ids)
                total_package += number_of_packages
                for index, package_id in enumerate(package_ids, 1):
                    # _logger.info(
                    #     "WK  %r [%r/%r] %r : %r kg",
                    #     packaging_id,
                    #     number_of_packages,
                    #     total_package,package_id.name,
                    #     package_id.shipping_weight
                    # )


                    shipment = FedexProcessShipmentRequest(self.config_fedex())
                    if number_of_packages > 1:
                        shipment.RequestedShipment.PackageCount = number_of_packages - 1
                    shipment.RequestedShipment.LabelSpecification.LabelFormatType = 'COMMON2D'
                    shipment.RequestedShipment.LabelSpecification.ImageType = 'PNG'
                    shipment.RequestedShipment.LabelSpecification.LabelStockType = self.fedex_label_stock_type
                    shipment.RequestedShipment.LabelSpecification.LabelPrintingOrientation = 'BOTTOM_EDGE_OF_TEXT_FIRST'
                    #####################################
                    if packaging_id.fedex_edt_request_type=='ALL':
                        shipment.RequestedShipment.SpecialServicesRequested.SpecialServiceTypes = "ELECTRONIC_TRADE_DOCUMENTS"
                        shipment.RequestedShipment.SpecialServicesRequested.EtdDetail.RequestedDocumentCopies = "COMMERCIAL_INVOICE"
                        spec = shipment.create_wsdl_object_of_type('ShippingDocumentSpecification')
                        spec.ShippingDocumentTypes = 'COMMERCIAL_INVOICE'
                        spec_format = shipment.create_wsdl_object_of_type('ShippingDocumentFormat')
                        spec_format.ImageType='PDF'
                        spec_format.StockType='PAPER_LETTER'
                        spec.CommercialInvoiceDetail.Format=spec_format
                        shipment.RequestedShipment.ShippingDocumentSpecification=spec
                    #####################################
                    shipment = self.fedex_preprocessing(
                        shipment, packaging_id, pickings=pickings,package_id=package_id)
                    weight = self._get_api_weight(package_id.shipping_weight)
                    weight = weight and weight  or self.default_product_weight

                    package = self.get_fedex_package(shipment, weight,
                        packaging_id.length, packaging_id.width, packaging_id.height, packaging_id)
                    package.ItemDescription = package_id.description

                    package.SequenceNumber = index
                    if index == 1:
                        if package_id.cover_amount:
                            package.InsuredValue.Amount = package_id.cover_amount
                            package.InsuredValue.Currency = currency_id.name
                        shipment.add_package(package)

                        shipment.send_request()
                        CompletedPackageDetails = shipment.response.CompletedShipmentDetail.CompletedPackageDetails[
                            0]
                        MasterTrackingIds[packaging_id] = CompletedPackageDetails.TrackingIds[
                            0].TrackingNumber

                    else:
                        if number_of_packages > 1:
                            shipment.RequestedShipment.MasterTrackingId.TrackingIdType = self.fedex_trackingid_type
                            shipment.RequestedShipment.MasterTrackingId.TrackingNumber = MasterTrackingIds.get(
                                packaging_id)
                        shipment.add_package(package)
                        shipment.send_request()

                        CompletedPackageDetails = shipment.response.CompletedShipmentDetail.CompletedPackageDetails[
                            0]
                    TrackingNumber = CompletedPackageDetails.TrackingIds[
                        0].TrackingNumber
                    image = CompletedPackageDetails.Label.Parts[0].Image

                    result['attachments'].append(
                        ('FedEx' + str(TrackingNumber) + '.png', binascii.a2b_base64(str(image))))
                    result['tracking_number'] += ',' + TrackingNumber
                    result['weight'] += weight

                    Amount = hasattr(CompletedPackageDetails, 'PackageRating')and CompletedPackageDetails.PackageRating.PackageRateDetails[
                        0].NetCharge.Amount or 0
                    if Amount:
                        CurrencyCode = CompletedPackageDetails.PackageRating.PackageRateDetails[
                            0].NetCharge.Currency
                        if currency_id.name == CurrencyCode:
                            result['exact_price'] += Amount
                        else:
                            currency = currency_id.search(
                                [('name', '=', CurrencyCode)], limit=1)
                            result[
                                'exact_price'] += currency.compute(Amount, currency_id)
            pickings.number_of_packages = total_package
            return result
        except (FedexError, FedexFailure, SchemaValidationError) as f_err:
            pickings.message_post(body=f_err.value, subject="FedEx Error:")
            _logger.warning(
                "#1 FEDEX SEND SHIPMENT ERROR-------%r---------------", f_err.value)
            raise ValidationError(f_err.value)
        except Exception as e:
            pickings.message_post(body=e, subject="FedEx Error:")
            _logger.warning('#2 FEDEX SEND SHIPMENT ERROR--%r', e)
            raise ValidationError(e)

    @api.model
    def fedex_get_tracking_link(self, pickings):
        return fedex_provider_tracking_link + '%s' % pickings.carrier_tracking_ref

    @api.model
    def fedex_cancel_shipment(self, pickings):
        try:
            for tracking_ref in pickings.carrier_tracking_ref.split(','):
                del_request = FedexDeleteShipmentRequest(self.config_fedex())
                del_request.DeletionControlType = "DELETE_ALL_PACKAGES"
                del_request.TrackingId.TrackingNumber = tracking_ref
                del_request.TrackingId.TrackingIdType = self.fedex_trackingid_type
                del_request.send_request()
                assert (del_request.response.HighestSeverity ==
                        'SUCCESS'), 'ID:{},{}'.format(tracking_ref, del_request.response.Notifications[0].Message)
            return True
        except (FedexError, FedexFailure, SchemaValidationError) as f_err:
            pickings.message_post(body=f_err.value, subject="FedEx Error:")
            _logger.warning(
                "---#1 FEDEX Cancel SHIPMENT ERROR-------%r---------------", f_err.value)
            raise ValidationError(f_err.value)
        except Exception as e:
            pickings.message_post(body=e, subject="FedEx Error:")
            _logger.warning('-#2 FEDEX Cancel SHIPMENT ERROR--%r', e)
            raise ValidationError(e)
