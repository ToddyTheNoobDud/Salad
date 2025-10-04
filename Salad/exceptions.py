"""
Custom exception classes for handling various error scenarios in the Salad library.
"""

class SaladException(Exception):
    """The root exception class for all Salad-related errors"""
    pass

class NodeException(SaladException):
    """Raised when node-related operations fail"""
    pass


class NodeCreationError(NodeException):
    """Triggered during node initialization failures"""
    pass


class NodeConnectionFailure(NodeException):
    """Occurs when establishing connection to node fails"""
    pass


class NodeConnectionClosed(NodeException):
    """Raised when node connection terminates unexpectedly"""
    pass


class NodeRestException(NodeException):
    """Triggered when REST API requests to node fail"""
    pass


class NodeNotAvailable(SaladException):
    """Raised when requested node is inaccessible"""
    pass


class NoNodesAvailable(SaladException):
    """Occurs when no operational nodes exist"""
    pass

class TrackException(SaladException):
    """Base class for audio track errors"""
    pass


class TrackStartError(TrackException):
    """Triggered when track playback initialization fails"""
    pass


class TrackEndError(TrackException):
    """Raised when track termination encounters problems"""
    pass


class TrackError(TrackException):
    """General track processing failure"""
    pass


class TrackStuckError(TrackException):
    """Occurs when track playback halts unexpectedly"""
    pass


class TrackInvalidPosition(TrackException):
    """Raised when seeking to invalid track timestamp"""
    pass


class TrackLoadError(TrackException):
    """Triggered when track data cannot be retrieved"""
    pass


class TrackChangeError(TrackException):
    """Occurs during track transition failures"""
    pass

class LyricsException(SaladException):
    """Base class for lyrics processing errors"""
    pass


class LyricsNotFound(LyricsException):
    """Raised when lyrics cannot be located"""
    pass

class QueueException(SaladException):
    """Base class for queue management errors"""
    pass


class QueueFull(QueueException):
    """Triggered when adding items to saturated queue"""
    pass


class QueueEmpty(QueueException):
    """Raised when accessing empty queue"""
    pass


class QueueEndError(QueueException):
    """Occurs when queue playback completes"""
    pass

class PlayerException(SaladException):
    """Base class for player management errors"""
    pass


class PlayerUpdateError(PlayerException):
    """Triggered when player state update fails"""
    pass


class PlayerMoveError(PlayerException):
    """Raised during player relocation failures"""
    pass


class PlayerReconnectionFailed(PlayerException):
    """Occurs when player reconnection attempts fail"""
    pass


class PlayerCreateError(PlayerException):
    """Triggered during player instantiation issues"""
    pass


class PlayerDestroyError(PlayerException):
    """Raised when player cleanup encounters problems"""
    pass


class PlayerMigrationError(PlayerException):
    """Occurs during player migration between nodes"""
    pass

class AutoplayFailed(SaladException):
    """Raised when automatic playlist continuation fails"""
    pass


class SocketClosedException(SaladException):
    """Triggered when WebSocket connection drops"""
    pass


class LavalinkVersionIncompatible(SaladException):
    """Occurs when Lavalink server version is unsupported"""
    pass