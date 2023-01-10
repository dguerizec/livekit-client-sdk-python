# Wrapper classes to avoid protobuf weirdness in client apps
import logging
import sys
import enum

from dataclasses import dataclass
from typing import NewType, List

import aiortc
from aiortc import RTCIceCandidate  # type: ignore

from .livekit_protobuf_defs import lkrtc  # type: ignore
from .livekit_protobuf_defs import lkmodels
from .utils import proto_to_aio_candidate, aio_to_proto_candidate

Time = NewType("Time", int)
Token = NewType("Token", str)
ParticipantId = NewType("ParticipantId", str)
TrackId = NewType("TrackId", str)


class LKEnum(enum.Enum):
    def __str__(self):
        return self.name

    @classmethod
    def from_lk(cls, pb):
        raise NotImplementedError()

    def to_lk(self):
        raise NotImplementedError()


def ind(indent):
    return f"{indent:2d}" + " " * indent


class LKBase:
    def __str__(self):
        return self.__dump__()

    def __repr__(self):
        return self.__dump__()

    def __dump__(self, indent=""):
        if indent == "":
            s = ["\nXXXXX " + self.__class__.__name__ + ":"]
            indent = "    "
        else:
            s = [f"{self.__class__.__name__}:"]
        for attr in dir(self):
            if attr.startswith("_"):
                continue
            value = getattr(self, attr)
            # check if it's a method
            if callable(value):
                continue
            if isinstance(value, LKBase):
                s.append(f"{indent}{attr} = {value.__dump__(indent + '    ')}")
            elif isinstance(value, list):
                s.append(f"{indent}{attr} = [")
                for v in value:
                    if isinstance(v, LKBase):
                        s.append(f"{indent}    " + v.__dump__(indent + "        "))
                    else:
                        s.append(f"{indent}    {v}")
                s.append(f"{indent}]")
            else:
                s.append(f"{indent}{attr} = {value}")

        return f"\n".join(s)

    @classmethod
    def from_lk(cls, pb):
        raise NotImplementedError()

    def to_lk(self):
        raise NotImplementedError()

    def to_signal_request(self):
        msg = getattr(self, '__signal_request__', None)
        if msg is None:
            raise Exception(f"Cannot convert {self.__class__} to SignalRequest")
        req = lkrtc.SignalRequest(**{msg: self.to_lk()})
        return req

    @classmethod
    def from_signal_response(cls, response: lkrtc.SignalResponse):
        msg = getattr(cls, '__signal_response__', None)
        if msg is None:
            print(dir(cls))
            raise Exception(f"Cannot convert {type(response)} to {cls.__class__}: {response}")
        if response.WhichOneof("message") != msg:
            raise Exception(f"SignalResponse is not {msg}")
        return cls.from_lk(getattr(response, msg))

    @classmethod
    def from_signal_request(cls, request: lkrtc.SignalRequest):
        msg = getattr(cls, '__signal_request__', None)
        if msg is None:
            raise Exception(f"Cannot convert {type(request)} to {cls.__class__}")
        if request.WhichOneof("message") != msg:
            raise Exception(f"SignalRequest is not {msg}")
        return cls.from_lk(getattr(request, msg))

    def get_response_name(self):
        return getattr(self, '__signal_response__', None)

    def get_request_name(self):
        return getattr(self, '__signal_request__', None)


class ParticipantInfoState(LKEnum):
    JOINING = enum.auto()
    JOINED = enum.auto()
    ACTIVE = enum.auto()
    DISCONNECTED = enum.auto()

    @classmethod
    def from_lk(cls, state: lkmodels.ParticipantInfo.State) -> "ParticipantInfoState":
        if state == lkmodels.ParticipantInfo.State.JOINING:
            return cls.JOINING
        elif state == lkmodels.ParticipantInfo.State.JOINED:
            return cls.JOINED
        elif state == lkmodels.ParticipantInfo.State.ACTIVE:
            return cls.ACTIVE
        elif state == lkmodels.ParticipantInfo.State.DISCONNECTED:
            return cls.DISCONNECTED
        else:
            raise ValueError(f"Unknown ParticipantState: {state}")

    def to_lk(self) -> lkmodels.ParticipantInfo.State:
        if self == ParticipantInfoState.JOINING:
            return lkmodels.ParticipantInfo.State.JOINING
        elif self == ParticipantInfoState.JOINED:
            return lkmodels.ParticipantInfo.State.JOINED
        elif self == ParticipantInfoState.ACTIVE:
            return lkmodels.ParticipantInfo.State.ACTIVE
        elif self == ParticipantInfoState.DISCONNECTED:
            return lkmodels.ParticipantInfo.State.DISCONNECTED
        else:
            raise ValueError(f"Unknown ParticipantState: {self}")


class TrackType(LKEnum):
    AUDIO = enum.auto()
    VIDEO = enum.auto()
    DATA = enum.auto()

    @classmethod
    def from_lk(cls, track_type: lkmodels.TrackType) -> "TrackType":
        if track_type == lkmodels.TrackType.AUDIO:
            return cls.AUDIO
        elif track_type == lkmodels.TrackType.VIDEO:
            return cls.VIDEO
        elif track_type == lkmodels.TrackType.DATA:
            return cls.DATA
        else:
            raise ValueError(f"Unknown TrackType: {track_type}")

    def to_lk(self) -> lkmodels.TrackType:
        if self == self.AUDIO:
            return lkmodels.TrackType.AUDIO
        elif self == self.VIDEO:
            return lkmodels.TrackType.VIDEO
        elif self == self.DATA:
            return lkmodels.TrackType.DATA
        else:
            raise ValueError(f"Unknown TrackType: {self}")


@dataclass
class TrackSource(LKEnum):
    """
    UNKNOWN = 0;
    CAMERA = 1;
    MICROPHONE = 2;
    SCREEN_SHARE = 3;
    SCREEN_SHARE_AUDIO = 4;
    """
    NONE = enum.auto()
    UNKNOWN = enum.auto()
    CAMERA = enum.auto()
    MICROPHONE = enum.auto()
    SCREEN_SHARE = enum.auto()
    SCREEN_SHARE_AUDIO = enum.auto()

    @classmethod
    def from_lk(cls, source: lkmodels.TrackSource) -> "TrackSource":
        if source == lkmodels.TrackSource.UNKNOWN:
            return cls.UNKNOWN
        elif source == lkmodels.TrackSource.CAMERA:
            return cls.CAMERA
        elif source == lkmodels.TrackSource.MICROPHONE:
            return cls.MICROPHONE
        elif source == lkmodels.TrackSource.SCREEN_SHARE:
            return cls.SCREEN_SHARE
        elif source == lkmodels.TrackSource.SCREEN_SHARE_AUDIO:
            return cls.SCREEN_SHARE_AUDIO
        else:
            raise ValueError(f"Unknown TrackSource: {source}")

    def to_lk(self) -> lkmodels.TrackSource:
        if self == self.UNKNOWN:
            return lkmodels.TrackSource.UNKNOWN
        elif self == self.CAMERA:
            return lkmodels.TrackSource.CAMERA
        elif self == self.MICROPHONE:
            return lkmodels.TrackSource.MICROPHONE
        elif self == self.SCREEN_SHARE:
            return lkmodels.TrackSource.SCREEN_SHARE
        elif self == self.SCREEN_SHARE_AUDIO:
            return lkmodels.TrackSource.SCREEN_SHARE_AUDIO
        else:
            raise ValueError(f"Unknown TrackSource: {self}")


