"""
ZeroMQ Client module for MT4 communication.
Implements robust Lazy Pirate pattern for REQ/REP socket recovery,
background 5s heartbeat auto-reconnect, and fault-tolerant query handling.
"""
import json
import logging
import threading
import time
from typing import Any, Dict, Optional
import zmq
from config import ZMQ_SERVER_URL, ZMQ_TIMEOUT_MS, ZMQ_RETRY_INTERVAL_SEC

logger = logging.getLogger(__name__)

class MT4ZmqClient:
    def __init__(self, server_url: str = ZMQ_SERVER_URL, timeout_ms: int = ZMQ_TIMEOUT_MS, retry_interval: int = ZMQ_RETRY_INTERVAL_SEC):
        self.server_url = server_url
        self.timeout_ms = timeout_ms
        self.retry_interval = retry_interval
        self.context = zmq.Context()
        self.socket: Optional[zmq.Socket] = None
        self._lock = threading.Lock()
        self.is_connected = False
        self._stop_heartbeat = threading.Event()
        
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

    def send_command(self, action: str, **kwargs) -> Dict[str, Any]:
        """
        Sends a JSON-encoded command to the MT4 ZeroMQ Bridge EA and returns the parsed response.
        If MT4 is closed or times out, safely resets socket and returns "MT4 not connected".
        """
        payload = {"action": action, **kwargs}
        req_bytes = json.dumps(payload).encode("utf-8")

        with self._lock:
            try:
                if self.socket is None:
                    self._init_socket()
                
                self.socket.send(req_bytes)
                reply_bytes = self.socket.recv()
                reply_str = reply_bytes.decode("utf-8", errors="replace")
                res = json.loads(reply_str)
                self.is_connected = True
                return res
            except zmq.Again:
                logger.warning(f"Timeout ({self.timeout_ms}ms) waiting for MT4 ZeroMQ response for action '{action}'")
                self.is_connected = False
                self._init_socket() # Reset socket to clear EFSM state
                return {
                    "status": "error",
                    "connected": False,
                    "message": "⚠️ MT4 not connected"
                }
            except Exception as e:
                logger.error(f"ZeroMQ communication error for '{action}': {e}")
                self.is_connected = False
                self._init_socket()
                return {
                    "status": "error",
                    "connected": False,
                    "message": "⚠️ MT4 not connected"
                }

    def get_account(self) -> Dict[str, Any]:
        return self.send_command("GET_ACCOUNT")

    def get_positions(self) -> Dict[str, Any]:
        return self.send_command("GET_POSITIONS")

    def get_history(self, limit: int = 10, filter_type: str = "all") -> Dict[str, Any]:
        return self.send_command("GET_HISTORY", limit=limit, filter=filter_type)

    def close_all(self) -> Dict[str, Any]:
        return self.send_command("CLOSE_ALL")

    def close_symbol(self, symbol: str) -> Dict[str, Any]:
        return self.send_command("CLOSE_SYMBOL", symbol=symbol)

    def close_half(self, ticket: int) -> Dict[str, Any]:
        return self.send_command("CLOSE_HALF", ticket=ticket)

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

    def apply_colors(self) -> Dict[str, Any]:
        return self.send_command("APPLY_COLORS")

    def get_screenshot(self, symbol: str = "", timeframe: str = "", width: int = 1280, height: int = 720) -> Dict[str, Any]:
        return self.send_command("SCREENSHOT", symbol=symbol, timeframe=timeframe, width=width, height=height)

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

    def close(self):
        """Stops heartbeat thread and closes socket cleanly."""
        self._stop_heartbeat.set()
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

# Global singleton client
zmq_client = MT4ZmqClient()
