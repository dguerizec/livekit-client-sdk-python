#!/usr/bin/env python3
import argparse
import asyncio
import logging
import os
import sys
from typing import Any

from aiortc import MediaStreamTrack, sdp
from recorder import FrameRecorder

from livekit_signaling import LK, Signaling
from livekit_signaling.utils import PeerConnectionEvents, create_pc, wintolin

logger = logging.getLogger("livekit-subscriber")

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
    "app": logging.getLogger("livekit-subscriber"),
    "sub": logging.getLogger("livekit-subscriber-sub"),
    "pub": logging.getLogger("livekit-subscriber-pub"),
    "rec": logging.getLogger("livekit-recorder"),
}


async def run(recorder: FrameRecorder, signaling: Signaling) -> None:
    sub_logger = logging.getLogger("livekit-subscriber-sub")
    sub_events = PeerConnectionEvents(sub_logger)
    sub = create_pc(events=sub_events)

    pub_logger = logging.getLogger("livekit-subscriber-pub")
    pub_events = PeerConnectionEvents(pub_logger)
    pub = create_pc(events=pub_events)

    channel = pub.createDataChannel("test")

    # DEBUG
    @channel.on("open")  # type: ignore
    def on_open() -> None:
        logger.debug("Channel opened")
        channel.send("hello")

    # DEBUG
    @channel.on("message")  # type: ignore
    def on_message(message: str) -> None:
        logger.debug(f"Received message: {message}")

    # DEBUG
    @channel.on("close")  # type: ignore
    def on_close() -> None:
        logger.debug("Channel closed")

    @sub.on("track")  # type: ignore
    def on_track(track: MediaStreamTrack) -> None:
        logger.warning(f"Receiving track {track.kind} {track.id}")

        if track.kind == "audio":
            return

        asyncio.ensure_future(recorder.addTrack(track))

        # DEBUG
        @track.on("ended")  # type: ignore
        async def on_ended() -> None:
            logger.debug(f"Track {track.trid} ended")

    # DEBUG
    @recorder.on(FrameRecorder.recorder_stopped)  # type: ignore
    async def on_recorder_stopped() -> None:
        logger.debug(f"on_recorder_stopped")

    # DEBUG
    @recorder.on(FrameRecorder.track_added)  # type: ignore
    def on_track_added(track: MediaStreamTrack) -> None:
        logger.debug(f"on_track_added Adding track {track.trid}")
        print(f"on_track_added Adding track {track.trid}")

    @recorder.on(FrameRecorder.track_removed)  # type: ignore
    async def on_track_removed(track_id: LK.TrackId) -> None:
        # FIXME: this is messy
        logger.debug(f"on_track_removed Removing track {track_id}")
        paxtracks = signaling.paxtracker.get_lkParticipantTracks(track_id=track_id)
        if not paxtracks:
            logger.error(f"on_track_removed No participant track for {track_id}")
            return

        tracks = paxtracks.track_sids

        unsub = LK.UpdateSubscription(
            track_sids=tracks, subscribe=False, participant_tracks=[paxtracks]
        )
        logger.debug(
            f"on_track_removed Participant {paxtracks.participant_sid} {paxtracks.track_sids}"
        )

        await signaling.send_unsubscription_request(unsub)

    # DEBUG
    @sub.on("connectionstatechange")  # type: ignore
    async def on_connectionstatechange() -> None:
        logger.debug(f"Connection state is {sub.connectionState}")

    # DEBUG
    @sub.on("statechange")  # type: ignore
    async def on_statechange() -> None:
        logger.debug(f"State is {sub.iceConnectionState}")

    # DEBUG
    @sub.on("iceconnectionstatechange")  # type: ignore
    async def on_iceconnectionstatechange() -> None:
        logger.debug(f"ICE connection state is {sub.iceConnectionState}")

    # DEBUG
    @sub.on("icegatheringstatechange")  # type: ignore
    async def on_icegatheringstatechange() -> None:
        logger.debug(f"ICE gathering state is {sub.iceGatheringState}")

    # DEBUG
    @sub.on("signalingstatechange")  # type: ignore
    async def on_signalingstatechange() -> None:
        logger.debug(f"Signaling state is {sub.signalingState}")

    async def send_answer() -> None:
        ans = await sub.createAnswer()
        try:
            await sub.setLocalDescription(ans)
        except:
            logger.exception(
                f"ERROR: Cannot set local description with answer:\n{wintolin(ans.sdp)}"
            )
            return

        local_desc = sub.localDescription

        logger.debug(f"Sending ANSWER:\n{wintolin(local_desc.sdp)}")

        await signaling.send_answer(local_desc)

    @signaling.on_recv("join")  # type: ignore
    async def on_join(join: LK.JoinResponse) -> None:
        # FIXME: this is messy
        logger.debug(f"Received join response: {join}")
        subscriptions: dict[LK.ParticipantId, list[LK.TrackId]] = {}
        layers: dict[
            LK.ParticipantId,
            dict[LK.TrackId, dict[str, dict[str, None | str | int | float]]],
        ] = {}
        tracks_added = 0
        for participant in join.other_participants:
            if participant.state.name == "DISCONNECTED":
                continue
            logger.debug(f"Participant: {participant.identity} {participant.sid}")
            subscriptions[participant.sid] = []
            layers[participant.sid] = {}
            for track in participant.tracks:
                layers[participant.sid][track.sid] = {}
                logger.debug(f"Track: {track.type} {track.sid}")
                if LK.TrackType(track.type) == LK.TrackType("audio"):
                    continue
                for layer in track.layers:
                    layers[participant.sid][track.sid][layer.quality.name] = {
                        "quality": layer.quality.name,
                        "width": layer.width,
                        "height": layer.height,
                        "bitrate": layer.bitrate,
                        "ssrc": layer.ssrc,
                    }

                    if layer.ssrc == 0:
                        continue
                    logger.debug(f"Layer: {layer.width} {layer.height} {layer.ssrc}")
                logger.debug(f"Adding track {track.sid} to subscriber")
                subscriptions[participant.sid].append(track.sid)
                signaling.paxtracker.add_track(participant.sid, track.sid)
                tracks_added += 1
        if tracks_added > 0:
            await signaling.send_subscription_request(subscriptions)

            for pax_id, tracks in layers.items():
                for track_id, track_layers in tracks.items():
                    ssrc = None
                    res = 10000**2
                    for quality, track_layer in track_layers.items():
                        if track_layer["ssrc"] == 0 or None in (
                            track_layer["width"],
                            track_layer["height"],
                        ):
                            continue

                        width: int = int(track_layer["width"])  # type: ignore[arg-type]
                        height: int = int(track_layer["height"])  # type: ignore[arg-type]

                        if width * height < res:
                            res = width * height
                            ssrc = track_layer["ssrc"]
                    await signaling.send_update_track_settings(
                        track_id=track_id, width=width, height=height
                    )

    @signaling.on_recv("offer")  # type: ignore
    async def on_offer(offer: LK.SessionDescription) -> None:
        logger.debug(f"Received OFFER:\n{wintolin(offer.sdp)}")
        await sub.setRemoteDescription(offer.to_aiortc())
        desc = sdp.SessionDescription.parse(sub.remoteDescription.sdp)
        for media in desc.media:
            for ssrc in media.ssrc:
                logger.debug(f"Media: {media.kind} {ssrc.ssrc} {ssrc.label}")
        await send_answer()

    @signaling.on_recv("trickle")  # type: ignore
    async def on_trickle(trickle: LK.TrickleRequest) -> None:
        logger.debug(f"Trickle: add subscriber candidate with {trickle.target}")
        logger.debug(trickle)
        await sub.addIceCandidate(trickle.candidate)

    @signaling.on_recv("update")  # type: ignore
    async def on_participant_update(update: LK.ParticipantUpdate) -> None:
        # FIXME: this is messy
        logger.debug(f"Received update: {update}")
        subscriptions: dict[LK.ParticipantId, list[LK.TrackId]] = {}
        layers: dict[
            LK.ParticipantId,
            dict[LK.TrackId, dict[str, dict[str, None | str | int | float]]],
        ] = {}
        tracks_added = 0
        for participant in update.participants:
            if participant.state.name == "DISCONNECTED":
                for track in participant.tracks:
                    logger.debug(f"Removing track {track.sid}")
                    recorder.disconnect_track(track.sid)
                continue
            logger.debug(f"Participant: {participant.identity} {participant.sid}")
            subscriptions[participant.sid] = []
            layers[participant.sid] = {}
            for track in participant.tracks:
                layers[participant.sid][track.sid] = {}
                logger.debug(f"Track: {track.type} {track.sid}")
                if LK.TrackType(track.type) == LK.TrackType("audio"):
                    continue
                for layer in track.layers:
                    layers[participant.sid][track.sid][layer.quality.name] = {
                        "quality": layer.quality.name,
                        "width": layer.width,
                        "height": layer.height,
                        "bitrate": layer.bitrate,
                        "ssrc": layer.ssrc,
                    }

                    if layer.ssrc == 0:
                        continue
                    logger.debug(f"Layer: {layer.width} {layer.height} {layer.ssrc}")
                logger.debug(f"Adding track {track.sid} to subscriber")
                subscriptions[participant.sid].append(track.sid)
                signaling.paxtracker.add_track(participant.sid, track.sid)
                tracks_added += 1
        if tracks_added > 0:
            await signaling.send_subscription_request(subscriptions)

            for pax_id, tracks in layers.items():
                for track_id, track_layers in tracks.items():
                    ssrc = None
                    res = 10000**2
                    for quality, track_layer in track_layers.items():
                        if track_layer["ssrc"] == 0 or None in (
                            track_layer["width"],
                            track_layer["height"],
                        ):
                            continue

                        width: int = int(track_layer["width"])  # type: ignore[arg-type]
                        height: int = int(track_layer["height"])  # type: ignore[arg-type]

                        if width * height < res:
                            res = width * height
                            ssrc = track_layer["ssrc"]
                    await signaling.send_update_track_settings(
                        track_id=track_id, width=width, height=height
                    )

    @signaling.on_recv("stream_state_update")  # type: ignore
    async def on_stream_state_update(update: LK.StreamStateUpdate) -> None:
        logger.debug(f"Received stream state update: {update}")
        for state in update.stream_states:
            if state.state.name == "ACTIVE":
                logger.debug(
                    f"Stream {state.participant_sid} {state.track_sid} is active"
                )
                # FIXME: this call still does nothing but should tell the recorder to start recording this track
                recorder.start_recording(track_id=LK.TrackId(state.track_sid))

    # DEBUG
    @signaling.on_sent("subscription")  # type: ignore
    async def on_subscription_request(subscription: object) -> None:
        logger.debug(f"Sent subscription request: {subscription}")

    # DEBUG
    @signaling.on_sent("track_setting")  # type: ignore
    async def on_track_setting_request(track_setting: object) -> None:
        logger.debug(f"Sent track setting request: {track_setting}")

    # DEBUG
    @signaling.on_recv("all_messages")  # type: ignore
    async def on_all_messages(event: str, message: LK.LKBase) -> None:
        handled = ["join", "offer", "trickle", "update", "stream_state_update"]
        if event in handled:
            return
        logger.debug(
            f"Received unhandled {event} message from livekit: {type(message)}"
        )
        logger.debug(message)

    import time

    start_time = int(1000 * time.time())

    @signaling.on_recv("pong")  # type: ignore
    async def on_pong(pong: LK.Pong) -> None:
        logger.warning(f"Received pong: {(pong.time - start_time) / 1000} seconds")

    # Run the main loop
    await signaling.run(sdk="go")


async def run_wrapper(recorder: FrameRecorder, signaling: Signaling) -> None:
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
    parser.add_argument(
        "path",
        help="Write video tracks to path/{id}/frame{number}.png",
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

    if not args.path:
        parser.error("Missing path (Which directory you want your files written to ?)")

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

    logger.info(f"Writing to directory: {args.path}")
    recorder = FrameRecorder(args.path)

    try:
        result: Any = asyncio.run(
            run_wrapper(
                recorder=recorder,
                signaling=signaling,
            )
        )
    except KeyboardInterrupt:
        logger.debug("Exiting")
    except:
        logger.exception(f"ERROR:")
    finally:
        logger.debug("Exiting")