class VideoQuality(LKEnum):
    """
    LOW = 0;
    MEDIUM = 1;
    HIGH = 2;
    OFF = 3;
    """
    NONE = enum.auto()
    LOW = enum.auto()
    MEDIUM = enum.auto()
    HIGH = enum.auto()
    OFF = enum.auto()

    @classmethod
    def from_lk(cls, layer: lkmodels.VideoQuality) -> "VideoQuality":
        if layer == lkmodels.VideoQuality.LOW:
            return cls.LOW
        elif layer == lkmodels.VideoQuality.MEDIUM:
            return cls.MEDIUM
        elif layer == lkmodels.VideoQuality.HIGH:
            return cls.HIGH
        elif layer == lkmodels.VideoQuality.OFF:
            return cls.OFF
        else:
            raise ValueError(f"Unknown VideoQuality: {layer}")

    def to_lk(self) -> lkmodels.VideoQuality:
        if self == self.LOW:
            return lkmodels.VideoQuality.LOW
        elif self == self.MEDIUM:
            return lkmodels.VideoQuality.MEDIUM
        elif self == self.HIGH:
            return lkmodels.VideoQuality.HIGH
        elif self == self.OFF:
            return lkmodels.VideoQuality.OFF
        else:
            raise ValueError(f"Unknown VideoQuality: {self}")


@dataclass
class VideoLayer(LKBase):
    """
    // for tracks with a single layer, this should be HIGH
    VideoQuality quality = 1;
    uint32 width = 2;
    uint32 height = 3;
    // target bitrate in bit per second (bps), server will measure actual
    uint32 bitrate = 4;
    uint32 ssrc = 5;
    """
    quality: VideoQuality
    width: int
    height: int
    bitrate: int
    ssrc: int

    @classmethod
    def from_lk(cls, layer: lkmodels.VideoLayer) -> "VideoLayer":
        return cls(
            VideoQuality.from_lk(layer.quality),
            layer.width,
            layer.height,
            layer.bitrate,
            layer.ssrc,
        )

    def to_lk(self) -> lkmodels.VideoLayer:
        return lkmodels.VideoLayer(
            quality=self.quality.to_lk(),
            width=self.width,
            height=self.height,
            bitrate=self.bitrate,
            ssrc=self.ssrc,
        )


@dataclass
class SimulcastCodecInfo(LKBase):
    """
    string mime_type = 1;
    string mid = 2;
    string cid = 3;
    repeated VideoLayer layers = 4;
    """
    mime_type: str
    mid: str
    cid: str
    layers: List[VideoLayer]

    @classmethod
    def from_lk(cls, codec: lkmodels.SimulcastCodecInfo) -> "SimulcastCodecInfo":
        return cls(
            codec.mime_type,
            codec.mid,
            codec.cid,
            [VideoLayer.from_lk(layer) for layer in codec.layers],
        )

    def to_lk(self) -> lkmodels.SimulcastCodecInfo:
        return lkmodels.SimulcastCodecInfo(
            mime_type=self.mime_type,
            mid=self.mid,
            cid=self.cid,
            layers=[layer.to_lk() for layer in self.layers],
        )


@dataclass
class TrackInfo(LKBase):
    """
    string sid = 1;
    TrackType type = 2;
    string name = 3;
    bool muted = 4;
    // original width of video (unset for audio)
    // clients may receive a lower resolution version with simulcast
    uint32 width = 5;
    // original height of video (unset for audio)
    uint32 height = 6;
    // true if track is simulcasted
    bool simulcast = 7;
    // true if DTX (Discontinuous Transmission) is disabled for audio
    bool disable_dtx = 8;
    // source of media
    TrackSource source = 9;
    repeated VideoLayer layers = 10;
    // mime type of codec
    string mime_type = 11;
    string mid = 12;
    repeated SimulcastCodecInfo codecs = 13;
    bool stereo = 14;
    // true if RED (Redundant Encoding) is disabled for audio
    bool disable_red = 15;
    """

    sid: str
    type: TrackType
    name: str
    muted: bool
    width: int
    height: int
    simulcast: bool
    disable_dtx: bool
    source: TrackSource
    layers: List[VideoLayer]
    mime_type: str
    mid: str
    codecs: List[SimulcastCodecInfo]
    stereo: bool
    disable_red: bool

    @classmethod
    def from_lk(cls, track_info: lkmodels.TrackInfo) -> "TrackInfo":
        return cls(
            sid=track_info.sid,
            type=TrackType.from_lk(track_info.type),
            name=track_info.name,
            muted=track_info.muted,
            width=track_info.width,
            height=track_info.height,
            simulcast=track_info.simulcast,
            disable_dtx=track_info.disable_dtx,
            source=TrackSource.from_lk(track_info.source),
            layers=[VideoLayer.from_lk(layer) for layer in track_info.layers],
            mime_type=track_info.mime_type,
            mid=track_info.mid,
            codecs=[SimulcastCodecInfo.from_lk(c) for c in track_info.codecs],
            stereo=track_info.stereo,
            disable_red=track_info.disable_red,
        )

    def to_lk(self) -> lkmodels.TrackInfo:
        return lkmodels.TrackInfo(
            sid=self.sid,
            type=self.type.to_lk(),
            name=self.name,
            muted=self.muted,
            width=self.width,
            height=self.height,
            simulcast=self.simulcast,
            disable_dtx=self.disable_dtx,
            source=self.source.to_lk(),
            layers=[layer.to_lk() for layer in self.layers],
            mime_type=self.mime_type,
            mid=self.mid,
            codecs=[c.to_lk() for c in self.codecs],
            stereo=self.stereo,
            disable_red=self.disable_red,
        )


@dataclass
class ParticipantPermission(LKBase):
    """
    // allow participant to subscribe to other tracks in the room
    bool can_subscribe = 1;
    // allow participant to publish new tracks to room
    bool can_publish = 2;
    // allow participant to publish data
    bool can_publish_data = 3;
    // indicates that it's hidden to others
    bool hidden = 7;
    // indicates it's a recorder instance
    bool recorder = 8;
    """
    can_subscribe: bool
    can_publish: bool
    can_publish_data: bool
    hidden: bool
    recorder: bool

    @classmethod
    def from_lk(cls, perm: lkmodels.ParticipantPermission) -> "ParticipantPermission":
        return cls(
            can_subscribe=perm.can_subscribe,
            can_publish=perm.can_publish,
            can_publish_data=perm.can_publish_data,
            hidden=perm.hidden,
            recorder=perm.recorder,
        )

    def to_lk(self) -> lkmodels.ParticipantPermission:
        return lkmodels.ParticipantPermission(
            can_subscribe=self.can_subscribe,
            can_publish=self.can_publish,
            can_publish_data=self.can_publish_data,
            hidden=self.hidden,
            recorder=self.recorder,
        )


