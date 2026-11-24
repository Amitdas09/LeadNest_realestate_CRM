"""Wake-up signals for the background workers (in-process)."""

import threading

outbox_event = threading.Event()
sync_event = threading.Event()


def kick_outbox() -> None:
    outbox_event.set()


def kick_sync() -> None:
    sync_event.set()
