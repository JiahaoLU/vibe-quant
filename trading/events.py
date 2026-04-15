from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum, auto
from typing import Literal  # noqa: F401 — kept for OrderEvent/FillEvent


class EventType(Enum):
    BAR_BUNDLE      = auto()
    STRATEGY_BUNDLE = auto()
    ORDER           = auto()
    FILL            = auto()


@dataclass
class Event:
    type: EventType


@dataclass
class TickEvent:                 # value type — not an Event subclass, not queued directly
    symbol:       str
    timestamp:    datetime
    open:         float
    high:         float
    low:          float
    close:        float
    volume:       float
    is_synthetic: bool = False   # True when bar is carry-forwarded (no real data at this timestamp)
    is_delisted:  bool = False   # True on the last bar before the symbol exits the universe


@dataclass
class BarBundleEvent(Event):
    timestamp:     datetime
    bars:          dict[str, TickEvent]   # symbol → tick
    is_end_of_day: bool = False
    type: EventType = field(default=EventType.BAR_BUNDLE, init=False)


@dataclass
class SignalEvent:               # value type — not an Event subclass, not queued directly
    symbol:    str
    timestamp: datetime
    signal:    float             # target weight in [-1, 1]; sum across bundle ≤ 1; >0 long, <0 short, =0 exit


@dataclass
class SignalBundleEvent:         # value type — not queued; used internally by strategies and StrategyContainer
    timestamp: datetime
    signals:   dict[str, SignalEvent]   # symbol → signal


@dataclass
class StrategyBundleEvent(Event):
    timestamp:    datetime
    combined:     dict[str, SignalEvent]        # aggregated signal per symbol (used by portfolio fill logic)
    per_strategy: dict[str, dict[str, float]]  # strategy_id → symbol → fractional weight; intended to sum to 1.0 per symbol
    type: EventType = field(default=EventType.STRATEGY_BUNDLE, init=False)


@dataclass
class OrderEvent(Event):
    symbol:          str
    timestamp:       datetime
    order_type:      Literal["MARKET", "LIMIT"]
    direction:       Literal["BUY", "SELL", "HOLD"]
    quantity:        int
    reference_price: float = 0.0   # fill reference price (next bar's open for EOD signals); execution handler applies slippage
    bar_volume:      float = 0.0   # day's total volume (0.0 when unknown)
    bar_high:        float = 0.0   # bar high; used for spread floor
    bar_low:         float = 0.0   # bar low; used for spread floor
    bar_close:       float = 0.0   # bar close; used for Parkinson vol normalisation
    bar_is_synthetic: bool = False  # True when the bar is carry-forwarded; skip volume impact
    order_id:        str = ""      # broker order ID; empty string if not yet assigned
    type: EventType = field(default=EventType.ORDER, init=False)


@dataclass
class FillEvent(Event):
    symbol:     str
    timestamp:  datetime
    direction:  Literal["BUY", "SELL", "HOLD"]
    quantity:   int
    fill_price: float
    commission: float
    order_id:   str = ""      # broker order ID; empty string if not yet assigned
    type: EventType = field(default=EventType.FILL, init=False)
