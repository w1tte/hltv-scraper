import httpx
from typing import Dict, Any, Optional

from .exceptions import TwoCaptchaError


class GetBalance:
    """Handle getBalance API endpoint."""

    def __init__(
        self,
        api_key: str,
        base_url: str,
        client: httpx.Client,
        async_client: Optional[httpx.AsyncClient] = None,
    ):
        """
        Initialize GetBalance handler.

        Args:
            api_key: TwoCaptcha API key
            base_url: API base URL
            client: httpx client for sync calls
            async_client: httpx async client for async calls
        """
        self.api_key = api_key
        self.base_url = base_url
        self.client = client
        self.async_client = async_client
        self.endpoint = "/getBalance"

    def _make_request(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        Make synchronous HTTP request.

        Args:
            payload: Request payload

        Returns:
            API response data

        Raises:
            TwoCaptchaError: If request fails
        """
        try:
            response = self.client.post(
                f"{self.base_url}{self.endpoint}", json=payload, timeout=30
            )
            response.raise_for_status()
            result = response.json()

            if result.get("errorId") != 0:
                error_id = result.get("errorId")
                error_desc = result.get("errorDescription", "Unknown error")
                raise TwoCaptchaError(
                    f"API Error {error_id}: {error_desc}",
                    error_id=error_id,
                    error_code=str(error_id),
                )

            return result

        except httpx.RequestError as e:
            raise TwoCaptchaError(f"Request failed: {str(e)}")
        except ValueError as e:
            raise TwoCaptchaError(f"Invalid JSON response: {str(e)}")

    async def _make_async_request(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        Make asynchronous HTTP request.

        Args:
            payload: Request payload

        Returns:
            API response data

        Raises:
            TwoCaptchaError: If request fails
        """
        if self.async_client is None:
            raise TwoCaptchaError("Async client not initialized")

        try:
            response = await self.async_client.post(
                f"{self.base_url}{self.endpoint}", json=payload, timeout=30
            )
            response.raise_for_status()
            result = response.json()

            if result.get("errorId") != 0:
                error_id = result.get("errorId")
                error_desc = result.get("errorDescription", "Unknown error")
                raise TwoCaptchaError(
                    f"API Error {error_id}: {error_desc}",
                    error_id=error_id,
                    error_code=str(error_id),
                )

            return result

        except httpx.RequestError as e:
            raise TwoCaptchaError(f"Request failed: {str(e)}")
        except ValueError as e:
            raise TwoCaptchaError(f"Invalid JSON response: {str(e)}")

    def get_balance(self) -> Dict[str, Any]:
        """
        Get account balance (sync).

        Returns:
            Balance information

        Raises:
            TwoCaptchaError: If API request fails
        """
        payload = {"clientKey": self.api_key}
        return self._make_request(payload)

    async def get_balance_async(self) -> Dict[str, Any]:
        """
        Get account balance (async).

        Returns:
            Balance information

        Raises:
            TwoCaptchaError: If API request fails
        """
        payload = {"clientKey": self.api_key}
        return await self._make_async_request(payload)
