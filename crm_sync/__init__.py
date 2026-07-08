"""CRM Sync: external CRM → normalized events → memory & analytics.

The flow is deterministic Python end to end — no LLM anywhere::

    Bitrix webhook ──► Normalizer ──► internal event ──► Event Bus
                                             │
                                             └──► Customer Memory

The connector is a port: :class:`SimulatedBitrixConnector` replays
realistic webhook payloads from a local inbox file (the agreed
simulation — no Docker/live CRM), and a real webhook receiver later
implements the same two methods.
"""

from crm_sync.connector import CrmConnectorPort, SimulatedBitrixConnector
from crm_sync.models import CrmContact, CrmDeal, NormalizedCrmEvent
from crm_sync.normalizer import BitrixNormalizer
from crm_sync.service import CrmSyncReport, CrmSyncService

__all__ = [
    "BitrixNormalizer",
    "CrmConnectorPort",
    "CrmContact",
    "CrmDeal",
    "CrmSyncReport",
    "CrmSyncService",
    "NormalizedCrmEvent",
    "SimulatedBitrixConnector",
]
