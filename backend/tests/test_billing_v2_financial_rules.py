from app.services.commercial_service import CommercialError,minute_rate_from_hourly,reseller_price_preview,calculate_marketplace_split
import pytest

def test_hourly_to_minute(): assert minute_rate_from_hourly(6000)==100

def test_reseller_50_30():
    assert reseller_price_preview(list_price_minor=100000,wholesale_discount_bps=5000,customer_discount_bps=3000)=={"customer_charge_minor":70000,"khan_cloud_floor_minor":50000,"reseller_earning_minor":20000}

def test_reseller_floor():
    with pytest.raises(CommercialError): reseller_price_preview(list_price_minor=100000,wholesale_discount_bps=3000,customer_discount_bps=4000)

def test_marketplace_margin():
    x=calculate_marketplace_split(customer_charge_minor=12000,host_payout_minor=7000,reseller_earning_minor=1500,payment_cost_minor=500,minimum_khan_margin_minor=2500);assert x["khan_cloud_margin_minor"]==3000
