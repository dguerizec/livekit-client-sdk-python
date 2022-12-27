How to install locally
----------------------

    python -m venv venv
    source venv/bin/activate
    pip install -e .

How to test
-----------

    livekit-server --config doc/livekit-server-config.yaml

How to run
----------

    # send a video
    python examples/publisher/publisher.py examples/publisher/video.mp4

    # receive a video
    python examples/subscriber/subscriber.py /tmp/output.mp4


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
- My publisher WS client gets disconnected without a Leave message after ~30-40 seconds, but there is no useful debug message in livekit-server log.
- Is datachannel establishment necessary/mandatory ? If yes, is it mandatory on both PCs ?

aiortc
------

- When (and where) is called the _start() method of a track ?
- What happens when receive two offers or more on the same RTCPeerConnection ?
 

