from django.urls import path

from .views import (
    booking_request_collection_view,
    fee_schedule_pricing_collection_view,
    schedule_opportunity_collection_view,
)


urlpatterns = [
    path("booking-requests/", booking_request_collection_view, name="driller-booking-collection"),
    path("opportunities/", schedule_opportunity_collection_view, name="driller-opportunity-collection"),
    path("fee-schedule-pricing/", fee_schedule_pricing_collection_view, name="driller-fee-schedule-pricing-collection"),
]
