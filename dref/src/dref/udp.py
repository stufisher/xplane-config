import binascii
import platform
import logging
import select
import socket
import struct
import time
import threading

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)


class XPlaneIpNotFound(Exception):
    args = "Could not find any running X Plane instance on the network."


def find_xp(wait: float = 3.0):
    MCAST_GRP = "239.255.1.1"
    MCAST_PORT = 49707

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    if platform.system() == "Windows":
        sock.bind(("", MCAST_PORT))
    else:
        sock.bind((MCAST_GRP, MCAST_PORT))
    mreq = struct.pack("=4sl", socket.inet_aton(MCAST_GRP), socket.INADDR_ANY)
    sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mreq)

    if wait > 0:
        sock.settimeout(wait)

    beacon_data = {}
    while not beacon_data:
        try:
            packet, sender = sock.recvfrom(15000)
            header = packet[0:5]
            if header != b"BECN\x00":
                logging.info("Unknown packet from " + sender[0])
                logging.info(str(len(packet)) + " bytes")
                logging.info(packet)
                logging.info(binascii.hexlify(packet))

            else:
                data = packet[5:21]
                (
                    beacon_major_version,
                    beacon_minor_version,
                    application_host_id,
                    xplane_version_number,
                    role,
                    port,
                ) = struct.unpack("<BBiiIH", data)

                computer_name = packet[21:]
                computer_name = computer_name.split(b"\x00")[0]
                (raknet_port,) = struct.unpack("<H", packet[-2:])

                if all(
                    [
                        beacon_major_version == 1,
                        beacon_minor_version == 2,
                        application_host_id == 1,
                    ]
                ):
                    beacon_data = {
                        "ip": sender[0],
                        "port": port,
                        "hostname": computer_name.decode("utf-8"),
                        "xplane_version": xplane_version_number,
                        "role": role,
                        "raknet_port": raknet_port,
                    }

        except socket.timeout:
            raise XPlaneIpNotFound()

    sock.close()
    return beacon_data


class UDP:
    def __init__(self, drefs: list[str], on_drefs_changed: callable):
        self._state_lock = threading.Lock()
        self._xplane_socket_lock = threading.Lock()
        self._xplane_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

        self._xplane_address = []
        self._running = True
        self._should_subscribe = True
        self._refresh_all = False

        self._dref_buffer = {key: None for key in drefs}
        self._on_drefs_changed = on_drefs_changed

        self.beacon_thread = threading.Thread(target=self.beacon_task)
        self.beacon_thread.daemon = True
        self.beacon_thread.start()

        self.subscribe_thread = threading.Thread(target=self.subscribe_task)
        self.subscribe_thread.daemon = True
        self.subscribe_thread.start()

        self.parse_thread = threading.Thread(target=self.parse_datarefs_task)
        self.parse_thread.daemon = True
        self.parse_thread.start()

    def close(self):
        with self._state_lock:
            self._running = False

        logger.info("joining threads")
        self.beacon_thread.join()
        self.subscribe_thread.join()
        self.parse_thread.join()

        self._subscribe(0)

    def get_dref_value(self, dref: str | list[str]):
        if isinstance(dref, list):
            return [self._dref_buffer.get(d) for d in dref]
        return self._dref_buffer.get(dref)

    @property
    def lock(self):
        return self._state_lock

    @property
    def socket_lock(self):
        return self._xplane_socket_lock

    @property
    def running(self):
        with self._state_lock:
            return self._running

    def beacon_task(self):
        while self.running:
            logger.debug("Beacon thread running")
            try:
                beacon = find_xp()
                with self._state_lock:
                    if not self._xplane_address:
                        logger.info("Baacon available")
                    self._xplane_address = (beacon["ip"], beacon["port"])

            except XPlaneIpNotFound:
                logger.info("X-Plane not found")
                with self.lock:
                    if not self._should_subscribe:
                        self._should_subscribe = True
                        self._xplane_address = []
            time.sleep(1)
        logger.info("beacon task ended")

    def _subscribe(self, interval: int = 3):
        with self.socket_lock:
            for dref_id, dref in enumerate(self._dref_buffer.keys()):
                dref_and_opts = dref.split(",")
                msg = struct.pack(
                    "<4sxii400s",
                    b"RREF",
                    interval,
                    dref_id,
                    dref_and_opts[0].encode("utf-8"),
                )
                self._xplane_socket.sendto(msg, self._xplane_address)

    def subscribe_task(self):
        while self.running:
            logger.debug("Subscribe thread running")
            with self._state_lock:
                if self._should_subscribe and self._xplane_address:
                    logger.info("Subscribing to drefs")
                    self._subscribe()
                    self._should_subscribe = False

            time.sleep(1)
        logger.info("subscribe task ended")

    def parse_datarefs_task(self):
        dref_lookup = list(self._dref_buffer.keys())
        while self.running:
            ready_to_read, _, _ = select.select([self._xplane_socket], [], [], 1)
            if ready_to_read:
                data, addr = ready_to_read[0].recvfrom(2048)
                header = data[:4]
                if header == b"RREF":
                    dref_bytes = data[5:]
                    drefs = [list(v) for v in struct.iter_unpack("<if", dref_bytes)]
                    changed = {}
                    for dref in drefs:
                        dref_key = dref_lookup[dref[0]]
                        if dref_key in self._dref_buffer:
                            dref_opts = dref_key.split(",")
                            if len(dref_opts) > 1:
                                dref[1] = round(dref[1], int(dref_opts[1]))
                            if dref[1] != self._dref_buffer[dref_key]:
                                changed[dref_key] = dref[1]
                        else:
                            changed[dref_key] = dref[1]
                        self._dref_buffer[dref_key] = dref[1]

                    if changed:
                        if self._on_drefs_changed:
                            self._on_drefs_changed(changed)

                    if self._refresh_all:
                        logger.info("Refresh all")
                        if self._on_drefs_changed:
                            self._on_drefs_changed(self._dref_buffer)
                        with self._state_lock:
                            self._refresh_all = False
        logger.info("parse task ended")

    def set_dref(self, dref: str, value: any):
        msg = struct.pack("<4sxf500s", b"DREF", value, dref.encode("utf-8"))
        print("set dref", dref, value)
        with self.socket_lock:
            self._xplane_socket.sendto(msg, self._xplane_address)

    def execute_command(self, command: str):
        msg = struct.pack("<4sx500s", b"CMND", command.encode("utf-8"))
        with self.socket_lock:
            self._xplane_socket.sendto(msg, self._xplane_address)


if __name__ == "__main__":
    try:

        def on_dref_changed(drefs: dict[str, any]):
            print("drefs", drefs)

        drefs = [
            # "AirbusFBW/APUBleedSwitch",
            # "AirbusFBW/APUMaster",
            # "AirbusFBW/APUAvail",
            # "AirbusFBW/APUStarter",
            # "AirbusFBW/OHPLightsATA28_Raw[5]",
            # "AirbusFBW/OHPLightsATA28_Raw[6]", # RTXF OFF
            # "AirbusFBW/OHPLightsATA28_Raw[7]",
            # "AirbusFBW/OHPLightsATA28_Raw[8]",
            # "AirbusFBW/OHPLightsATA28_Raw[9]",
            "AirbusFBW/OHPLightsATA28_Raw[14]",
            "AirbusFBW/OHPLightsATA28_Raw[15]",
        ]

        udp = UDP(drefs, on_dref_changed)

        while 1:
            time.sleep(1)

    except KeyboardInterrupt:
        pass
