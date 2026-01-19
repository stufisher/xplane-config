# import asyncio
import base64
import logging
import time

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
    ".": "AirbusFBW/MCDU2KeyDecimal",
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

        self.__commands = {}
        self.__datarefs = {}

    async def _init(self):
        resp = await self._client.get(self._base_url + self._commands)
        if resp.status_code == 200:
            for row in resp.json()["data"]:
                self.__commands[row["name"]] = row["id"]

        resp = await self._client.get(self._base_url + self._datarefs)
        if resp.status_code == 200:
            for row in resp.json()["data"]:
                self.__datarefs[row["name"]] = {
                    "id": row["id"],
                    "type": row["value_type"],
                }

    async def get_dataref(self, dataref: str):
        dref = self.__datarefs[dataref]
        resp = await self._client.get(
            self._base_url + self._datarefs + "/" + str(dref["id"]) + "/value"
        )
        if resp.status_code == 200:
            result = resp.json()["data"]
            if dref["type"] == "data":
                result = base64.b64decode(result).decode("ascii").replace("\x00", "")
            return result

    async def set_dataref(self, dataref: str, value: any):
        if isinstance(value, str):
            value = base64.b64encode(value)

        dref = self.__datarefs[dataref]
        resp = await self._client.patch(
            self._base_url + self._datarefs + "/" + str(dref["id"]) + "/value",
            data={"data": value},
        )
        if resp.status_code == 200:
            return True

    async def execute_command(self, command: str):
        command_id = self.__commands[command]
        resp = await self._client.post(
            self._base_url + "/command/" + str(command_id) + "/activate",
            json={"duration": 0},
        )
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
    rest.read_display()
