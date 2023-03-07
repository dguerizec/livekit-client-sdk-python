#!/usr/bin/env python3
import argparse
import asyncio
import logging
import os
import sys
from typing import Any, Coroutine

from aiortc import RTCSessionDescription  # type: ignore
from player import VideoPlayer

from livekit_signaling import LK, Signaling
from livekit_signaling.utils import PeerConnectionEvents, create_pc, wintolin

logger = logging.getLogger("livekit-publisher")

from aiortc.rtcdatachannel import logger as chan_logger
from aiortc.rtcdtlstransport import logger as dtls_logger
from aiortc.rtcicetransport import logger as ice_logger
from aiortc.rtcpeerconnection import logger as pc_logger
from aiortc.rtcrtpreceiver import logger as rtp_receiver_logger
from aiortc.rtcrtpsender import logger as rtp_sender_logger
from aiortc.rtcrtptransceiver import logger as rtp_logger
from aiortc.rtcsctptransport import logger as sctp_logger

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
    "app": logging.getLogger("livekit-publisher"),
    "sub": logging.getLogger("livekit-publisher-sub"),
    "pub": logging.getLogger("livekit-publisher-pub"),
    "rec": logging.getLogger("livekit-recorder"),
}


async def run(player: VideoPlayer, signaling: Signaling) -> None:
    sub_logger = logging.getLogger("livekit-publisher-sub")
    sub_events = PeerConnectionEvents(sub_logger)
    sub = create_pc(events=sub_events)

    pub_logger = logging.getLogger("livekit-publisher-pub")
    pub_events = PeerConnectionEvents(pub_logger)
    pub = create_pc(events=pub_events)

    pub.addTransceiver("video", direction="sendonly")

    async def add_tracks() -> None:
        if player and player.audio:
            logger.debug(f"Ignoring audio track")

        if player and player.video:
            logger.debug(f"Adding video track")

            pub.addTrack(player.video)
            # FIXME: should video be started from here ? how ?
            # player._start(player.video)

    async def send_answer() -> bool:
        ans = await sub.createAnswer()
        try:
            await sub.setLocalDescription(ans)
        except:
            logger.exception(
                f"ERROR: Cannot set local description with answer:\n{wintolin(ans.sdp)}"
            )
            return False

        local_desc = sub.localDescription

        logger.debug(f"Sending ANSWER:\n{wintolin(local_desc.sdp)}")
        await signaling.send_answer(local_desc)

        return True

    async def send_offer() -> bool:
        # try:
        #    await add_tracks()
        # except:
        #    logger.exception(f"ERROR: Cannot add tracks")
        #    return False
        await signaling.send_add_track(player.video)

        offer = await pub.createOffer()
        try:
            await pub.setLocalDescription(offer)
        except Exception as e:
            logger.exception(
                f"ERROR: Cannot set local description with offer:\n{wintolin(offer.sdp)}"
            )
            return False

        local_desc = pub.localDescription
        await signaling.send_offer(local_desc)

        return True

    @signaling.on_recv("join")  # type: ignore
    async def on_join(join: LK.JoinResponse) -> None:
        logger.debug(f"Received join")

    @signaling.on_recv("offer")  # type: ignore
    async def on_offer(offer: RTCSessionDescription) -> None:
        logger.debug(f"Received OFFER:\n{wintolin(offer.sdp)}")
        await sub.setRemoteDescription(offer)
        await send_answer()

    @signaling.on_sent("answer")  # type: ignore
    async def on_answer_sent(answer: RTCSessionDescription) -> None:
        await signaling.send_subscription_permission()

    @signaling.on_sent("subscription_permission")  # type: ignore
    async def on_subscription_permission_sent(
        subscription_permission: LK.SubscriptionPermission,
    ) -> None:
        await send_offer()

    @signaling.on_recv("answer")  # type: ignore
    async def on_answer(answer: RTCSessionDescription) -> None:
        logger.debug(f"PLAYER: RECEIVED ANSWER:\n{wintolin(answer.sdp)}")
        await pub.setRemoteDescription(answer)

    @signaling.on_recv("track_published")  # type: ignore
    async def on_track_published(track: LK.TrackPublishedResponse) -> None:
        logger.debug("PLAYER: Track published")
        logger.debug(track)

    @signaling.on_recv("trickle")  # type: ignore
    async def on_trickle(trickle: LK.TrickleRequest) -> None:
        logger.debug(f"Trickle: add publisher candidate with {trickle.target}")
        logger.debug(trickle)
        await sub.addIceCandidate(trickle.candidate)

    @signaling.on_sent("offer")  # type: ignore
    async def on_send_offer(offer: RTCSessionDescription) -> None:
        logger.debug(f"Sent OFFER:\n{wintolin(offer.sdp)}")
        await add_tracks()

    @signaling.on_recv("all_messages")  # type: ignore
    async def on_all_messages(event: str, message: LK.LKBase) -> None:
        handled = ["offer", "answer", "trickle", "track_published"]
        if event in handled:
            return
        logger.debug(f"Received message from livekit:{type(message)}")
        logger.debug(message)

    @player.on(VideoPlayer.started)
    async def on_player_started() -> None:
        logger.debug("PLAYER: started")
        # await add_tracks()

    @player.on(VideoPlayer.ended)
    async def on_player_ended() -> None:
        logger.debug("PLAYER: ended")

    # connect and run signaling
    await signaling.run(sdk="go")


async def run_wrapper(player: VideoPlayer, signaling: Signaling) -> None:
    try:
        await run(player, signaling)
    finally:
        logger.error(f"Exiting")
        # await player.stop()
        await signaling.close()


if __name__ == "__main__":
    host = "localhost"
    port = 7880
    api_key = "devkey"
    api_secret = "secret"
    room = "room1011"
    identity = f"pypub-{os.getppid()}"

    parser = argparse.ArgumentParser(description="Video stream from the command line")
    parser.add_argument(
        "file",
        help="Read the media from the file and sent it.",
        default=None,
        nargs="?",
    )
    parser.add_argument("--host", "-H", help="Livekit host", default=host)
    parser.add_argument("--port", "-p", help="Livekit host port", default=port)
    parser.add_argument("--api-key", "-k", help="Livekit API key", default=api_key)
    parser.add_argument(
        "--api-secret", "-s", help="Livekit API secret", default=api_secret
    )
    parser.add_argument("--room", "-r", help="Livekit room name", default=room)
    parser.add_argument("--identity", "-i", help="Livekit identity", default=identity)
    parser.add_argument("--log", "-l", action="append", help="Log DEBUG module")
    parser.add_argument(
        "--list-log-modules", "-L", action="count", help="List module names"
    )
    args = parser.parse_args()

    if args.list_log_modules:
        print("-l " + " -l ".join(loggers.keys()))
        sys.exit(0)

    if not args.file:
        parser.error("Missing input video file")

    ch = logging.StreamHandler()
    formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )
    ch.setFormatter(formatter)

    logger.addHandler(ch)

    # create signaling
    signaling = Signaling(
        args.host, args.port, args.room, args.api_key, args.api_secret, args.identity
    )
    signaling.logger.addHandler(ch)

    if args.log:
        for m in args.log:
            loggers[m].addHandler(ch)
            loggers[m].setLevel(logging.DEBUG)

    logger.info(f"Reading from file: {args.file}")
    player = VideoPlayer(args.file, loop=True)

    try:
        result: Any = asyncio.run(
            run_wrapper(
                player=player,
                signaling=signaling,
            )
        )
    except KeyboardInterrupt:
        logger.debug("Exiting")
    except:
        logger.exception(f"ERROR:")
    finally:
        logger.debug("Exiting")