@dataclass
class ParticipantInfo(LKBase):
    """
    enum State {
      // websocket' connected, but not offered yet
      JOINING = 0;
      // server received client offer
      JOINED = 1;
      // ICE connectivity established
      ACTIVE = 2;
      // WS disconnected
      DISCONNECTED = 3;
    }
    string sid = 1;
    string identity = 2;
    State state = 3;
    repeated TrackInfo tracks = 4;
    string metadata = 5;
    // timestamp when participant joined room, in seconds
    int64 joined_at = 6;
    string name = 9;
    uint32 version = 10;
    ParticipantPermission permission = 11;
    string region = 12;
    // indicates the participant has an active publisher connection
    // and can publish to the server
    bool is_publisher = 13;

    """
    sid: str
    identity: str
    state: ParticipantInfoState
    tracks: List["TrackInfo"]
    metadata: str
    joined_at: Time
    name: str
    version: int
    permission: "ParticipantPermission"
    region: str
    is_publisher: bool

    @classmethod
    def from_lk(cls, info: lkmodels.ParticipantInfo) -> "ParticipantInfo":
        return cls(
            sid=info.sid,
            identity=info.identity,
            state=ParticipantInfoState.from_lk(info.state),
            tracks=[TrackInfo.from_lk(t) for t in info.tracks],
            metadata=info.metadata,
            joined_at=Time(info.joined_at),
            name=info.name,
            version=info.version,
            permission=ParticipantPermission.from_lk(info.permission),
            region=info.region,
            is_publisher=info.is_publisher,
        )

    def to_lk(self) -> lkmodels.ParticipantInfo:
        return lkmodels.ParticipantInfo(
            sid=self.sid,
            identity=self.identity,
            state=self.state.to_lk(),
            tracks=[t.to_lk() for t in self.tracks],
            metadata=self.metadata,
            joined_at=self.joined_at,
            name=self.name,
            version=self.version,
            permission=self.permission.to_lk(),
            region=self.region,
            is_publisher=self.is_publisher,
        )


@dataclass
class Codec(LKBase):
    """
    string mime = 1;
    string fmtp_line = 2;
    """
    mime: str
    fmtp_line: str

    @classmethod
    def from_lk(cls, codec: lkmodels.Codec) -> "Codec":
        return cls(
            mime=codec.mime,
            fmtp_line=codec.fmtp_line,
        )

    def to_lk(self) -> lkmodels.Codec:
        return lkmodels.Codec(
            mime=self.mime,
            fmtp_line=self.fmtp_line,
        )


@dataclass
class Room(LKBase):
    """
    string sid = 1;
    string name = 2;
    uint32 empty_timeout = 3;
    uint32 max_participants = 4;
    int64 creation_time = 5;
    string turn_password = 6;
    repeated Codec enabled_codecs = 7;
    string metadata = 8;
    uint32 num_participants = 9;
    bool active_recording = 10;
    """
    sid: str
    name: str
    empty_timeout: int
    max_participants: int
    creation_time: Time
    turn_password: str
    enabled_codecs: List[Codec]
    metadata: str
    num_participants: int
    active_recording: bool

    @classmethod
    def from_lk(cls, room: lkmodels.Room) -> "Room":
        return cls(
            sid=room.sid,
            name=room.name,
            empty_timeout=room.empty_timeout,
            max_participants=room.max_participants,
            creation_time=Time(room.creation_time),
            turn_password=room.turn_password,
            enabled_codecs=[Codec.from_lk(c) for c in room.enabled_codecs],
            metadata=room.metadata,
            num_participants=room.num_participants,
            active_recording=room.active_recording,
        )

    def to_lk(self) -> lkmodels.Room:
        return lkmodels.Room(
            sid=self.sid,
            name=self.name,
            empty_timeout=self.empty_timeout,
            max_participants=self.max_participants,
            creation_time=self.creation_time,
            turn_password=self.turn_password,
            enabled_codecs=[c.to_lk() for c in self.enabled_codecs],
            metadata=self.metadata,
            num_participants=self.num_participants,
            active_recording=self.active_recording,
        )


@dataclass
class ICEServer(LKBase):
    """
    repeated string urls = 1;
    string username = 2;
    string credential = 3;
    """
    urls: List[str]
    username: str
    credential: str

    @classmethod
    def from_lk(cls, ice: lkrtc.ICEServer) -> "ICEServer":
        return cls(
            urls=[url for url in ice.urls],
            username=ice.username,
            credential=ice.credential,
        )

    def to_lk(self) -> lkrtc.ICEServer:
        return lkrtc.ICEServer(
            urls=self.urls,
            username=self.username,
            credential=self.credential,
        )


class ClientConfigSetting(LKEnum):
    """
    UNSET = 0;
    DISABLED = 1;
    ENABLED = 2;
    """
    UNSET = enum.auto()
    DISABLED = enum.auto()
    ENABLED = enum.auto()

    @classmethod
    def from_lk(cls, setting: lkmodels.ClientConfigSetting) -> "ClientConfigSetting":
        if setting == lkmodels.ClientConfigSetting.UNSET:
            return cls.UNSET
        elif setting == lkmodels.ClientConfigSetting.DISABLED:
            return cls.DISABLED
        elif setting == lkmodels.ClientConfigSetting.ENABLED:
            return cls.ENABLED
        else:
            raise ValueError(f"Unknown ClientConfigSetting: {setting}")

    def to_lk(self) -> lkmodels.ClientConfigSetting:
        if self == self.UNSET:
            return lkmodels.ClientConfigSetting.UNSET
        elif self == self.DISABLED:
            return lkmodels.ClientConfigSetting.DISABLED
        elif self == self.ENABLED:
            return lkmodels.ClientConfigSetting.ENABLED
        else:
            raise ValueError(f"Unknown ClientConfigSetting: {self}")


@dataclass
class VideoConfiguration(LKBase):
    """
    ClientConfigSetting hardware_encoder = 1;
    """
    hardware_encoder: ClientConfigSetting

    @classmethod
    def from_lk(cls, config: lkmodels.VideoConfiguration) -> "VideoConfiguration":
        return cls(
            hardware_encoder=ClientConfigSetting.from_lk(config.hardware_encoder),
        )

    def to_lk(self) -> lkmodels.VideoConfiguration:
        return lkmodels.VideoConfiguration(
            hardware_encoder=self.hardware_encoder.to_lk(),
        )


@dataclass
class DisabledCodecs(LKBase):
    """
    repeated Codec codecs = 1;
    """
    codecs: List[Codec]

    @classmethod
    def from_lk(cls, disabled_codecs: lkmodels.DisabledCodecs) -> "DisabledCodecs":
        return cls(
            codecs=[Codec.from_lk(c) for c in disabled_codecs.codecs],
        )

    def to_lk(self) -> lkmodels.DisabledCodecs:
        return lkmodels.DisabledCodecs(
            codecs=[c.to_lk() for c in self.codecs],
        )


@dataclass
class ClientConfiguration(LKBase):
    """
    VideoConfiguration video = 1;
    VideoConfiguration screen = 2;

    ClientConfigSetting resume_connection = 3;
    DisabledCodecs disabled_codecs = 4;
    ClientConfigSetting force_relay = 5;
    """
    video: VideoConfiguration
    screen: VideoConfiguration
    resume_connection: ClientConfigSetting
    disabled_codecs: DisabledCodecs
    force_relay: ClientConfigSetting

    @classmethod
    def from_lk(cls, config: lkmodels.ClientConfiguration) -> "ClientConfiguration":
        return cls(
            video=VideoConfiguration.from_lk(config.video),
            screen=VideoConfiguration.from_lk(config.screen),
            resume_connection=ClientConfigSetting.from_lk(config.resume_connection),
            disabled_codecs=DisabledCodecs.from_lk(config.disabled_codecs),
            force_relay=ClientConfigSetting.from_lk(config.force_relay),
        )

    def to_lk(self) -> lkmodels.ClientConfiguration:
        return lkmodels.ClientConfiguration(
            video=self.video.to_lk(),
            screen=self.screen.to_lk(),
            resume_connection=self.resume_connection.to_lk(),
            disabled_codecs=self.disabled_codecs.to_lk(),
            force_relay=self.force_relay.to_lk(),
        )


