from .livekit_protobuf_defs import lkrtc, lkmodels
from .utils import create_access_token, proto_to_aio_candidate, wintolin

from typing import Union, Callable, Optional
import logging
import traceback
import asyncio

from pyee.asyncio import AsyncIOEventEmitter
from pyee.base import Handler

from aiortc import RTCSessionDescription

import websockets



class SignalingEvents(AsyncIOEventEmitter):
    def __init__(self):
        super().__init__()
        self.emit_all = False


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
            "version": "8",   # this version is made up, as python is not in the livekit supported protocols
        },
    }


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
        self.token = create_access_token(self.api_key, self.api_secret, self.room, self.identity)
        self._ws = None
        self.logger = logging.getLogger("livekit-signaling")

    def set_log_level(self, level):
        self.logger.setLevel(level)
        self.logger.critical(f"Signaling log level set to {self.logger.level}")

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

    async def connect(self, sdk=None) -> bool:
        if self._ws is None:
            self.logger.debug(f"connecting to {self.host}:{self.port}")
            secure = ['', 's'][self.port == 443]
            param_dict = {
                "access_token": self.token,
                "auto_subscribe": self.auto_subscribe,
            }
            param_dict.update(self.sdk_params[sdk or self.sdk])

            params = '&'.join([f"{k}={v}" for k, v in param_dict.items()])
            try:
                self._ws = await websockets.connect(f"ws{secure}://{self.host}:{self.port}{self.uri}?{params}")
            except:
                self.logger.exception(f"Failed to connect to {self.host}:{self.port}{self.uri}?{params}")
                return False
            self.logger.debug(f"connected to {self.host}:{self.port}")
            return True

    async def close(self):
        if self._ws is not None:
            self.logger.info(f"Closing websocket")
            try:
                await self._ws.close()
            except:
                self.logger.exception(f"ERROR: Closing websocket failed")
                pass
            self._ws = None

    async def send(self, obj):
        await self.connect()
        self.logger.debug(f"=" * 80)
        self.logger.info(f"Signal sending: {type(obj)} {obj}")
        if self.logger.level == logging.DEBUG:
            for desc, field in obj.ListFields():
                self.logger.debug(f"Desc: {type(desc)} {desc.full_name} {desc.name}")
                self.logger.debug(f"Field: {type(field)} {field}")

        rc = await self._ws.send(obj.SerializeToString())

        if self._emitting_requests:
            self._emit_request(obj)

        return rc

    async def receive(self):
        await self.connect()
        try:
            r = await self._ws.recv()
        except asyncio.exceptions.CancelledError:
            self.logger.exception(f"Websocket recv cancelled")
            await self.close()
            return None
        except:
            self.logger.exception(f"ERROR on websocket recv")
            self.logger.debug(traceback.format_exc())
            await self.close()
            return None

        req = lkrtc.SignalResponse()
        try:
            req.ParseFromString(r)
        except:
            self.logger.error(f"ERROR: {traceback.format_exc()}")
            raise
        self.logger.debug(f"=" * 80)
        self.logger.info(f"Signal receiving: {type(req)} {req}")
        if self.logger.level == logging.DEBUG:
            for desc, field in req.ListFields():
                self.logger.debug(f"Desc: {type(desc)} {desc.full_name} {desc.name}")
                self.logger.debug(f"Field: {type(field)} {field}")

        self._emit_response(req)
        return req

    async def run(self):
        # setup locally handled events
        self.on_recv("refresh_token", self._on_token_refresh)
        self.on_recv("leave", self._on_leave)

        await self.connect()
        while True:
            try:
                obj = await self.receive()
            except KeyboardInterrupt:
                self.logger.debug(f"KeyboardInterrupt")
                await self.close()
                break
            except:
                self.logger.exception(f"ERROR: Failed to receive")
                await self.close()
                break
            if obj is None:
                break

    async def send_answer(self, local_desc):
        req = lkrtc.SignalRequest()
        req.answer.type = local_desc.type
        req.answer.sdp = local_desc.sdp

        self.logger.debug(f"SENDING ANSWER:\n{wintolin(local_desc.sdp)}")

        return await self.send(req)

    async def send_offer(self, local_desc):
        req = lkrtc.SignalRequest()
        req.offer.type = local_desc.type
        req.offer.sdp = local_desc.sdp

        self.logger.debug(f"SENDING OFFER:\n{wintolin(local_desc.sdp)}")

        return await self.send(req)

    async def send_add_track(self, track):
        kind = track.kind
        req = lkrtc.SignalRequest()
        req.add_track.cid = track.id
        if kind == "video":
            req.add_track.type = lkmodels.TrackType.VIDEO
            req.add_track.width = 1920  # track.width
            req.add_track.height = 1080  # track.height
            req.add_track.source = lkmodels.TrackSource.CAMERA
            layer = lkmodels.VideoLayer()
            layer.quality = lkmodels.VideoQuality.HIGH
            layer.bitrate = 1000000
            layer.width = 1920
            layer.height = 1080
            req.add_track.layers.append(layer)
        else:
            raise NotImplementedError("Track type '{kind}' not supported")

        self.logger.debug(f"PLAYER: Sending add track '{kind}' request, id={track.id}")
        return await self.send(req)

    async def send_subscription_permission(self):
        req = lkrtc.SignalRequest()
        req.subscription_permission.all_participants = True
        self.logger.debug(f"PLAYER: Sending subscription permission request to all participants")
        return await self.send(req)

    def _on_token_refresh(self, token):
        # save the token for reconnection
        self.token = token

    def _on_leave(self, reason):
        # close the websocket
        asyncio.create_task(self.close())

    def _emit_response(self, input: lkrtc.SignalResponse):
        if input.WhichOneof('message') == 'join':
            event, output = "join", input.join
        elif input.WhichOneof('message') == "offer":
            event, output = "offer", RTCSessionDescription(sdp=input.offer.sdp, type=input.offer.type)
        elif input.WhichOneof('message') == "answer":
            event, output = "answer", RTCSessionDescription(sdp=input.answer.sdp, type=input.answer.type)
        elif input.WhichOneof('message') == 'trickle':
            event, output = "trickle", (proto_to_aio_candidate(input.trickle.candidateInit), input.trickle.target)
        elif input.WhichOneof('message') == 'update':
            event, output = "update", input.update
        elif input.WhichOneof('message') == 'track_published':
            event, output = "track_published", input.track_published
        elif input.WhichOneof('message') == 'leave':
            event, output = "leave", input.leave
        elif input.WhichOneof('message') == 'mute':
            event, output = "mute", input.mute
        elif input.WhichOneof('message') == 'speakers_changed':
            event, output = "speakers_changed", input.speakers_changed
        elif input.WhichOneof('message') == 'room_update':
            event, output = "room_update", input.room_update
        elif input.WhichOneof('message') == 'connection_quality':
            event, output = "connection_quality", input.connection_quality
        elif input.WhichOneof('message') == 'stream_state_update':
            event, output = "stream_state_update", input.stream_state_update
        elif input.WhichOneof('message') == 'subscribed_quality_update':
            event, output = "subscribed_quality_update", input.subscribed_quality_update
        elif input.WhichOneof('message') == 'subscription_permission_update':
            event, output = "subscription_permission_update", input.subscription_permission_update
        elif input.WhichOneof('message') == 'refresh_token':
            event, output = "refresh_token", input.refresh_token
        elif input.WhichOneof('message') == 'track_unpublished':
            event, output = "track_unpublished", input.track_unpublished
        elif input.WhichOneof('message') == 'pong':
            event, output = "pong", input.pong
        else:
            event, output = "unknown", input
            self.logger.debug(f"RECEIVING UNKNOWN MESSAGE: {input}")
        self.received_events.emit(event, output)

        if self.received_events.emit_all:
            self.received_events.emit("all_messages", output)

    def _emit_request(self, input: lkrtc.SignalRequest):
        if input.WhichOneof('message') == "offer":
            event, output = "offer", RTCSessionDescription(sdp=input.offer.sdp, type=input.offer.type)
        elif input.WhichOneof('message') == "answer":
            event, output = "answer", RTCSessionDescription(sdp=input.answer.sdp, type=input.answer.type)
        elif input.WhichOneof('message') == 'trickle':
            event, output = "trickle", (proto_to_aio_candidate(input.trickle.candidateInit), input.trickle.target)
        elif input.WhichOneof('message') == 'add_track':
            event, output = "add_track", input.add_track
        elif input.WhichOneof('message') == 'mute':
            event, output = "mute", input.mute
        elif input.WhichOneof('message') == 'subscription':
            event, output = "subscription", input.subscription
        elif input.WhichOneof('message') == 'track_setting':
            event, output = "track_setting", input.track_setting
        elif input.WhichOneof('message') == 'leave':
            event, output = "leave", None
        elif input.WhichOneof('message') == 'update_layers':
            event, output = "update_layers", input.update_layers
        elif input.WhichOneof('message') == 'subscription_permission':
            event, output = "subscription_permission", input.subscription_permission
        elif input.WhichOneof('message') == 'sync_state':
            event, output = "sync_state", input.sync_state
        elif input.WhichOneof('message') == 'simulate':
            event, output = "simulate", input.simulate
        elif input.WhichOneof('message') == 'ping':
            event, output = "ping", input.ping
        else:
            event, output = "unkown", input
            kind = input.WhichOneof('message')
            self.logger.debug(f"SENDING UNKNOWN MESSAGE: {type(kind)} {kind} {input}")

        self.sent_events.emit(event, output)

        if self.sent_events.emit_all:
            self.sent_events.emit("all_messages", output)
