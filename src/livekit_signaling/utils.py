import json
import logging
from dataclasses import dataclass
from typing import Callable, Optional

from .livekit_protobuf_defs import lkrtc  # type: ignore
from livekit import AccessToken, VideoGrant
from aiortc import RTCIceCandidate, RTCPeerConnection, RTCDataChannel, MediaStreamTrack
from aiortc.sdp import candidate_from_sdp, candidate_to_sdp


def wintolin(s):
    return s.replace('\r\n', '\n')


def create_access_token(api_key, api_secret, room_name, identity):
    grant = VideoGrant(room_join=True, room=room_name)
    token = AccessToken(api_key, api_secret, identity=identity, grant=grant)
    return token.to_jwt()


def proto_to_aio_candidate(candidate) -> RTCIceCandidate:
    obj = json.loads(candidate)
    c = candidate_from_sdp(obj["candidate"])
    c.sdpMid = obj.get('sdpMid')
    c.sdpMLineIndex = obj.get('sdpMLineIndex')
    return c


def aio_to_proto_candidate(candidate: RTCIceCandidate):
    sdp = candidate_to_sdp(candidate)

    req = lkrtc.SignalRequest()
    req.trickle.candidateInit = json.dumps({
        'sdp': sdp,
        'sdpMid': candidate.sdpMid,
        'sdpMLineIndex': candidate.sdpMLineIndex,
    })
    return req


@dataclass
class PeerConnectionEvents:
    on_datachannel: Callable[[RTCDataChannel], None]
    on_connectionstatechange: Callable[[], None]
    on_iceconnectionstatechange: Callable[[], None]
    on_icegatheringstatechange: Callable[[], None]
    on_signalingstatechange: Callable[[], None]
    on_track: Callable[[MediaStreamTrack], None]

    def _on_datachannel(self, channel: RTCDataChannel):
        self.logger.debug(f"Data channel created {channel.label}#{channel.id}")

        @channel.on('message')
        def on_message(message):
            self.logger.debug(f"Received message {channel.label}#{channel.id}: {message}")

        @channel.on('open')
        def on_open():
            self.logger.debug(f"Data channel opened {channel.label}#{channel.id}")

        @channel.on('close')
        def on_close():
            self.logger.debug(f"Data channel closed {channel.label}#{channel.id}")

    def _on_connectionstatechange(self):
        self.logger.debug(f"Connection state changed: {self.pc.connectionState}")

    def _on_iceconnectionstatechange(self):
        self.logger.debug(f"Ice connection state changed: {self.pc.iceConnectionState}")

    def _on_icegatheringstatechange(self):
        self.logger.debug(f"Ice gathering state changed: {self.pc.iceGatheringState}")

    def _on_signalingstatechange(self):
        self.logger.debug(f"Signaling state changed: {self.pc.signalingState}")

    def _on_track(self, track: MediaStreamTrack):
        self.logger.debug(f"Track received: {track.kind}")

        @track.on('ended')
        def on_ended():
            self.logger.debug(f"Track ended")

    def __init__(self, logger: Optional[logging.Logger] = None):
        if logger is not None:
            self.logger = logger
        else:
            self.logger = logging.getLogger("PeerConnectionEvents-default")
        self.on_datachannel = self._on_datachannel
        self.on_connectionstatechange = self._on_connectionstatechange
        self.on_iceconnectionstatechange = self._on_iceconnectionstatechange
        self.on_icegatheringstatechange = self._on_icegatheringstatechange
        self.on_signalingstatechange = self._on_signalingstatechange
        self.on_track = self._on_track
        self.pc = None

    def set_pc(self, pc: RTCPeerConnection):
        self.pc = pc


def create_pc(events: Optional[PeerConnectionEvents] = None,
              logger: Optional[logging.Logger] = None) -> RTCPeerConnection:
    pc = RTCPeerConnection()

    if events is None:
        events = PeerConnectionEvents(logger)

    events.set_pc(pc)
    pc.on('datachannel', events.on_datachannel)
    pc.on('connectionstatechange', events.on_connectionstatechange)
    pc.on('iceconnectionstatechange', events.on_iceconnectionstatechange)
    pc.on('icegatheringstatechange', events.on_icegatheringstatechange)
    pc.on('signalingstatechange', events.on_signalingstatechange)
    pc.on('track', events.on_track)

    return pc


def get_track_ids(track: MediaStreamTrack):
    msid = getattr(track, "msid", None)
    if msid is None:
        return None, None
    if not " " in msid:
        return None, msid

    bits = msid.split(" ")
    pax_id = bits[0].split(":")[0] if bits and len(bits) > 0 and ":" in bits[0] else None
    track_id = bits[1] if bits and len(bits) > 1 else None
    return pax_id, track_id
