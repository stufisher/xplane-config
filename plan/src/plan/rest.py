import asyncio
import base64
import json
import logging
import os
import re
import signal
import time
import typing

import httpx
import websockets
from websockets.asyncio.client import connect

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

# os.environ["WEBSOCKETS_BACKOFF_FACTOR"] = "1"

BUTTON_MAP = {
    "FPLN": "AirbusFBW/MCDU1Fpln",
    "INIT": "AirbusFBW/MCDU1Init",
    "PERF": "AirbusFBW/MCDU1Perf",
    "CLR": "AirbusFBW/MCDU1KeyClear",
}

NAV_MAP = {
    "UP": "AirbusFBW/MCDU1SlewUp",
    "DOWN": "AirbusFBW/MCDU1SlewDown",
    "LEFT": "AirbusFBW/MCDU1SlewLeft",
    "RIGHT": "AirbusFBW/MCDU1SlewRight",
}

LRMAP = {
    "1L": "AirbusFBW/MCDU1LSK1L",
    "2L": "AirbusFBW/MCDU1LSK2L",
    "3L": "AirbusFBW/MCDU1LSK3L",
    "4L": "AirbusFBW/MCDU1LSK4L",
    "5L": "AirbusFBW/MCDU1LSK5L",
    "6L": "AirbusFBW/MCDU1LSK6L",
    "1R": "AirbusFBW/MCDU1LSK1R",
    "2R": "AirbusFBW/MCDU1LSK2R",
    "3R": "AirbusFBW/MCDU1LSK3R",
    "4R": "AirbusFBW/MCDU1LSK4R",
    "5R": "AirbusFBW/MCDU1LSK5R",
    "6R": "AirbusFBW/MCDU1LSK6R",
}

CHARACTER_MAP = {
    "/": "AirbusFBW/MCDU1KeySlash",
    ".": "AirbusFBW/MCDU1KeyDecimal",
    " ": "AirbusFBW/MCDU1KeySpace",
    "KEY": "AirbusFBW/MCDU1Key",
}

CONTENT = [
    "AirbusFBW/MCDU1cont1",
    "AirbusFBW/MCDU1cont2",
    "AirbusFBW/MCDU1cont3",
    "AirbusFBW/MCDU1cont4",
    "AirbusFBW/MCDU1cont5",
    "AirbusFBW/MCDU1cont6",
]


def get_dref_and_index(dataref: str):
    dref_and_opts = dataref.split(",")
    match = re.search(r"\[(\d+)\]", dref_and_opts[0])
    if match:
        dref_key = re.sub(r"\[\d+\]", "", dref_and_opts[0])
        index = match.group(1)
        return dref_key, index

    return dataref, None


