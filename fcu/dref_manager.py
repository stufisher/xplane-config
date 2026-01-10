import argparse
import binascii
import platform
import logging
import select
import socket
import struct
import time
import threading

""" X Plane UDP DREF Subscriber / Forwarder

    Related useful information:
    - https://forums.x-plane.org/forums/topic/168360-yet-another-arduino-and-udp-thread/?page=1
    - https://xppython3.readthedocs.io/en/latest/development/udp/rref.html
    - https://gist.github.com/eburlingame/30f2453061053180e8215e21b494bc5e

    From https://github.com/charlylima/XPlaneUDP/blob/master/XPlaneUdp.py
    and https://gitlab.bliesener.com/jbliesener/PiDisplay/-/blob/master/XPlaneUDP.py
"""

logger = logging.getLogger("dref manager")
logging.basicConfig(level=logging.INFO)


class XPlaneIpNotFound(Exception):
    args = "Could not find any running xplane instance in network."


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
                print("Unknown packet from " + sender[0])
                print(str(len(packet)) + " bytes")
                print(packet)
                print(binascii.hexlify(packet))

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


DREFS = {
    "citationx": [
        [b"sim/cockpit2/autopilot/airspeed_mode", 2, 1],
        [b"sim/cockpit2/autopilot/airspeed_dial_kts", 8, 2],
        [b"sim/cockpit2/autopilot/heading_mode", 2, 3],
        [b"sim/cockpit/autopilot/heading_mag", 8, 4],
        [b"sim/cockpit2/autopilot/altitude_mode", 2, 5],
        [b"sim/cockpit2/autopilot/vvi_status", 2, 6],
        [b"sim/cockpit2/autopilot/altitude_dial_ft", 8, 7],
        [b"sim/cockpit/autopilot/vertical_velocity", 8, 8],
        [b"sim/cockpit/radios/nav1_freq_hz", 8, 9],
        [b"sim/cockpit/radios/nav1_stdby_freq_hz", 8, 10],
        [b"sim/cockpit/misc/barometer_setting", 8, 11],
        [b"sim/flightmodel/controls/parkbrake", 2, 12],
        [b"sim/aircraft/parts/acf_gear_deploy[0]", 2, 13],
        [b"sim/cockpit2/autopilot/TOGA_status", 2, 14],
    ],
    "a320": [
        [b"AirbusFBW/SPDmanaged", 2, 1],
        [b"sim/cockpit2/autopilot/airspeed_dial_kts", 8, 2],
        [b"AirbusFBW/HDGmanaged", 2, 3],
        [b"sim/cockpit/autopilot/heading_mag", 8, 4],
        [b"AirbusFBW/ALTmanaged", 2, 5],
        [b"AirbusFBW/VSdashed", 2, 6],
        [b"sim/cockpit2/autopilot/altitude_dial_ft", 8, 7],
        [b"sim/cockpit/autopilot/vertical_velocity", 8, 8],
        [b"sim/cockpit/radios/com1_freq_hz", 8, 9],
        [b"sim/cockpit/radios/com1_stdby_freq_hz", 8, 10],
        [b"sim/cockpit/misc/barometer_setting", 8, 11],
        [b"sim/flightmodel/controls/parkbrake", 2, 12],
        [b"sim/aircraft/parts/acf_gear_deploy[0]", 2, 13],
        [b"sim/cockpit2/autopilot/TOGA_status", 2, 14],
    ],
}


class ClientState:
    def __init__(self):
        self._lock = threading.Lock()
        self.refresh_all = False
        self.running = True
        self.should_subscribe = True
        self.xplane_address = []

    @property
    def lock(self):
        return self._lock


if __name__ == "__main__":
    logger.info("DREF Manager Starting...")
    hostname = socket.gethostname()
    ip_addr = socket.gethostbyname(hostname)

    parser = argparse.ArgumentParser()
    parser.add_argument("-a", "--aircraft", choices=DREFS.keys(), default="a320")
    parser.add_argument("--esp-port", type=int, default=55678)
    parser.add_argument("--esp-ip", type=str, default="192.168.1.199")
    parser.add_argument("--bind-ip", type=str, default=ip_addr)

    args = parser.parse_args()

    dref_buffer = {}

    esp_sock_lock = threading.Lock()
    esp_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    esp_sock.bind((args.bind_ip, args.esp_port))

    xplane_sock_lock = threading.Lock()
    xplane_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

    client_state = ClientState()

    def subscribe(cl_state: ClientState):
        while cl_state.running:
            logger.debug(f"Subscribe thread running {cl_state.running}")
            if cl_state.should_subscribe and cl_state.xplane_address:
                logger.info(f"Subscribing for `{args.aircraft}`")
                with xplane_sock_lock:
                    for message in DREFS[args.aircraft]:
                        msg = struct.pack(
                            "<4sxii400s", b"RREF", message[1], message[2], message[0]
                        )
                        xplane_sock.sendto(msg, cl_state.xplane_address)

                with cl_state.lock:
                    cl_state.should_subscribe = False

            time.sleep(1)

    def listen_beacon(cl_state: ClientState):
        while cl_state.running:
            logger.debug(f"Beacon thread running {cl_state.running}")
            try:
                beacon = find_xp()
                with cl_state.lock:
                    if not cl_state.xplane_address:
                        logger.info("Baacon available")
                    cl_state.xplane_address = (beacon["ip"], beacon["port"])

            except XPlaneIpNotFound:
                if not cl_state.should_subscribe:
                    with cl_state.lock:
                        cl_state.should_subscribe = True
                        cl_state.xplane_address = []
        time.sleep(1)

    def listen_client(cl_state: ClientState):
        # esp_sock.setblocking(0)
        while cl_state.running:
            logger.debug(f"Client thread running {cl_state.running}")
            ready = select.select([esp_sock], [], [], 2)
            if ready:
                data1, addr1 = esp_sock.recvfrom(2048)
                logger.info("ESP: %s %s", data1, addr1)
                if data1:
                    with cl_state.lock:
                        cl_state.refresh_all = True
            else:
                time.sleep(1)

    beacon_thread = threading.Thread(target=listen_beacon, args=(client_state,))
    beacon_thread.start()

    subscribe_thread = threading.Thread(target=subscribe, args=(client_state,))
    subscribe_thread.start()

    client_thread = threading.Thread(target=listen_client, args=(client_state,))
    client_thread.start()

    try:
        while True:
            data, addr = xplane_sock.recvfrom(2048)
            header = data[:4]
            if header == b"RREF":
                dref_bytes = data[5:]
                drefs = [list(v) for v in struct.iter_unpack("<if", dref_bytes)]
                changed = []
                for dref in drefs:
                    if dref[0] == 11:
                        dref[1] *= 33.864
                    if dref[0] in [2, 4]:
                        dref[1] = round(dref[1])
                    if client_state.refresh_all:
                        changed.append(dref)
                    elif dref[0] in dref_buffer:
                        if dref[1] != dref_buffer[dref[0]]:
                            changed.append(dref)
                    else:
                        changed.append(dref)
                    dref_buffer[dref[0]] = dref[1]

                if changed:
                    bytes = b"RREF,"
                    for value in changed:
                        bytes += struct.pack("<if", value[0], value[1])
                    # print(changed)
                    esp_sock.sendto(bytes, (args.esp_ip, args.esp_port))
                    if client_state.refresh_all:
                        client_state.refresh_all = False

    except KeyboardInterrupt:
        with client_state.lock:
            client_state.running = False
        beacon_thread.join()
        subscribe_thread.join()
        client_thread.join()
