"""NinjaPear (formerly Proxycurl) data provider."""

import os
import requests
from linkedin_lookup.models import CompanyInfo, Employee
from linkedin_lookup.providers.base import BaseProvider


class NinjaPearProvider(BaseProvider):
    """Fetches company & employee data via the NinjaPear API (https://nubela.co/)."""

    BASE_URL = "https://nubela.co/api/v1"

    def __init__(self, api_key: str | None = None):
        self.api_key = api_key or os.getenv("PROXYCURL_API_KEY", "")
        if not self.api_key:
            raise ValueError(
                "PROXYCURL_API_KEY is required. "
                "Get one at https://nubela.co/auth/register and set it in .env"
            )
        self._session = requests.Session()
        self._session.headers.update({"Authorization": f"Bearer {self.api_key}"})

    def get_company_info(self, website_url: str) -> CompanyInfo:
        """Fetch company details from NinjaPear Company Details endpoint."""
        resp = self._session.get(
            f"{self.BASE_URL}/company/details",
            params={"website": website_url},
            timeout=100,
        )
        resp.raise_for_status()
        data = resp.json()

        executives = data.get("executives", []) or []
        exec_names = [f"{e.get('name', '')} ({e.get('title', '')})" for e in executives]

        return CompanyInfo(
            name=data.get("name", "Unknown"),
            website=website_url,
            description=data.get("description", ""),
            industry=str(data.get("industry", "")),
            employee_count=data.get("employee_count", 0),
            executives=exec_names,
        )

    def get_employees(self, website_url: str, role_keywords: list[str] | None = None) -> list[Employee]:
        """
        Look up employees by role using NinjaPear's Person Profile endpoint.

        For each unique role keyword, calls GET /api/v1/employee/profile with
        employer_website + role. Each call costs 3 credits and returns one person.
        """
        if not role_keywords:
            return []

        all_employees: list[Employee] = []
        seen_names: set[str] = set()

        for role in role_keywords:
            try:
                resp = self._session.get(
                    f"{self.BASE_URL}/employee/profile",
                    params={"employer_website": website_url, "role": role},
                    timeout=100,
                )
                if resp.status_code == 404:
                    continue  # No one found for this role
                resp.raise_for_status()
                data = resp.json()

                full_name = data.get("full_name", "")
                if not full_name:
                    first = data.get("first_name", "")
                    last = data.get("last_name", "")
                    full_name = f"{first} {last}".strip() or "Unknown"

                # Deduplicate — same person may match multiple role keywords
                if full_name.lower() in seen_names:
                    continue
                seen_names.add(full_name.lower())

                # Extract current role from work experience
                title = ""
                work_exp = data.get("work_experience", []) or []
                for exp in work_exp:
                    if exp.get("end_date") is None:  # Current role
                        title = exp.get("role", "")
                        break
                if not title:
                    title = role  # Fallback to searched role

                location_parts = []
                if data.get("city"):
                    location_parts.append(data["city"])
                if data.get("country"):
                    location_parts.append(data["country"])

                all_employees.append(Employee(
                    name=full_name,
                    title=title,
                    profile_url=data.get("x_profile_url", "") or data.get("personal_website", ""),
                    location=", ".join(location_parts),
                    profile_pic_url=data.get("profile_pic_url", ""),
                    employer=_current_employer(work_exp),
                ))
            except requests.HTTPError:
                continue  # Skip failed lookups

        return all_employees


# Keep backward-compatible alias
ProxycurlProvider = NinjaPearProvider


def _current_employer(work_experience: list[dict]) -> str:
    for exp in work_experience:
        if exp.get("end_date") is None:
            return exp.get("company_name", "")
    return ""