class REST:
    def __init__(self, on_drefs_changed: callable = None):
        self._client = httpx.AsyncClient(verify=False)
        self._base_url = "http://localhost:8086/api/v3"
        self._commands = "/commands"
        self._datarefs = "/datarefs"

        self.__commands: dict[str, int] = {}
        self.__datarefs: dict[str, dict[str, any]] = {}

        self._dataref_cache = {}
        self._websocket_running = True
        self._websocket = None
        self._on_drefs_changed = on_drefs_changed

        self._xplane_running = False
        self._xplane_ready = False

    async def _init(self):
        await self.resolve_rest()

    async def resolve_rest(self):
        self._xplane_running = False
        try:
            success = True
            resp = await self._client.get(self._base_url + self._commands)
            if resp.status_code == 200:
                for row in resp.json()["data"]:
                    self.__commands[row["name"]] = row["id"]
            else:
                success = False

            resp = await self._client.get(self._base_url + self._datarefs)
            if resp.status_code == 200:
                for row in resp.json()["data"]:
                    self.__datarefs[row["name"]] = {
                        "id": row["id"],
                        "type": row["value_type"],
                    }
            else:
                success = False
            if success:
                self._xplane_running = True
                logger.info("Initialilsed REST mapping")
            else:
                logger.info("Error initialising REST mapping")
        except Exception:
            if self._xplane_running:
                logger.warning("X-Plane is offline")
                self.__commands = {}
                self.__datarefs = {}
            self._xplane_running = False

    @property
    def online(self):
        return self._xplane_running

    async def _request(
        self, method: typing.Literal["get", "post", "patch"], *args, **kwargs
    ):
        if method == "get":
            client_method = self._client.get
        elif method == "post":
            client_method = self._client.post
        else:
            client_method = self._client.patch
        try:
            resp = await client_method(*args, **kwargs)
            return resp
        except httpx.ReadTimeout:
            logger.info("Timeout waiting for REST API")
            raise
        except Exception as err:
            logger.info(f"Error getting response from REST API {err}")
            raise

    async def _resolve(
        self,
        identifier: str,
        item_type: typing.Literal["dataref", "command"] = "dataref",
        should_raise=False,
    ):
        if not self._xplane_running:
            await self.resolve_rest()
            if not self._xplane_running:
                logger.info("X-Plane REST API not available after retry")
                if should_raise:
                    raise KeyError("X-Plane REST API not available")
                return

        type_dict = self.__datarefs if item_type == "dataref" else self.__commands
        try:
            return type_dict[identifier]
        except KeyError:
            logger.info("X-Plane running but not all datrefs available yet")
            if should_raise:
                raise
            await self.resolve_rest()
            try:
                return type_dict[identifier]
            except Exception:
                logger.warning(
                    f"Could not resolve {item_type} {identifier} after retry"
                )
                return

    async def get_dataref(self, dataref: str):
        dref, index = get_dref_and_index(dataref)
        dref = await self._resolve(dref)
        if not dref:
            return

        extra_params = {}
        if index is not None:
            extra_params["index"] = index

        try:
            resp = await self._request(
                "get",
                f"{self._base_url}{self._datarefs}/{dref['id']}/value",
                params=extra_params,
            )
        except Exception:
            self._xplane_running = False
            return
        if resp.status_code == 200:
            result = resp.json()["data"]
            if dref["type"] == "data":
                result = base64.b64decode(result).decode("ascii").replace("\x00", "")
            return result

    async def set_dataref(self, dataref: str, value: any):
        dref, index = get_dref_and_index(dataref)
        dref = await self._resolve(dref)
        if not dref:
            return

        extra_params = {}
        if index is not None:
            extra_params["index"] = index

        if isinstance(value, str):
            value = base64.b64encode(value)
        try:
            resp = await self._request(
                "patch",
                f"{self._base_url}{self._datarefs}/{dref['id']}/value",
                json={"data": value},
                params=extra_params,
            )
        except Exception:
            self._xplane_running = False
            return
        if resp.status_code == 200:
            return True
        else:
            raise RuntimeError(f"{resp.status_code}: {resp.json()}")

    async def execute_command(self, command: str, duration: int = 0):
        command_id = await self._resolve(command, item_type="command")
        if not command_id:
            return

        try:
            resp = await self._request(
                "post",
                f"{self._base_url}/command/{command_id}/activate",
                json={"duration": duration},
            )
        except Exception:
            self._xplane_running = False
            return
        if resp.status_code == 200:
            return True
        return False

    def set_subscribed_drefs(self, drefs: list[str]):
        drefs.sort()
        self._dref_cache = {key: None for key in drefs}

    def _get_dref_by_id_and_index(self, id: int, index: int = 0):
        dataref = None
        for dref, dref_details in self.__datarefs.items():
            if dref_details["id"] == id:
                dataref = dref

        if not dataref:
            logger.warning(f"No dref for id: {id} index: {index}")
            return
        matched_drefs = []
        for dref in self._dref_cache.keys():
            if dataref in dref:
                matched_drefs.append(dref)
        return matched_drefs[index]

    async def _subscribe(self):
        dref_by_root = {}
        for dref in self._dref_cache.keys():
            dref_and_opts = dref.split(",")
            match = re.search(r"\[(\d+)\]", dref_and_opts[0])
            if match:
                dref_key = re.sub(r"\[\d+\]", "", dref_and_opts[0])
                if dref_key not in dref_by_root:
                    dref_by_root[dref_key] = []
                dref_by_root[dref_key].append(int(match.group(1)))
            else:
                dref_by_root[dref_and_opts[0]] = []

        datarefs = []
        for dref, indexes in dref_by_root.items():
            resolved = await self._resolve(dref, should_raise=True)
            request = {"id": resolved["id"]}
            if indexes:
                request["index"] = indexes
            datarefs.append(request)

        message = json.dumps(
            {
                "req_id": 1234,
                "type": "dataref_subscribe_values",
                "params": {"datarefs": datarefs},
            }
        )
        await self._websocket.send(message)
        self._xplane_ready = True

    def _update_dref_cache(self, dref_key: str, value: int):
        dref_opts = dref_key.split(",")
        if len(dref_opts) > 1:
            value = round(value, int(dref_opts[1]))

        current_value = self._dref_cache[dref_key]
        changed = {}
        if current_value != value:
            self._dref_cache[dref_key] = value
            changed[dref_key] = value
            # print(dref_key, value)

        if changed:
            if self._on_drefs_changed:
                self._on_drefs_changed(changed)

    def _parse_socket_response(self, data: dict[str, any]):
        if data["type"] == "dataref_update_values":
            for id, values in data["data"].items():
                if isinstance(values, list):
                    for idx, value in enumerate(values):
                        dref_key = self._get_dref_by_id_and_index(int(id), idx)
                        self._update_dref_cache(dref_key, value)

                else:
                    dref_key = self._get_dref_by_id_and_index(int(id))
                    self._update_dref_cache(dref_key, values)

    async def socket_client(self):
        url = self._base_url.replace("http://", "ws://")
        logger.info("Starting socket client")
        async for websocket in connect(url):
            try:
                logger.info("Websocket connected")
                self._websocket = websocket
                while not self._xplane_ready:
                    try:
                        await self.resolve_rest()
                        await self._subscribe()
                    except KeyError:
                        await asyncio.sleep(5)
                        logger.info("Waiting for subscribe retry")

                while self._websocket_running:
                    message = await websocket.recv()
                    self._parse_socket_response(json.loads(message))
                    await asyncio.sleep(0)
            except websockets.exceptions.ConnectionClosed:
                logger.warning("Reconnecting to socket")
                self.__datarefs = {}
                self.__commands = {}
                self._xplane_running = False
                self._xplane_ready = False
                continue

    def get_dref_value(self, dref: str):
        if isinstance(dref, list):
            return [self._dref_cache.get(d) for d in dref]
        return self._dref_cache.get(dref)

    async def clear_scratchpad(self):
        current = await self.get_dataref("AirbusFBW/MCDU1spw")
        for _ in range(len(current)):
            await self.execute_command(BUTTON_MAP["CLR"])

    async def write_scratchpad(self, text: str):
        await self.clear_scratchpad()
        for char in text:
            if char in CHARACTER_MAP:
                await self.execute_command(CHARACTER_MAP[char])
            else:
                await self.execute_command(CHARACTER_MAP["KEY"] + char)

    async def press_button(self, button: str):
        if button in LRMAP:
            await self.execute_command(LRMAP[button])
            return

        if button in NAV_MAP:
            await self.execute_command(NAV_MAP[button])
            return

        if button in BUTTON_MAP:
            await self.execute_command(BUTTON_MAP[button])
            return

        logger.warning(f"Could not find button `{button}`")

    async def read_display(self, color="b"):
        lines = []
        for dataref in CONTENT:
            lines.append(await self.get_dataref(dataref + color))

        # print(lines)
        return lines

    async def find_row_in_display(
        self,
        text: str,
        color="b",
        secondary=None,
        direction="UP",
        iterate=True,
        timeout=5,
    ):
        start_time = time.time()
        found = False
        last_lines = []
        while not found:
            lines = await self.read_display(color=color)
            if secondary is not None:
                secondary_lines = await self.read_display(color=secondary)
                for i, secondary_line in enumerate(secondary_lines):
                    lines[i] += secondary_line
            if lines == last_lines:
                return
            for line_id, line in enumerate(lines):
                # print(line_id, line, text, text in line)
                if text in line:
                    found = True
                    return line_id

            if not iterate:
                return
            await self.press_button(direction)
            last_lines = lines
            # print("iterate")
            # await asyncio.sleep(0.5)
            if (time.time() - start_time) > timeout:
                logger.warning(f"Timeout searching for `{text}`")
                return

    async def shutdown(self):
        await self._client.aclose()
        logger.info("REST: Shutdown")


