import asyncio
from typing import Callable, Dict, List, Any, Optional, Set
from collections import defaultdict
import logging

__all__ = ('EventEmitter',)

logger = logging.getLogger(__name__)


class EventEmitter:
    """
    A straightforward event emitter that supports both synchronous and
    asynchronous listeners.
    """

    __slots__ = ('_listeners', '_once_listeners', '_max_listeners')

    def __init__(self, max_listeners: int = 100):
        self._listeners: Dict[str, List[Callable]] = defaultdict(list)
        self._once_listeners: Dict[str, List[Callable]] = defaultdict(list)
        self._max_listeners = max_listeners

    def on(self, event: str, listener: Callable) -> None:
        """Register a persistent event listener."""
        if len(self._listeners[event]) < self._max_listeners:
            self._listeners[event].append(listener)

    def once(self, event: str, listener: Callable) -> None:
        """Register a one-time event listener."""
        if len(self._once_listeners[event]) < self._max_listeners:
            self._once_listeners[event].append(listener)

    def off(self, event: str, listener: Optional[Callable] = None) -> None:
        """Remove a specific listener or all listeners for an event."""
        if listener is None:
            self._listeners.pop(event, None)
            self._once_listeners.pop(event, None)
            return

        if event in self._listeners:
            try:
                self._listeners[event].remove(listener)
            except ValueError:
                pass  # Listener not found

        if event in self._once_listeners:
            try:
                self._once_listeners[event].remove(listener)
            except ValueError:
                pass  # Listener not found

    def emit(self, event: str, *args: Any, **kwargs: Any) -> None:
        """
        Emit an event, calling all registered listeners.
        Async listeners are scheduled to run in the background.
        """
        # Gather all listeners for the event
        all_listeners = (
            self._listeners.get(event, []) +
            self._once_listeners.pop(event, [])
        )

        if not all_listeners:
            return

        for listener in all_listeners:
            try:
                if asyncio.iscoroutinefunction(listener):
                    # Schedule async listeners to run without blocking
                    asyncio.create_task(listener(*args, **kwargs))
                else:
                    # Call sync listeners directly
                    listener(*args, **kwargs)
            except Exception as e:
                logger.error(f"Error in event listener for '{event}': {e}", exc_info=True)

    def remove_all_listeners(self, event: Optional[str] = None) -> None:
        """Remove all listeners for a specific event or all events."""
        if event is None:
            self._listeners.clear()
            self._once_listeners.clear()
        else:
            self._listeners.pop(event, None)
            self._once_listeners.pop(event, None)

    def listener_count(self, event: str) -> int:
        """Get the number of listeners for an event."""
        return (len(self._listeners.get(event, [])) +
                len(self._once_listeners.get(event, [])))

    def event_names(self) -> List[str]:
        """Get list of all events with listeners."""
        return list(set(list(self._listeners.keys()) + list(self._once_listeners.keys())))
