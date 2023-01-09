import time
from dataclasses import dataclass, field

import pyee

from .livekit_protobuf_defs import lkrtc
from .utils import create_access_token, wintolin
from . import livekit_types as LK

from typing import Union, Callable, Optional, List, Dict
import logging
import traceback
import asyncio

from pyee import AsyncIOEventEmitter
from pyee.base import Handler

from aiortc import RTCSessionDescription  # type: ignore

import websockets


class SignalingEvents(AsyncIOEventEmitter):
    def __init__(self):
        super().__init__()
        self.emit_all = False


@dataclass
class ParticipantTracksTracker(pyee.AsyncIOEventEmitter):
    participants: Dict[LK.ParticipantId, List[LK.TrackId]] = field(default_factory=dict)
    tracks: Dict[LK.TrackId, LK.ParticipantId] = field(default_factory=dict)

    # define events
    participant_added: str = "participant_added"
    participant_removed: str = "participant_removed"
    track_added: str = "track_added"
    track_removed: str = "track_removed"

    def __init__(self):
        super().__init__()
        self.participants = {}
        self.tracks = {}

    def add_participant(self, participant: LK.ParticipantId):
        if participant not in self.participants:
            self.participants[participant] = []
            self.emit(self.participant_added, participant)

    def add_track(self, participant: LK.ParticipantId, track: LK.TrackId):
        self.add_participant(participant)
        if track not in self.tracks:
            self.tracks[track] = participant
            self.participants[participant].append(track)
            self.emit(self.track_added, participant, track)

    def remove_track(self, track: LK.TrackId):
        if track in self.tracks:
            participant = self.tracks.pop(track)
            self.participants[participant].remove(track)
            self.emit(self.track_removed, participant, track)

    def remove_participant(self, participant: LK.ParticipantId):
        if participant in self.participants:
            tracks = self.participants.pop(participant)
            for track in tracks:
                self.tracks.pop(track)
            self.emit(self.participant_removed, participant)

    def get_lkParticipantTracks(self, participant_id: Optional[LK.ParticipantId] = None,
                                track_id: Optional[LK.TrackId] = None) -> Optional[
        LK.ParticipantTracks]:
        if participant_id in self.participants:
            tracks = self.participants[participant_id]
            if track_id is None:
                return LK.ParticipantTracks(participant_id, tracks)
            elif track_id in tracks:
                return LK.ParticipantTracks(participant_id, [track_id])
            else:
                return None
        if track_id in self.tracks:
            return LK.ParticipantTracks(self.tracks[track_id], self.participants[self.tracks[track_id]])
        return None


