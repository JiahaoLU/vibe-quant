from typing import Callable

from trading.base.strategy_params import StrategyParams

from ..base.strategy import Strategy, StrategySignalGenerator
from ..events import BarBundleEvent, Event, SignalBundleEvent, StrategyBundleEvent, SignalEvent, TickEvent


class StrategyContainer(StrategySignalGenerator):
    """
    Holds multiple strategies, dispatches BarBundleEvents to each via calculate_signals,
    then aggregates their results into a single weighted StrategyBundleEvent.

    Each strategy's contribution is proportional to its nominal.  Signals are
    carried forward from the last bar on which a strategy fired, so a strategy
    that returns None this bar still contributes its previous target weights.
    One combined StrategyBundleEvent is emitted per bar whenever at least one
    strategy has fired at least once.

    Important: a strategy that has *never* fired (e.g. still warming up) has an
    empty carry-forward and therefore contributes zero signal, but its nominal is
    still included in total_nominal.  This means it dilutes all other strategies'
    effective weight until it fires for the first time.  Register strategies only
    when they are ready to produce signals, or accept this warm-up dilution.
    """

    def __init__(
        self,
        emit:     Callable[[Event], None],
        get_bars: Callable[[str, int], list[TickEvent]],
    ):
        super().__init__(get_bars=get_bars)
        self._emit_fn    = emit
        self._strategies: list[tuple[Strategy, float]] = []   # (strategy, nominal)
        self._carried:    list[dict[str, float]]        = []   # parallel; symbol → last signal
        self._ids:        list[str]                     = []   # parallel; strategy id

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

    def emit(self, event: Event) -> None:
        self._emit_fn(event)

    def add(
        self,
        strategy_class:  type[Strategy],
        strategy_params: StrategyParams,
        *,
        get_bars: Callable[[str, int], list[TickEvent]] | None = None,
    ) -> None:
        """Factory: construct a strategy and register it with its nominal."""
        index = len(self._strategies)
        strategy_id = strategy_params.name if strategy_params.name else f"{strategy_class.__name__}_{index}"
        instance = strategy_class(
            get_bars=get_bars if get_bars is not None else self._get_bars,
            strategy_params=strategy_params,
        )
        self._strategies.append((instance, strategy_params.nominal))
        self._carried.append({})
        self._ids.append(strategy_id)

    def add_strategy(self, strategy: Strategy, nominal: float = 1.0) -> None:
        """Add a pre-constructed strategy instance with an explicit nominal."""
        index = len(self._strategies)
        strategy_id = f"{strategy.__class__.__name__}_{index}"
        self._strategies.append((strategy, nominal))
        self._carried.append({})
        self._ids.append(strategy_id)

    def get_signals(self, event: BarBundleEvent) -> None:
        # Snapshot carries before updating — needed for full-exit attribution
        prev_carried = [{**c} for c in self._carried]

        any_new = False
        for i, (strategy, _) in enumerate(self._strategies):
            result = strategy.calculate_signals(event)
            strategy.on_get_signal(result)
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

        # Compute per-strategy attribution fractions
        per_strategy: dict[str, dict[str, float]] = {}
        for symbol, combined_val in combined.items():
            if combined_val != 0.0:
                for i, (_, nominal) in enumerate(self._strategies):
                    weight_i = nominal / total_nominal
                    carried_val = self._carried[i].get(symbol, 0.0)
                    frac = weight_i * carried_val / combined_val
                    if frac != 0.0:
                        per_strategy.setdefault(self._ids[i], {})[symbol] = frac
            else:
                # Full exit: split equally among strategies that were long last bar
                prev_nonzero = [i for i in range(len(self._strategies))
                                if prev_carried[i].get(symbol, 0.0) != 0.0]
                if prev_nonzero:
                    share = 1.0 / len(prev_nonzero)
                    for i in prev_nonzero:
                        per_strategy.setdefault(self._ids[i], {})[symbol] = share

        self.emit(StrategyBundleEvent(
            timestamp=event.timestamp,
            combined={
                symbol: SignalEvent(symbol=symbol, timestamp=event.timestamp, signal=val)
                for symbol, val in combined.items()
            },
            per_strategy=per_strategy,
        ))
