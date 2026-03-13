"""Event parsing convention.

JSON-RPC notifications follow the pattern ``notifications/{component_type}.{event}``.
Each component defines its own ``parse_{component}_event(params)`` in its events module.
Callers match on ``msg.method`` and call the right parser directly.
"""