class ServerInfoEdition(LKEnum):
    """
    Standard = 0;
    Cloud = 1;
    """
    NONE = enum.auto()
    STANDARD = enum.auto()
    CLOUD = enum.auto()

    @classmethod
    def from_lk(cls, edition: lkmodels.ServerInfo.Edition) -> "ServerInfoEdition":
        if edition == lkmodels.ServerInfo.Edition.Standard:
            return cls.STANDARD
        elif edition == lkmodels.ServerInfo.Edition.Cloud:
            return cls.CLOUD
        else:
            raise ValueError(f"Unknown ServerInfo_Edition: {edition}")

    def to_lk(self) -> lkmodels.ServerInfo.Edition:
        if self == self.STANDARD:
            return lkmodels.ServerInfo.Edition.Standard
        elif self == self.CLOUD:
            return lkmodels.ServerInfo.Edition.Cloud
        else:
            raise ValueError(f"Unknown ServerInfo_Edition: {self}")


@dataclass
class ServerInfo(LKBase):
    """
    enum Edition {
      Standard = 0;
      Cloud = 1;
    }
    Edition edition = 1;
    string version = 2;
    int32 protocol = 3;
    string region = 4;
    string node_id = 5;
    // additional debugging information. sent only if server is in development mode
    string debug_info = 6;
    """
    edition: ServerInfoEdition
    version: str
    protocol: int
    region: str
    node_id: str
    debug_info: str

    @classmethod
    def from_lk(cls, info: lkmodels.ServerInfo) -> "ServerInfo":
        return cls(
            edition=ServerInfoEdition.from_lk(info.edition),
            version=info.version,
            protocol=info.protocol,
            region=info.region,
            node_id=info.node_id,
            debug_info=info.debug_info,
        )

    def to_lk(self) -> lkmodels.ServerInfo:
        return lkmodels.ServerInfo(
            edition=self.edition.to_lk(),
            version=self.version,
            protocol=self.protocol,
            region=self.region,
            node_id=self.node_id,
            debug_info=self.debug_info,
        )


@dataclass
class JoinResponse(LKBase):
    __signal_response__ = "join"
    """
    Room room = 1;
    ParticipantInfo participant = 2;
    repeated ParticipantInfo other_participants = 3;
    // deprecated. use server_info.version instead.
    string server_version = 4;
    repeated ICEServer ice_servers = 5;
    // use subscriber as the primary PeerConnection
    bool subscriber_primary = 6;
    // when the current server isn't available, return alternate url to retry connection
    // when this is set, the other fields will be largely empty
    string alternative_url = 7;
    ClientConfiguration client_configuration = 8;
    // deprecated. use server_info.region instead.
    string server_region = 9;
    int32 ping_timeout = 10;
    int32 ping_interval = 11;
    ServerInfo server_info = 12;

    """
    room: Room
    participant: ParticipantInfo
    other_participants: List[ParticipantInfo]

    server_version: str
    ice_servers: List[ICEServer]
    subscriber_primary: bool
    alternative_url: str
    client_configuration: ClientConfiguration
    server_region: str
    ping_timeout: int
    ping_interval: int
    server_info: ServerInfo

    @classmethod
    def from_lk(cls, resp: lkrtc.JoinResponse) -> "JoinResponse":
        return cls(
            room=Room.from_lk(resp.room),
            participant=ParticipantInfo.from_lk(resp.participant),
            other_participants=[ParticipantInfo.from_lk(p) for p in resp.other_participants],
            server_version=resp.server_version,
            ice_servers=[ICEServer.from_lk(i) for i in resp.ice_servers],
            subscriber_primary=resp.subscriber_primary,
            alternative_url=resp.alternative_url,
            client_configuration=ClientConfiguration.from_lk(resp.client_configuration),
            server_region=resp.server_region,
            ping_timeout=resp.ping_timeout,
            ping_interval=resp.ping_interval,
            server_info=ServerInfo.from_lk(resp.server_info),
        )

    def to_lk(self):
        return lkrtc.JoinResponse(
            room=self.room.to_lk(),
            participant=self.participant.to_lk(),
            other_participants=[p.to_lk() for p in self.other_participants],
            server_version=self.server_version,
            ice_servers=[i.to_lk() for i in self.ice_servers],
            subscriber_primary=self.subscriber_primary,
            alternative_url=self.alternative_url,
            client_configuration=self.client_configuration.to_lk(),
            server_region=self.server_region,
            ping_timeout=self.ping_timeout,
            ping_interval=self.ping_interval,
            server_info=self.server_info.to_lk(),
        )


@dataclass
class SignalTarget(LKEnum):
    """
    PUBLISHER = 0;
    SUBSCRIBER = 1;
    """
    NONE = enum.auto()
    PUBLISHER = enum.auto()
    SUBSCRIBER = enum.auto()

    @classmethod
    def from_lk(cls, target: lkrtc.SignalTarget) -> "SignalTarget":
        if target == lkrtc.SignalTarget.PUBLISHER:
            return cls.PUBLISHER
        elif target == lkrtc.SignalTarget.SUBSCRIBER:
            return cls.SUBSCRIBER
        else:
            raise ValueError(f"Unknown SignalTarget: {target}")

    def to_lk(self) -> lkrtc.SignalTarget:
        if self == self.PUBLISHER:
            return lkrtc.SignalTarget.PUBLISHER
        elif self == self.SUBSCRIBER:
            return lkrtc.SignalTarget.SUBSCRIBER
        else:
            raise ValueError(f"Unknown SignalTarget: {self}")


@dataclass
class TrickleRequest(LKBase):
    __signal_request__ = "trickle"
    __signal_response__ = "trickle"
    """
    string candidateInit = 1;
    SignalTarget target = 2;
    """
    candidate: RTCIceCandidate
    target: SignalTarget

    @classmethod
    def from_lk(cls, req: lkrtc.TrickleRequest) -> "TrickleRequest":
        candidate = proto_to_aio_candidate(req.candidateInit)
        return cls(
            candidate=candidate,
            target=SignalTarget.from_lk(req.target),
        )

    def to_lk(self) -> lkrtc.TrickleRequest:
        candidateInit = aio_to_proto_candidate(self.candidate)
        return lkrtc.TrickleRequest(
            candidateInit=candidateInit,
            target=self.target.to_lk(),
        )


@dataclass
class MuteTrackRequest(LKBase):
    __signal_request__ = "mute"
    __signal_response__ = "mute"
    """
    string sid = 1;
    bool muted = 2;
    """
    sid: str
    muted: bool

    @classmethod
    def from_lk(cls, req: lkrtc.MuteTrackRequest) -> "MuteTrackRequest":
        return cls(
            sid=req.sid,
            muted=req.muted,
        )

    def to_lk(self) -> lkrtc.MuteTrackRequest:
        return lkrtc.MuteTrackRequest(
            sid=self.sid,
            muted=self.muted,
        )


