"""
Anthem A/V setup flow implementation.

:copyright: (c) 2025 by Meir Miyara.
:license: MPL-2.0, see LICENSE for more details.
"""

import asyncio
import logging

from ucapi_framework import BaseSetupFlow
from ucapi.api_definitions import (
    IntegrationSetupError,
    SetupError,
)

from uc_intg_anthemav.config import AnthemDeviceConfig, ZoneConfig
from uc_intg_anthemav.device import AnthemDevice

_LOG = logging.getLogger(__name__)


class AnthemSetupFlow(BaseSetupFlow):
    """Setup flow for Anthem A/V receivers."""
    
    def get_manual_entry_form(self) -> dict:
        """Return manual entry configuration form."""
        return {
            "title": {"en": "Anthem A/V Receiver Setup"},
            "settings": [
                {
                    "id": "host",
                    "label": {"en": "IP Address"},
                    "description": {"en": "IP address of your Anthem receiver"},
                    "field": {"text": {"value": "192.168.1.100"}}
                },
                {
                    "id": "port",
                    "label": {"en": "Port"},
                    "description": {"en": "TCP port number (default: 14999)"},
                    "field": {"text": {"value": "14999"}}
                },
                {
                    "id": "name",
                    "label": {"en": "Device Name"},
                    "description": {"en": "Friendly name for your receiver"},
                    "field": {"text": {"value": "Anthem"}}
                },
                {
                    "id": "model",
                    "label": {"en": "Model Series"},
                    "description": {"en": "Select your Anthem model series"},
                    "field": {
                        "dropdown": {
                            "items": [
                                {"id": "MRX", "label": {"en": "MRX Series (520, 720, 1120, 1140)"}},
                                {"id": "AVM", "label": {"en": "AVM Series (60, 70, 90)"}},
                                {"id": "STR", "label": {"en": "STR Series"}}
                            ]
                        }
                    }
                },
                {
                    "id": "zones",
                    "label": {"en": "Number of Zones"},
                    "description": {"en": "How many zones does your receiver have?"},
                    "field": {
                        "dropdown": {
                            "items": [
                                {"id": "1", "label": {"en": "1 Zone"}},
                                {"id": "2", "label": {"en": "2 Zones"}},
                                {"id": "3", "label": {"en": "3 Zones"}}
                            ]
                        }
                    }
                }
            ]
        }
    
    async def query_device(self, input_values: dict) -> AnthemDeviceConfig:
        """Query device and return configuration."""
        host = input_values.get("host", "").strip()
        if not host:
            raise SetupError(IntegrationSetupError.OTHER, "IP address is required")
        
        port = int(input_values.get("port", 14999))
        name = input_values.get("name", f"Anthem ({host})").strip()
        model = input_values.get("model", "MRX").strip()
        zones_count = int(input_values.get("zones", "1"))
        
        identifier = f"anthem_{host.replace('.', '_')}_{port}"
        
        zones = [ZoneConfig(zone_number=i) for i in range(1, zones_count + 1)]
        
        device_config = AnthemDeviceConfig(
            identifier=identifier,
            name=name,
            host=host,
            model=model,
            port=port,
            zones=zones
        )
        
        _LOG.info(f"Testing connection to Anthem at {host}:{port}")
        
        test_device = AnthemDevice(device_config)
        
        try:
            connection_successful = await test_device.connect()
            
            if not connection_successful:
                _LOG.error(f"Connection test failed for host: {host}")
                raise SetupError(IntegrationSetupError.CONNECTION_REFUSED)
            
            _LOG.info("Connection successful, verifying device responds...")
            await test_device.query_model()
            await asyncio.sleep(0.2)
            await test_device.query_power(1)
            await asyncio.sleep(0.5)
            
            response_timeout = 3.0
            start_time = asyncio.get_event_loop().time()
            received_response = False
            
            while (asyncio.get_event_loop().time() - start_time) < response_timeout:
                if test_device.get_cached_state("model"):
                    received_response = True
                    _LOG.info(f"Received response from device: {test_device.get_cached_state('model')}")
                    break
                await asyncio.sleep(0.1)
            
            if not received_response:
                _LOG.warning("No response received during connection test (may still work)")
            
            _LOG.info(f"Successfully validated Anthem receiver at {host}:{port}")
            return device_config
            
        except SetupError:
            raise
        except Exception as e:
            _LOG.error(f"Connection test error: {e}", exc_info=True)
            raise SetupError(IntegrationSetupError.OTHER)
        finally:
            await test_device.disconnect()