"""Signals for an owned maintenance dispatch that performed no check."""


class MaintenanceDeferred(Exception):
    """A live operation prevented a scan; neither success nor a new failure."""
