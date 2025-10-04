class Queue:
  """
  Optimized queue that stores track objects WITHOUT encoding them.
  Tracks are only sent to Lavalink when actually playing, not when added.
  """
  def __init__(self, player):
    self.player = player
    self._q = []
    self.loop = None  # None, 'track', or 'queue'
    self.previous = []
    self._maxPreviousSize = 10

  def add(self, track):
    """Add track to queue without sending to Lavalink"""
    if not track:
      return False

    self._q.append(track)
    return True

  def insert(self, track, position=0):
    """Insert track at specific position"""
    if not track:
      return False

    position = max(0, min(position, len(self._q)))
    self._q.insert(position, track)
    return True

  def remove(self, index):
    """Remove track at index"""
    if 0 <= index < len(self._q):
      removed = self._q.pop(index)
      return removed
    return None

  def clear(self):
    """Clear entire queue"""
    self._q.clear()
    self.previous.clear()

  def shuffle(self):
    """Shuffle the queue"""
    import random
    random.shuffle(self._q)

  def getNext(self):
    """
    Get next track to play WITHOUT removing it from queue.
    The track will be removed later when it actually finishes playing.
    """
    if self.loop == 'track' and self.player.currentTrackObj:
      # Loop current track - return the same track
      return self.player.currentTrackObj

    if not self._q:
      # Queue empty
      if self.loop == 'queue' and self.previous:
        # Loop queue - restore from previous
        self._q = self.previous.copy()
        self.previous.clear()
        return self._q[0] if self._q else None
      return None

    # Return first track without removing it
    return self._q[0]

  def consumeNext(self):
    """
    Actually remove the track that just finished playing.
    Called from Node when TrackEndEvent is received.
    """
    if not self._q:
      return None

    # Remove first track and add to previous
    consumed = self._q.pop(0)

    # Maintain previous history
    self.previous.append(consumed)
    if len(self.previous) > self._maxPreviousSize:
      self.previous.pop(0)

    return consumed

  def peek(self, index=0):
    """Look at track at index without removing"""
    if 0 <= index < len(self._q):
      return self._q[index]
    return None

  def getAll(self):
    """Get all tracks in queue"""
    return self._q.copy()

  def __len__(self):
    return len(self._q)

  def __bool__(self):
    return len(self._q) > 0

  def __repr__(self):
    return f"Queue(length={len(self._q)}, loop={self.loop})"