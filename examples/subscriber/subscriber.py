#!/usr/bin/env python3
import argparse
import asyncio
import logging
import os
import sys
from typing import Tuple

from aiortc import RTCPeerConnection, RTCSessionDescription, RTCIceCandidate, sdp
from aiortc.contrib.media import MediaPlayer, MediaBlackhole, MediaRecorder

from recorder import FrameRecorder
from livekit_signaling import Signaling, lkrtc, lkmodels
from livekit_signaling.utils import wintolin, create_pc, PeerConnectionEvents

logger = logging.getLogger("livekit-subscriber")

from aiortc.rtcdatachannel import logger as chan_logger
from aiortc.rtcdtlstransport import logger as dtls_logger
from aiortc.rtcicetransport import logger as ice_logger
from aiortc.rtcpeerconnection import logger as pc_logger
from aiortc.rtcsctptransport import logger as sctp_logger
from aiortc.rtcrtpreceiver import logger as rtp_receiver_logger
from aiortc.rtcrtpsender import logger as rtp_sender_logger
from aiortc.rtcrtptransceiver import logger as rtp_logger
from recorder import logger as recorder_logger

loggers = {
    "chan": chan_logger,
    "dtls": dtls_logger,
    "ice": ice_logger,
    "pc": pc_logger,
    "rtp": rtp_logger,
    "rtp.receiver": rtp_receiver_logger,
    "rtp.sender": rtp_sender_logger,
    "sctp": sctp_logger,

    "sig": logging.getLogger("livekit-signaling"),
    "app": logging.getLogger("livekit-subscriber"),
    "sub": logging.getLogger("livekit-subscriber-sub"),
    "pub": logging.getLogger("livekit-subscriber-pub"),
    "rec": logging.getLogger("livekit-recorder"),
}


async def run(recorder: MediaRecorder, signaling: Signaling):
    player = MediaBlackhole()

    sub_logger = logging.getLogger("livekit-subscriber-sub")
    sub_events = PeerConnectionEvents(sub_logger)
    sub = create_pc(events=sub_events)

    pub_logger = logging.getLogger("livekit-subscriber-pub")
    pub_events = PeerConnectionEvents(pub_logger)
    pub = create_pc(events=pub_events)

    channel = pub.createDataChannel("test")
    @channel.on('open')
    def on_open():
        logger.debug("Channel opened")
        channel.send("hello")

    @channel.on('message')
    def on_message(message):
        logger.debug(f"Received message: {message}")

    @channel.on('close')
    def on_close():
        logger.debug("Channel closed")

    @sub.on("track")
    def on_track(track):
        logger.debug(f"XXX Receiving track {track.kind}")

        if track.kind == "audio":
            return

        # FIXME: should this be delayed after receiving an update message ?
        asyncio.ensure_future(recorder.addTrack(track))

    async def send_answer():
        ans = await sub.createAnswer()
        try:
            await sub.setLocalDescription(ans)
        except:
            logger.exception(f"ERROR: Cannot set local description with answer:\n{wintolin(ans.sdp)}")
            return

        local_desc = sub.localDescription

        logger.debug(f"Sending ANSWER:\n{wintolin(local_desc.sdp)}")

        await signaling.send_answer(local_desc)

    @signaling.on_recv("join")
    async def on_join(join: lkrtc.JoinResponse):
        logger.debug(f"Received join")

    @signaling.on_recv("offer")
    async def on_offer(offer: RTCSessionDescription):
        logger.debug(f"XXX Received OFFER:\n{wintolin(offer.sdp)}")
        await sub.setRemoteDescription(offer)
        desc = sdp.SessionDescription.parse(sub.remoteDescription.sdp)
        for media in desc.media:
            for ssrc in media.ssrc:
                logger.debug(f"XXX media: {media.kind} {ssrc.ssrc} {ssrc.label}")
        await send_answer()

    @signaling.on_recv("trickle")
    async def on_trickle(trickle: Tuple[RTCIceCandidate, str]):
        candidate, target = trickle
        logger.debug(f"Trickle: add subscriber candidate with {target}")
        logger.debug(trickle)
        await sub.addIceCandidate(candidate)

    @signaling.on_recv("update")
    async def on_participant_update(update: lkrtc.ParticipantUpdate):
        logger.debug(f"XXX Received update: {update}")
        subscriptions = {}
        layers = {}
        tracks_added = 0
        for participant in update.participants:
            if participant.state == lkmodels.ParticipantInfo.State.DISCONNECTED:
                continue
            logger.debug(f"XXX Participant: {participant.identity} {participant.sid}")
            subscriptions[participant.sid] = []
            layers[participant.sid] = {}
            for track in participant.tracks:
                layers[participant.sid][track.sid] = {}
                logger.debug(f"XXX Track: {signaling.track_type_name(track.type)} {track.sid}")
                if signaling.track_type_name(track.type) == "audio":
                    continue
                for layer in track.layers:
                    if layer.ssrc == 0:
                        continue
                    logger.debug(f"XXX Layer: {layer.width} {layer.height} {layer.ssrc}")
                logger.debug(f"XXX Adding track {track.sid} to subscriber")
                subscriptions[participant.sid].append(track.sid)
                tracks_added += 1
        if tracks_added > 0:
            await signaling.send_subscription_request(subscriptions)


    @signaling.on_sent("subscription")
    async def on_subscription_request(subscription: object):
        logger.debug(f"XXX Sent subscription request: {subscription}")



    @signaling.on_recv("all_messages")
    async def on_all_messages(event: str, message: lkrtc.SignalResponse):
        handled = [ "offer", "trickle", "update" ]
        if event in handled:
            return
        logger.debug(f"Received {event} message from livekit: {type(message)}")
        logger.debug(message)

    await signaling.run(sdk="go")