if __name__ == "__main__":

    def on_drefs_changed(drefs):
        print("drefs", drefs)

    rest = REST(on_drefs_changed=on_drefs_changed)
    # rest.clear_scratchpad()
    # rest.write_scratchpad("LOWS/LSGG")
    # rest.press_button("1R")
    loop = asyncio.new_event_loop()

    async def moo():
        await rest._init()
        rest.set_subscribed_drefs(
            [
                "sim/cockpit/autopilot/heading_mag",
                "AirbusFBW/BrakeTemperatureArray[1],0",
                "AirbusFBW/BrakeTemperatureArray[0],0",
                "sim/time/zulu_time_sec,0",
            ]
        )
        loop.create_task(rest.socket_client())
        # value = await rest.get_dataref("sim/time/zulu_time_sec")
        # print(value)
        # await rest.set_dataref("toliss_airbus/performance/VR", 145)
        # value = await rest.get_dataref("toliss_airbus/init/ZFW")
        # value = await rest.get_dataref("sim/flightmodel/weight/m_total")
        # value = await rest.get_dataref("sim/flightmodel2/misc/cg_offset_z")
        # value = await rest.get_dataref("sim/flightmodel2/misc/cg_offset_z_mac")
        value = await rest.get_dataref("AirbusFBW/MCDU1spw")
        print(value, value is None)
        while 1:
            await asyncio.sleep(1)

    loop.run_until_complete(moo())
