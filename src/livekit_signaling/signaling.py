from __future__ import annotations

import asyncio
import logging
import time
from asyncio import Task
from dataclasses import dataclass, field
from typing import Any, Callable, Coroutine, Mapping, Union

import aiohttp
from aiohttp import ClientWebSocketResponse
from aiortc import MediaStreamTrack, RTCSessionDescription
from pyee.asyncio import AsyncIOEventEmitter

from . import livekit_types as LK
from .livekit_protobuf_defs import lkrtc
from .utils import create_access_token, wintolin

# use EventHandler instead of pyee.base.Handler to make mypy happy
EventHandler = Union[
    Callable[[LK.LKBase], Coroutine[Any, Any, None] | None],
    Callable[[LK.JoinResponse], None],
    Callable[[LK.JoinResponse], Coroutine[Any, Any, None] | None],
    Callable[[LK.LeaveRequest], Coroutine[Any, Any, None]],
    Callable[[RTCSessionDescription], None],
    Callable[[None], None],
]


class SignalingEvents(AsyncIOEventEmitter):
    def __init__(self) -> None:
        super().__init__()
        self.emit_all = False


@dataclass
class ParticipantTracksTracker(AsyncIOEventEmitter):
    participants: dict[LK.ParticipantId, list[LK.TrackId]] = field(default_factory=dict)
    tracks: dict[LK.TrackId, LK.ParticipantId] = field(default_factory=dict)

    # define events
    participant_added: str = "participant_added"
    participant_removed: str = "participant_removed"
    track_added: str = "track_added"
    track_removed: str = "track_removed"

    def __init__(self) -> None:
        super().__init__()
        self.participants = {}
        self.tracks = {}

    def add_participant(self, participant: LK.ParticipantId) -> None:
        if participant not in self.participants:
            self.participants[participant] = []
            self.emit(self.participant_added, participant)

    def add_track(self, participant: LK.ParticipantId, track: LK.TrackId) -> None:
        self.add_participant(participant)
        if track not in self.tracks:
            self.tracks[track] = participant
            self.participants[participant].append(track)
            self.emit(self.track_added, participant, track)

    def remove_track(self, track: LK.TrackId) -> None:
        if track in self.tracks:
            participant = self.tracks.pop(track)
            self.participants[participant].remove(track)
            self.emit(self.track_removed, participant, track)

    def remove_participant(self, participant: LK.ParticipantId) -> None:
        if participant in self.participants:
            tracks = self.participants.pop(participant)
            for track in tracks:
                self.tracks.pop(track)
            self.emit(self.participant_removed, participant)

    def get_lkParticipantTracks(
        self,
        participant_id: LK.ParticipantId | None = None,
        track_id: LK.TrackId | None = None,
    ) -> LK.ParticipantTracks | None:
        if participant_id in self.participants:
            tracks = self.participants[participant_id]
            if track_id is None:
                return LK.ParticipantTracks(participant_id, tracks)
            elif track_id in tracks:
                return LK.ParticipantTracks(participant_id, [track_id])
            else:
                return None
        if track_id in self.tracks:
            return LK.ParticipantTracks(
                self.tracks[track_id], self.participants[self.tracks[track_id]]
            )
        return None


