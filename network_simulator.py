# network_simulator.py
# ------------------------------------------------------------
# NETWORK SIMULATOR (TCP proxy)
#
# Problem: The network inside one computer (localhost) is perfect.
# Messages arrive in under 1 ms and are never lost. In this
# environment there is no visible difference between QoS 0, 1 and 2.
#
# Solution: Clients connect not to the broker directly but to a
# "middle door" opened by this program. While forwarding the traffic
# to the broker, the program:
#   - Adds DELAY by holding each chunk of data for a set time,
#   - Creates DISCONNECTS by suddenly cutting all connections at random
#     moments (like Wi-Fi dropping for a moment).
#
#       client  <-->  [ NetworkSimulator :1885 ]  <-->  broker :1883
#
# Note: MQTT runs over TCP, and TCP repairs individual packet loss by
# itself. So in MQTT, loss really happens WHEN THE CONNECTION DROPS.
# The simulator creates loss the same way.
# ------------------------------------------------------------

import asyncio
import random
import threading


class NetworkSimulator:
    def __init__(self, listen_port, target_host, target_port,
                 delay_ms=0.0, jitter_ms=0.0, mean_disconnect_s=None, seed=None):
        """
        listen_port       : Port clients connect to (e.g. 1885)
        target_host/port  : The real broker's address (e.g. localhost:1883)
        delay_ms          : Average delay added in each direction (milliseconds)
        jitter_ms         : Random variation added to the delay (± milliseconds)
        mean_disconnect_s : On average how many seconds between connection drops (None = never)
        seed              : Random number seed. Same seed = same disconnect times.
                            This way every QoS level is tested under the same network conditions.
        """
        self.listen_port = listen_port
        self.target_host = target_host
        self.target_port = target_port
        self.delay_s = delay_ms / 1000
        self.jitter_s = jitter_ms / 1000
        self.mean_disconnect_s = mean_disconnect_s
        self.disconnect_count = 0

        # Two separate random generators: disconnect times depend only on the
        # seed and are not affected by how many data chunks were sent.
        self._disconnect_random = random.Random(seed)
        self._delay_random = random.Random(seed)

        self._loop = None
        self._stop_event = None
        self._thread = None
        self._connections = set()  # Open (client, broker) connection pairs

    # ---------- The two functions used from outside ----------

    def start(self):
        """Starts the simulator in the background and waits for it to be ready."""
        ready = threading.Event()
        self._thread = threading.Thread(target=lambda: asyncio.run(self._main(ready)), daemon=True)
        self._thread.start()
        if not ready.wait(timeout=5):
            raise RuntimeError("Could not start the network simulator.")

    def stop(self):
        """Closes all connections and stops the simulator."""
        if self._loop:
            self._loop.call_soon_threadsafe(self._stop_event.set)
            self._thread.join(timeout=5)

    # ---------- Internals (with asyncio) ----------
    # asyncio: A Python library for handling many connections at once on a
    # single thread. Wherever you see "await", the program switches to other
    # connections' work while it waits.

    async def _main(self, ready):
        self._loop = asyncio.get_running_loop()
        self._stop_event = asyncio.Event()
        server = await asyncio.start_server(self._new_connection, "127.0.0.1", self.listen_port)

        cutter = None
        if self.mean_disconnect_s:
            cutter = asyncio.create_task(self._cutter())

        ready.set()
        async with server:
            await self._stop_event.wait()
            if cutter:
                cutter.cancel()
            self._cut_all()

    async def _new_connection(self, client_reader, client_writer):
        """Called when a client connects: opens a second connection to the broker."""
        try:
            broker_reader, broker_writer = await asyncio.open_connection(self.target_host, self.target_port)
        except OSError:
            client_writer.transport.abort()
            return

        pair = (client_writer, broker_writer)
        self._connections.add(pair)
        try:
            # Forward both directions at once: client -> broker and broker -> client
            await asyncio.gather(
                self._forward(client_reader, broker_writer),
                self._forward(broker_reader, client_writer),
                return_exceptions=True,
            )
        finally:
            self._connections.discard(pair)
            for writer in pair:
                writer.transport.abort()

    async def _forward(self, reader, writer):
        """
        Forwards one direction's data with delay. Every chunk read is put on a
        queue with a "delivery time"; a separate task writes it to the other
        side when its time comes. The order is never broken (just like TCP).
        """
        queue = asyncio.Queue()

        async def sender():
            while True:
                delivery_time, data = await queue.get()
                if data is None:
                    return
                wait = delivery_time - self._loop.time()
                if wait > 0:
                    await asyncio.sleep(wait)
                writer.write(data)
                await writer.drain()

        send_task = asyncio.create_task(sender())
        last_delivery = 0.0
        try:
            while data := await reader.read(65536):
                delay = max(0.0, self.delay_s + self._delay_random.uniform(-self.jitter_s, self.jitter_s))
                # Must not be delivered before the previous chunk (order is preserved)
                last_delivery = max(self._loop.time() + delay, last_delivery)
                queue.put_nowait((last_delivery, data))
            # The other side closed the connection cleanly: deliver what's queued
            queue.put_nowait((0.0, None))
            await send_task
            writer.transport.abort()
        finally:
            send_task.cancel()

    async def _cutter(self):
        """Suddenly cuts all connections at random intervals."""
        while True:
            # Exponential distribution: the standard distribution for random
            # events that happen "on average every X seconds" (e.g. failures, network drops).
            await asyncio.sleep(self._disconnect_random.expovariate(1 / self.mean_disconnect_s))
            if self._connections:
                self.disconnect_count += 1
                self._cut_all()

    def _cut_all(self):
        for client_writer, broker_writer in list(self._connections):
            # abort(): drop the connection suddenly, without "saying goodbye"
            client_writer.transport.abort()
            broker_writer.transport.abort()
