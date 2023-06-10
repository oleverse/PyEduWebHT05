import argparse
import json
from datetime import date, timedelta
import platform
import logging

import aiohttp
import asyncio


class ExchangeRateHistory:
    EXCHANGE_HISTORY_DEPTH = 10
    DATE_FORMAT = '%d.%m.%Y'
    DEFAULT_CURRENCIES = ["USD", "EUR"]

    def __init__(self, days_count: int):
        self.__currencies = self.DEFAULT_CURRENCIES
        self.__history_days_count = days_count
        self.__base_url = "http://api.privatbank.ua"
        self.__win_async_prepare()

    def __check_history_depth(self):
        if 0 < self.__history_days_count <= self.EXCHANGE_HISTORY_DEPTH:
            return True

        print(f"You can get exchange history only within last {self.EXCHANGE_HISTORY_DEPTH} days.")

    def __dates_range(self):
        for d in range(self.__history_days_count, 0, -1):
            yield (date.today() - timedelta(days=d)).strftime(self.DATE_FORMAT)

    def __format_exchange_result(self, full_result):
        try:
            logging.debug(full_result)
            logging.debug(self.currencies)
            filtered = filter(lambda c: c["currency"] in self.currencies, full_result["exchangeRate"])
            return {
                full_result["date"]: {
                    entry["currency"]: {
                        "sale": entry["saleRateNB"],
                        "purchase": entry["purchaseRateNB"]
                    } for entry in filtered
                }
            }
        except KeyError as ex:
            print(f"Key {ex} does not exist.")

    @property
    def currencies(self):
        return self.__currencies

    @currencies.setter
    def currencies(self, currencies):
        self.__currencies = currencies

    @staticmethod
    def __win_async_prepare():
        if platform.system() == 'Windows':
            asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

    async def get_exchange_rate(self, from_date):
        try:
            async with aiohttp.ClientSession(base_url=self.__base_url, raise_for_status=True) as session:
                async with session.get("/p24api/exchange_rates", params={"date": from_date}) as response:
                    logging.debug("Response OK: %r", response.ok)
                    result = self.__format_exchange_result(await response.json())
                    return result
        except aiohttp.ClientConnectorError as ex:
            print(ex)
        except aiohttp.ClientResponseError as ex:
            print(f"URL {ex.request_info.url} not found.")

    async def get_exchange_history(self):
        if self.__check_history_depth():
            responses = list()

            for from_date in self.__dates_range():
                logging.debug("Retrieving date: %s", from_date)
                responses.append(self.get_exchange_rate(from_date))

            return await asyncio.gather(*responses)


def init_argparse():
    parser = argparse.ArgumentParser(prog="Privatbank exchange rate history")
    parser.add_argument('days', type=int, help=f'how many days the history should be retrieved for')
    parser.add_argument('-c', '--currency', help='currency code', action='append',
                        default=ExchangeRateHistory.DEFAULT_CURRENCIES)
    args = parser.parse_args()

    return args


def main():
    logging.basicConfig(level=None)

    args = init_argparse()

    exch_history = ExchangeRateHistory(args.days)
    exch_history.currencies = args.currency

    try:
        if currency_results := asyncio.run(exch_history.get_exchange_history()):
            print(json.dumps(currency_results, indent=2))
    except (KeyboardInterrupt, EOFError):
        print("Interrupted by user.")


if __name__ == "__main__":
    main()
