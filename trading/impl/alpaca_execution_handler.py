from typing import Callable

from ..events import Event
from .alpaca_paper_execution_handler import AlpacaPaperExecutionHandler


class AlpacaExecutionHandler(AlpacaPaperExecutionHandler):
    """Routes orders to Alpaca's live trading API. Identical to paper handler, paper=False."""

    _PAPER = False

    def __init__(self, emit: Callable[[Event], None], api_key: str, secret: str):
        super().__init__(emit=emit, api_key=api_key, secret=secret)
