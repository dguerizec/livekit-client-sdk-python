# fix protobuf implementation
import os

os.environ["PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION"] = "python"

import livekit.proto.livekit_rtc_pb2 as lkrtc
import livekit.proto.livekit_models_pb2 as lkmodels
