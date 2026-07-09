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

# NOTE: CrmSyncService is intentionally NOT re-exported here. The service
# depends on services.customer_memory, which itself uses crm_sync.models —
# re-exporting it from the package __init__ would close an import cycle.
# Import it explicitly: ``from crm_sync.service import CrmSyncService``.

__all__ = [
    "BitrixNormalizer",
    "CrmConnectorPort",
    "CrmContact",
    "CrmDeal",
    "NormalizedCrmEvent",
    "SimulatedBitrixConnector",
]
