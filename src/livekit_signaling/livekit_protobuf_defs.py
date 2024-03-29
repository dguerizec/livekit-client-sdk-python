# fix protobuf implementation
import os

os.environ["PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION"] = "python"

import livekit._proto.livekit_models_pb2 as lkmodels  # type: ignore
import livekit._proto.livekit_rtc_pb2 as lkrtc  # type: ignore

__all__ = ["lkmodels", "lkrtc"]
