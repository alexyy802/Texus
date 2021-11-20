.. currentmodule:: discord

``discord.ext.audio`` -- Advanced Audio And Music Playing Extension
=====================================================================

.. autofunction:: discord.ext.audio.enable_debug_logging

.. autofunction:: discord.ext.audio.add_event_hook

Client
------
.. autoclass:: Client
    :members:

Events
------
All Events are derived from :class:`discord.ext.audio.Event`

.. autoclass:: discord.ext.audio.Event
    :members:

.. autoclass:: discord.ext.audio.TrackStartEvent
    :members:

.. autoclass:: discord.ext.audio.TrackEndEvent
    :members:

.. autoclass:: discord.ext.audio.TrackStuckEvent
    :members:

.. autoclass:: discord.ext.audio.TrackExceptionEvent
    :members:

.. autoclass:: discord.ext.audio.QueueEndEvent
    :members:

.. autoclass:: discord.ext.audio.NodeConnectedEvent
    :members:

.. autoclass:: discord.ext.audio.NodeChangedEvent
    :members:

.. autoclass:: discord.ext.audio.NodeDisconnectedEvent
    :members:

.. autoclass:: discord.ext.audio.WebSocketClosedEvent
    :members:

Models
------
**All** custom players must derive from :class:`discord.ext.audio.BasePlayer`

.. autoclass:: discord.ext.audio.AudioTrack
    :members:

.. autoclass:: discord.ext.audioBasePlayer
    :members:

.. autoclass:: discord.ext.audio.DefaultPlayer
    :members:

Node
----
.. autoclass:: discord.ext.audio.Node
    :members:

Node Manager
------------
.. autoclass:: discord.ext.audio.NodeManager
    :members:

Player Manager
--------------
.. autoclass:: discord.ext.audio.PlayerManager
    :members:

Stats
-----
.. autoclass:: discord.ext.audio.Stats
    :members:

.. autoclass:: discord.ext.audio.Penalty
    :members:

Utilities
---------
.. autofunction:: discord.ext.audio.format_time

.. autofunction:: discord.ext.audio.parse_time

.. autofunction:: discord.ext.audio.decode_track
