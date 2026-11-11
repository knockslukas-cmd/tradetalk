"""Signal-Auswahl für Filter (Anzeigename -> Schlüssel)."""

from __future__ import annotations

from tt_app.common import signals

SIGNAL_OPTIONS = {name: key for key, (name, _, _) in signals.SIGNALS.items()}
