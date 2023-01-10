import asyncio
import os
from collections import namedtuple
from dataclasses import dataclass
from typing import List, Dict

import av  # type: ignore
from aiortc import MediaStreamTrack  # type: ignore
from aiortc.contrib.media import MediaRecorderContext  # type: ignore
from aiortc.mediastreams import MediaStreamError  # type: ignore
from av.video import VideoFrame  # type: ignore

import logging

from pyee import AsyncIOEventEmitter

from livekit_signaling.utils import get_track_ids
import livekit_signaling.livekit_types as LK

logger = logging.getLogger("livekit-recorder")

#StreamContext = namedtuple("StreamContext", ["track", "context", "container"])
@dataclass
class StreamContext:
    track: MediaStreamTrack
    context: MediaRecorderContext
    container: av.container.OutputContainer
    can_start: bool = False

tracks = {}

@dataclass
class FrameRecorder(AsyncIOEventEmitter):
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
    tracks: Dict[LK.TrackId, StreamContext]

    track_added = "track_added"
    track_removed = "track_removed"
    recorder_stopped = "recorder_stopped"

    def __init__(self, path):
        super().__init__()
        self.path = path
        self.tracks = {}


    async def addTrack(self, track: MediaStreamTrack):
        """
        Add a track to be recorded.

        :param track: A :class:`aiortc.MediaStreamTrack`.
        """

        if track.kind == "audio":
            return

        pax_id, track_id = get_track_ids(track)

        track.trid = track_id
        track.paxid = track_id
        if tracks.get(track_id):
            logger.debug(f"Track {pax_id} {track_id} already being recorded")
            return

        try:
            path = f"{self.path}/track-{track_id}"
            file = f"{path}/frame-%d.png"
            #file = f"{path}/video.mp4"
            try:
                os.mkdir(self.path)
            except FileExistsError:
                pass
            os.mkdir(path)

            logger.debug(f"Recording track {track_id} to {file}")

            options: Dict[str, object] = {}

            container = av.open(file=file, format=None, mode="w", options=options)

            if container.format.name == "image2":
                stream = container.add_stream("png", rate=30)
                stream.pix_fmt = "rgb24"
            else:
                stream = container.add_stream("libx264", rate=60)
                stream.pix_fmt = "yuv420p"

            context = MediaRecorderContext(stream)
            record = StreamContext(track=track, context=context, container=container)
            self.tracks[track_id] = record

            # start the recording
            record.context.task = asyncio.ensure_future(self.__run_track(record))

            tracks[track_id] = record
            self.emit(self.track_added, track)

        except Exception as e:
            logger.exception(f"ERROR: Cannot add track {track.kind} #{track.id} to recorder")
            await self.stop()
            raise

    def disconnect_track(self, track_id: LK.TrackId):
        record = tracks.pop(track_id, None)
        if record:
            # don't stop the track, because it won't restart
            #record.track.stop()
            if record.context.task is not None:
                logger.debug(f"Stopping recording of track {track_id}")
                record.context.task.cancel()
                record.context.task = None
                for packet in record.context.stream.encode(None):
                    record.container.mux(packet)

            if record.container:
                record.container.close()
                record.container = None
            self.emit(self.track_removed, track_id)


    async def stop(self):
        """
        Stop recording.
        """
        for track_id, record in tracks.items():
            record.track.stop()
            if record.context.task is not None:
                record.context.task.cancel()
                record.context.task = None
                for packet in record.context.stream.encode(None):
                    record.container.mux(packet)

            if record.container:
                record.container.close()
                record.container = None
            self.emit(self.track_removed, track_id)
        self.emit(self.recorder_stopped)


    async def __run_track(self, record: StreamContext):
        while True:
            try:
                frame = await record.track.recv()
            except MediaStreamError:
                logger.exception(f"Recorder track {record.track.trid} ended")
                return
            except:
                logger.exception(f"Recorder track {record.track.trid} ended")
                return

            if record.can_start is False:
                continue

            if not record.context.started:
                # adjust the output size to match the first frame
                if isinstance(frame, VideoFrame):
                    record.context.stream.width = frame.width
                    record.context.stream.height = frame.height
                record.context.started = True

            for packet in record.context.stream.encode(frame):
                record.container.mux(packet)

    def start_recording(self, track_id: LK.TrackId):
        logger.debug(f"Starting recording of track {track_id}")
        self.tracks[track_id].can_start = True
        pass

