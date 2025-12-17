import threading
import time
from dataclasses import dataclass, field
from queue import Empty, Full, Queue

import LXMF
import RNS


@dataclass
class OutboundPayload:
    """
    Message payload scheduled for outbound delivery.

    Args:
        connection (RNS.Destination): Destination to deliver the message to.
        message_text (str): Plaintext message body to deliver.
        destination_hash (bytes | None): Raw destination hash for diagnostics.
        destination_hex (str | None): Hex-encoded destination hash for logging.
        attempts (int): Number of delivery attempts performed.
        next_attempt_at (float): Monotonic timestamp before the next attempt.
    """

    connection: RNS.Destination
    message_text: str
    destination_hash: bytes | None
    destination_hex: str | None
    attempts: int = 0
    next_attempt_at: float = field(default_factory=time.monotonic)


class OutboundMessageQueue:
    """
    Threaded dispatcher that delivers LXMF messages without blocking callers.
    """

    def __init__(
        self,
        lxm_router: LXMF.LXMRouter,
        sender: RNS.Destination,
        *,
        queue_size: int = 64,
        worker_count: int = 2,
        send_timeout: float = 5.0,
        backoff_seconds: float = 0.5,
        max_attempts: int = 3,
    ):
        """
        Initialize a bounded outbound queue.

        Args:
            lxm_router (LXMF.LXMRouter): Router responsible for delivery.
            sender (RNS.Destination): Sender identity to attach to messages.
            queue_size (int): Maximum queued payloads before applying backpressure.
            worker_count (int): Parallel worker threads processing the queue.
            send_timeout (float): Seconds to wait for a send before timing out.
            backoff_seconds (float): Base delay between retry attempts.
            max_attempts (int): Maximum attempts before dropping a message.
        """
        self._lxm_router = lxm_router
        self._sender = sender
        self._queue: Queue[OutboundPayload] = Queue(maxsize=max(queue_size, 1))
        self._worker_count = max(worker_count, 1)
        self._send_timeout = max(send_timeout, 0.1)
        self._backoff_seconds = max(backoff_seconds, 0.01)
        self._max_attempts = max(max_attempts, 1)
        self._stop_event = threading.Event()
        self._workers: list[threading.Thread] = []
        self._inflight = 0
        self._inflight_lock = threading.Lock()

    def start(self) -> None:
        """Start background worker threads if they are not already running."""

        if self._workers:
            return

        self._stop_event.clear()
        for index in range(self._worker_count):
            worker = threading.Thread(
                target=self._worker_loop,
                name=f"lxmf-outbound-{index}",
                daemon=True,
            )
            worker.start()
            self._workers.append(worker)

    def stop(self) -> None:
        """Signal workers to stop and wait for them to exit."""

        if not self._workers:
            return

        self._stop_event.set()
        for worker in self._workers:
            worker.join(timeout=0.5)
        self._workers.clear()

    def queue_message(
        self,
        connection: RNS.Destination,
        message_text: str,
        destination_hash: bytes | None,
        destination_hex: str | None,
    ) -> bool:
        """
        Enqueue a message for delivery.

        Args:
            connection (RNS.Destination): Destination to deliver the message to.
            message_text (str): Plaintext message body to deliver.
            destination_hash (bytes | None): Raw destination hash for diagnostics.
            destination_hex (str | None): Hex-encoded destination hash for logging.

        Returns:
            bool: ``True`` when the message was queued successfully.
        """

        payload = OutboundPayload(
            connection=connection,
            message_text=message_text,
            destination_hash=destination_hash,
            destination_hex=destination_hex,
        )
        return self._enqueue_payload(payload)

    def wait_for_flush(self, timeout: float = 1.0) -> bool:
        """
        Wait until the queue and inflight sends complete.

        Args:
            timeout (float): Seconds to wait before giving up.

        Returns:
            bool: ``True`` when the queue drained before the timeout elapsed.
        """
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            with self._inflight_lock:
                inflight = self._inflight
            if self._queue.empty() and inflight == 0:
                return True
            time.sleep(0.01)
        return False

    def _enqueue_payload(self, payload: OutboundPayload) -> bool:
        try:
            self._queue.put_nowait(payload)
            return True
        except Full:
            dropped = self._drop_oldest()
            if dropped is not None:
                RNS.log(
                    (
                        "Outbound queue is full; dropped oldest payload destined for"
                        f" {dropped.destination_hex or 'unknown destination'}"
                    ),
                    getattr(RNS, "LOG_WARNING", 2),
                )
            try:
                self._queue.put_nowait(payload)
                return True
            except Full:
                RNS.log(
                    (
                        "Outbound queue is saturated; dropping payload destined for"
                        f" {payload.destination_hex or 'unknown destination'}"
                    ),
                    getattr(RNS, "LOG_WARNING", 2),
                )
                return False

    def _drop_oldest(self) -> OutboundPayload | None:
        try:
            oldest = self._queue.get_nowait()
            self._queue.task_done()
            return oldest
        except Empty:
            return None

    def _worker_loop(self) -> None:
        while not self._stop_event.is_set() or not self._queue.empty():
            try:
                payload = self._queue.get(timeout=0.1)
            except Empty:
                continue

            now = time.monotonic()
            if payload.next_attempt_at > now:
                delay = min(payload.next_attempt_at - now, 0.1)
                time.sleep(delay)
                self._enqueue_payload(payload)
                self._queue.task_done()
                continue

            try:
                self._process_payload(payload)
            finally:
                self._queue.task_done()

    def _process_payload(self, payload: OutboundPayload) -> None:
        with self._inflight_lock:
            self._inflight += 1

        try:
            success = self._send_with_timeout(payload)
            if not success:
                self._handle_failure(payload)
        finally:
            with self._inflight_lock:
                self._inflight -= 1

    def _send_with_timeout(self, payload: OutboundPayload) -> bool:
        error: list[Exception | None] = [None]

        def _send() -> None:
            try:
                message = LXMF.LXMessage(
                    payload.connection,
                    self._sender,
                    payload.message_text,
                    desired_method=LXMF.LXMessage.DIRECT,
                )
                if payload.destination_hash:
                    message.destination_hash = payload.destination_hash
                self._lxm_router.handle_outbound(message)
            except Exception as exc:  # pragma: no cover - defensive logging
                error[0] = exc

        sender = threading.Thread(target=_send, name="lxmf-send", daemon=True)
        sender.start()
        sender.join(timeout=self._send_timeout)
        if sender.is_alive():
            RNS.log(
                (
                    "Timed out delivering outbound message to"
                    f" {payload.destination_hex or 'unknown destination'}"
                ),
                getattr(RNS, "LOG_WARNING", 2),
            )
            return False

        if error[0] is not None:
            RNS.log(
                (
                    "Failed to deliver outbound message to"
                    f" {payload.destination_hex or 'unknown destination'}: {error[0]}"
                ),
                getattr(RNS, "LOG_WARNING", 2),
            )
            return False
        return True

    def _handle_failure(self, payload: OutboundPayload) -> None:
        payload.attempts += 1
        if payload.attempts >= self._max_attempts:
            RNS.log(
                (
                    "Dropping outbound message to"
                    f" {payload.destination_hex or 'unknown destination'} after"
                    f" {payload.attempts} attempts"
                ),
                getattr(RNS, "LOG_WARNING", 2),
            )
            return

        payload.next_attempt_at = (
            time.monotonic() + self._backoff_seconds * payload.attempts
        )
        # Reason: requeue with backoff so slower destinations do not halt others.
        self._enqueue_payload(payload)