@dataclass
class ParticipantUpdate(LKBase):
    __signal_response__ = "update"
    """
    repeated ParticipantInfo participants = 1;
    """
    participants: List[ParticipantInfo]

    @classmethod
    def from_lk(cls, update: lkrtc.ParticipantUpdate) -> "ParticipantUpdate":
        return cls(
            participants=[ParticipantInfo.from_lk(p) for p in update.participants],
        )

    def to_lk(self) -> lkrtc.ParticipantUpdate:
        return lkrtc.ParticipantUpdate(
            participants=[p.to_lk() for p in self.participants],
        )


@dataclass
class TrackPublishedResponse:
    __signal_response__ = "track_published"
    """
    string cid = 1;
    TrackInfo track = 2;
    """
    cid: str
    track: TrackInfo

    @classmethod
    def from_lk(cls, resp: lkrtc.TrackPublishedResponse) -> "TrackPublishedResponse":
        return cls(
            cid=resp.cid,
            track=TrackInfo.from_lk(resp.track),
        )

    def to_lk(self) -> lkrtc.TrackPublishedResponse:
        return lkrtc.TrackPublishedResponse(
            cid=self.cid,
            track=self.track.to_lk(),
        )


class DisconnectReason(LKEnum):
    """
    UNKNOWN_REASON = 0;
    CLIENT_INITIATED = 1;
    DUPLICATE_IDENTITY = 2;
    SERVER_SHUTDOWN = 3;
    PARTICIPANT_REMOVED = 4;
    ROOM_DELETED = 5;
    STATE_MISMATCH = 6;
    JOIN_FAILURE = 7;
    """
    UNKNOWN_REASON = enum.auto()
    CLIENT_INITIATED = enum.auto()
    DUPLICATE_IDENTITY = enum.auto()
    SERVER_SHUTDOWN = enum.auto()
    PARTICIPANT_REMOVED = enum.auto()
    ROOM_DELETED = enum.auto()
    STATE_MISMATCH = enum.auto()
    JOIN_FAILURE = enum.auto()

    @classmethod
    def from_lk(cls, reason: lkmodels.DisconnectReason) -> "DisconnectReason":
        if reason == lkmodels.DisconnectReason.UNKNOWN_REASON:
            return cls.UNKNOWN_REASON
        elif reason == lkmodels.DisconnectReason.CLIENT_INITIATED:
            return cls.CLIENT_INITIATED
        elif reason == lkmodels.DisconnectReason.DUPLICATE_IDENTITY:
            return cls.DUPLICATE_IDENTITY
        elif reason == lkmodels.DisconnectReason.SERVER_SHUTDOWN:
            return cls.SERVER_SHUTDOWN
        elif reason == lkmodels.DisconnectReason.PARTICIPANT_REMOVED:
            return cls.PARTICIPANT_REMOVED
        elif reason == lkmodels.DisconnectReason.ROOM_DELETED:
            return cls.ROOM_DELETED
        elif reason == lkmodels.DisconnectReason.STATE_MISMATCH:
            return cls.STATE_MISMATCH
        elif reason == lkmodels.DisconnectReason.JOIN_FAILURE:
            return cls.JOIN_FAILURE
        else:
            raise ValueError(f"Unknown DisconnectReason: {reason}")

    def to_lk(self) -> lkmodels.DisconnectReason:
        if self == self.UNKNOWN_REASON:
            return lkmodels.DisconnectReason.UNKNOWN_REASON
        elif self == self.CLIENT_INITIATED:
            return lkmodels.DisconnectReason.CLIENT_INITIATED
        elif self == self.DUPLICATE_IDENTITY:
            return lkmodels.DisconnectReason.DUPLICATE_IDENTITY
        elif self == self.SERVER_SHUTDOWN:
            return lkmodels.DisconnectReason.SERVER_SHUTDOWN
        elif self == self.PARTICIPANT_REMOVED:
            return lkmodels.DisconnectReason.PARTICIPANT_REMOVED
        elif self == self.ROOM_DELETED:
            return lkmodels.DisconnectReason.ROOM_DELETED
        elif self == self.STATE_MISMATCH:
            return lkmodels.DisconnectReason.STATE_MISMATCH
        elif self == self.JOIN_FAILURE:
            return lkmodels.DisconnectReason.JOIN_FAILURE
        else:
            raise ValueError(f"Unknown DisconnectReason: {self}")


@dataclass
class LeaveRequest(LKBase):
    __signal_request__ = "leave"
    __signal_response__ = "leave"
    """
     // sent when server initiates the disconnect due to server-restart
     // indicates clients should attempt full-reconnect sequence
    bool can_reconnect = 1;
    DisconnectReason reason = 2;
    """
    can_reconnect: bool
    reason: DisconnectReason

    @classmethod
    def from_lk(cls, req: lkrtc.LeaveRequest) -> "LeaveRequest":
        return cls(
            can_reconnect=req.can_reconnect,
            reason=DisconnectReason.from_lk(req.reason),
        )

    def to_lk(self) -> lkrtc.LeaveRequest:
        return lkrtc.LeaveRequest(
            can_reconnect=self.can_reconnect,
            reason=self.reason.to_lk(),
        )


@dataclass
class SpeakerInfo(LKBase):
    """
    string sid = 1;
    // audio level, 0-1.0, 1 is loudest
    float level = 2;
    // true if speaker is currently active
    bool active = 3;
    """
    sid: str
    level: float
    active: bool

    @classmethod
    def from_lk(cls, info: lkmodels.SpeakerInfo) -> "SpeakerInfo":
        return cls(
            sid=info.sid,
            level=info.level,
            active=info.active,
        )

    def to_lk(self) -> lkmodels.SpeakerInfo:
        return lkmodels.SpeakerInfo(
            sid=self.sid,
            level=self.level,
            active=self.active,
        )


@dataclass
class SpeakersChanged(LKBase):
    __signal_response__ = "speakers_changed"
    """
    repeated SpeakerInfo speakers = 1;
    """
    speakers: List[SpeakerInfo]

    @classmethod
    def from_lk(cls, update: lkrtc.SpeakersChanged) -> "SpeakersChanged":
        return cls(
            speakers=[SpeakerInfo.from_lk(s) for s in update.speakers],
        )

    def to_lk(self) -> lkrtc.SpeakersChanged:
        return lkrtc.SpeakersChanged(
            speakers=[s.to_lk() for s in self.speakers],
        )


@dataclass
class RoomUpdate(LKBase):
    __signal_response__ = "room_update"
    """
    Room room = 1;
    """
    room: Room

    @classmethod
    def from_lk(cls, update: lkrtc.RoomUpdate) -> "RoomUpdate":
        return cls(
            room=Room.from_lk(update.room),
        )

    def to_lk(self) -> lkrtc.RoomUpdate:
        return lkrtc.RoomUpdate(
            room=self.room.to_lk(),
        )


@dataclass
class ConnectionQuality(LKEnum):
    """
    POOR = 0;
    GOOD = 1;
    EXCELLENT = 2;
    """
    POOR = 0
    GOOD = 1
    EXCELLENT = 2

    @classmethod
    def from_lk(cls, quality: lkmodels.ConnectionQuality) -> "ConnectionQuality":
        if quality == lkmodels.ConnectionQuality.POOR:
            return cls.POOR
        elif quality == lkmodels.ConnectionQuality.GOOD:
            return cls.GOOD
        elif quality == lkmodels.ConnectionQuality.EXCELLENT:
            return cls.EXCELLENT
        else:
            raise ValueError(f"Unknown ConnectionQuality: {quality}")

    def to_lk(self) -> lkmodels.ConnectionQuality:
        if self == self.POOR:
            return lkmodels.ConnectionQuality.POOR
        elif self == self.GOOD:
            return lkmodels.ConnectionQuality.GOOD
        elif self == self.EXCELLENT:
            return lkmodels.ConnectionQuality.EXCELLENT
        else:
            raise ValueError(f"Unknown ConnectionQuality: {self}")


