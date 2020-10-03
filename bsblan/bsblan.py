"""Asynchronous Python client for BSB-Lan."""
import asyncio
import socket
from typing import Any, Mapping, Optional

import aiohttp
import async_timeout
from yarl import URL

from .__version__ import __version__
from .exceptions import BSBLanConnectionError, BSBLanError
from .models import Info, State


class BSBLan:
    """Main class for handling connections with BSBLan."""

    def __init__(
        self,
        host: str,
        port: int = 80,
        request_timeout: int = 10,
        session: aiohttp.client.ClientSession = None,
        username: str = None,
        password: str = None,
        passkey: str = None,
    ) -> None:
        """Initialize connection with BSBLan."""
        self._session = session
        self._close_session = False
        self.host = host
        self.port = port
        self.request_timeout = request_timeout
        self.username = username
        self.password = password
        self.passkey = passkey
        self._parameters = None

    async def _request(
        self,
        uri: str,
        method: str = "POST",
        data: Optional[dict] = None,
        params: Optional[Mapping[str, str]] = None,
    ) -> Any:
        """Handle a request to a BSBLan device."""

        base_path = "/JQ" if data is None else "/JS"
        if self.passkey is not None:
            base_path = f"/{self.passkey}{base_path}"

        url = URL.build(
            scheme="http", host=self.host, port=self.port, path=base_path,
        ).join(URL(uri))

        auth = None
        if self.username and self.password:
            auth = aiohttp.BasicAuth(self.username, self.password)

        headers = {
            "User-Agent": f"PythonBSBLan/{__version__}",
            "Accept": "application/json",  # text/plain, */*",
        }

        if self._session is None:
            self._session = aiohttp.ClientSession()
            self._close_session = True

        try:
            with async_timeout.timeout(self.request_timeout):
                response = await self._session.request(
                    method, url, auth=auth, json=data, params=params, headers=headers,
                )
                response.raise_for_status()
        except asyncio.TimeoutError as exception:
            raise BSBLanConnectionError(
                "Timeout occurred while connecting to BSBLan device."
            ) from exception
        except (
            aiohttp.ClientError,
            aiohttp.ClientResponseError,
            socket.gaierror,
        ) as exception:
            raise BSBLanConnectionError(
                "Error occurred while communicating with BSBLan device."
            ) from exception

        content_type = response.headers.get("Content-Type", "")
        if "application/json" not in content_type:
            text = await response.text()
            raise BSBLanError(
                "Unexpected response from the BSBLan device",
                {"Content-Type": content_type, "response": text},
            )

        return await response.json()

    async def scan(self):
        """Scan params that return a value."""
        # We should add parameters here using scan function.
        # By default we need a list with basic params.
        data = await self._request(uri="", params={"Parameter": "8740,710,700"})
        notValidData = []
        for k, v in data.items():
            # print(k, v)
            if not v.get("value"):
                notValidData.append(k)

        # remove parameters with no returning value
        for i in notValidData:
            data.pop(i)

        # join parameters to create one string
        parameters = []
        for i in data.keys():
            parameters.append(i)
        parameters = ",".join(parameters)

        self._parameters = parameters
        return self._parameters

    async def state(self) -> State:
        """Get the current state from BSBLan device."""

        if self._parameters is None:
            self._parameters = await self.scan()
            # return self._parameters
        parameters = self._parameters

        data = await self._request(
            "",
            params={"Parameter": f"{parameters}"},
            # construct params values with user input
        )
        return State.from_dict(data)

    async def info(self):
        """Get information about the current heating system config."""
        data = await self._request(
            "",
            params={"Parameter": "6224,6225,6226"},
            # construct params values with user input
        )
        return Info.from_dict(data)

    async def thermostat(
        self, target_temperature: Optional[str] = None, hvac_mode: Optional[str] = None,
    ) -> None:
        """Change the state of the thermostat through BSB-Lan."""

        state = {}

        if target_temperature is not None:
            state["Parameter"] = "710"
            state["Value"] = target_temperature
            state["Type"] = "1"
        if hvac_mode is not None:
            state["Parameter"] = "700"
            state["EnumValue"] = hvac_mode
            state["Type"] = "1"
        # Type needs to be 1 to really set value.
        # Now it only checks if it could set value.
        await self._request("", data=state)
        # return Thermostat.from_dict(data)

    async def close(self) -> None:
        """Close open client session."""
        if self._session and self._close_session:
            await self._session.close()

    async def __aenter__(self) -> "BSBLan":
        """Async enter."""
        return self

    async def __aexit__(self, *exc_info) -> None:
        """Async exit."""
        await self.close()
