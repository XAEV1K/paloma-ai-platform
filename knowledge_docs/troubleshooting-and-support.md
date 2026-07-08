# Paloma365 Support — Troubleshooting Guide

## Delivery orders not appearing in the kitchen queue

Check three things in order. First, the aggregator connection status in
Settings, Integrations: a red badge means the marketplace token expired
and needs re-authorisation. Second, verify the venue is marked "open" in
the aggregator's own dashboard. Third, confirm the kitchen display
terminal is on the same local network as the POS. Ninety percent of cases
are the expired token.

## Loyalty points not accruing

Points accrue only for orders linked to a guest profile. If the cashier
skipped the phone number prompt, the order is anonymous and earns nothing.
Enable "require guest phone for loyalty categories" in CRM settings to
prevent this. Also check that the order category participates in the
accrual rules — alcohol and tobacco are excluded by default in Kazakhstan.

## QR menu shows an outdated menu

The QR menu caches for five minutes. If changes are older than that and
still missing, the menu was likely edited in a draft: open Menu Editor and
press Publish. Photos larger than 5 MB are rejected silently by older app
versions — keep photos between 200 KB and 2 MB.

## Courier app loses GPS during deliveries

Battery optimisation on Android kills background GPS. Ask couriers to
exclude the Paloma365 Courier app from battery optimisation and to keep
location mode on "high accuracy". Devices older than Android 10 are not
supported for live tracking.

## How to reach support

Business hours support (09:00–21:00 Almaty time) responds within 15
minutes in the in-app chat. Critical incidents (POS down, payments
failing) have a 24/7 hotline with a one-hour resolution target. Every
venue has a dedicated success manager for non-urgent questions.
