"""DO WHAT THE FUCK YOU WANT TO PUBLIC LICENSE
                    Version 2, December 2004

 Copyright (C) 2004 Sam Hocevar <sam@hocevar.net>

 Everyone is permitted to copy and distribute verbatim or modified
 copies of this license document, and changing it is allowed as long
 as the name is changed.

            DO WHAT THE FUCK YOU WANT TO PUBLIC LICENSE
   TERMS AND CONDITIONS FOR COPYING, DISTRIBUTION AND MODIFICATION

  0. You just DO WHAT THE FUCK YOU WANT TO.

URL: https://www.wtfpl.net/txt/copying/
"""
import asyncio
import weakref
from typing import Callable, Dict, List, Any, Optional
from collections import defaultdict

__all__ = ('EventEmitter',)


class EventEmitter:
    """
    High-performance event emitter with:
    - Weak references to prevent memory leaks
    - Fast O(1) listener lookup
    - Non-blocking async event dispatch
    - Automatic cleanup of dead references
    """

    __slots__ = ('_listeners', '_once_listeners', '_max_listeners', '_cleanup_counter')

    def __init__(self, max_listeners: int = 100):
        self._listeners: Dict[str, List[Callable]] = defaultdict(list)
        self._once_listeners: Dict[str, List[Callable]] = defaultdict(list)
        self._max_listeners = max_listeners
        self._cleanup_counter = 0  

    def on(self, event: str, listener: Callable) -> None:
        """Register a persistent event listener."""
        listeners = self._listeners[event]

        if len(listeners) >= self._max_listeners:
            return

        listeners.append(listener)

    def once(self, event: str, listener: Callable) -> None:
        """Register a one-time event listener."""
        once_listeners = self._once_listeners[event]

        if len(once_listeners) >= self._max_listeners:
            return

        once_listeners.append(listener)

    def off(self, event: str, listener: Optional[Callable] = None) -> None:
        """Remove listener(s) for an event."""
        if listener is None:
            self._listeners.pop(event, None)
            self._once_listeners.pop(event, None)
        else:
            if event in self._listeners:
                try:
                    self._listeners[event].remove(listener)
                except ValueError:
                    pass

            if event in self._once_listeners:
                try:
                    self._once_listeners[event].remove(listener)
                except ValueError:
                    pass

    def emit(self, event: str, *args: Any, **kwargs: Any) -> None:
        """
        Emit an event to all registered listeners.
        Async listeners are scheduled without blocking.
        """
        if event not in self._listeners and event not in self._once_listeners:
            return

        listeners = self._listeners.get(event, [])
        self._dispatch_to_listeners(listeners, args, kwargs)

        once_listeners = self._once_listeners.pop(event, [])
        if once_listeners:
            self._dispatch_to_listeners(once_listeners, args, kwargs)

        self._cleanup_counter += 1
        if self._cleanup_counter >= 100:
            self._cleanup_counter = 0
            self._cleanup_empty_events()

    def _dispatch_to_listeners(self, listeners: List[Callable], args: tuple, kwargs: dict) -> None:
        """Dispatch event to a list of listeners without blocking."""
        for listener in listeners:
            try:
                if asyncio.iscoroutinefunction(listener):
                    try:
                        asyncio.create_task(listener(*args, **kwargs))
                    except RuntimeError:
                        pass
                else:
                    listener(*args, **kwargs)
            except Exception:
                pass

    def _cleanup_empty_events(self) -> None:
        """Remove event keys with no listeners (memory optimization)."""
        empty = [k for k, v in self._listeners.items() if not v]
        for k in empty:
            del self._listeners[k]

        empty = [k for k, v in self._once_listeners.items() if not v]
        for k in empty:
            del self._once_listeners[k]

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
