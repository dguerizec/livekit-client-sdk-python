import asyncio
import logging
import os
from dataclasses import dataclass
from typing import Dict, List

import av  # type: ignore
from aiortc import MediaStreamTrack
from aiortc.contrib.media import MediaRecorderContext
from aiortc.mediastreams import MediaStreamError
from av.video import VideoFrame  # type: ignore
from pyee.asyncio import AsyncIOEventEmitter

import livekit_signaling.livekit_types as LK
from livekit_signaling.utils import get_track_ids

logger = logging.getLogger("livekit-recorder")


@dataclass
class StreamContext:
    track: MediaStreamTrack
    context: MediaRecorderContext
    container: av.container.OutputContainer
    can_start: bool = False


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

    def __init__(self, path: str, record_frames: bool = True) -> None:
        super().__init__()
        self.path = path
        self.tracks = {}
        self.record_frames = record_frames

    async def addTrack(self, track: MediaStreamTrack) -> None:
        """
        Add a track to be recorded.

        :param track: A :class:`aiortc.MediaStreamTrack`.
        """

        if track.kind == "audio":
            return

        _pax_id, _track_id = get_track_ids(track)

        print(f"NEW TRACK: track.id={track.id}, track.kind={track.kind}, pax_id={_pax_id}, track_id={_track_id}")

        if _pax_id is None or _track_id is None:
            raise MediaStreamError("Track must have paxid and trid")

        track_id = LK.TrackId(_track_id)
        pax_id = LK.ParticipantId(_pax_id)

        track.trid = track_id
        track.paxid = track_id
        if self.tracks.get(track_id):
            logger.debug(f"Track {pax_id} {track_id} already being recorded")
            return

        try:
            path = f"{self.path}/track-{track_id}"
            try:
                os.mkdir(self.path)
            except FileExistsError:
                pass
            if self.record_frames:
                try:
                    os.mkdir(path)
                except FileExistsError:
                    pass
                file = f"{path}/frame-%d.png"
            else:
                file = f"{path}_video.mp4"

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

            self.tracks[track_id] = record
            self.emit(self.track_added, track)
            logger.debug(f"Added track {track.kind} #{track.id} to recorder")

        except Exception as e:
            logger.exception(
                f"ERROR: Cannot add track {track.kind} #{track.id} to recorder"
            )
            await self.stop()
            raise

    def disconnect_track(self, track_id: LK.TrackId) -> None:
        record = self.tracks.pop(track_id, None)
        if record:
            # don't stop the track, because it won't restart
            # record.track.stop()
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

    async def stop(self) -> None:
        """
        Stop recording.
        """
        for track_id, record in self.tracks.items():
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

    async def __run_track(self, record: StreamContext) -> None:
        while True:
            try:
                logger.debug(f"Waiting for frame")
                frame = await record.track.recv()
            except MediaStreamError as e:
                logger.exception(f"Recorder track {record.track.trid} ended")
                print(f"Recorder track {record.track.trid} ended {e}")
                return
            except Exception as e:
                logger.exception(f"Recorder track {record.track.trid} ended")
                print(f"Recorder track {record.track.trid} ended {e}")
                return

            print(f"Got frame")
            if record.can_start is False:
                continue

            print(f"Recording track {record.track.trid} frame {frame}")

            if not record.context.started:
                # adjust the output size to match the first frame
                if isinstance(frame, VideoFrame):
                    record.context.stream.width = frame.width
                    record.context.stream.height = frame.height
                record.context.started = True

            for packet in record.context.stream.encode(frame):
                record.container.mux(packet)

    def start_recording(self, track_id: LK.TrackId) -> None:
        logger.debug(f"Starting recording of track {track_id}")
        self.tracks[track_id].can_start = True
