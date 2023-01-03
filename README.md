Python client for Livekit
=========================

This is still a work in progress. There are still some (a lot of!) missing features, and the API is subject to change.


How to install locally
----------------------

    sudo apt install libvpx-dev libopusfile-dev libavformat-dev

    python -m venv venv
    source venv/bin/activate
    pip install -e .
    
    # patch aiortc (for subscriber example to work)
    git clone https://github.com/aiortc/aiortc.git
    # edit aiortc/src/aiortc/rtcpeerconnection.py, replace line 1018
    #      if self.__sctp:
    # with
    #      if False:
    # then proceed with editable installation of aiortc:
    pip uninstall aiortc
    pip install -e aiortc


How to test
-----------

    # in a first terminal, run the livekit server:
    livekit-server --config doc/livekit-server-config.yaml

    # in another terminal, run a livekit client:
    livekit-cli load-test --api-key devkey --api-secret secret --room "room1011" --publishers 1

Run the subscriber
------------------

Note[WIP]:
    The subscriber does not work without patching aiortc


    # receive a video track and save it to /tmp/output.mp4
    python examples/subscriber/subscriber.py /tmp/output.mp4

You may need to specify a random identifier to run it several times.
The reconnection to livekit-server is not yet implemented correctly, and reusing the same id can cause bad behavior.


    python examples/subscriber/subscriber.py /tmp/output.mp4 --identifier "pysub-$RANDOM"

Run the publisher
-----------------

Note[WIP]: the publisher is not yet working.

    # send a video
    python examples/publisher/publisher.py examples/publisher/video.mp4


Logging
-------
To get verbose logs, you can add flags

    -v --verbose                Output debug info from publisher/subscriber
    -V --verbose-signaling      Ouput debug info from the signaling module
    -vv                         Output debug info from every logger (aiortc/aioice/websockets included)




Open questions
==============


livekit/signaling
-----------------

- What is the version field in ParticipantUpdate ?
- Why is there sometimes two different versions of the same participant "record" ?
- Is datachannel establishment necessary/mandatory ?


