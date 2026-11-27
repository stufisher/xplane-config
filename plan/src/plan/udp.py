import asyncio
import logging
import random
import struct
import time

from .apt import APT


logger = logging.getLogger(__name__)

XPLANE_UDP_PORT = 49000
# Updates per second requested for each subscribed dataref
RREF_FREQUENCY = 5
# No packet for this long means X-Plane is gone, and subscriptions are resent
# so they come back after a sim restart
STALE_S = 5


class _Protocol(asyncio.DatagramProtocol):
    def __init__(self, on_packet: callable):
        self._on_packet = on_packet

    def datagram_received(self, data, addr):
        self._on_packet(data)


class UDP:
    """X-Plane's UDP interface: dataref subscriptions (RREF) and moving the
    aircraft (PREL)"""

    def __init__(
        self, apt: APT, host: str = "localhost", on_drefs_changed: callable = None
    ):
        self._apt = apt
        self._address = (host, XPLANE_UDP_PORT)
        self._on_drefs_changed = on_drefs_changed
        self._transport = None
        self._running = True
        self._last_packet = 0
        # Subscription keys as given, e.g. "sim/time/zulu_time_sec,0", in
        # RREF index order
        self._drefs: list[str] = []
        self._dref_cache = {}

    async def _ensure_transport(self):
        if self._transport is None:
            loop = asyncio.get_running_loop()
            self._transport, _ = await loop.create_datagram_endpoint(
                lambda: _Protocol(self._on_packet), local_addr=("0.0.0.0", 0)
            )

    def send(self, msg: bytes):
        self._transport.sendto(msg, self._address)

    @property
    def online(self):
        return time.monotonic() - self._last_packet < STALE_S

    def set_subscribed_drefs(self, drefs: list[str]):
        self._drefs = sorted(drefs)
        self._dref_cache = {key: None for key in self._drefs}

    def get_dref_value(self, dref: str):
        if isinstance(dref, list):
            return [self._dref_cache.get(d) for d in dref]
        return self._dref_cache.get(dref)

    def _send_subscriptions(self, frequency: int):
        for index, dref in enumerate(self._drefs):
            name = dref.split(",")[0]
            self.send(
                struct.pack(
                    "<4sxii400s", b"RREF", frequency, index, name.encode("utf-8")
                )
            )

    def _on_packet(self, data: bytes):
        if data[:4] != b"RREF":
            return
        self._last_packet = time.monotonic()
        changed = {}
        payload = data[5:]
        payload = payload[: len(payload) // 8 * 8]
        for index, value in struct.iter_unpack("<if", payload):
            if not 0 <= index < len(self._drefs):
                continue
            dref = self._drefs[index]
            opts = dref.split(",")
            if len(opts) > 1:
                value = round(value, int(opts[1]))
            if self._dref_cache[dref] != value:
                self._dref_cache[dref] = value
                changed[dref] = value
        if changed and self._on_drefs_changed:
            self._on_drefs_changed(changed)

    async def socket_client(self):
        """Keep the subscriptions alive, resending them while X-Plane is silent"""
        await self._ensure_transport()
        logger.info(f"Subscribing to {len(self._drefs)} datarefs over UDP")
        was_online = False
        while self._running:
            if not self.online:
                if was_online:
                    logger.warning("X-Plane UDP is offline")
                self._send_subscriptions(RREF_FREQUENCY)
            elif not was_online:
                logger.info("X-Plane UDP connected")
            was_online = self.online
            await asyncio.sleep(STALE_S)

    async def move_aircraft_to_runway(self, icao_code: str, runway: str):
        await self._ensure_transport()
        logger.info(f"Finding airport info for {icao_code} {runway}")
        runway_details = await self._apt.get_runway_idx_dir(icao_code, runway)
        logger.info(f"Moving aircraft to {icao_code} {runway}")
        msg = struct.pack(
            "<4sxii8siiddddd",
            b"PREL",
            11,
            0,
            icao_code.encode("utf-8"),
            runway_details.rwy_idx,
            runway_details.rwy_dir,
            0,
            0,
            0,
            1,
            0,
        )

        self.send(msg)

    async def move_aircraft_to_gate(self, icao_code: str, gate_name: str = None):
        await self._ensure_transport()
        logger.info(
            f"Finding airport info for {icao_code} {gate_name if gate_name else 'and selecting random gate'}"
        )
        ramps = await self._apt.get_ramps(icao_code)
        if gate_name:
            ramp = ramps[gate_name]
        else:
            ramp = random.choice(list(ramps.values()))
        logger.info(f"Moving aircraft to {icao_code} {ramp.name}")

        msg = struct.pack(
            "<4sxii8siiddddd",
            b"PREL",
            10,
            0,
            icao_code.encode("utf-8"),
            ramp.ramp_idx,
            0,
            0,
            0,
            0,
            1,
            0,
        )

        self.send(msg)

    async def shutdown(self):
        self._running = False
        if self._transport is not None:
            # Frequency 0 stops X-Plane sending
            self._send_subscriptions(0)
            self._transport.close()
        logger.info("UDP: Shutdown")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    async def main():
        udp = UDP(APT(), on_drefs_changed=print)
        udp.set_subscribed_drefs(
            ["sim/time/zulu_time_sec,0", "sim/flightmodel/position/latitude,3"]
        )
        await udp.socket_client()

    asyncio.run(main())
