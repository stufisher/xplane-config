import asyncio
import base64
import logging
import time
import typing

import httpx

logger = logging.getLogger(__name__)

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


class REST:
    def __init__(self):
        self._client = httpx.AsyncClient(verify=False)
        self._base_url = "http://localhost:8086/api/v2"
        self._commands = "/commands"
        self._datarefs = "/datarefs"

        self.__commands: dict[str, int] = {}
        self.__datarefs: dict[str, dict[str, any]] = {}

        self._xplane_running = False

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
                self.__commands = []
                self.__datarefs = []
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
    ):
        if not self._xplane_running:
            await self.resolve_rest()
            if not self._xplane_running:
                logger.info("X-Plane REST API not available after retry")
                return

        type_dict = self.__datarefs if item_type == "dataref" else self.__commands
        try:
            return type_dict[identifier]
        except KeyError:
            logger.info("X-Plane running but not all datrefs available yet")
            await self.resolve_rest()
            try:
                return type_dict[identifier]
            except Exception:
                logger.warning(f"Could not resolve {item_type} {identifier} after retry")
                return

    async def get_dataref(self, dataref: str):
        dref = await self._resolve(dataref)
        if not dref:
            return

        try:
            resp = await self._request(
                "get",
                f"{self._base_url}{self._datarefs}/{dref['id']}/value",
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
        dref = await self._resolve(dataref)
        if not dref:
            return

        if isinstance(value, str):
            value = base64.b64encode(value)
        try:
            resp = await self._request(
                "patch",
                f"{self._base_url}{self._datarefs}/{dref['id']}/value",
                json={"data": value},
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
    rest = REST()
    # rest.clear_scratchpad()
    # rest.write_scratchpad("LOWS/LSGG")
    # rest.press_button("1R")
    loop = asyncio.new_event_loop()

    async def moo():
        await rest._init()
        # value = await rest.get_dataref("sim/time/zulu_time_sec")
        # print(value)
        # await rest.set_dataref("toliss_airbus/performance/VR", 145)
        # value = await rest.get_dataref("toliss_airbus/init/ZFW")
        # value = await rest.get_dataref("sim/flightmodel/weight/m_total")
        # value = await rest.get_dataref("sim/flightmodel2/misc/cg_offset_z")
        # value = await rest.get_dataref("sim/flightmodel2/misc/cg_offset_z_mac")
        value = await rest.get_dataref("AirbusFBW/MCDU1spw")
        print(value, value is None)

    loop.run_until_complete(moo())
