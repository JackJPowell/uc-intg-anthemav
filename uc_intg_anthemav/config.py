"""
Configuration dataclasses for Anthem A/V integration.

:copyright: (c) 2025 by Meir Miyara.
:license: MPL-2.0, see LICENSE for more details.
"""

from dataclasses import dataclass, field


@dataclass
class ZoneConfig:
    """Configuration for a single zone."""
    zone_number: int
    enabled: bool = True
    name: str | None = None
    
    def __post_init__(self):
        if self.name is None:
            self.name = f"Zone {self.zone_number}"


@dataclass
class AnthemDeviceConfig:
    """Configuration for an Anthem A/V receiver/processor."""
    identifier: str
    name: str
    host: str
    model: str
    port: int = 14999
    timeout: int = 10
    zones: list[ZoneConfig] = field(default_factory=lambda: [ZoneConfig(1)])
    
    def __post_init__(self):
        """Ensure zones is a list of ZoneConfig objects."""
        if self.zones and isinstance(self.zones[0], dict):
            self.zones = [ZoneConfig(**z) if isinstance(z, dict) else z for z in self.zones]