import logging
import random
import socket
import struct

from .apt import APT


logger = logging.getLogger(__name__)


class UDP:
    def __init__(self, apt: APT):
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._apt = apt

    def send(self, msg):
        self._sock.sendto(msg, ("192.168.1.100", 49000))

    def move_aircraft_to_runway(self, icao_code: str, runway: str):
        logger.info(f"Finding airport info for {icao_code} {runway}")
        runway_details = self._apt.get_runway_idx_dir(icao_code, runway)
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

    def move_aircraft_to_gate(self, icao_code: str, gate_name: str = None):
        logger.info(
            f"Finding airport info for {icao_code} {gate_name if gate_name else 'and selecting random gate'}"
        )
        ramps = self._apt.get_ramps(icao_code)
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


if __name__ == "__main__":
    udp = UDP()
    udp.move_aircraft("LFPO", "RW07")
