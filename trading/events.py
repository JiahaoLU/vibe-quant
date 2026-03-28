from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum, auto
from typing import Literal


class EventType(Enum):
    BAR_BUNDLE    = auto()
    SIGNAL_BUNDLE = auto()
    ORDER         = auto()
    FILL          = auto()


@dataclass
class Event:
    type: EventType


@dataclass
class TickEvent:                 # value type — not an Event subclass, not queued directly
    symbol:    str
    timestamp: datetime
    open:      float
    high:      float
    low:       float
    close:     float
    volume:    float


@dataclass
class BarBundleEvent(Event):
    timestamp: datetime
    bars:      dict[str, TickEvent]   # symbol → tick
    type: EventType = field(default=EventType.BAR_BUNDLE, init=False)


@dataclass
class SignalEvent:               # value type — not an Event subclass, not queued directly
    symbol:      str
    timestamp:   datetime
    signal_type: Literal["LONG", "EXIT"]
    strength:    float = 1.0


@dataclass
class SignalBundleEvent(Event):
    timestamp: datetime
    signals:   dict[str, SignalEvent]   # symbol → signal
    type: EventType = field(default=EventType.SIGNAL_BUNDLE, init=False)


@dataclass
class OrderEvent(Event):
    symbol:          str
    timestamp:       datetime
    order_type:      Literal["MARKET", "LIMIT"]
    direction:       Literal["BUY", "SELL"]
    quantity:        int
    reference_price: float = 0.0  # current bar close; execution handler applies slippage
    type: EventType = field(default=EventType.ORDER, init=False)


@dataclass
class FillEvent(Event):
    symbol:     str
    timestamp:  datetime
    direction:  Literal["BUY", "SELL"]
    quantity:   int
    fill_price: float
    commission: float
    type: EventType = field(default=EventType.FILL, init=False)