@dataclass
class ConnectionQualityInfo(LKBase):
    """
    string participant_sid = 1;
    ConnectionQuality quality = 2;
    float score = 3;
    """
    participant_sid: str
    quality: ConnectionQuality
    score: float

    @classmethod
    def from_lk(cls, info: lkrtc.ConnectionQualityInfo) -> "ConnectionQualityInfo":
        return cls(
            participant_sid=info.participant_sid,
            quality=ConnectionQuality.from_lk(info.quality),
            score=info.score,
        )

    def to_lk(self) -> lkrtc.ConnectionQualityInfo:
        return lkrtc.ConnectionQualityInfo(
            participant_sid=self.participant_sid,
            quality=self.quality.to_lk(),
            score=self.score,
        )


@dataclass
class ConnectionQualityUpdate(LKBase):
    __signal_response__ = "connection_quality"
    """
    repeated ConnectionQualityInfo updates = 1;
    """
    updates: List[ConnectionQualityInfo]

    @classmethod
    def from_lk(cls, update: lkrtc.ConnectionQualityUpdate) -> "ConnectionQualityUpdate":
        return cls(
            updates=[ConnectionQualityInfo.from_lk(u) for u in update.updates],
        )

    def to_lk(self) -> lkrtc.ConnectionQualityUpdate:
        return lkrtc.ConnectionQualityUpdate(
            updates=[u.to_lk() for u in self.updates],
        )


@dataclass
class StreamState(LKEnum):
    """
    ACTIVE = 0;
    PAUSED = 1;
    """
    ACTIVE = 0
    PAUSED = 1

    @classmethod
    def from_lk(cls, state: lkrtc.StreamState) -> "StreamState":
        if state == lkrtc.StreamState.ACTIVE:
            return cls.ACTIVE
        elif state == lkrtc.StreamState.PAUSED:
            return cls.PAUSED
        else:
            raise ValueError(f"Unknown StreamState: {state}")

    def to_lk(self) -> lkrtc.StreamState:
        if self == self.ACTIVE:
            return lkrtc.StreamState.ACTIVE
        elif self == self.PAUSED:
            return lkrtc.StreamState.PAUSED
        else:
            raise ValueError(f"Unknown StreamState: {self}")


@dataclass
class StreamStateInfo(LKBase):
    """
    string participant_sid = 1;
    string track_sid = 2;
    StreamState state = 3;
    """
    participant_sid: str
    track_sid: str
    state: StreamState

    @classmethod
    def from_lk(cls, info: lkrtc.StreamStateInfo) -> "StreamStateInfo":
        return cls(
            participant_sid=info.participant_sid,
            track_sid=info.track_sid,
            state=StreamState.from_lk(info.state),
        )

    def to_lk(self) -> lkrtc.StreamStateInfo:
        return lkrtc.StreamStateInfo(
            participant_sid=self.participant_sid,
            track_sid=self.track_sid,
            state=self.state.to_lk(),
        )


@dataclass
class StreamStateUpdate(LKBase):
    __signal_response__ = "stream_state_update"
    """
    repeated StreamStateInfo stream_states = 1;
    """
    stream_states: List[StreamStateInfo]

    @classmethod
    def from_lk(cls, update: lkrtc.StreamStateUpdate) -> "StreamStateUpdate":
        return cls(
            stream_states=[StreamStateInfo.from_lk(s) for s in update.stream_states],
        )

    def to_lk(self) -> lkrtc.StreamStateUpdate:
        return lkrtc.StreamStateUpdate(
            stream_states=[s.to_lk() for s in self.stream_states],
        )


@dataclass
class SubscribedQuality(LKBase):
    """
    VideoQuality quality = 1;
    bool enabled = 2;
    """
    quality: VideoQuality
    enabled: bool

    @classmethod
    def from_lk(cls, quality: lkrtc.SubscribedQuality) -> "SubscribedQuality":
        return cls(
            quality=VideoQuality.from_lk(quality.quality),
            enabled=quality.enabled,
        )

    def to_lk(self) -> lkrtc.SubscribedQuality:
        return lkrtc.SubscribedQuality(
            quality=self.quality.to_lk(),
            enabled=self.enabled,
        )


@dataclass
class SubscribedCodec(LKBase):
    """
    string codec = 1;
    repeated SubscribedQuality qualities = 2;
    """
    codec: str
    qualities: List[SubscribedQuality]

    @classmethod
    def from_lk(cls, codec: lkrtc.SubscribedCodec) -> "SubscribedCodec":
        return cls(
            codec=codec.codec,
            qualities=[SubscribedQuality.from_lk(q) for q in codec.qualities],
        )

    def to_lk(self) -> lkrtc.SubscribedCodec:
        return lkrtc.SubscribedCodec(
            codec=self.codec,
            qualities=[q.to_lk() for q in self.qualities],
        )


@dataclass
class SubscribedQualityUpdate(LKBase):
    __signal_response__ = "subscribed_quality_update"
    """
    string track_sid = 1;
    repeated SubscribedQuality subscribed_qualities = 2;
    repeated SubscribedCodec subscribed_codecs = 3;
    """
    track_sid: str
    subscribed_qualities: List[SubscribedQuality]
    subscribed_codecs: List[SubscribedCodec]

    @classmethod
    def from_lk(cls, update: lkrtc.SubscribedQualityUpdate) -> "SubscribedQualityUpdate":
        return cls(
            track_sid=update.track_sid,
            subscribed_qualities=[SubscribedQuality.from_lk(q) for q in update.subscribed_qualities],
            subscribed_codecs=[SubscribedCodec.from_lk(c) for c in update.subscribed_codecs],
        )

    def to_lk(self) -> lkrtc.SubscribedQualityUpdate:
        return lkrtc.SubscribedQualityUpdate(
            track_sid=self.track_sid,
            subscribed_qualities=[q.to_lk() for q in self.subscribed_qualities],
            subscribed_codecs=[c.to_lk() for c in self.subscribed_codecs],
        )


@dataclass
class SubscriptionPermissionUpdate(LKBase):
    __signal_response__ = "subscription_permission_update"
    """
    string participant_sid = 1;
    string track_sid = 2;
    bool allowed = 3;
    """
    participant_sid: str
    track_sid: str
    allowed: bool

    @classmethod
    def from_lk(cls, update: lkrtc.SubscriptionPermissionUpdate) -> "SubscriptionPermissionUpdate":
        return cls(
            participant_sid=update.participant_sid,
            track_sid=update.track_sid,
            allowed=update.allowed,
        )

    def to_lk(self) -> lkrtc.SubscriptionPermissionUpdate:
        return lkrtc.SubscriptionPermissionUpdate(
            participant_sid=self.participant_sid,
            track_sid=self.track_sid,
            allowed=self.allowed,
        )


