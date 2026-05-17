"""Tests for Block 24 sandboxing stub (v1.0, D-153 AC-1).

Verifies:
- Package is importable
- SANDBOXING_ACTIVE is False (production guard)
- SandboxSpec validates correctly
- SandboxRunner is abstract (cannot be instantiated directly)
"""

from __future__ import annotations

import pytest

from sandboxing import SANDBOXING_ACTIVE, SandboxRunner, SandboxSpec, SandboxType


# ── Production guard ──────────────────────────────────────────────────────────

def test_sandboxing_not_active_by_default():
    """SANDBOXING_ACTIVE must be False — no production activation without D-042 decision."""
    assert SANDBOXING_ACTIVE is False


# ── SandboxType ───────────────────────────────────────────────────────────────

def test_sandbox_type_values():
    assert SandboxType.PROCESS.value == "process"
    assert SandboxType.CONTAINER.value == "container"


# ── SandboxSpec validation ────────────────────────────────────────────────────

def test_sandbox_spec_valid_process():
    spec = SandboxSpec(
        sandbox_type=SandboxType.PROCESS,
        capability_declarations=["read:personal"],
        execution_scope="personal",
        max_duration_seconds=30,
    )
    assert spec.sandbox_type == SandboxType.PROCESS
    assert spec.capability_declarations == ["read:personal"]
    assert spec.execution_scope == "personal"
    assert spec.max_duration_seconds == 30
    assert spec.network_allowed is False


def test_sandbox_spec_valid_container_with_network():
    spec = SandboxSpec(
        sandbox_type=SandboxType.CONTAINER,
        capability_declarations=["read:personal", "write:notifications"],
        network_allowed=True,
        max_duration_seconds=120,
    )
    assert spec.network_allowed is True


def test_sandbox_spec_process_network_raises():
    """PROCESS type cannot have network_allowed=True."""
    with pytest.raises(ValueError, match="network_allowed"):
        SandboxSpec(
            sandbox_type=SandboxType.PROCESS,
            network_allowed=True,
        )


def test_sandbox_spec_zero_duration_raises():
    with pytest.raises(ValueError, match="max_duration_seconds"):
        SandboxSpec(sandbox_type=SandboxType.PROCESS, max_duration_seconds=0)


def test_sandbox_spec_low_memory_raises():
    with pytest.raises(ValueError, match="memory_limit_mb"):
        SandboxSpec(sandbox_type=SandboxType.PROCESS, memory_limit_mb=16)


def test_sandbox_spec_defaults():
    spec = SandboxSpec(sandbox_type=SandboxType.PROCESS)
    assert spec.capability_declarations == []
    assert spec.execution_scope == "personal"
    assert spec.max_duration_seconds == 300
    assert spec.memory_limit_mb == 256


# ── SandboxRunner abstract ────────────────────────────────────────────────────

def test_sandbox_runner_is_abstract():
    """SandboxRunner cannot be instantiated — must be subclassed."""
    with pytest.raises(TypeError):
        SandboxRunner()  # type: ignore[abstract]


def test_sandbox_runner_subclass_must_implement_execute():
    """Concrete subclass without execute() cannot be instantiated."""

    class BrokenRunner(SandboxRunner):
        pass  # forgot to implement execute()

    with pytest.raises(TypeError):
        BrokenRunner()


def test_sandbox_runner_concrete_subclass_is_instantiable():
    """Concrete subclass that implements execute() can be instantiated."""

    class StubRunner(SandboxRunner):
        async def execute(self, spec: SandboxSpec, fn: object, args: dict) -> dict:
            return {
                "success": True,
                "output": None,
                "duration_seconds": 0.0,
                "sandbox_type": spec.sandbox_type.value,
                "capabilities_used": [],
            }

    runner = StubRunner()
    assert runner is not None