class Signaling:
    sdk = "python"
    uri = "/rtc"
    auto_subscribe = 1
    adaptive_stream = 1
    sdk_params: Mapping[str, Mapping[str, str]] = {
        "go": {
            "protocol": "8",
            "sdk": "go",
            "version": "1.0.3",
        },
        "js": {
            "protocol": "8",
            "sdk": "js",
            "version": "1.3.2",
        },
        "python": {
            "protocol": "8",
            "sdk": "python",  # sdk python is unknown to livekit server, but it shouldn't matter much
            "version": "8",  # this version is made up, as python is not in the livekit supported protocols
        },
    }
    paxtracker = ParticipantTracksTracker()

    def __init__(
        self,
        host: str,
        port: int,
        room: str,
        api_key: str,
        api_secret: str,
        identity: str = "",
    ):
        # setup event emitters
        self.sent_events = SignalingEvents()
        self.received_events = SignalingEvents()
        self._emitting_requests = False

        self.host = host
        self.port = port
        self.room = room
        self.api_key = api_key
        self.api_secret = api_secret
        self.identity = identity
        self.token: LK.Token = LK.Token(
            create_access_token(self.api_key, self.api_secret, self.room, self.identity)
        )
        self._ws: ClientWebSocketResponse | None = None
        self.logger = logging.getLogger("livekit-signaling")
        self.ping_task: Task[Any] | None = None

    def on_recv(
        self, event: str, handler: EventHandler | None = None
    ) -> EventHandler | Callable[[EventHandler], EventHandler]:
        if event == "all_messages":
            self.received_events.emit_all = True
        if handler is None:
            return self.received_events.listens_to(event)
        else:
            return self.received_events.add_listener(event, handler)

    def on_sent(
        self, event: str, handler: EventHandler | None = None
    ) -> EventHandler | Callable[[EventHandler], EventHandler]:
        self._emitting_requests = True
        if event == "all_messages":
            self.sent_events.emit_all = True
        if handler is None:
            return self.sent_events.listens_to(event)
        else:
            return self.sent_events.add_listener(event, handler)

    async def connect_and_run(self, sdk: str | None = None) -> None:
        self.logger.debug(f"connecting to {self.host}:{self.port}")
        secure = ["", "s"][self.port == 443]
        param_dict: Mapping[str, str] = {
            "access_token": self.token,
            "auto_subscribe": str(self.auto_subscribe),
        } | self.sdk_params[sdk or self.sdk]

        url = f"ws{secure}://{self.host}:{self.port}{self.uri}"

        attempts: int = 0
        wait = 0.01

        try:
            async with aiohttp.ClientSession() as session:
                while True:
                    try:
                        async with session.ws_connect(
                            url, params=param_dict
                        ) as self._ws:
                            self.logger.info(f"Connected to {url}...")
                            attempts = 0
                            wait = 0.01
                            async for msg in self._ws:
                                if msg.type == aiohttp.WSMsgType.BINARY:
                                    await self.receive2(msg.data)
                                    continue
                                elif msg.type == aiohttp.WSMsgType.ERROR:
                                    self.logger.error(
                                        f"Connection errored - Reconnecting..."
                                    )
                                    print(f"Connection errored - Reconnecting...")
                                elif msg.type == aiohttp.WSMsgType.CLOSED:
                                    self.logger.error(
                                        f"Connection closed - Reconnecting..."
                                    )
                                    print(f"Connection closed - Reconnecting...")
                                else:
                                    self.logger.error(
                                        f"Unexpected message type {msg.type}"
                                    )
                                    print(f"Unexpected message type {msg.type}")
                                break
                            # raise Exception("Websocket unexpectedly closed")
                    except aiohttp.client_exceptions.ClientConnectorError:
                        self.logger.error(f"Connection closed - Reconnecting...")
                        pass
                    except asyncio.CancelledError:
                        raise
                    except KeyboardInterrupt:
                        await self.close()
                        break
                    attempts += 1
                    self.logger.debug(
                        f"Reconnecting in {wait} seconds... attempts={attempts}"
                    )
                    await asyncio.sleep(wait)
                    wait = min(wait * 2, 2)
        except asyncio.CancelledError:
            raise
        except Exception as e:
            self.logger.exception(f"Failed to connect to {url}: {e}")
            raise

        self.logger.error(f"Disconnected from {url}, not retrying.")

    async def close(self) -> None:
        if self._ws is not None:
            self.logger.info(f"Closing websocket")
            if self.ping_task is not None:
                self.ping_task.cancel()
                self.ping_task = None
            try:
                await self._ws.close()
            except asyncio.CancelledError:
                raise
            except Exception:
                self.logger.exception(f"ERROR: Closing websocket failed")
                raise
            finally:
                self._ws = None

    async def send(self, obj: LK.LKBase, no_log: bool = False) -> bool:
        if self._ws is None:
            return False
        lkobj = obj.to_signal_request()
        if not no_log:
            self.logger.debug(f"=" * 80)
            self.logger.info(f"Signal sending: {type(obj)} {obj}")

        try:
            await self._ws.send_bytes(lkobj.SerializeToString())
        except asyncio.CancelledError:
            raise
        except Exception:
            return False

        if self._emitting_requests and not no_log:
            self._emit_request(obj)

        return True

    async def receive2(self, msg: bytes) -> None:
        try:
            lkobj = lkrtc.SignalResponse()
            lkobj.ParseFromString(msg)
            self.logger.debug(f"Signal received: {type(lkobj)} {lkobj}")
        except asyncio.CancelledError:
            raise
        except Exception:
            self.logger.exception(f"Error parsing message: {msg!r}")
        try:
            obj = LK.from_signal_response(lkobj)
        except asyncio.CancelledError:
            raise
        except Exception as e:
            self.logger.exception(f"Failed to parse input: {type(input)} {input}")
            raise
        self._emit_response(obj)

    async def run(self, sdk: str | None = None) -> None:
        # setup locally handled events
        self.on_recv("refresh_token", self._on_token_refresh)
        self.on_recv("join", self._on_join)
        self.on_recv("leave", self._on_leave)

        await self.connect_and_run(sdk=sdk)

    async def send_pings(self, interval: int = 30, timeout: int = 60) -> None:
        self.logger.info(f"Sending pings at {interval} seconds")

        while True:
            current_time = LK.Time(int(1000 * time.time()))
            await self.send(LK.Ping(time=current_time), no_log=True)
            await asyncio.sleep(interval)

    async def send_answer(self, local_desc: RTCSessionDescription) -> bool:
        self.logger.debug(f"Sending ANSWER:\n{wintolin(local_desc.sdp)}")

        answer = LK.SessionDescription(type=local_desc.type, sdp=local_desc.sdp)
        return await self.send(answer)

    async def send_offer(self, local_desc: RTCSessionDescription) -> bool:
        self.logger.debug(f"Sending OFFER:\n{wintolin(local_desc.sdp)}")

        offer = LK.SessionDescription(type=local_desc.type, sdp=local_desc.sdp)
        return await self.send(offer)

    async def send_add_track(self, track: MediaStreamTrack) -> bool:
        kind = track.kind
        if kind != "video":
            raise NotImplementedError("Track type '{kind}' not supported")

        layer = LK.VideoLayer(
            quality=LK.VideoQuality.HIGH,
            bitrate=1000000,
            width=1920,
            height=1080,
            ssrc=None,
        )

        add_track = LK.AddTrackRequest(
            cid=track.id,
            type=LK.TrackType.VIDEO,
            source=LK.TrackSource.CAMERA,
            width=1920,
            height=1080,
            layers=[layer],
            name=None,
            muted=False,
            disable_dtx=None,
            simulcast_codecs=[],
            sid=None,
            stereo=None,
            disable_red=None,
        )

        self.logger.debug(f"Sending add track '{kind}' request, id={track.id}")
        return await self.send(add_track)

    async def send_subscription_permission(self) -> bool:
        self.logger.debug(
            f"Sending subscription permission request to all participants"
        )
        return await self.send(
            LK.SubscriptionPermission(all_participants=True, track_permissions=[])
        )

    async def send_subscription_request(
        self, pax_tracks: dict[LK.ParticipantId, list[LK.TrackId]]
    ) -> bool:
        """
        message UpdateSubscription {
          repeated string track_sids = 1;
          bool subscribe = 2;
          repeated ParticipantTracks participant_tracks = 3;
        }
        message ParticipantTracks {
          // participant ID of participant to whom the tracks belong
          string participant_sid = 1;
          repeated string track_sids = 2;
        }
        """
        subreq = LK.UpdateSubscription(
            subscribe=True, participant_tracks=[], track_sids=[]
        )
        for pax_id, track_ids in pax_tracks.items():
            participant_tracks = LK.ParticipantTracks(
                participant_sid=pax_id, track_sids=track_ids
            )
            subreq.participant_tracks.append(participant_tracks)
            subreq.track_sids.extend(track_ids)

        self.logger.debug(f"Sending subscription request to the server")
        return await self.send(subreq)

    async def send_unsubscription_request(self, unsub: LK.UpdateSubscription) -> bool:
        self.logger.debug(f"Sending unsubscription request to the server")
        return await self.send(unsub)

    async def send_update_track_settings(
        self, track_id: str, width: int | None = None, height: int | None = None
    ) -> bool:
        """
        message UpdateTrackSettings {
          repeated string track_sids = 1;
          // when true, the track is placed in a paused state, with no new data returned
          bool disabled = 3;
          // deprecated in favor of width & height
          VideoQuality quality = 4;
          // for video, width to receive
          uint32 width = 5;
          // for video, height to receive
          uint32 height = 6;
          uint32 fps = 7;
        }
        """
        req = LK.UpdateTrackSettings(
            track_sids=[track_id],
            disabled=False,
            width=width,
            height=height,
            quality=None,
            fps=30,
        )
        self.logger.debug(f"Sending update track settings request to the server")
        return await self.send(req)

    def _on_join(self, join: LK.JoinResponse) -> None:
        timeout: int = int(join.ping_timeout or 42)
        interval: int = int(join.ping_interval or timeout / 2)
        self.logger.debug(f"Received join response")
        if self.ping_task is not None:
            self.ping_task.cancel()
        self.ping_task = asyncio.create_task(self.send_pings(interval, timeout))

    def _on_token_refresh(self, token: LK.Token) -> None:
        # save the token for reconnection
        self.token = token

    async def _on_leave(self, leave: LK.LeaveRequest) -> None:
        # close the websocket
        # asyncio.create_task(self.close())
        await self.close()

    def _emit_response(self, input: LK.LKBase) -> None:
        try:
            event, output = input.get_response_name(), input
            assert event
        except Exception as e:
            self.logger.exception(f"Failed to parse input: {type(input)} {input}")
            raise

        self.received_events.emit(event, output)

        if self.received_events.emit_all and event != "pong":
            self.received_events.emit("all_messages", event, output)

    def _emit_request(self, input: LK.LKBase) -> None:
        try:
            event, output = input.get_request_name(), input
            assert event
        except Exception as e:
            self.logger.exception(f"Failed to parse input: {type(input)} {input}")
            raise

        self.sent_events.emit(event, output)

        if self.sent_events.emit_all:
            self.sent_events.emit("all_messages", event, output)
