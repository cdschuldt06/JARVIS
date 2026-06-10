from dataclasses import dataclass


@dataclass(frozen=True)
class DeviceAgentDescriptor:
    device_id: str
    display_name: str
    platform: str
    permissions: tuple[str, ...] = ()
    online: bool = False
