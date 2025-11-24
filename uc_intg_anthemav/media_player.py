"""
Anthem Media Player entity implementation.

:copyright: (c) 2025 by Meir Miyara.
:license: MPL-2.0, see LICENSE for more details.
"""

import logging
from typing import Any, Dict, Optional

from ucapi import StatusCodes
from ucapi.media_player import Attributes, Commands, DeviceClasses, Features, MediaPlayer, States

from uc_intg_anthemav.client import AnthemClient
from uc_intg_anthemav.config import DeviceConfig, ZoneConfig

_LOG = logging.getLogger(__name__)


class AnthemMediaPlayer(MediaPlayer):
    
    def __init__(
        self,
        client: AnthemClient,
        device_config: DeviceConfig,
        zone_config: ZoneConfig,
        api
    ):
        self._client = client
        self._device_config = device_config
        self._zone_config = zone_config
        self._api = api
        
        entity_id = f"anthem_{device_config.device_id}_zone{zone_config.zone_number}"
        
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
        
        super().__init__(
            entity_id,
            entity_name,
            features,
            attributes,
            device_class=DeviceClasses.RECEIVER,
            area=device_config.name if zone_config.zone_number > 1 else None,
            cmd_handler=self.handle_command
        )
        
        self._client.set_update_callback(self._on_device_update)
        
    def _on_device_update(self, message: str) -> None:
        zone_state = self._client.get_zone_state(self._zone_config.zone_number)
        
        if zone_state:
            self._update_attributes_from_state(zone_state)
    
    def _update_attributes_from_state(self, zone_state: Dict[str, Any]) -> None:
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
            
            if self._api and self._api.configured_entities.contains(self.id):
                self._api.configured_entities.update_attributes(
                    self.id,
                    updated_attrs
                )
    
    def _db_to_percentage(self, db_value: int) -> float:
        db_range = 90
        percentage = ((db_value + 90) / db_range) * 100
        return max(0.0, min(100.0, percentage))
    
    def _percentage_to_db(self, percentage: float) -> int:
        db_range = 90
        db_value = int((percentage * db_range) - 90)
        return max(-90, min(0, db_value))
    
    async def handle_command(self, entity: MediaPlayer, cmd_id: str, params: Optional[Dict[str, Any]]) -> StatusCodes:
        _LOG.info(f"Received command {cmd_id} for {self.id}")
        
        try:
            zone = self._zone_config.zone_number
            
            if cmd_id == Commands.ON:
                success = await self._client.power_on(zone)
                return StatusCodes.OK if success else StatusCodes.SERVER_ERROR
            
            elif cmd_id == Commands.OFF:
                success = await self._client.power_off(zone)
                return StatusCodes.OK if success else StatusCodes.SERVER_ERROR
            
            elif cmd_id == Commands.VOLUME:
                if params and "volume" in params:
                    volume_pct = float(params["volume"])
                    volume_db = self._percentage_to_db(volume_pct)
                    success = await self._client.set_volume(volume_db, zone)
                    return StatusCodes.OK if success else StatusCodes.SERVER_ERROR
                return StatusCodes.BAD_REQUEST
            
            elif cmd_id == Commands.VOLUME_UP:
                success = await self._client.volume_up(zone)
                return StatusCodes.OK if success else StatusCodes.SERVER_ERROR
            
            elif cmd_id == Commands.VOLUME_DOWN:
                success = await self._client.volume_down(zone)
                return StatusCodes.OK if success else StatusCodes.SERVER_ERROR
            
            elif cmd_id == Commands.MUTE_TOGGLE:
                current_mute = self.attributes.get(Attributes.MUTED, False)
                success = await self._client.set_mute(not current_mute, zone)
                return StatusCodes.OK if success else StatusCodes.SERVER_ERROR
            
            elif cmd_id == Commands.MUTE:
                success = await self._client.set_mute(True, zone)
                return StatusCodes.OK if success else StatusCodes.SERVER_ERROR
            
            elif cmd_id == Commands.UNMUTE:
                success = await self._client.set_mute(False, zone)
                return StatusCodes.OK if success else StatusCodes.SERVER_ERROR
            
            elif cmd_id == Commands.SELECT_SOURCE:
                if params and "source" in params:
                    source_name = params["source"]
                    input_num = self._get_input_number(source_name)
                    if input_num is not None:
                        success = await self._client.select_input(input_num, zone)
                        return StatusCodes.OK if success else StatusCodes.SERVER_ERROR
                    return StatusCodes.BAD_REQUEST
                return StatusCodes.BAD_REQUEST
            
            else:
                _LOG.debug(f"Suppressing unsupported command: {cmd_id}")
                return StatusCodes.OK
        
        except Exception as e:
            _LOG.error(f"Error executing command {cmd_id}: {e}")
            return StatusCodes.SERVER_ERROR
    
    def _get_input_number(self, source_name: str) -> Optional[int]:
        input_map = {
            "HDMI 1": 1,
            "HDMI 2": 2,
            "HDMI 3": 3,
            "HDMI 4": 4,
            "HDMI 5": 5,
            "HDMI 6": 6,
            "HDMI 7": 7,
            "HDMI 8": 8,
            "Analog 1": 9,
            "Analog 2": 10,
            "Digital 1": 11,
            "Digital 2": 12,
            "USB": 13,
            "Network": 14,
            "ARC": 15
        }
        
        return input_map.get(source_name)
    
    async def push_update(self) -> None:
        await self._client.query_all_status(self._zone_config.zone_number)
    
    @property
    def zone_number(self) -> int:
        return self._zone_config.zone_number