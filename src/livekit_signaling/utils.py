import json
import logging
from dataclasses import dataclass
from typing import Callable, Optional

from aiortc import MediaStreamTrack, RTCDataChannel, RTCIceCandidate, RTCPeerConnection
from aiortc.sdp import candidate_from_sdp, candidate_to_sdp
from livekit import AccessToken, VideoGrant  # type: ignore

from .livekit_protobuf_defs import lkrtc  # type: ignore


def wintolin(s: str) -> str:
    return s.replace("\r\n", "\n")


def create_access_token(
    api_key: str, api_secret: str, room_name: str, identity: str
) -> str:
    grant = VideoGrant(room_join=True, room=room_name)
    token = AccessToken(api_key, api_secret, identity=identity, grant=grant)
    r: str = token.to_jwt()
    return r


def proto_to_aio_candidate(candidate: str) -> RTCIceCandidate:
    obj = json.loads(candidate)
    c = candidate_from_sdp(obj["candidate"])
    c.sdpMid = obj.get("sdpMid")
    c.sdpMLineIndex = obj.get("sdpMLineIndex")
    return c


def aio_to_proto_candidate(candidate: RTCIceCandidate) -> lkrtc.SignalRequest:
    sdp = candidate_to_sdp(candidate)

    req = lkrtc.SignalRequest()
    req.trickle.candidateInit = json.dumps(
        {
            "sdp": sdp,
            "sdpMid": candidate.sdpMid,
            "sdpMLineIndex": candidate.sdpMLineIndex,
        }
    )
    return req


@dataclass
class PeerConnectionEvents:
    on_datachannel: Callable[[RTCDataChannel], None]
    on_connectionstatechange: Callable[[], None]
    on_iceconnectionstatechange: Callable[[], None]
    on_icegatheringstatechange: Callable[[], None]
    on_signalingstatechange: Callable[[], None]
    on_track: Callable[[MediaStreamTrack], None]

    def _on_datachannel(self, channel: RTCDataChannel) -> None:
        self.logger.debug(f"Data channel created {channel.label}#{channel.id}")

        @channel.on("message")  # type: ignore
        def on_message(message) -> None:
            self.logger.debug(
                f"Received message {channel.label}#{channel.id}: {message}"
            )

        @channel.on("open")  # type: ignore
        def on_open() -> None:
            self.logger.debug(f"Data channel opened {channel.label}#{channel.id}")

        @channel.on("close")  # type: ignore
        def on_close() -> None:
            self.logger.debug(f"Data channel closed {channel.label}#{channel.id}")

    def _on_connectionstatechange(self) -> None:
        self.logger.debug(f"Connection state changed: {self.pc.connectionState}")  # type: ignore

    def _on_iceconnectionstatechange(self) -> None:
        self.logger.debug(f"Ice connection state changed: {self.pc.iceConnectionState}")  # type: ignore

    def _on_icegatheringstatechange(self) -> None:
        self.logger.debug(f"Ice gathering state changed: {self.pc.iceGatheringState}")  # type: ignore

    def _on_signalingstatechange(self) -> None:
        self.logger.debug(f"Signaling state changed: {self.pc.signalingState}")  # type: ignore

    def _on_track(self, track: MediaStreamTrack) -> None:
        self.logger.debug(f"Track received: {track.kind}")

        @track.on("ended")  # type: ignore
        def on_ended() -> None:
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
        self.pc: Optional[RTCPeerConnection] = None

    def set_pc(self, pc: RTCPeerConnection) -> None:
        self.pc = pc


def create_pc(
    events: Optional[PeerConnectionEvents] = None,
    logger: Optional[logging.Logger] = None,
) -> RTCPeerConnection:
    pc = RTCPeerConnection()

    if events is None:
        events = PeerConnectionEvents(logger)

    events.set_pc(pc)
    pc.on("datachannel", events.on_datachannel)
    pc.on("connectionstatechange", events.on_connectionstatechange)
    pc.on("iceconnectionstatechange", events.on_iceconnectionstatechange)
    pc.on("icegatheringstatechange", events.on_icegatheringstatechange)
    pc.on("signalingstatechange", events.on_signalingstatechange)
    pc.on("track", events.on_track)

    return pc


def get_track_ids(track: MediaStreamTrack) -> tuple[Optional[str], Optional[str]]:
    # FIXME: return the track_id once, we should not need the pax_id
    return track.id, track.id
    #msid = getattr(track, "msid", None)
    #if msid is None:
    #    return None, None
    #if not " " in msid:
    #    return None, msid

    #bits = msid.split(" ")
    #pax_id = (
    #    bits[0].split(":")[0] if bits and len(bits) > 0 and ":" in bits[0] else None
    #)
    #track_id = bits[1] if bits and len(bits) > 1 else None
    #return pax_id, track_id
