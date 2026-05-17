"""Block 24 — Sandboxing framework types (v1.0, D-152).

Defines the interface for sandboxed execution environments used by the
Evolution Engine (Block 21) and experimental workers.

SANDBOXING_ACTIVE is False in production. All callers must check this flag
before attempting to instantiate or use a SandboxRunner. Attempting to
execute in an unchecked production path is a D-006 violation (irreversible
action without confirmation gate) and a D-004 alignment boundary breach.

Sandbox types:
  PROCESS  — isolated subprocess with restricted capabilities and resource limits.
             Lowest overhead. Appropriate for pure-Python workers with no network
             or filesystem access required.
  CONTAINER — Docker container with explicit capability declarations. Higher
              overhead. Required for workers that need network access or
              filesystem isolation. Experimental environments use this type
              (D-022).

Usage (post-activation only):
    from sandboxing import SANDBOXING_ACTIVE, SandboxSpec, SandboxType
    from sandboxing.runners import ProcessRunner  # not yet implemented

    if not SANDBOXING_ACTIVE:
        raise RuntimeError("Sandboxing is not active — cannot execute in sandbox")

    spec = SandboxSpec(
        sandbox_type=SandboxType.PROCESS,
        capability_declarations=["read:personal"],
        execution_scope="personal",
        max_duration_seconds=30,
    )
    runner = ProcessRunner()
    result = await runner.execute(spec, fn=my_worker_fn, args={})
"""

from __future__ import annotations

import abc
from dataclasses import dataclass, field
from enum import Enum

# Production guard — must be False until Block 21 is activated post-v1.0.
# Changing this to True in production without a recorded activation decision
# violates D-004 (alignment boundary) and D-042 (Block 21 paused).
SANDBOXING_ACTIVE: bool = False


class SandboxType(Enum):
    """Execution isolation model for a sandboxed worker.

    PROCESS:
        Isolated subprocess with restricted capabilities. No network access.
        Resource-limited via OS-level controls. Appropriate for pure computation
        workers (e.g. digest generation from in-memory data).

    CONTAINER:
        Docker container with explicit capability declarations. Network access
        is opt-in per capability declaration. Required for workers that fetch
        external data or write to filesystem paths outside the data volume.
        Experimental environments always use CONTAINER (D-022).
    """

    PROCESS = "process"
    CONTAINER = "container"


@dataclass
class SandboxSpec:
    """Specification for a sandboxed execution environment.

    Attributes:
        sandbox_type: Isolation model to use (PROCESS or CONTAINER).
        capability_declarations: Explicit list of capabilities the worker
            requires. Block 13 validates these against the tool registry
            entry before allowing execution. Unlisted capabilities are
            denied. Example: ["read:personal", "write:notifications"].
        execution_scope: Zone name the worker operates within. Determines
            which data the worker can access. Must match a registered zone
            in clive_state.zones. Default "personal".
        max_duration_seconds: Hard timeout. Worker is killed after this
            duration regardless of state. Default 300 (5 minutes).
        network_allowed: Whether outbound network access is permitted.
            Only valid for CONTAINER type. PROCESS type always has
            network_allowed=False regardless of this field.
        memory_limit_mb: Maximum memory allocation in megabytes.
            Default 256 MB.
    """

    sandbox_type: SandboxType
    capability_declarations: list[str] = field(default_factory=list)
    execution_scope: str = "personal"
    max_duration_seconds: int = 300
    network_allowed: bool = False
    memory_limit_mb: int = 256

    def __post_init__(self) -> None:
        if self.sandbox_type == SandboxType.PROCESS and self.network_allowed:
            raise ValueError(
                "SandboxType.PROCESS does not support network_allowed=True. "
                "Use SandboxType.CONTAINER for workers that require network access."
            )
        if self.max_duration_seconds < 1:
            raise ValueError("max_duration_seconds must be >= 1")
        if self.memory_limit_mb < 32:
            raise ValueError("memory_limit_mb must be >= 32")


class SandboxRunner(abc.ABC):
    """Abstract base class for sandboxed execution runners.

    Concrete implementations (ProcessRunner, ContainerRunner) are not
    provided in the v1.0 stub. They will be implemented when Block 21
    is activated post-v1.0.

    All runners must:
    - Check SANDBOXING_ACTIVE before executing and raise if False.
    - Enforce the capability_declarations in the SandboxSpec.
    - Enforce max_duration_seconds as a hard kill timeout.
    - Log execution start, completion, and failure to Block 16 audit log.
    - Return a result dict with at minimum: {success: bool, output: any,
      duration_seconds: float, sandbox_type: str}.
    - Be idempotent on re-delivery (D-025).
    """

    @abc.abstractmethod
    async def execute(self, spec: SandboxSpec, fn: object, args: dict) -> dict:
        """Execute fn with args inside the sandbox defined by spec.

        Args:
            spec: Sandbox specification (type, capabilities, scope, limits).
            fn: Callable to execute. Must be serialisable for CONTAINER type.
            args: Keyword arguments to pass to fn.

        Returns:
            dict with keys: success (bool), output (any), duration_seconds
            (float), sandbox_type (str), capabilities_used (list[str]).

        Raises:
            RuntimeError: If SANDBOXING_ACTIVE is False.
            TimeoutError: If execution exceeds max_duration_seconds.
            PermissionError: If fn attempts to use an undeclared capability.
        """
        raise NotImplementedError
