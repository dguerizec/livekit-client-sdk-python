#!/usr/bin/env python3
import argparse
import asyncio
import logging
import os
import sys
from typing import Tuple

from aiortc import RTCPeerConnection, RTCSessionDescription, RTCIceCandidate
from aiortc.contrib.media import MediaPlayer, MediaBlackhole, MediaRecorder

from livekit_signaling import Signaling, lkrtc
from livekit_signaling.utils import wintolin, create_pc

logger = logging.getLogger("livekit-subscriber")

async def run(recorder: MediaRecorder, signaling: Signaling):
    player = MediaBlackhole()

    sub_logger = logging.getLogger("livekit-subscriber-sub")
    pub_logger = logging.getLogger("livekit-subscriber-pub")
    sub = create_pc(sub_logger)
    pub = create_pc(pub_logger)

    async def add_tracks():
        raise NotImplementedError

    @sub.on("track")
    def on_track(track):
        raise NotImplementedError

    async def send_answer():
        ans = await sub.createAnswer()
        try:
            await sub.setLocalDescription(ans)
        except:
            logger.exception(f"ERROR: Cannot set local description with answer:\n{wintolin(ans.sdp)}")
            return False

        local_desc = sub.localDescription

        await signaling.send_answer(local_desc)

        return True

    async def send_offer():
        offer = await pub.createOffer()
        try:
            await pub.setLocalDescription(offer)
        except Exception as e:
            logger.exception(f"ERROR: Cannot set local description with offer:\n{wintolin(offer.sdp)}")
            return False

        local_desc = pub.localDescription
        await signaling.send_offer(local_desc)

        return True

    @signaling.on_recv("join")
    async def on_join(join: lkrtc.JoinResponse):
        logger.debug(f"Received join")

    @signaling.on_recv("offer")
    async def on_offer(offer: RTCSessionDescription):
        logger.debug(f"Received offer:\n{wintolin(offer.sdp)}")
        await sub.setRemoteDescription(offer)
        await send_answer()

    @signaling.on_recv("answer")
    async def on_answer(answer: RTCSessionDescription):
        logger.debug(f"PLAYER: RECEIVED ANSWER:\n{wintolin(answer.sdp)}")
        await pub.setRemoteDescription(answer)

    @signaling.on_recv("track_published")
    async def on_track_published(track: lkrtc.TrackPublishedResponse):
        logger.debug("PLAYER: Track published")
        logger.debug(track)

    @signaling.on_recv("trickle")
    async def on_trickle(trickle: Tuple[RTCIceCandidate, str]):
        candidate, target = trickle
        logger.debug(f"Trickle: add subscriber candidate with {target}")
        logger.debug(trickle)
        await sub.addIceCandidate(candidate)

    @signaling.on_sent("offer")
    async def on_send_offer(offer: RTCSessionDescription):
        logger.debug(f"Sent offer:\n{wintolin(offer.sdp)}")
        await add_tracks()

    @signaling.on_recv("all_messages")
    async def on_all_messages(message: lkrtc.SignalResponse):
        logger.debug(f"Received message from livekit:{type(message)}")
        logger.debug(message)

    # connect signaling
    ok = await signaling.connect(sdk="js")

    if not ok:
        logger.error("Cannot connect to signaling")
        return

    await signaling.run()


if __name__ == "__main__":
    host = "localhost"
    port = 7880
    api_key = "devkey"
    api_secret = "secret"
    room = "room1011"
    identity = f"client-{os.getppid()}"

    parser = argparse.ArgumentParser(description="Video stream from the command line")
    parser.add_argument("file", help="Read the media from the file and sent it.")
    parser.add_argument("--host", "-H", help="Livekit host", default=host)
    parser.add_argument("--port", "-p", help="Livekit host port", default=port)
    parser.add_argument("--api-key", "-k", help="Livekit API key", default=api_key)
    parser.add_argument("--api-secret", "-s", help="Livekit API secret", default=api_secret)
    parser.add_argument("--room", "-r", help="Livekit room name", default=room)
    parser.add_argument("--identity", "-i", help="Livekit identity", default=identity)
    parser.add_argument("--verbose", "-v", action="count")
    parser.add_argument("--verbose-signaling", "-V", action="count")
    args = parser.parse_args()

    ch = logging.StreamHandler()
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    ch.setFormatter(formatter)

    logger.addHandler(ch)

    print("ARGS=", args)

    # create signaling
    signaling = Signaling(args.host, args.port, args.room, args.api_key, args.api_secret, args.identity)
    signaling.logger.addHandler(ch)

    if args.verbose:
        logger.setLevel(logging.DEBUG)

        if args.verbose > 1:
            logging.basicConfig(level=logging.DEBUG)

    if args.verbose_signaling:
        signaling.set_log_level(logging.DEBUG)

    logger.info(f"Writing to file: {args.file}")
    recorder = MediaRecorder(args.file)

    try:
        result = asyncio.run(run(
            recorder=recorder,
            signaling=signaling,
        ))
    except KeyboardInterrupt:
        logger.debug("Exiting")
    finally:
        # cleanup
        asyncio.run(signaling.close())
