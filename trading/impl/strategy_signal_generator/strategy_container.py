from typing import Callable

from trading.base.strategy_params import StrategyParams

from ...base.strategy import Strategy, StrategySignalGenerator
from ...events import BarBundleEvent, Event, StrategyBundleEvent, SignalEvent, TickEvent


def _bar_freq_to_minutes(bar_freq: str) -> int:
    """Convert a bar_freq string to its minute equivalent.

    "1d" → 390  (6.5-hour trading day)
    "Xm" → X    (e.g. "5m" → 5)
    """
    if bar_freq == "1d":
        return 390
    return int(bar_freq.rstrip("m"))


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

    @property
    def required_freq(self) -> str:
        """The finest bar_freq declared across all registered strategies.

        Raises ValueError if daily ("1d") and intraday ("Xm") strategies are mixed,
        since the demux step count (390 / X) is ambiguous for arbitrary minute freqs.
        Returns "1d" when no strategies are registered.
        """
        if not self._strategies:
            return "1d"
        freqs = [s.strategy_params.bar_freq for s, _ in self._strategies]
        kinds = {"daily" if f == "1d" else "intraday" for f in freqs}
        if len(kinds) > 1:
            raise ValueError(
                "Cannot mix daily ('1d') and intraday ('Xm') strategies in the same "
                "StrategyContainer. Use separate containers or a single frequency."
            )
        if "daily" in kinds:
            return "1d"
        minutes = [_bar_freq_to_minutes(f) for f in freqs]
        return f"{min(minutes)}m"

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
        strategy_id = strategy_params.name or f"{strategy_class.__name__}_{len(self._strategies)}"
        if strategy_id in self._ids:
            raise ValueError(f"Strategy id {strategy_id!r} is already registered")
        instance = strategy_class(
            get_bars=get_bars if get_bars is not None else self._get_bars,
            strategy_params=strategy_params,
        )
        self._strategies.append((instance, strategy_params.nominal))
        self._carried.append({})
        self._ids.append(strategy_id)

    def add_strategy(self, strategy: Strategy, nominal: float = 1.0) -> None:
        """Add a pre-constructed strategy instance with an explicit nominal.

        Note: the strategy ID is always auto-generated as ClassName_index.
        To use a custom name, register via add() with StrategyParams.name instead.
        """
        self._strategies.append((strategy, nominal))
        self._carried.append({})
        self._ids.append(f"{strategy.__class__.__name__}_{len(self._strategies) - 1}")

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
        weights = [n / total_nominal for _, n in self._strategies]

        # Weighted sum across all carried signals
        combined: dict[str, float] = {}
        for i, weight in enumerate(weights):
            for symbol, signal_val in self._carried[i].items():
                combined[symbol] = combined.get(symbol, 0.0) + signal_val * weight

        if not combined:
            return

        # Delta-based attribution: buys go to strategies that raised their signal,
        # sells go to strategies that lowered their signal.  This keeps
        # _strategy_qty in the portfolio accurate so unrealized PnL reconciles.
        per_strategy: dict[str, dict[str, float]] = {}
        for symbol, combined_val in combined.items():
            prev_combined = sum(prev_carried[i].get(symbol, 0.0) * w for i, w in enumerate(weights))
            delta = combined_val - prev_combined

            if combined_val == 0.0:
                # Full exit: split equally among strategies that were long last bar
                prev_nonzero = [i for i in range(len(self._strategies))
                                if prev_carried[i].get(symbol, 0.0) != 0.0]
                if prev_nonzero:
                    share = 1.0 / len(prev_nonzero)
                    for i in prev_nonzero:
                        per_strategy.setdefault(self._ids[i], {})[symbol] = share
            elif delta != 0:
                # Net entry/increase (delta > 0): attribute to strategies that raised signal.
                # Net exit/decrease (delta < 0): attribute to strategies that lowered signal.
                wdeltas = {
                    i: (self._carried[i].get(symbol, 0.0) - prev_carried[i].get(symbol, 0.0)) * weights[i]
                    for i in range(len(self._strategies))
                }
                if delta > 0:
                    contributors = {i: d for i, d in wdeltas.items() if d > 0}
                else:
                    contributors = {i: -d for i, d in wdeltas.items() if d < 0}
                total = sum(contributors.values())
                if total > 0:
                    for i, d in contributors.items():
                        per_strategy.setdefault(self._ids[i], {})[symbol] = d / total
            else:
                # delta == 0: signal unchanged, but prices may cause rebalancing
                # fills — use current signal fractions so those fills are attributed
                for i, weight in enumerate(weights):
                    frac = weight * self._carried[i].get(symbol, 0.0) / combined_val
                    if frac != 0.0:
                        per_strategy.setdefault(self._ids[i], {})[symbol] = frac

        self.emit(StrategyBundleEvent(
            timestamp=event.timestamp,
            combined={
                symbol: SignalEvent(symbol=symbol, timestamp=event.timestamp, signal=val)
                for symbol, val in combined.items()
            },
            per_strategy=per_strategy,
        ))
