# Paloma365 Delivery Module — Operations Manual

## Overview

The Delivery module turns a dine-in venue into a delivery business without
third-party lock-in. It covers courier dispatch, delivery zones with
per-zone fees, live GPS tracking and native ingestion of aggregator orders
(Glovo, Wolt, Yandex Eda) into a single kitchen queue.

## Courier dispatch

Orders enter the dispatch board the moment the kitchen bumps them. The
dispatcher assigns a courier manually or enables auto-assign, which picks
the nearest idle courier by GPS position. Each courier uses the Paloma365
Courier app; customers receive SMS or push notifications at "accepted",
"picked up" and "arriving" stages.

## Delivery zones and fees

Zones are drawn on the map as polygons. Each zone has its own delivery fee,
minimum order value and estimated time. Orders outside all zones are
rejected at checkout with a clear message, which prevents unprofitable
long-distance runs.

## Aggregator integration

Aggregator orders arrive through the marketplace API and appear in the same
kitchen display queue as native orders. Menu synchronisation is one-way:
Paloma365 is the source of truth, aggregator menus update within minutes.
Note that aggregator commissions are billed by the aggregators themselves
and are not part of the module subscription.

## Requirements and limitations

The module requires at least one dedicated courier on staff. GPS tracking
requires Android 10+ on courier devices. Typical onboarding takes three to
five working days including zone setup and staff training.

## Pricing

Setup fee 90,000 KZT, subscription 25,000 KZT per month per location.
The setup includes zone configuration, aggregator connection and two
training sessions for dispatchers.
