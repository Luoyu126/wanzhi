from __future__ import annotations

import time

import numpy as np

from wanzhi.core.bus import JsonlEventBus, ZmqEventBus
from wanzhi.core.events import Event, EventTypes
from wanzhi.core.frame_shm import SharedMemoryFrameReader, SharedMemoryFrameWriter


def test_zmq_event_bus_delivers_event(tmp_path) -> None:
    endpoint = f"ipc://{tmp_path}/wanzhi-test.sock"
    receiver = ZmqEventBus(endpoint, role="pull")
    time.sleep(0.05)
    sender = ZmqEventBus(endpoint, role="push")
    event = Event(EventTypes.UI_SHOW_MEDICATION, {"source": "test"}, source="test")
    sender.emit(event)
    time.sleep(0.05)
    events = list(receiver.poll_new())
    assert len(events) == 1
    assert events[0].type == EventTypes.UI_SHOW_MEDICATION
    sender.close()
    receiver.close()


def test_jsonl_event_bus_still_works(tmp_path) -> None:
    bus = JsonlEventBus(tmp_path / "events.jsonl")
    bus.emit(Event(EventTypes.VOICE_AWAKE, source="voice"))
    events = list(bus.poll_new())
    assert len(events) == 1
    assert events[0].type == EventTypes.VOICE_AWAKE


def test_shared_memory_frame_roundtrip() -> None:
    name = "wanzhi_test_preview"
    writer = SharedMemoryFrameWriter(name, width=4, height=2, channels=3)
    reader = SharedMemoryFrameReader(name)
    frame = np.arange(4 * 2 * 3, dtype=np.uint8).reshape(2, 4, 3)
    writer.write(frame)
    read_frame, header = reader.read_if_updated()
    assert header is not None
    assert header.sequence == 1
    assert read_frame is not None
    assert read_frame.shape == (2, 4, 3)
    assert np.array_equal(read_frame, frame)
    writer.close()
    writer.unlink()
    reader.close()
