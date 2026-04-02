"""RapidAPI-based LinkedIn data provider (alternative to Proxycurl)."""

import os
import requests
from linkedin_lookup.models import CompanyInfo, Employee
from linkedin_lookup.providers.base import BaseProvider


class RapidApiProvider(BaseProvider):
    """
    Fetches LinkedIn data via RapidAPI's 'Fresh LinkedIn Profile Data' API.
    Subscribe at: https://rapidapi.com/freshdata-freshdata-default/api/fresh-linkedin-profile-data

    Set RAPIDAPI_KEY in your .env file.
    """

    BASE_URL = "https://fresh-linkedin-profile-data.p.rapidapi.com"

    def __init__(self, api_key: str | None = None):
        self.api_key = api_key or os.getenv("RAPIDAPI_KEY", "")
        if not self.api_key:
            raise ValueError(
                "RAPIDAPI_KEY is required. "
                "Get one at https://rapidapi.com and set it in .env"
            )
        self._session = requests.Session()
        self._session.headers.update({
            "x-rapidapi-key": self.api_key,
            "x-rapidapi-host": "fresh-linkedin-profile-data.p.rapidapi.com",
        })

    def get_company_info(self, linkedin_url: str) -> CompanyInfo:
        resp = self._session.get(
            f"{self.BASE_URL}/get-company-details",
            params={"linkedin_url": linkedin_url},
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json().get("data", {})

        return CompanyInfo(
            name=data.get("company_name", "Unknown"),
            linkedin_url=linkedin_url,
            description=data.get("description", ""),
            industry=data.get("industry", ""),
            website=data.get("website", ""),
            employee_count=data.get("company_size", 0),
        )

    def get_employees(self, linkedin_url: str, role_keywords: list[str] | None = None) -> list[Employee]:
        resp = self._session.get(
            f"{self.BASE_URL}/get-company-employees",
            params={"linkedin_url": linkedin_url, "limit": 100},
            timeout=60,
        )
        resp.raise_for_status()
        raw = resp.json().get("data", [])

        employees = []
        for item in raw:
            emp = Employee(
                name=item.get("full_name", "Unknown"),
                title=item.get("title", ""),
                linkedin_url=item.get("linkedin_url", ""),
                location=item.get("location", ""),
            )
            employees.append(emp)

        if role_keywords:
            employees = [e for e in employees if e.matches_role(role_keywords)]

        return employees
