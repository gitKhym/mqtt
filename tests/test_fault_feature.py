import sys
import json
from unittest.mock import MagicMock
import pytest

sys.modules["sense_hat"] = MagicMock()

from models.status import Status


class TestAgentFaultBehaviour:
    def setup_method(self):
        from agent import Agent
        self.Agent = Agent

    def test_agent_triggers_fault_warning_on_fault_status_mqtt(self, monkeypatch):
        agent = self.Agent()
        agent.sense = MagicMock()

        # Avoid sleeping during flashing 
        monkeypatch.setattr("agent.time.sleep", lambda *_: None)

        # Spy on fault handling methods
        agent._trigger_fault_warning = MagicMock()
        agent._clear_warning = MagicMock()

        # Simulate MQTT message on rooms/<id>/command with status Fault
        from paho.mqtt.client import Client, MQTTMessage
        client_mock = MagicMock(spec=Client)
        msg_mock = MagicMock(spec=MQTTMessage)
        msg_mock.topic = "rooms/1/command"
        msg_mock.payload = json.dumps({"status": "Fault"}).encode()

        agent._on_mqtt_message(client_mock, None, msg_mock)

        # Should update cache and trigger warning
        assert agent.rooms["1"]["status"] == "Fault"
        agent._trigger_fault_warning.assert_called_once()
        agent._clear_warning.assert_not_called()

    def test_agent_clears_warning_when_no_fault_rooms(self, monkeypatch):
        agent = self.Agent()
        agent.sense = MagicMock()

        monkeypatch.setattr("agent.time.sleep", lambda *_: None)

        agent._trigger_fault_warning = MagicMock()
        agent._clear_warning = MagicMock()

        # Simulate non-fault status
        from paho.mqtt.client import Client, MQTTMessage
        client_mock = MagicMock(spec=Client)
        msg_mock = MagicMock(spec=MQTTMessage)
        msg_mock.topic = "rooms/2/command"
        msg_mock.payload = json.dumps({"status": "Available"}).encode()
        agent._on_mqtt_message(client_mock, None, msg_mock)

        # No rooms in Fault -> clear warning
        assert agent.rooms["2"]["status"] == "Available"
        agent._clear_warning.assert_called_once()
        agent._trigger_fault_warning.assert_not_called()

    def test_trigger_fault_warning_flashes_pixels(self, monkeypatch):
        agent = self.Agent()
        agent.sense = MagicMock()

        calls = {"set": 0, "clear": 0}

        def count_set_pixels(*_args, **_kwargs):
            calls["set"] += 1

        def count_clear(*_args, **_kwargs):
            calls["clear"] += 1

        agent.sense.set_pixels = MagicMock(side_effect=count_set_pixels)
        agent.sense.clear = MagicMock(side_effect=count_clear)

        # Remove actual sleeping within agent module
        monkeypatch.setattr("agent.time.sleep", lambda *_: None)

        agent._trigger_fault_warning()

        assert calls["set"] >= 7  
        assert calls["clear"] >= 5


class TestRoomFaultLeds:
    def setup_method(self):
        from room import RoomPi
        self.RoomPi = RoomPi

    def test_room_fault_sets_red_leds(self):
        room = self.RoomPi()
        room.sense = MagicMock()

        room.current = Status.FAULT
        room.update_leds()

        room.sense.clear.assert_called_with((255, 0, 0))