@dataclass
class TrackUnpublishedResponse(LKBase):
    __signal_response__ = "track_unpublished"
    """
    string track_sid = 1;
    """
    track_sid: str

    @classmethod
    def from_lk(cls, response: lkrtc.TrackUnpublishedResponse) -> "TrackUnpublishedResponse":
        return cls(
            track_sid=response.track_sid,
        )

    def to_lk(self) -> lkrtc.TrackUnpublishedResponse:
        return lkrtc.TrackUnpublishedResponse(
            track_sid=self.track_sid,
        )


@dataclass
class SimulcastCodec(LKBase):
    """
    string codec = 1;
    string cid = 2;
    bool enable_simulcast_layers = 3;
    """
    codec: str
    cid: str
    enable_simulcast_layers: bool

    @classmethod
    def from_lk(cls, codec: lkrtc.SimulcastCodec) -> "SimulcastCodec":
        return cls(
            codec=codec.codec,
            cid=codec.cid,
            enable_simulcast_layers=codec.enable_simulcast_layers,
        )

    def to_lk(self) -> lkrtc.SimulcastCodec:
        return lkrtc.SimulcastCodec(
            codec=self.codec,
            cid=self.cid,
            enable_simulcast_layers=self.enable_simulcast_layers,
        )


@dataclass
class AddTrackRequest(LKBase):
    __signal_request__ = "add_track"
    """
    // client ID of track, to match it when RTC track is received
    string cid = 1;
    string name = 2;
    TrackType type = 3;
    // to be deprecated in favor of layers
    uint32 width = 4;
    uint32 height = 5;
    // true to add track and initialize to muted
    bool muted = 6;
    // true if DTX (Discontinuous Transmission) is disabled for audio
    bool disable_dtx = 7;
    TrackSource source = 8;
    repeated VideoLayer layers = 9;

    repeated SimulcastCodec simulcast_codecs = 10;

    // server ID of track, publish new codec to exist track
    string sid = 11;

    bool stereo = 12;
    // true if RED (Redundant Encoding) is disabled for audio
    bool disable_red = 13;
    """
    cid: str
    name: str
    type: TrackType
    width: int
    height: int
    muted: bool
    disable_dtx: bool
    source: TrackSource
    layers: List[VideoLayer]
    simulcast_codecs: List[SimulcastCodec]
    sid: str
    stereo: bool
    disable_red: bool

    @classmethod
    def from_lk(cls, request: lkrtc.AddTrackRequest) -> "AddTrackRequest":
        return cls(
            cid=request.cid,
            name=request.name,
            type=TrackType.from_lk(request.type),
            width=request.width,
            height=request.height,
            muted=request.muted,
            disable_dtx=request.disable_dtx,
            source=TrackSource.from_lk(request.source),
            layers=[VideoLayer.from_lk(layer) for layer in request.layers],
            simulcast_codecs=[SimulcastCodec.from_lk(codec) for codec in request.simulcast_codecs],
            sid=request.sid,
            stereo=request.stereo,
            disable_red=request.disable_red,
        )

    def to_lk(self) -> lkrtc.AddTrackRequest:
        return lkrtc.AddTrackRequest(
            cid=self.cid,
            name=self.name,
            type=self.type.to_lk(),
            width=self.width,
            height=self.height,
            muted=self.muted,
            disable_dtx=self.disable_dtx,
            source=self.source.to_lk(),
            layers=[layer.to_lk() for layer in self.layers],
            simulcast_codecs=[codec.to_lk() for codec in self.simulcast_codecs],
            sid=self.sid,
            stereo=self.stereo,
            disable_red=self.disable_red,
        )


@dataclass
class ParticipantTracks(LKBase):
    """
    // participant ID of participant to whom the tracks belong
    string participant_sid = 1;
    repeated string track_sids = 2;
    """
    participant_sid: ParticipantId
    track_sids: List[TrackId]

    @classmethod
    def from_lk(cls, participant_tracks: lkmodels.ParticipantTracks) -> "ParticipantTracks":
        return cls(
            participant_sid=participant_tracks.participant_sid,
            track_sids=[sid for sid in participant_tracks.track_sids],
        )

    def to_lk(self) -> lkmodels.ParticipantTracks:
        return lkmodels.ParticipantTracks(
            participant_sid=self.participant_sid,
            track_sids=[sid for sid in self.track_sids],
        )


@dataclass
class UpdateSubscription(LKBase):
    __signal_request__ = "subscription"
    """
    repeated string track_sids = 1;
    bool subscribe = 2;
    repeated ParticipantTracks participant_tracks = 3;
    """
    track_sids: List[str]
    subscribe: bool
    participant_tracks: List[ParticipantTracks]

    @classmethod
    def from_lk(cls, update: lkrtc.UpdateSubscription) -> "UpdateSubscription":
        return cls(
            track_sids=[s for s in update.track_sids],
            subscribe=update.subscribe,
            participant_tracks=[ParticipantTracks.from_lk(p) for p in update.participant_tracks],
        )

    def to_lk(self) -> lkrtc.UpdateSubscription:
        return lkrtc.UpdateSubscription(
            track_sids=[s for s in self.track_sids],
            subscribe=self.subscribe,
            participant_tracks=[p.to_lk() for p in self.participant_tracks],
        )


@dataclass
class UpdateTrackSettings(LKBase):
    __signal_request__ = "track_setting"
    """
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
    """
    track_sids: List[str]
    disabled: bool
    quality: VideoQuality
    width: int
    height: int
    fps: int

    @classmethod
    def from_lk(cls, update: lkrtc.UpdateTrackSettings) -> "UpdateTrackSettings":
        return cls(
            track_sids=[s for s in update.track_sids],
            disabled=update.disabled,
            quality=VideoQuality.from_lk(update.quality),
            width=update.width,
            height=update.height,
            fps=update.fps,
        )

    def to_lk(self) -> lkrtc.UpdateTrackSettings:
        return lkrtc.UpdateTrackSettings(
            track_sids=[s for s in self.track_sids],
            disabled=self.disabled,
            quality=self.quality.to_lk() if self.quality else None,
            width=self.width,
            height=self.height,
            fps=self.fps,
        )


@dataclass
class UpdateVideoLayers(LKBase):
    __signal_request__ = "update_layers"
    """
    string track_sid = 1;
    repeated VideoLayer layers = 2;
    """
    track_sid: str
    layers: List[VideoLayer]

    @classmethod
    def from_lk(cls, update: lkrtc.UpdateVideoLayers) -> "UpdateVideoLayers":
        return cls(
            track_sid=update.track_sid,
            layers=[VideoLayer.from_lk(layer) for layer in update.layers],
        )

    def to_lk(self) -> lkrtc.UpdateVideoLayers:
        return lkrtc.UpdateVideoLayers(
            track_sid=self.track_sid,
            layers=[layer.to_lk() for layer in self.layers],
        )


@dataclass
class TrackPermission(LKBase):
    """
    // permission could be granted either by participant sid or identity
    string participant_sid = 1;
    bool all_tracks = 2;
    repeated string track_sids = 3;
    string participant_identity = 4;
    """
    participant_sid: str
    all_tracks: bool
    track_sids: List[str]
    participant_identity: str

    @classmethod
    def from_lk(cls, permission: lkrtc.TrackPermission) -> "TrackPermission":
        return cls(
            participant_sid=permission.participant_sid,
            all_tracks=permission.all_tracks,
            track_sids=[s for s in permission.track_sids],
            participant_identity=permission.participant_identity,
        )

    def to_lk(self) -> lkrtc.TrackPermission:
        return lkrtc.TrackPermission(
            participant_sid=self.participant_sid,
            all_tracks=self.all_tracks,
            track_sids=[s for s in self.track_sids],
            participant_identity=self.participant_identity,
        )


