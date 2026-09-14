"""
ZeroMQ Client module for MT4 communication.
Implements robust Lazy Pirate pattern for REQ/REP socket recovery,
background 5s heartbeat auto-reconnect, and fault-tolerant query handling.
"""
import asyncio
import json
import logging
import threading
import time
from typing import Any, Dict, List, Optional
import zmq
import zmq.asyncio
from config import ZMQ_SERVER_URL, ZMQ_TIMEOUT_MS, ZMQ_RETRY_INTERVAL_SEC

logger = logging.getLogger(__name__)

DEFAULT_MAX_TIMEOUT_MS = 2500


class MT4ZmqClient:
    def __init__(
        self,
        server_url: str = ZMQ_SERVER_URL,
        timeout_ms: int = ZMQ_TIMEOUT_MS,
        retry_interval: int = ZMQ_RETRY_INTERVAL_SEC,
        sub_url: Optional[str] = None
    ):
        self.server_url = server_url
        self.timeout_ms = min(timeout_ms, DEFAULT_MAX_TIMEOUT_MS)
        self.retry_interval = retry_interval
        self.context = zmq.Context()
        self.socket: Optional[zmq.Socket] = None
        self._lock = threading.Lock()
        self.is_connected = False
        self._stop_heartbeat = threading.Event()

        # pyzmq.asyncio context & non-blocking SUB socket
        self.async_context = zmq.asyncio.Context()
        self.sub_url = sub_url or (
            server_url.replace(":5555", ":5556") if ":5555" in server_url else "tcp://127.0.0.1:5556"
        )
        self._async_sub_socket: Optional[zmq.asyncio.Socket] = None
        self._async_lock = asyncio.Lock()

        # Performance & telemetry metrics
        self.last_latency_ms: float = 0.0
        self.total_commands_sent: int = 0
        self.total_commands_failed: int = 0
        
        self._init_socket()
        
        # Start background health-check / auto-reconnect thread
        self._heartbeat_thread = threading.Thread(target=self._heartbeat_loop, daemon=True, name="ZmqHeartbeat")
        self._heartbeat_thread.start()

    def switch_endpoint(self, new_url: str) -> None:

        """Switches the active ZeroMQ connection target to a new server endpoint."""
        with self._lock:
            if self.server_url == new_url and self.socket is not None:
                return
            logger.info(f"Switching ZeroMQ endpoint from {self.server_url} to {new_url}")
            self.server_url = new_url
            self.is_connected = False
            self._init_socket()

    def _init_socket(self) -> None:
        """Initializes or safely resets the ZeroMQ REQ socket."""
        if self.socket is not None:
            try:
                self.socket.setsockopt(zmq.LINGER, 0)
                self.socket.close()
            except Exception as e:
                logger.debug(f"Error closing old ZeroMQ socket: {e}")
            finally:
                self.socket = None
        
        try:
            self.socket = self.context.socket(zmq.REQ)
            self.socket.setsockopt(zmq.RCVTIMEO, self.timeout_ms)
            self.socket.setsockopt(zmq.SNDTIMEO, self.timeout_ms)
            self.socket.setsockopt(zmq.LINGER, 0)
            self.socket.connect(self.server_url)
            logger.debug(f"ZeroMQ REQ connected to {self.server_url}")
        except Exception as ex:
            logger.error(f"Failed to create ZeroMQ socket: {ex}")
            self.socket = None

    def _heartbeat_loop(self) -> None:
        """Background thread checking MT4 health every 5 seconds and auto-reconnecting."""
        while not self._stop_heartbeat.is_set():
            time.sleep(self.retry_interval)
            try:
                # Silent ping check
                res = self.ping()
                was_connected = self.is_connected
                if res.get("status") == "ok":
                    self.is_connected = True
                    if not was_connected:
                        logger.info(f"✅ ZeroMQ connection to MT4 restored ({self.server_url}).")
                else:
                    self.is_connected = False
                    if was_connected:
                        logger.warning("⚠️ MT4 ZeroMQ bridge unreachable. Auto-reconnecting every 5s...")
            except Exception as ex:
                self.is_connected = False
                logger.debug(f"Heartbeat check error: {ex}")

    def send_command(self, action: str, timeout_ms: Optional[int] = None, **kwargs) -> Dict[str, Any]:
        """
        Sends a JSON-encoded command to the MT4 ZeroMQ Bridge EA and returns the parsed response.
        If MT4 is closed or times out, safely resets socket and returns "MT4 not connected".
        Enforces maximum 2500ms timeout limit.
        """
        payload = {"action": action, **kwargs}
        req_bytes = json.dumps(payload).encode("utf-8")
        eff_timeout = min(timeout_ms if timeout_ms is not None else self.timeout_ms, DEFAULT_MAX_TIMEOUT_MS)
        t0 = time.perf_counter()

        with self._lock:
            try:
                if self.socket is None:
                    self._init_socket()
                
                if eff_timeout != self.timeout_ms and self.socket is not None:
                    self.socket.setsockopt(zmq.RCVTIMEO, eff_timeout)
                    self.socket.setsockopt(zmq.SNDTIMEO, eff_timeout)

                self.socket.send(req_bytes)
                reply_bytes = self.socket.recv()
                reply_str = reply_bytes.decode("utf-8", errors="replace")
                res = json.loads(reply_str)
                self.is_connected = True
                self.last_latency_ms = round((time.perf_counter() - t0) * 1000.0, 2)
                self.total_commands_sent += 1
                return res
            except zmq.Again:
                self.total_commands_failed += 1
                if self.is_connected:
                    logger.warning(f"Timeout ({eff_timeout}ms) waiting for MT4 ZeroMQ response for action '{action}'")
                else:
                    logger.debug(f"ZeroMQ socket timeout ({eff_timeout}ms) for action '{action}'")
                self.is_connected = False
                self._init_socket() # Reset socket to clear EFSM state
                return {
                    "status": "error",
                    "connected": False,
                    "message": "⚠️ MT4 not connected"
                }
            except Exception as e:
                self.total_commands_failed += 1
                logger.error(f"ZeroMQ communication error for '{action}': {e}")
                self.is_connected = False
                self._init_socket()
                return {
                    "status": "error",
                    "connected": False,
                    "message": "⚠️ MT4 not connected"
                }
            finally:
                if eff_timeout != self.timeout_ms and self.socket is not None:
                    try:
                        self.socket.setsockopt(zmq.RCVTIMEO, self.timeout_ms)
                        self.socket.setsockopt(zmq.SNDTIMEO, self.timeout_ms)
                    except Exception:
                        pass

    async def send_command_async(self, action: str, timeout_ms: Optional[int] = None, **kwargs) -> Dict[str, Any]:
        """
        Asynchronously sends a JSON command to MT4 bridge without blocking the event loop.
        Guarantees maximum 2500ms timeout.
        """
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, lambda: self.send_command(action, timeout_ms=timeout_ms, **kwargs))


    def open_order(
        self,
        symbol: str,
        cmd: str,
        lots: float = 0.01,
        price: float = 0.0,
        sl: float = 0.0,
        tp: float = 0.0,
        sl_pips: float = 0.0,
        tp_pips: float = 0.0,
        slippage: int = 5,
        magic: int = 8882026,
        comment: str = "TelegramTrade",
        timeout_ms: int = 8000
    ) -> Dict[str, Any]:
        return self.send_command(
            "OPEN_ORDER",
            symbol=symbol,
            cmd=cmd,
            lots=lots,
            price=price,
            sl=sl,
            tp=tp,
            sl_pips=sl_pips,
            tp_pips=tp_pips,
            slippage=slippage,
            magic=magic,
            comment=comment,
            timeout_ms=timeout_ms
        )

    def close_ticket(self, ticket: int, timeout_ms: int = 10000) -> Dict[str, Any]:
        return self.close_symbol(str(ticket), timeout_ms=timeout_ms)

    def close_partial(self, ticket: int, lots: float, timeout_ms: int = 10000) -> Dict[str, Any]:
        return self.send_command("CLOSE_PARTIAL", ticket=ticket, lots=lots, timeout_ms=timeout_ms)

    def get_account(self) -> Dict[str, Any]:
        return self.send_command("GET_ACCOUNT")

    def get_positions(self) -> Dict[str, Any]:
        return self.send_command("GET_POSITIONS")

    def get_history(self, limit: int = 10, filter_type: str = "all") -> Dict[str, Any]:
        return self.send_command("GET_HISTORY", limit=limit, filter=filter_type)

    def close_all(self) -> Dict[str, Any]:
        return self.send_command("CLOSE_ALL", timeout_ms=12000)

    def close_symbol(self, symbol: str, timeout_ms: int = 10000) -> Dict[str, Any]:
        return self.send_command("CLOSE_SYMBOL", symbol=symbol, timeout_ms=timeout_ms)

    def close_half(self, ticket: int, timeout_ms: int = 10000) -> Dict[str, Any]:
        return self.send_command("CLOSE_HALF", ticket=ticket, timeout_ms=timeout_ms)

    def modify_order(self, ticket: int = 0, symbol: str = "", sl: float = -1.0, tp: float = -1.0, timeout_ms: int = 5000) -> Dict[str, Any]:
        return self.send_command("MODIFY_ORDER", ticket=ticket, symbol=symbol, sl=sl, tp=tp, timeout_ms=timeout_ms)

    def modify_sl(self, symbol: str = "", ticket: int = 0, sl: float = 0.0) -> Dict[str, Any]:
        return self.send_command("MODIFY_SL", symbol=symbol, ticket=ticket, sl=sl)

    def modify_tp(self, symbol: str = "", ticket: int = 0, tp: float = 0.0) -> Dict[str, Any]:
        return self.send_command("MODIFY_TP", symbol=symbol, ticket=ticket, tp=tp)

    def set_breakeven(self, symbol: str = "", ticket: int = 0, lock_pips: int = 1) -> Dict[str, Any]:
        return self.send_command("SET_BREAKEVEN", symbol=symbol, ticket=ticket, lock_pips=lock_pips)

    def set_trailing(self, symbol: str = "", ticket: int = 0, trail_pips: int = 20) -> Dict[str, Any]:
        return self.send_command("SET_TRAILING", symbol=symbol, ticket=ticket, trail_pips=trail_pips)

    def pause_bot(self) -> Dict[str, Any]:
        return self.send_command("PAUSE_BOT")

    def resume_bot(self) -> Dict[str, Any]:
        return self.send_command("RESUME_BOT")

    def ping(self) -> Dict[str, Any]:
        return self.send_command("PING")

    def get_prop(self) -> Dict[str, Any]:
        return self.send_command("GET_PROP")

    def get_report(self) -> Dict[str, Any]:
        return self.send_command("GET_REPORT")

    def apply_colors(self, timeout_ms: int = 5000) -> Dict[str, Any]:
        return self.send_command("APPLY_COLORS", timeout_ms=timeout_ms)

    def get_screenshot(
        self,
        symbol: str = "",
        timeframe: str = "",
        width: int = 1280,
        height: int = 720,
        entry_price: float = 0.0,
        sl_price: float = 0.0,
        tp_price: float = 0.0,
        event_type: str = "",
        timeout_ms: int = 10000,
        compose: bool = True,
        **kwargs
    ) -> Dict[str, Any]:
        res = self.send_command(
            "SCREENSHOT",
            symbol=symbol,
            timeframe=timeframe,
            width=width,
            height=height,
            entry_price=entry_price,
            sl_price=sl_price,
            tp_price=tp_price,
            event_type=event_type,
            timeout_ms=timeout_ms,
            **kwargs
        )
        if compose and res.get("status") == "ok":
            fn = res.get("filename")
            if fn:
                try:
                    import os
                    from config import MT4_FILES_DIR
                    from autotrade.analytics.chart_composer import compose_chart_screenshot
                    shot_path = os.path.join(MT4_FILES_DIR, fn)
                    for _ in range(25):
                        if os.path.exists(shot_path) and os.path.getsize(shot_path) > 500:
                            compose_chart_screenshot(shot_path, res)
                            break
                        time.sleep(0.1)
                except Exception as ex:
                    logger.warning(f"Error composing screenshot in zmq_client: {ex}")
        return res

    def get_market_watch_symbols(self, timeout_ms: int = 5000) -> Dict[str, Any]:
        """
        Queries MT4 bridge for dynamically discovered active, tradable instruments
        directly from the Market Watch window.
        """
        res = self.send_command("GET_MARKET_WATCH_SYMBOLS", timeout_ms=timeout_ms)
        if res.get("status") == "ok" and "symbols" in res:
            return res
        return self.send_command("GET_SYMBOLS", timeout_ms=timeout_ms)

    def get_symbols(self, timeout_ms: int = 5000) -> Dict[str, Any]:
        return self.send_command("GET_SYMBOLS", timeout_ms=timeout_ms)

    def get_quote(self, symbol: str, timeout_ms: int = 3000) -> Dict[str, Any]:
        """Queries MT4 bridge for live market quotes (bid, ask, spread)."""
        return self.send_command("GET_QUOTE", symbol=symbol, timeout_ms=timeout_ms)

    def get_rates(self, symbol: str, timeframe: str = "H1", count: int = 100, timeout_ms: int = 5000) -> Dict[str, Any]:
        """Queries MT4 bridge for historical OHLCV candle rates."""
        return self.send_command("GET_RATES", symbol=symbol, timeframe=timeframe, count=count, timeout_ms=timeout_ms)

    def scan_symbols(self, symbols: str = "", timeframe: str = "H1", timeout_ms: int = 5000) -> Dict[str, Any]:
        return self.send_command("SCAN_SYMBOLS", symbols=symbols, timeframe=timeframe, timeout_ms=timeout_ms)

    def get_symbol_info(self, symbol: str, timeout_ms: int = 5000) -> Dict[str, Any]:
        """Queries MT4 bridge for autonomous broker specification metrics (lot sizing, tick value, contract size)."""
        return self.send_command("GET_SYMBOL_INFO", symbol=symbol, timeout_ms=timeout_ms)

    def get_boost(self) -> Dict[str, Any]:
        return self.send_command("GET_BOOST")

    def reset_safeguards(self) -> Dict[str, Any]:
        return self.send_command("RESET_SAFEGUARDS")

    def ping_latency_ms(self) -> float:
        """Measures roundtrip latency to MT4 ZeroMQ bridge in milliseconds."""
        t0 = time.perf_counter()
        res = self.ping()
        t1 = time.perf_counter()
        if res.get("status") == "ok":
            return round((t1 - t0) * 1000.0, 2)
        return -1.0

    # --- Asynchronous ZeroMQ Helpers & Market Data Stream (SUB Socket) ---

    def init_async_sub_socket(self, sub_url: Optional[str] = None, topics: Optional[List[str]] = None) -> None:
        """Initializes non-blocking zmq.asyncio SUB socket for market tick/bar streaming."""
        if self._async_sub_socket is not None:
            try:
                self._async_sub_socket.close()
            except Exception:
                pass
        self.sub_url = sub_url or self.sub_url
        try:
            self._async_sub_socket = self.async_context.socket(zmq.SUB)
            self._async_sub_socket.setsockopt(zmq.LINGER, 0)
            self._async_sub_socket.setsockopt(zmq.RCVTIMEO, DEFAULT_MAX_TIMEOUT_MS)
            target_topics = topics or ["", "TICK", "BAR", "MARKET"]
            for topic in target_topics:
                self._async_sub_socket.setsockopt_string(zmq.SUBSCRIBE, topic)
            self._async_sub_socket.connect(self.sub_url)
            logger.info(f"ZeroMQ Async SUB connected to {self.sub_url}")
        except Exception as ex:
            logger.warning(f"Failed to connect ZeroMQ Async SUB socket to {self.sub_url}: {ex}")
            self._async_sub_socket = None

    async def recv_market_event_async(self) -> Optional[Dict[str, Any]]:
        """Asynchronously receives next broadcast message from SUB socket without blocking."""
        if self._async_sub_socket is None:
            self.init_async_sub_socket()
        if self._async_sub_socket is None:
            return None
        try:
            msg = await self._async_sub_socket.recv_string()
            parts = msg.split(" ", 1)
            json_str = parts[1] if len(parts) > 1 and parts[1].startswith("{") else msg
            if json_str.startswith("{") and json_str.endswith("}"):
                return json.loads(json_str)
            return {"raw": msg}
        except (zmq.Again, asyncio.TimeoutError):
            return None
        except Exception as ex:
            logger.debug(f"Async SUB receive error: {ex}")
            return None

    async def open_order_async(self, **kwargs) -> Dict[str, Any]:
        """Asynchronously executes market order via ZeroMQ bridge."""
        return await self.send_command_async("OPEN_ORDER", **kwargs)

    async def get_account_async(self) -> Dict[str, Any]:
        """Asynchronously queries MT4 account metrics."""
        return await self.send_command_async("GET_ACCOUNT")

    async def get_positions_async(self) -> Dict[str, Any]:
        """Asynchronously queries MT4 open positions."""
        return await self.send_command_async("GET_POSITIONS")

    async def get_quote_async(self, symbol: str) -> Dict[str, Any]:
        """Asynchronously queries MT4 live quote."""
        return await self.send_command_async("GET_QUOTE", symbol=symbol)

    async def get_rates_async(self, symbol: str, timeframe: str = "H1", count: int = 100) -> Dict[str, Any]:
        """Asynchronously queries MT4 historical bars."""
        return await self.send_command_async("GET_RATES", symbol=symbol, timeframe=timeframe, count=count)

    async def scan_symbols_async(self, symbols: str = "", timeframe: str = "H1") -> Dict[str, Any]:
        """Asynchronously triggers multi-symbol market surveillance."""
        return await self.send_command_async("SCAN_SYMBOLS", symbols=symbols, timeframe=timeframe)

    async def get_symbol_info_async(self, symbol: str) -> Dict[str, Any]:
        """Asynchronously queries MT4 broker specification metrics."""
        return await self.send_command_async("GET_SYMBOL_INFO", symbol=symbol)

    async def get_market_watch_symbols_async(self, timeout_ms: int = 5000) -> Dict[str, Any]:
        """
        Asynchronously queries MT4 bridge for dynamically discovered active, tradable instruments
        directly from the Market Watch window.
        """
        res = await self.send_command_async("GET_MARKET_WATCH_SYMBOLS", timeout_ms=timeout_ms)
        if res.get("status") == "ok" and "symbols" in res:
            return res
        return await self.send_command_async("GET_SYMBOLS", timeout_ms=timeout_ms)

    async def get_symbols_async(self, timeout_ms: int = 5000) -> Dict[str, Any]:
        """Asynchronously queries MT4 active symbols."""
        return await self.send_command_async("GET_SYMBOLS", timeout_ms=timeout_ms)

    async def get_screenshot_async(self, **kwargs) -> Dict[str, Any]:
        """Asynchronously requests chart screenshot from MT4 bridge and composes telemetry overlay."""
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, lambda: self.get_screenshot(**kwargs))

    def close(self):
        """Stops heartbeat thread and closes sockets cleanly."""
        self._stop_heartbeat.set()
        if self._async_sub_socket:
            try:
                self._async_sub_socket.close()
            except Exception:
                pass
            self._async_sub_socket = None
        with self._lock:
            if self.socket:
                try:
                    self.socket.setsockopt(zmq.LINGER, 0)
                    self.socket.close()
                except Exception:
                    pass
                self.socket = None
            try:
                self.context.term()
            except Exception:
                pass
        try:
            self.async_context.term()
        except Exception:
            pass


# Global singleton client
zmq_client = MT4ZmqClient()