class Signaling:
    sdk = "python"
    uri = "/rtc"
    auto_subscribe = 1
    adaptive_stream = 1
    sdk_params = {
        "go": {
            "protocol": 8,
            "sdk": "go",
            "version": "1.0.3",
        },
        "js": {
            "protocol": 8,
            "sdk": "js",
            "version": "1.3.2",
        },
        "python": {
            "protocol": 8,
            "sdk": "python",  # sdk python is unknown to livekit server, but it shouldn't matter much
            "version": "8",  # this version is made up, as python is not in the livekit supported protocols
        },
    }
    paxtracker = ParticipantTracksTracker()

    def __init__(self, host: str, port: int, room: str, api_key: str, api_secret: str, identity: str = ""):
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
        self.token: LK.Token = create_access_token(self.api_key, self.api_secret, self.room, self.identity)
        self._ws = None
        self.logger = logging.getLogger("livekit-signaling")
        self.ping_task = None

    def on_recv(
            self, event: str, handler: Optional[Handler] = None
    ) -> Union[Handler, Callable[[Handler], Handler]]:
        if event == "all_messages":
            self.received_events.emit_all = True
        if handler is None:
            return self.received_events.listens_to(event)
        else:
            return self.received_events.add_listener(event, handler)

    def on_sent(
            self, event: str, handler: Optional[Handler] = None
    ) -> Union[Handler, Callable[[Handler], Handler]]:
        self._emitting_requests = True
        if event == "all_messages":
            self.sent_events.emit_all = True
        if handler is None:
            return self.sent_events.listens_to(event)
        else:
            return self.sent_events.add_listener(event, handler)

    async def connect_and_run(self, sdk=None):
        self.logger.debug(f"connecting to {self.host}:{self.port}")
        secure = ['', 's'][self.port == 443]
        param_dict = {
            "access_token": self.token,
            "auto_subscribe": self.auto_subscribe,
        }
        param_dict.update(self.sdk_params[sdk or self.sdk])

        params = '&'.join([f"{k}={v}" for k, v in param_dict.items()])
        url = f"ws{secure}://{self.host}:{self.port}{self.uri}?{params}"

        try:
            async for self._ws in websockets.connect(url):
                try:
                    self.logger.info(f"Connected to {url}...")
                    while True:
                        await self.receive()
                    raise Exception("Websocket unexpectedly closed")
                except KeyboardInterrupt:
                    await self.close()
                    break
                except websockets.ConnectionClosed:
                    self.logger.error(f"Connection closed - Reconnecting...")
                    raise
                    continue
                except:
                    self.logger.exception(f"Unexpected error")
                    await self.close()
                    break
        except:
            self.logger.exception(f"Failed to connect to {url}")
            return

        self.logger.error(f"Disconnected from {url}, not retrying.")

    async def close(self):
        if self._ws is not None:
            self.logger.info(f"Closing websocket")
            try:
                await self._ws.close()
            except:
                self.logger.exception(f"ERROR: Closing websocket failed")
                pass
            self._ws = None

    async def send(self, obj: LK.LKBase, no_log=False):
        lkobj = obj.to_signal_request()
        if not no_log:
            self.logger.debug(f"=" * 80)
            self.logger.info(f"Signal sending: {type(obj)} {obj}")

        rc = await self._ws.send(lkobj.SerializeToString())

        if self._emitting_requests and not no_log:
            self._emit_request(obj)

        return rc

    async def receive(self):
        try:
            r = await self._ws.recv()
        except asyncio.exceptions.CancelledError:
            self.logger.exception(f"Websocket recv cancelled")
            raise
            await self.close()
            return None
        except asyncio.exceptions.IncompleteReadError:
            raise
            return None
        except:
            self.logger.exception(f"ERROR on websocket recv")
            self.logger.debug(traceback.format_exc())
            raise
            await self.close()
            return None

        req = lkrtc.SignalResponse()
        try:
            req.ParseFromString(r)
        except:
            self.logger.error(f"ERROR: {traceback.format_exc()}")
            raise
        if req.WhichOneof("message") != "pong":
            self.logger.debug(f"=" * 80)
            self.logger.info(f"Signal receiving: {type(req)} {req}")
            if self.logger.level == logging.DEBUG:
                for desc, field in req.ListFields():
                    self.logger.debug(f"Desc: {type(desc)} {desc.full_name} {desc.name}")
                    self.logger.debug(f"Field: {type(field)} {field}")

        try:
            obj = LK.from_signal_response(req)
        except Exception as e:
            self.logger.exception(f"Failed to parse input: {type(input)} {input}")
            raise
        self._emit_response(obj)
        return req

    async def run(self, sdk=None):
        # setup locally handled events
        self.on_recv("refresh_token", self._on_token_refresh)
        self.on_recv("join", self._on_join)
        self.on_recv("leave", self._on_leave)

        await self.connect_and_run(sdk=sdk)

    async def send_pings(self, interval=30, timeout=60):
        self.logger.info(f"Sending pings at {interval} seconds")

        while True:
            current_time = int(1000 * time.time())
            await self.send(LK.Ping(time=current_time), no_log=True)
            await asyncio.sleep(interval)

    async def send_answer(self, local_desc):
        self.logger.debug(f"Sending ANSWER:\n{wintolin(local_desc.sdp)}")

        #return await self.send(req)
        answer = LK.SessionDescription(type=local_desc.type, sdp=local_desc.sdp)
        return await self.send(answer)

    async def send_offer(self, local_desc):
        self.logger.debug(f"Sending OFFER:\n{wintolin(local_desc.sdp)}")

        offer = LK.SessionDescription(type=local_desc.type, sdp=local_desc.sdp)
        return await self.send(offer)

        #return await self.send(req)

    async def send_add_track(self, track):
        kind = track.kind
        if kind != "video":
            raise NotImplementedError("Track type '{kind}' not supported")

        layer = LK.VideoLayer(
            quality=LK.VideoQuality.HIGH,
            bitrate=1000000,
            width=1920,
            height=1080,
            ssrc=None
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
            disable_red=None

        )

        self.logger.debug(f"Sending add track '{kind}' request, id={track.id}")
        return await self.send(add_track)

    async def send_subscription_permission(self):
        self.logger.debug(f"Sending subscription permission request to all participants")
        return await self.send(LK.SubscriptionPermission(all_participants=True, track_permissions=[]))

    async def send_subscription_request(self, pax_tracks: Dict[str, List[str]]):
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
        subreq = LK.UpdateSubscription(subscribe=True, participant_tracks=[], track_sids=[])
        for pax_id, track_ids in pax_tracks.items():
            participant_tracks = LK.ParticipantTracks(participant_sid=pax_id, track_sids=track_ids)
            subreq.participant_tracks.append(participant_tracks)
            subreq.track_sids.extend(track_ids)

        self.logger.debug(f"Sending subscription request to the server")
        return await self.send(subreq)

    async def send_unsubscription_request(self, unsub: LK.UpdateSubscription):
        self.logger.debug(f"Sending unsubscription request to the server")
        return await self.send(unsub)

    async def send_update_track_settings(self,
                                         track_id: str,
                                         width: Optional[int] = None,
                                         height: Optional[int] = None
                                         ):
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
        req = LK.UpdateTrackSettings(track_sids=[track_id], disabled=False, width=width, height=height, quality=None, fps=30)
        self.logger.debug(f"Sending update track settings request to the server")
        return await self.send(req)

    def _on_join(self, join: LK.JoinResponse):
        timeout = join.ping_timeout or 42
        interval = join.ping_interval or timeout / 2
        self.logger.debug(f"Received join response")
        if self.ping_task is not None:
            self.ping_task.cancel()
        self.ping_task = asyncio.create_task(self.send_pings(interval, timeout))

    def _on_token_refresh(self, token: LK.Token):
        # save the token for reconnection
        self.token = token

    def _on_leave(self, leave: LK.LeaveRequest):
        # close the websocket
        asyncio.create_task(self.close())

    def _emit_response(self, input: LK.LKBase):
        try:
            event, output = input.get_response_name(), input
        except Exception as e:
            self.logger.exception(f"Failed to parse input: {type(input)} {input}")
            raise

        self.received_events.emit(event, output)

        if self.received_events.emit_all and event != "pong":
            self.received_events.emit("all_messages", event, output)

    def _emit_request(self, input: LK.LKBase):
        try:
            event, output = input.get_request_name(), input
        except Exception as e:
            self.logger.exception(f"Failed to parse input: {type(input)} {input}")
            raise

        self.sent_events.emit(event, output)

        if self.sent_events.emit_all:
            self.sent_events.emit("all_messages", event, output)
