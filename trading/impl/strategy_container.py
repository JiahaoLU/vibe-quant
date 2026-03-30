from typing import Callable

from trading.base.strategy_params import StrategyParams

from ..base.strategy import Strategy, StrategyBase
from ..events import BarBundleEvent, Event, SignalBundleEvent, SignalEvent, TickEvent


class StrategyContainer(StrategyBase):
    """
    Holds multiple strategies, dispatches BarBundleEvents to each via calculate_signals,
    then aggregates their results into a single weighted SignalBundleEvent.

    Each strategy's contribution is proportional to its nominal.  Signals are
    carried forward from the last bar on which a strategy fired, so a strategy
    that returns None this bar still contributes its previous target weights.
    One combined SignalBundleEvent is emitted per bar whenever at least one
    strategy has fired at least once.
    """

    def __init__(
        self,
        emit:     Callable[[Event], None],
        get_bars: Callable[[str, int], list[TickEvent]],
    ):
        super().__init__(emit, get_bars)
        self._strategies: list[tuple[Strategy, float]] = []   # (strategy, nominal)
        self._carried:    list[dict[str, float]]        = []   # parallel; symbol → last signal

    @property
    def symbols(self) -> list[str]:
        """Union of symbols across all contained strategies (order-preserving, deduplicated)."""
        seen: set[str] = set()
        result: list[str] = []
        for strategy, _ in self._strategies:
            for sym in getattr(strategy, "symbols", []):
                if sym not in seen:
                    seen.add(sym)
                    result.append(sym)
        return result

    def add(
        self,
        strategy_class:  type[Strategy],
        strategy_params: StrategyParams,
        *,
        get_bars: Callable[[str, int], list[TickEvent]] | None = None,
    ) -> None:
        """Factory: construct a strategy and register it with its nominal."""
        instance = strategy_class(
            emit=self._emit,
            get_bars=get_bars if get_bars is not None else self._get_bars,
            strategy_params=strategy_params,
        )
        self._strategies.append((instance, strategy_params.nominal))
        self._carried.append({})

    def add_strategy(self, strategy: Strategy, nominal: float = 1.0) -> None:
        """Add a pre-constructed strategy instance with an explicit nominal."""
        self._strategies.append((strategy, nominal))
        self._carried.append({})

    def get_signals(self, event: BarBundleEvent) -> None:
        any_new = False
        for i, (strategy, _) in enumerate(self._strategies):
            result = strategy.calculate_signals(event)
            if result is not None:
                any_new = True
                for symbol, sig in result.signals.items():
                    self._carried[i][symbol] = sig.signal

        if not any_new:
            return

        total_nominal = sum(n for _, n in self._strategies) or 1.0

        # Weighted sum across all carried signals
        combined: dict[str, float] = {}
        for i, (_, nominal) in enumerate(self._strategies):
            weight = nominal / total_nominal
            for symbol, signal_val in self._carried[i].items():
                combined[symbol] = combined.get(symbol, 0.0) + signal_val * weight

        if not combined:
            return

        self._emit(SignalBundleEvent(
            timestamp=event.timestamp,
            signals={
                symbol: SignalEvent(symbol=symbol, timestamp=event.timestamp, signal=val)
                for symbol, val in combined.items()
            },
        ))