@dataclass
class SubscriptionPermission(LKBase):
    __signal_request__ = "subscription_permission"
    """
    bool all_participants = 1;
    repeated TrackPermission track_permissions = 2;
    """
    all_participants: bool
    track_permissions: List[TrackPermission]

    @classmethod
    def from_lk(cls, permission: lkrtc.SubscriptionPermission) -> "SubscriptionPermission":
        return cls(
            all_participants=permission.all_participants,
            track_permissions=[TrackPermission.from_lk(p) for p in permission.track_permissions],
        )

    def to_lk(self) -> lkrtc.SubscriptionPermission:
        return lkrtc.SubscriptionPermission(
            all_participants=self.all_participants,
            track_permissions=[p.to_lk() for p in self.track_permissions],
        )


@dataclass
class SessionDescription(LKBase):
    __signal_request__ = ["offer", "answer"]  # check to_signal_request() method
    __signal_response__ = ["offer", "answer"]  # check from_signal_response() method
    """
    string type = 1; // "answer" | "offer" | "pranswer" | "rollback"
    string sdp = 2;
    """
    type: str
    sdp: str

    @classmethod
    def from_lk(cls, desc: lkrtc.SessionDescription) -> "SessionDescription":
        return cls(
            type=desc.type,
            sdp=desc.sdp,
        )

    def to_lk(self) -> lkrtc.SessionDescription:
        return lkrtc.SessionDescription(
            type=self.type,
            sdp=self.sdp,
        )

    def to_aiortc(self) -> aiortc.RTCSessionDescription:
        # aiortc.RTCSessionDescription and SessionDescription are compatible, but...
        return aiortc.RTCSessionDescription(type=self.type, sdp=self.sdp)

    def to_signal_request(self):
        # special handling because offer and answer share the same type
        return lkrtc.SignalRequest(**{self.type: self.to_lk()})

    @classmethod
    def from_signal_response(cls, response: lkrtc.SignalResponse):
        # special handling because offer and answer share the same type
        if response.WhichOneof("message") == "offer":
            return cls.from_lk(response.offer)
        elif response.WhichOneof("message") == "answer":
            return cls.from_lk(response.answer)
        else:
            raise ValueError(f"SignalResponse does not contain offer or answer: {response}")

    @classmethod
    def from_signal_request(cls, request: lkrtc.SignalRequest):
        # special handling because offer and answer share the same type
        if request.WhichOneof("message") == "offer":
            return cls.from_lk(request.offer)
        elif request.WhichOneof("message") == "answer":
            return cls.from_lk(request.answer)
        else:
            raise ValueError(f"SignalRequest does not contain offer or answer: {request}")

    def get_response_name(self):
        return self.type

    def get_request_name(self):
        return self.type


@dataclass
class DataChannelInfo:
    """
    string label = 1;
    uint32 id = 2;
    SignalTarget target = 3;
    """
    label: str
    id: int
    target: SignalTarget

    @classmethod
    def from_lk(cls, info: lkrtc.DataChannelInfo) -> "DataChannelInfo":
        return cls(
            label=info.label,
            id=info.id,
            target=SignalTarget.from_lk(info.target),
        )

    def to_lk(self) -> lkrtc.DataChannelInfo:
        return lkrtc.DataChannelInfo(
            label=self.label,
            id=self.id,
            target=self.target.to_lk(),
        )


@dataclass
class SyncState(LKBase):
    __signal_request__ = "sync_state"
    """
    // last subscribe answer before reconnecting
    SessionDescription answer = 1;
    UpdateSubscription subscription = 2;
    repeated TrackPublishedResponse publish_tracks = 3;
    repeated DataChannelInfo data_channels = 4;
    // last received server side offer before reconnecting
    SessionDescription offer = 5;
    """
    answer: SessionDescription
    subscription: UpdateSubscription
    publish_tracks: List[TrackPublishedResponse]
    data_channels: List[DataChannelInfo]
    offer: SessionDescription

    @classmethod
    def from_lk(cls, state: lkrtc.SyncState) -> "SyncState":
        return cls(
            answer=SessionDescription.from_lk(state.answer),
            subscription=UpdateSubscription.from_lk(state.subscription),
            publish_tracks=[TrackPublishedResponse.from_lk(p) for p in state.publish_tracks],
            data_channels=[DataChannelInfo.from_lk(d) for d in state.data_channels],
            offer=SessionDescription.from_lk(state.offer),
        )

    def to_lk(self) -> lkrtc.SyncState:
        return lkrtc.SyncState(
            answer=self.answer.to_lk(),
            subscription=self.subscription.to_lk(),
            publish_tracks=[p.to_lk() for p in self.publish_tracks],
            data_channels=[d.to_lk() for d in self.data_channels],
            offer=self.offer.to_lk(),
        )


# fake wrapper classes for simple messages
@dataclass
class Ping(LKBase):
    __signal_request__ = "ping"
    time: Time

    @classmethod
    def from_lk(cls, ping: int) -> "Ping":
        return cls(
            time=Time(ping),
        )

    def to_lk(self) -> int:
        return int(self.time)


@dataclass
class Pong(LKBase):
    __signal_response__ = "pong"
    time: Time

    @classmethod
    def from_lk(cls, pong: int) -> "Pong":
        return cls(
            time=Time(pong),
        )

    def to_lk(self) -> int:
        return int(self.time)


@dataclass
class RefreshToken(LKBase):
    __signal_response__ = "refresh_token"
    token: Token

    @classmethod
    def from_lk(cls, token: str) -> "RefreshToken":
        return cls(
            token=Token(token),
        )

    def to_lk(self) -> str:
        return str(self.token)


map_signal_response_to_class = {}
map_signal_request_to_class = {}


def init_maps():
    global map_signal_response_to_class
    global map_signal_request_to_class

    for classname in sys.modules[__name__].__dir__():
        klass = getattr(sys.modules[__name__], classname)
        if hasattr(klass, "__signal_request__"):
            if isinstance(klass.__signal_request__, List):
                for request in klass.__signal_request__:
                    map_signal_request_to_class[request] = klass
            else:
                map_signal_request_to_class[klass.__signal_request__] = klass
        if hasattr(klass, "__signal_response__"):
            if isinstance(klass.__signal_response__, List):
                for response in klass.__signal_response__:
                    map_signal_response_to_class[response] = klass
            else:
                map_signal_response_to_class[klass.__signal_response__] = klass


init_maps()


def from_signal_response(response: lkrtc.SignalResponse) -> LKBase:
    """
    Convert a SignalResponse to a LKBase subclass.
    """
    msg = response.WhichOneof("message")
    lkclass = map_signal_response_to_class.get(msg, None)
    if lkclass is None:
        raise ValueError(f"Unknown SignalResponse message: {msg}")

    return lkclass.from_signal_response(response)


def from_signal_request(request: lkrtc.SignalRequest) -> LKBase:
    """
    Convert a SignalRequest to a LKBase subclass.
    """
    msg = request.WhichOneof("message")
    lkclass = map_signal_request_to_class.get(msg, None)
    if lkclass is None:
        raise ValueError(f"Unknown SignalResponse message: {msg}")

    return lkclass.from_signal_request(request)
