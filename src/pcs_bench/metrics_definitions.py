"""Shared metric constants (aligned with pcs-core benchmark methodology)."""

REQUIRED_MEMORY_SECTIONS = [
    "Claim",
    "Workflow Profile",
    "Runtime Evidence",
    "Certificate or Witness",
    "Verification Result",
    "Formal Trust Kernel",
    "Release Manifest",
    "Release Chain Validation",
    "Artifact Registry",
    "Handoff Manifests",
    "Artifact Dependency Graph",
    "Lineage",
    "Staleness",
    "Artifact Hashes",
    "Source Repositories",
    "Reproduce / Verify",
    "Limitations",
]

CERTIFICATE_REQUIRED_FIELDS = [
    "certificate_id",
    "witness_id",
    "trace_hash",
    "result_hashes",
    "property_id",
    "checker",
    "checker_version",
    "status",
    "source_repo",
    "source_commit",
    "signature_or_digest",
]
