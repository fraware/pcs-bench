"""Cross-repo CLI adapters."""

from pcs_bench.adapters.base import AdapterStatus, CommandResult, RepoAdapter
from pcs_bench.adapters.certifyedge import CertifyEdgeAdapter
from pcs_bench.adapters.labtrust import LabTrustAdapter
from pcs_bench.adapters.pcs_core import PcsCoreAdapter
from pcs_bench.adapters.provability_fabric import ProvabilityFabricAdapter
from pcs_bench.adapters.scientific_memory import ScientificMemoryAdapter

__all__ = [
    "AdapterStatus",
    "CommandResult",
    "RepoAdapter",
    "PcsCoreAdapter",
    "LabTrustAdapter",
    "CertifyEdgeAdapter",
    "ProvabilityFabricAdapter",
    "ScientificMemoryAdapter",
]
