import json
import logging

from .livekit_protobuf_defs import lkrtc
from livekit import AccessToken, VideoGrant
from aiortc import RTCIceCandidate, RTCPeerConnection
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


def create_pc(logger: logging.Logger=None):
    pc = RTCPeerConnection()

    if logger:
        @pc.on("datachannel")
        def on_datachannel(channel):
            logger.debug(f"Data channel created by remote: {channel}")

            @channel.on("message")
            def on_message(message):
                logger.debug(f"Message received: {message}")

        @pc.on("connectionstatechange")
        def on_connectionstatechange():
            logger.debug(f"Connection state is {pc.connectionState}")

        @pc.on("iceconnectionstatechange")
        def on_iceconnectionstatechange():
            logger.debug(f"ICE connection state is {pc.iceConnectionState}")

        @pc.on("icegatheringstatechange")
        def on_icegatheringstatechange():
            logger.debug(f"ICE gathering state is {pc.iceGatheringState}")

        @pc.on("signalingstatechange")
        def on_signalingstatechange():
            logger.debug(f"Signaling state is {pc.signalingState}")

        @pc.on("track")
        def on_track(track):
            logger.debug(f"Receiving track {track.kind}")

    return pc

