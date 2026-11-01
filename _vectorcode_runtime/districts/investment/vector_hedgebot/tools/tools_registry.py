from districts.investment.vector_hedgebot.tools.jupiter_search import search_tokens
from districts.investment.vector_hedgebot.tools.jupiter_price import get_token_price
from districts.investment.vector_hedgebot.tools.jupiter_ultra import execute_trade, get_holdings
from districts.investment.vector_hedgebot.tools.jupiter_ultra import get_order


def get_tools():
    return [
        search_tokens,
        get_token_price,
        execute_trade,
        get_holdings,
        get_order,
    ]
