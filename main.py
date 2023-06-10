from datetime import date, datetime, timedelta
import platform
import logging
import websockets
import names
from websockets import WebSocketServerProtocol
from websockets.exceptions import ConnectionClosedOK

import aiohttp
import asyncio
from aiopath import AsyncPath
from aiofile import async_open


class WebSockServer:
    clients = set()

    async def register(self, ws: WebSocketServerProtocol):
        ws.name = names.get_full_name()
        self.clients.add(ws)
        logging.info(f'{ws.remote_address} connects')

    async def unregister(self, ws: WebSocketServerProtocol):
        self.clients.remove(ws)
        logging.info(f'{ws.remote_address} disconnects')

    async def send_to_clients(self, message: str):
        if self.clients:
            [await client.send(message) for client in self.clients]

    async def ws_handler(self, ws: WebSocketServerProtocol):
        await self.register(ws)
        try:
            await self.distribute(ws)
        except ConnectionClosedOK:
            pass
        finally:
            await self.unregister(ws)

    async def distribute(self, ws: WebSocketServerProtocol):
        async for message in ws:
            await self.send_to_clients(f"{ws.name}: {message}")
            if message.lower().startswith("exchange"):
                await self.send_to_clients("Making a request to pb.ua API...")
                exchange_history = await self.exchange_handler(message.lower())
                if exchange_history is not None:
                    await self.send_to_clients(exchange_history)

    async def exchange_handler(self, message):
        await self.log_exchange_request(message)
        try:
            command, days = message.strip().split()
            exch_history = ExchangeRateHistory(int(days))
        except ValueError:
            return "The correct command is: exchange <days_number>"
        else:
            raw_result = await exch_history.get_exchange_history()
            await self.log_exchange_request(raw_result)
            return self.get_pretty_result(raw_result)

    @staticmethod
    async def log_exchange_request(text):
        log_dir = AsyncPath("logs")
        await log_dir.mkdir(exist_ok=True, parents=True)
        async with async_open(log_dir / AsyncPath("exchange_log.log"), "a") as log_file:
            await log_file.write(f"[{datetime.now()}] => ")
            await log_file.write(f"{text}\n")

    @staticmethod
    def get_pretty_result(raw_result):
        logging.debug(type(raw_result))

        result = f'<div class="exchange-history">'
        result += f'<h4>Exchange history</h4>'
        result += f'<div class="content"><ul>'
        for date_entry in raw_result:
            result += f'<li><span class="date">{list(date_entry.keys())[0]}</span><ul>'
            for currency, rates in date_entry[list(date_entry.keys())[0]].items():
                result += f'<li><span class="currency-code">{currency}</span> => '
                result += f'<span class="rates">sale: {rates["sale"]}, purchase: {rates["purchase"]}</span></li>'
            result += '</ul></li>'

        result += '</ul></div></div>'

        return result


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


async def main():
    logging.basicConfig(level=None)

    server = WebSockServer()
    async with websockets.serve(server.ws_handler, 'localhost', 8080):
        await asyncio.Future()  # run forever


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, EOFError):
        print("The server has been shutdown by the user.")
