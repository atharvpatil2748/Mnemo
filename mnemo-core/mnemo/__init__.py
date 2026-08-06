"""Mnemo core package."""

from .registry import (
    PLUGIN_ENTRY_POINT_GROUP,
    PLUGIN_INTERFACE_VERSION,
    CapabilityKind,
    PluginCompatibilityError,
    PluginDescriptor,
    PluginDiscoveryError,
    PluginInterface,
    PluginInterfaceV1,
    PluginLoadResult,
    PluginRegistry,
    PluginSource,
    PluginValidationError,
    RegistrationConflictError,
    RegistrationDescriptor,
    RegistryError,
    RegistryFrozenError,
    RegistryState,
)

__version__ = "0.0.0"

__all__ = [
    "PLUGIN_ENTRY_POINT_GROUP",
    "PLUGIN_INTERFACE_VERSION",
    "CapabilityKind",
    "PluginCompatibilityError",
    "PluginDescriptor",
    "PluginDiscoveryError",
    "PluginInterface",
    "PluginInterfaceV1",
    "PluginLoadResult",
    "PluginRegistry",
    "PluginSource",
    "PluginValidationError",
    "RegistrationConflictError",
    "RegistrationDescriptor",
    "RegistryError",
    "RegistryFrozenError",
    "RegistryState",
    "__version__",
]
