import logging
from rest_framework.exceptions import APIException
from rest_framework import status

# Configure logging
logger = logging.getLogger(__name__)

class CustomAPIException(APIException):
    """
    Custom API exception for more detailed error responses
    """
    def __init__(self, detail=None, code=None, status_code=status.HTTP_400_BAD_REQUEST):
        super().__init__(detail, code)
        self.status_code = status_code
        # Log the error
        logger.error(f"API Exception: {detail}")

class UserRegistrationError(CustomAPIException):
    """
    Specific exception for user registration errors
    """
    def __init__(self, detail):
        super().__init__(detail, status_code=status.HTTP_422_UNPROCESSABLE_ENTITY)

class InstitutionCreationError(CustomAPIException):
    """
    Specific exception for institution creation errors
    """
    def __init__(self, detail):
        super().__init__(detail, status_code=status.HTTP_400_BAD_REQUEST)