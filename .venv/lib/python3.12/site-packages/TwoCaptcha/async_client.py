import httpx
import asyncio
from typing import Dict, Any, Optional

from .create_task import CreateTask
from .get_task_result import GetTaskResult
from .get_balance import GetBalance
from .exceptions import TwoCaptchaError


class BaseClient:
    """Base client with shared functionality."""

    BASE_URL = "https://api.2captcha.com"

    def __init__(self, api_key: str, timeout: int = 120, polling_interval: int = 5):
        """
        Initialize base client.

        Args:
            api_key: Your TwoCaptcha API key
            timeout: Maximum time to wait for task completion in seconds
            polling_interval: Time between result checks in seconds
        """
        self.api_key = api_key
        self.timeout = timeout
        self.polling_interval = polling_interval


class AsyncClient(BaseClient):
    """Asynchronous TwoCaptcha client."""

    def __init__(self, api_key: str, timeout: int = 120, polling_interval: int = 5):
        """
        Initialize async client.

        Args:
            api_key: Your TwoCaptcha API key
            timeout: Maximum time to wait for task completion in seconds
            polling_interval: Time between result checks in seconds
        """
        super().__init__(api_key, timeout, polling_interval)
        self._async_client: Optional[httpx.AsyncClient] = None

    async def _ensure_async_client(self):
        """Ensure async client is initialized."""
        if self._async_client is None:
            self._async_client = httpx.AsyncClient()

    async def create_task(
        self,
        task: Dict[str, Any],
        language_pool: str = "en",
        callback_url: Optional[str] = None,
        soft_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Create a new captcha recognition task.

        Args:
            task: Task configuration dictionary
            (required)

            language_pool: Worker language pool ("en" or "rn")
            (optional)

            callback_url: Optional callback URL for results
            (optional)

            soft_id: Optional software ID
            (optional)

        Returns:
            Task creation response with taskId

        Raises:
            TwoCaptchaError: If API request fails
        """
        await self._ensure_async_client()

        create_task_module = CreateTask(
            self.api_key, self.BASE_URL, None, self._async_client
        )
        return await create_task_module.create_task_async(
            task, language_pool, callback_url, soft_id
        )

    async def get_task_result(self, task_id: int) -> Dict[str, Any]:
        """
        Get the result of a captcha task.

        Args:
            task_id: Task ID from create_task

        Returns:
            Task result with status and solution data

        Raises:
            TwoCaptchaError: If API request fails
        """
        await self._ensure_async_client()

        get_task_result_module = GetTaskResult(
            self.api_key, self.BASE_URL, None, self._async_client
        )
        return await get_task_result_module.get_task_result_async(task_id)

    async def solve_captcha(
        self,
        task: Dict[str, Any],
        language_pool: str = "en",
        callback_url: Optional[str] = None,
        soft_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Create a captcha task and wait for solution.

        Args:
            task: Task configuration dictionary
            (required)

            language_pool: Worker language pool ("en" or "rn")
            (optional)

            callback_url: Optional callback URL for results
            (optional)

            soft_id: Optional software ID
            (optional)

        Returns:
            Task result with solution data

        Raises:
            TwoCaptchaError: If task fails or times out
        """
        create_result = await self.create_task(
            task, language_pool, callback_url, soft_id
        )
        task_id = create_result["taskId"]

        start_time = asyncio.get_event_loop().time()
        while asyncio.get_event_loop().time() - start_time < self.timeout:
            result = await self.get_task_result(task_id)

            if result.get("status") == "ready":
                return result

            await asyncio.sleep(self.polling_interval)

        raise TwoCaptchaError(f"Task {task_id} timed out after {self.timeout} seconds")

    async def balance(self) -> Dict[str, Any]:
        """
        Get account balance (convenience method).

        Returns:
            Balance information

        Raises:
            TwoCaptchaError: If API request fails
        """
        await self._ensure_async_client()

        get_balance_module = GetBalance(
            self.api_key, self.BASE_URL, None, self._async_client
        )
        return await get_balance_module.get_balance_async()

    async def close(self):
        """
        Close the async HTTP client.

        Should be called when done with the client to free resources.
        """
        if self._async_client:
            await self._async_client.aclose()

    async def __aenter__(self):
        """Async context manager entry."""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.close()
