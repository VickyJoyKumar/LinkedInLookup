"""Abstract base for data providers."""

from abc import ABC, abstractmethod
from linkedin_lookup.models import CompanyInfo, Employee


class BaseProvider(ABC):
    """Interface that all data providers must implement."""

    @abstractmethod
    def get_company_info(self, website_url: str) -> CompanyInfo:
        """Fetch basic company information from a website URL."""
        ...

    @abstractmethod
    def get_employees(self, website_url: str, role_keywords: list[str] | None = None) -> list[Employee]:
        """Fetch employees of a company, optionally filtered by role keywords."""
        ...
