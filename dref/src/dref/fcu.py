import logging
import select
import socket
import struct
import time
import threading

from .udp import UDP

logger = logging.getLogger(__name__)

FCU_DREFS = [
    ["AirbusFBW/SPDmanaged", 1],
    ["sim/cockpit2/autopilot/airspeed_dial_kts", 2],
    ["AirbusFBW/HDGmanaged", 3],
    ["sim/cockpit/autopilot/heading_mag", 4],
    ["AirbusFBW/ALTmanaged", 5],
    ["AirbusFBW/VSdashed", 6],
    ["sim/cockpit2/autopilot/altitude_dial_ft", 7],
    ["sim/cockpit/autopilot/vertical_velocity", 8],
    ["sim/cockpit/radios/com1_freq_hz", 9],
    ["sim/cockpit/radios/com1_stdby_freq_hz", 10],
    ["sim/cockpit/misc/barometer_setting", 11],
    ["sim/flightmodel/controls/parkbrake", 12],
    ["sim/aircraft/parts/acf_gear_deploy[0]", 13],
    ["sim/cockpit2/autopilot/TOGA_status", 14],
]


class FCU:
    def __init__(self, ip: str = "192.168.1.199", port: int = 55678):
        self._udp: UDP = None
        self._esp_ip = ip
        self._esp_port = port

        self._esp_sock_lock = threading.Lock()
        self._esp_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

        self._running = True
        self.listen_thread = threading.Thread(target=self.listen_esp_task)
        self.listen_thread.daemon = True
        self.listen_thread.start()

    def get_drefs(self):
        return [dref[0] for dref in FCU_DREFS]

    @property
    def udp(self):
        return self._udp

    @udp.setter
    def udp(self, value: UDP):
        self._udp = value

    def close(self):
        with self._esp_sock_lock:
            self._running = False

        self.listen_thread.join()

    def on_drefs_changed(self, drefs: dict[str, any]):
        logger.info("dref changed", drefs)
        self.send_drefs(drefs.keys())

    def find_dref(self, dref: str):
        for fcu_dref in FCU_DREFS:
            if dref == fcu_dref[0]:
                return fcu_dref

    def send_drefs(self, drefs):
        msg = b"RREF,"
        for dref in drefs:
            dref_details = self.find_dref(dref)
            value = self._udp.get_dref_value(dref)
            if dref == "sim/cockpit/misc/barometer_setting":
                value *= 33.864
            msg += struct.pack("<if", dref_details[2], value)
        self._esp_sock.sendto(msg, (self._esp_ip, self._esp_port))

    def refresh_all(self):
        logger.info("Refreshing all drefs")
        self.send_drefs(self.get_drefs())

    def listen_esp_task(self):
        while self._running:
            try:
                hostname = socket.gethostname()
                ip_addr = socket.gethostbyname(hostname)
                self._esp_sock.bind((ip_addr, self._esp_port))

                while self._running:
                    ready_to_read, _, _ = select.select([self._esp_sock], [], [], 2)
                    if ready_to_read:
                        data1, addr1 = ready_to_read[0].recvfrom(2048)
                        logger.info("ESP: %s %s", data1, addr1)
                        if data1:
                            with self._esp_sock_lock:
                                self.refresh_all()
                    else:
                        time.sleep(1)
            except Exception as e:
                logger.exception(f"Could not listen to fcu: {str(e)}")
                time.sleep(1)

        logger.info("listen task ended")


if __name__ == "__main__":
    try:

        def on_dref_changed(drefs: dict[str, any]):
            fcu.on_drefs_changed(drefs)

        fcu = FCU()
        udp = UDP(drefs=fcu.get_drefs(), on_drefs_changed=on_dref_changed)
        fcu.udp = udp

        while 1:
            time.sleep(1)

    except KeyboardInterrupt:
        fcu.close()
        udp.close()
