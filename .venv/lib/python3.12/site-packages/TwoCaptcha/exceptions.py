from typing import Optional


class TwoCaptchaError(Exception):
    """
    Exception raised for TwoCaptcha API errors.

    Attributes:
        error_id: Error ID from API response
        error_code: Error code as string
    """

    def __init__(
        self,
        message: str,
        error_id: Optional[int] = None,
        error_code: Optional[str] = None,
    ):
        """
        Initialize TwoCaptchaError.

        Args:
            message: Error message
            error_id: Error ID from API response
            error_code: Error code as string
        """
        super().__init__(message)
        self.error_id = error_id
        self.error_code = error_code
