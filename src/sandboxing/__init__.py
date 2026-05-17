"""Block 24 — Sandboxing framework stub (v1.0, D-152).

This package defines the sandboxing interface that the Evolution Engine
(Block 21) will use when activated post-v1.0. It is NOT active in production.

All production code must check SANDBOXING_ACTIVE before using any runner.
No production service imports or instantiates a SandboxRunner.

Activation requires an explicit owner decision after v1.0 sign-off (D-042).

Design references:
  D-022 — Experimental zone on separate infrastructure
  D-029 — Block 21 uses parameterised IaC templates
  D-030 — Experimental events are a distinct trust class
  D-042 — Block 21 paused; unblocked by v1.0 sign-off
"""

from .types import SANDBOXING_ACTIVE, SandboxRunner, SandboxSpec, SandboxType

__all__ = ["SANDBOXING_ACTIVE", "SandboxRunner", "SandboxSpec", "SandboxType"]
