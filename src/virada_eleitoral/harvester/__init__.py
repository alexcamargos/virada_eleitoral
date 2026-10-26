"""Subpacote de coleta, integridade e streaming de Boletins de Urna (agent-harvester)."""

from virada_eleitoral.harvester.local_provider import LocalBuProvider
from virada_eleitoral.harvester.manifest import (
    ManifestManager,
    compute_sha512,
    verify_file_integrity,
)
from virada_eleitoral.harvester.remote_provider import RemoteTseBuProvider

__all__ = [
    "LocalBuProvider",
    "ManifestManager",
    "RemoteTseBuProvider",
    "compute_sha512",
    "verify_file_integrity",
]
