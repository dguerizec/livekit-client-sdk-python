import asyncio
import os
from collections import namedtuple
from dataclasses import dataclass
from typing import List

import av
from aiortc import MediaStreamTrack
from aiortc.contrib.media import MediaRecorderContext
from aiortc.mediastreams import MediaStreamError
from av.video import VideoFrame


import logging

logger = logging.getLogger("livekit-recorder")

#StreamContext = namedtuple("StreamContext", ["track", "context", "container"])
@dataclass
class StreamContext:
    track: MediaStreamTrack
    context: MediaRecorderContext
    container: av.container.OutputContainer

@dataclass
class FrameRecorder:
    """
    A media sink that writes audio and/or video to series of files.

    Examples:

    .. code-block:: python

        # Write to files.
        player = FrameRecorder('/path/to/file.mp4')

        # Write to a set of images.
        player = FrameRecorder('/path/to/file-%3d.png')

    :param path: The path to a file, or a file-like object.
    :param options: Additional options to pass to FFmpeg.
    """
    containers: List[StreamContext]

    def __init__(self, path):
        self.path = path
        self.containers = []


    async def addTrack(self, track: MediaStreamTrack):
        """
        Add a track to be recorded.

        :param track: A :class:`aiortc.MediaStreamTrack`.
        """

        if track.kind == "audio":
            return

        try:
            path = f"{self.path}/track-{track.id}"
            file = f"{path}/frame-%d.png"
            #file = f"{path}/video.mp4"
            try:
                os.mkdir(self.path)
            except FileExistsError:
                pass
            os.mkdir(path)

            logger.debug(f"Recording track {track.id} to {file}")

            options = {}

            container = av.open(file=file, format=None, mode="w", options=options)
            tracks = {}

            if container.format.name == "image2":
                stream = container.add_stream("png", rate=30)
                stream.pix_fmt = "rgb24"
            else:
                stream = container.add_stream("libx264", rate=60)
                stream.pix_fmt = "yuv420p"

            context = MediaRecorderContext(stream)
            record = StreamContext(track=track, context=context, container=container)
            self.containers.append(record)

            # start the recording
            record.context.task = asyncio.ensure_future(self.__run_track(record))
        except Exception as e:
            logger.exception(f"ERROR: Cannot add track {track.kind} #{track.id} to recorder")
            await self.stop()
            raise

    #async def start(self):
    #    """
    #    Start recording.
    #    """
    #    for track, context in self.__tracks.items():
    #        if context.task is None:
    #            context.task = asyncio.ensure_future(self.__run_track(track, context))

    async def stop(self):
        """
        Stop recording.
        """
        for record in self.containers:
            if record.context.task is not None:
                record.context.task.cancel()
                record.context.task = None
                for packet in record.context.stream.encode(None):
                    record.container.mux(packet)

            if record.container:
                record.container.close()
                record.container = None


    async def __run_track(self, record: StreamContext):
        while True:
            try:
                frame = await record.track.recv()
            except MediaStreamError:
                return

            if not record.context.started:
                # adjust the output size to match the first frame
                if isinstance(frame, VideoFrame):
                    record.context.stream.width = frame.width
                    record.context.stream.height = frame.height
                record.context.started = True

            for packet in record.context.stream.encode(frame):
                record.container.mux(packet)