async def run_wrapper(recorder: MediaRecorder, signaling: Signaling):
    try:
        await run(recorder, signaling)
    finally:
        logger.error(f"Exiting")
        await recorder.stop()
        await signaling.close()


if __name__ == "__main__":
    host = "localhost"
    port = 7880
    api_key = "devkey"
    api_secret = "secret"
    room = "room1011"
    identity = f"pysub-{os.getppid()}"

    parser = argparse.ArgumentParser(description="Video stream from the command line")
    parser.add_argument("path", help="Write video tracks to path/{id}/frame{number}.png", default=None, nargs="?")
    parser.add_argument("--host", "-H", help="Livekit host", default=host)
    parser.add_argument("--port", "-p", help="Livekit host port", default=port)
    parser.add_argument("--api-key", "-k", help="Livekit API key", default=api_key)
    parser.add_argument("--api-secret", "-s", help="Livekit API secret", default=api_secret)
    parser.add_argument("--room", "-r", help="Livekit room name", default=room)
    parser.add_argument("--identity", "-i", help="Livekit identity", default=identity)
    parser.add_argument("--verbose", "-v", action="count", help="Shortcut for -l app, use -vv for ALL debug")
    parser.add_argument("--verbose-signaling", "-V", action="count", help="Shortcut for -l sig")
    parser.add_argument("--log", "-l", action='append', help="Log DEBUG module")
    parser.add_argument("--list-log-modules", "-L", action="count", help="List module names")
    args = parser.parse_args()

    if args.list_log_modules:
        print('-l ' + ' -l '.join(loggers.keys()))
        sys.exit(0)

    if not args.path:
        parser.error("Missing path (Which directory you want your files written to ?)")


    ch = logging.StreamHandler()
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    ch.setFormatter(formatter)

    logger.addHandler(ch)

    print("ARGS=", args)

    # create signaling
    signaling = Signaling(args.host, args.port, args.room, args.api_key, args.api_secret, args.identity)
    signaling.logger.addHandler(ch)

    if args.log:
        for m in args.log:
            loggers[m].addHandler(ch)
            loggers[m].setLevel(logging.DEBUG)

    if args.verbose:
        logger.setLevel(logging.DEBUG)

        if args.verbose > 1:
            for l in loggers.values():
                l.addHandler(ch)
                l.setLevel(logging.DEBUG)

    if args.verbose_signaling:
        signaling.set_log_level(logging.DEBUG)
        signaling.addHandler(ch)

    logger.info(f"Writing to directory: {args.path}")
    recorder = FrameRecorder(args.path)

    try:
        result = asyncio.run(run_wrapper(
            recorder=recorder,
            signaling=signaling,
        ))
    except KeyboardInterrupt:
        logger.debug("Exiting")
    except:
        logger.exception(f"ERROR:")
    finally:
        logger.debug("Exiting")
