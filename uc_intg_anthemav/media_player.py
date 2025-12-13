"""
Anthem Media Player entity implementation.

:copyright: (c) 2025 by Meir Miyara.
:license: MPL-2.0, see LICENSE for more details.
"""

import logging
from typing import Any

from ucapi import StatusCodes
from ucapi.media_player import Attributes, Commands, DeviceClasses, Features, MediaPlayer, States, Options
from ucapi_framework import DeviceEvents

from uc_intg_anthemav.config import AnthemDeviceConfig, ZoneConfig
from uc_intg_anthemav.device import AnthemDevice

_LOG = logging.getLogger(__name__)


class AnthemMediaPlayer(MediaPlayer):
    """Media player entity for Anthem A/V receiver zone."""
    
    def __init__(
        self,
        entity_id: str,
        device: AnthemDevice,
        device_config: AnthemDeviceConfig,
        zone_config: ZoneConfig
    ):
        self._device = device
        self._device_config = device_config
        self._zone_config = zone_config
        
        if zone_config.zone_number == 1:
            entity_name = device_config.name
        else:
            entity_name = f"{device_config.name} {zone_config.name}"
        
        features = [
            Features.ON_OFF,
            Features.VOLUME,
            Features.VOLUME_UP_DOWN,
            Features.MUTE_TOGGLE,
            Features.MUTE,
            Features.UNMUTE,
            Features.SELECT_SOURCE
        ]
        
        source_list = [
            "HDMI 1", "HDMI 2", "HDMI 3", "HDMI 4",
            "HDMI 5", "HDMI 6", "HDMI 7", "HDMI 8",
            "Analog 1", "Analog 2",
            "Digital 1", "Digital 2",
            "USB", "Network", "ARC"
        ]
        
        attributes = {
            Attributes.STATE: States.UNAVAILABLE,
            Attributes.VOLUME: 0,
            Attributes.MUTED: False,
            Attributes.SOURCE: "",
            Attributes.SOURCE_LIST: source_list
        }
        
        options = {
            Options.SIMPLE_COMMANDS: [
                Commands.ON,
                Commands.OFF,
                Commands.VOLUME_UP,
                Commands.VOLUME_DOWN,
                Commands.MUTE_TOGGLE
            ]
        }
        
        super().__init__(
            entity_id,
            entity_name,
            features,
            attributes,
            device_class=DeviceClasses.RECEIVER,
            area=device_config.name if zone_config.zone_number > 1 else None,
            cmd_handler=self.handle_command,
            options=options
        )
        
        self._device.events.on(DeviceEvents.UPDATE, self._on_device_update)
        self._device.events.on(DeviceEvents.CONNECTED, self._on_device_connected)
        self._device.events.on(DeviceEvents.DISCONNECTED, self._on_device_disconnected)
    
    def _on_device_update(self, device_id: str, update_data: dict[str, Any]) -> None:
        """Handle device state updates."""
        if device_id != self._device_config.identifier:
            return
        
        if "zone" in update_data:
            if update_data["zone"] == self._zone_config.zone_number:
                zone_state = update_data.get("state", {})
                self._update_attributes_from_state(zone_state)
        
        if update_data.get("inputs_discovered"):
            source_list = self._device.get_input_list()
            if self.attributes.get(Attributes.SOURCE_LIST) != source_list:
                self.attributes[Attributes.SOURCE_LIST] = source_list
    
    def _on_device_connected(self, device_id: str) -> None:
        """Handle device connection."""
        if device_id != self._device_config.identifier:
            return
        
        _LOG.info(f"Device {self._device_config.name} connected, querying zone {self._zone_config.zone_number} status")
    
    def _on_device_disconnected(self, device_id: str) -> None:
        """Handle device disconnection."""
        if device_id != self._device_config.identifier:
            return
        
        self.attributes[Attributes.STATE] = States.UNAVAILABLE
        _LOG.warning(f"Device {self._device_config.name} disconnected, zone {self._zone_config.zone_number} unavailable")
    
    def _update_attributes_from_state(self, zone_state: dict[str, Any]) -> None:
        """Update entity attributes from zone state."""
        updated_attrs = {}
        
        if "power" in zone_state:
            new_state = States.ON if zone_state["power"] else States.OFF
            if self.attributes.get(Attributes.STATE) != new_state:
                updated_attrs[Attributes.STATE] = new_state
        
        if "volume" in zone_state:
            volume_db = zone_state["volume"]
            volume_pct = self._db_to_percentage(volume_db)
            if abs(self.attributes.get(Attributes.VOLUME, 0) - volume_pct) > 0.01:
                updated_attrs[Attributes.VOLUME] = volume_pct
        
        if "muted" in zone_state:
            if self.attributes.get(Attributes.MUTED) != zone_state["muted"]:
                updated_attrs[Attributes.MUTED] = zone_state["muted"]
        
        if "input_name" in zone_state:
            if self.attributes.get(Attributes.SOURCE) != zone_state["input_name"]:
                updated_attrs[Attributes.SOURCE] = zone_state["input_name"]
                if zone_state["input_name"]:
                    updated_attrs[Attributes.MEDIA_TITLE] = zone_state["input_name"]
        
        if "audio_format" in zone_state:
            if zone_state["audio_format"]:
                updated_attrs[Attributes.MEDIA_TYPE] = zone_state["audio_format"]
        
        if updated_attrs:
            self.attributes.update(updated_attrs)
    
    def _db_to_percentage(self, db_value: int) -> float:
        """Convert dB value to percentage (0-100)."""
        db_range = 90
        percentage = ((db_value + 90) / db_range) * 100
        return max(0.0, min(100.0, percentage))
    
    def _percentage_to_db(self, percentage: float) -> int:
        """Convert percentage to dB value (-90 to 0)."""
        db_range = 90
        db_value = int((percentage * db_range / 100) - 90)
        return max(-90, min(0, db_value))
    
    async def handle_command(self, entity: MediaPlayer, cmd_id: str, params: dict[str, Any] | None) -> StatusCodes:
        """Handle entity commands."""
        _LOG.info(f"Command {cmd_id} for {self.id}")
        
        try:
            zone = self._zone_config.zone_number
            
            if cmd_id == Commands.ON:
                success = await self._device.power_on(zone)
                return StatusCodes.OK if success else StatusCodes.SERVER_ERROR
            
            elif cmd_id == Commands.OFF:
                success = await self._device.power_off(zone)
                return StatusCodes.OK if success else StatusCodes.SERVER_ERROR
            
            elif cmd_id == Commands.VOLUME:
                if params and "volume" in params:
                    volume_pct = float(params["volume"])
                    volume_db = self._percentage_to_db(volume_pct)
                    success = await self._device.set_volume(volume_db, zone)
                    return StatusCodes.OK if success else StatusCodes.SERVER_ERROR
                return StatusCodes.BAD_REQUEST
            
            elif cmd_id == Commands.VOLUME_UP:
                success = await self._device.volume_up(zone)
                return StatusCodes.OK if success else StatusCodes.SERVER_ERROR
            
            elif cmd_id == Commands.VOLUME_DOWN:
                success = await self._device.volume_down(zone)
                return StatusCodes.OK if success else StatusCodes.SERVER_ERROR
            
            elif cmd_id == Commands.MUTE_TOGGLE:
                current_mute = self.attributes.get(Attributes.MUTED, False)
                success = await self._device.set_mute(not current_mute, zone)
                return StatusCodes.OK if success else StatusCodes.SERVER_ERROR
            
            elif cmd_id == Commands.MUTE:
                success = await self._device.set_mute(True, zone)
                return StatusCodes.OK if success else StatusCodes.SERVER_ERROR
            
            elif cmd_id == Commands.UNMUTE:
                success = await self._device.set_mute(False, zone)
                return StatusCodes.OK if success else StatusCodes.SERVER_ERROR
            
            elif cmd_id == Commands.SELECT_SOURCE:
                if params and "source" in params:
                    source_name = params["source"]
                    input_num = self._device.get_input_number_by_name(source_name)
                    if input_num is not None:
                        success = await self._device.select_input(input_num, zone)
                        return StatusCodes.OK if success else StatusCodes.SERVER_ERROR
                    return StatusCodes.BAD_REQUEST
                return StatusCodes.BAD_REQUEST
            
            else:
                _LOG.debug(f"Suppressing unsupported command: {cmd_id}")
                return StatusCodes.OK
        
        except Exception as e:
            _LOG.error(f"Error executing command {cmd_id}: {e}")
            return StatusCodes.SERVER_ERROR
    
    async def push_update(self) -> None:
        """Query device for current state."""
        await self._device.query_all_status(self._zone_config.zone_number)
    
    @property
    def zone_number(self) -> int:
        """Get zone number."""
        return self._zone_config.zone_number