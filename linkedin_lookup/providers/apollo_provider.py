"""Apollo.io data provider."""

import json
import logging
import os
import re
import requests
from urllib.parse import urlparse
from linkedin_lookup.models import CompanyInfo, Employee
from linkedin_lookup.providers.base import BaseProvider

logger = logging.getLogger(__name__)


class ApolloProvider(BaseProvider):
    """Fetches company & employee data via the Apollo.io API."""

    BASE_URL = "https://api.apollo.io/api/v1"

    def __init__(self, api_key: str | None = None):
        self.api_key = api_key or os.getenv("APOLLO_API_KEY", "")
        if not self.api_key:
            raise ValueError(
                "APOLLO_API_KEY is required. "
                "Get one at https://developer.apollo.io/ and set it in .env"
            )
        self._session = requests.Session()
        self._session.headers.update({
            "Content-Type": "application/json",
            "Cache-Control": "no-cache",
            "x-api-key": self.api_key,
        })
        self._resolved_org_names: dict[str, str] = {}  # slug -> best org name

    @staticmethod
    def _is_linkedin_url(url: str) -> bool:
        """Check if the input is a LinkedIn company profile URL."""
        return bool(re.match(r"https?://(www\.)?linkedin\.com/company/", url.strip()))

    @staticmethod
    def _extract_domain(url_or_domain: str) -> str:
        """Extract clean domain from a URL or domain string."""
        url_or_domain = url_or_domain.strip()
        if not url_or_domain.startswith(("http://", "https://")):
            url_or_domain = "https://" + url_or_domain
        parsed = urlparse(url_or_domain)
        domain = parsed.hostname or parsed.path
        domain = re.sub(r"^www\.", "", domain)
        return domain

    @staticmethod
    def _extract_linkedin_slug(linkedin_url: str) -> str:
        """Extract the company slug from a LinkedIn company URL."""
        match = re.search(r"linkedin\.com/company/([^/?#]+)", linkedin_url.strip())
        return match.group(1).rstrip("/") if match else ""

    @staticmethod
    def _slug_to_name(slug: str) -> str:
        """Convert a LinkedIn slug to a human-readable company name for search."""
        return slug.replace("-", " ")

    def _cache_key_for_input(self, url_or_domain: str) -> str:
        """
        Return a stable cache key for input.
        For LinkedIn URLs: uses the slug (e.g. 'kirby-building-systems-international')
        For domains/URLs: uses the extracted domain
        """
        if self._is_linkedin_url(url_or_domain):
            return self._extract_linkedin_slug(url_or_domain)
        return self._extract_domain(url_or_domain)

    def get_company_info(self, website_url: str) -> CompanyInfo:
        """Fetch company details. Uses enrichment for domains, people search for LinkedIn URLs."""
        if self._is_linkedin_url(website_url):
            return self._get_company_info_from_linkedin(website_url)

        domain = self._extract_domain(website_url)
        resp = self._session.get(
            f"{self.BASE_URL}/organizations/enrich",
            params={"domain": domain},
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json().get("organization", {}) or {}

        return CompanyInfo(
            name=data.get("name", "Unknown"),
            website=data.get("website_url", website_url),
            description=data.get("short_description", "") or data.get("seo_description", ""),
            industry=data.get("industry", ""),
            employee_count=data.get("estimated_num_employees", 0),
            linkedin_url=data.get("linkedin_url", ""),
            founded_year=data.get("founded_year", 0),
        )

    def _find_best_org_name(self, slug: str) -> str:
        """
        Find the best organization name search term by progressively shortening
        the slug until Apollo returns results. LinkedIn slugs often have extra
        words (e.g. 'kirby-building-systems-international') that need trimming.
        Results are cached per slug to avoid repeated API calls.
        """
        if slug in self._resolved_org_names:
            return self._resolved_org_names[slug]

        words = slug.replace("-", " ").split()
        # Try full name first, then progressively drop the last word
        for end in range(len(words), max(0, len(words) - 3), -1):
            candidate = " ".join(words[:end])
            if not candidate:
                continue
            resp = self._session.post(
                f"{self.BASE_URL}/mixed_people/api_search",
                json={"q_organization_name": candidate, "page": 1, "per_page": 1},
                timeout=30,
            )
            resp.raise_for_status()
            data = resp.json()
            if data.get("total_entries", 0) > 0:
                self._resolved_org_names[slug] = candidate
                return candidate
        # Fallback to full slug
        fallback = slug.replace("-", " ")
        self._resolved_org_names[slug] = fallback
        return fallback

    def _get_company_info_from_linkedin(self, linkedin_url: str) -> CompanyInfo:
        """Build CompanyInfo from people search when only a LinkedIn URL is available."""
        slug = self._extract_linkedin_slug(linkedin_url)
        search_term = self._find_best_org_name(slug)

        resp = self._session.post(
            f"{self.BASE_URL}/mixed_people/api_search",
            json={"q_organization_name": search_term, "page": 1, "per_page": 1},
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
        total = data.get("total_entries", 0)

        people = data.get("people", [])
        org_name = search_term.title()
        if people:
            org = people[0].get("organization", {}) or {}
            org_name = org.get("name") or org_name

        return CompanyInfo(
            name=org_name,
            website="",
            description="",
            industry="",
            employee_count=total,
            linkedin_url=linkedin_url.strip().rstrip("/"),
            founded_year=0,
        )

    def _search_people_by_org_name(self, org_name: str, max_pages: int = 5) -> list[Employee]:
        """Fetch employees using q_organization_name (for LinkedIn URL lookups)."""
        all_employees: list[Employee] = []
        seen_ids: set[str] = set()
        total = 0

        for page in range(1, max_pages + 1):
            payload = {
                "q_organization_name": org_name,
                "page": page,
                "per_page": 100,
            }

            resp = self._session.post(
                f"{self.BASE_URL}/mixed_people/api_search",
                json=payload,
                timeout=30,
            )
            resp.raise_for_status()
            data = resp.json()

            if page == 1:
                total = data.get("total_entries", 0)

            people = data.get("people", [])
            if not people:
                break

            for person in people:
                person_id = person.get("id", "")
                if person_id in seen_ids:
                    continue
                seen_ids.add(person_id)

                first_name = person.get("first_name", "")
                last_name_obf = person.get("last_name_obfuscated", "")
                name = f"{first_name} {last_name_obf}".strip() or "Unknown"

                title = person.get("title", "") or ""
                org = person.get("organization", {}) or {}
                employer = org.get("name", "")

                location_parts = []
                if person.get("city"):
                    location_parts.append(person["city"])
                elif person.get("state"):
                    location_parts.append(person["state"])
                if person.get("country"):
                    location_parts.append(person["country"])

                all_employees.append(Employee(
                    name=name,
                    title=title,
                    profile_url=person.get("linkedin_url", ""),
                    location=", ".join(location_parts),
                    employer=employer,
                    apollo_id=person_id,
                    has_email=person.get("has_email", False),
                ))

            if page * 100 >= total:
                break

        return all_employees

    def get_all_employees(self, website_url: str, max_pages: int = 5) -> list[Employee]:
        """
        Fetch ALL employees at a company (no role filter).

        POST /api/v1/mixed_people/api_search with only domain filter.
        FREE — no credits consumed. Fetches up to max_pages pages (100/page).
        For LinkedIn URLs, searches by organization name instead.
        """
        if self._is_linkedin_url(website_url):
            slug = self._extract_linkedin_slug(website_url)
            org_name = self._find_best_org_name(slug)
            return self._search_people_by_org_name(org_name, max_pages)

        domain = self._extract_domain(website_url)
        all_employees: list[Employee] = []
        seen_ids: set[str] = set()
        total = 0

        for page in range(1, max_pages + 1):
            payload = {
                "q_organization_domains_list": [domain],
                "page": page,
                "per_page": 100,
            }

            resp = self._session.post(
                f"{self.BASE_URL}/mixed_people/api_search",
                json=payload,
                timeout=30,
            )
            resp.raise_for_status()
            data = resp.json()

            if page == 1:
                total = data.get("total_entries", 0)

            people = data.get("people", [])
            if not people:
                break

            for person in people:
                person_id = person.get("id", "")
                if person_id in seen_ids:
                    continue
                seen_ids.add(person_id)

                first_name = person.get("first_name", "")
                last_name_obf = person.get("last_name_obfuscated", "")
                name = f"{first_name} {last_name_obf}".strip() or "Unknown"

                title = person.get("title", "") or ""
                org = person.get("organization", {}) or {}
                employer = org.get("name", "")

                location_parts = []
                if person.get("city"):
                    location_parts.append(person["city"])
                elif person.get("state"):
                    location_parts.append(person["state"])
                if person.get("country"):
                    location_parts.append(person["country"])

                all_employees.append(Employee(
                    name=name,
                    title=title,
                    profile_url=person.get("linkedin_url", ""),
                    location=", ".join(location_parts),
                    employer=employer,
                    apollo_id=person_id,
                    has_email=person.get("has_email", False),
                ))

            if page * 100 >= total:
                break

        return all_employees

    def get_employees(self, website_url: str, role_keywords: list[str] | None = None) -> list[Employee]:
        """
        Search for employees using Apollo's People API Search endpoint.

        POST /api/v1/mixed_people/api_search
        - Does NOT consume credits
        - Returns up to 100 results per page (max 500 pages)
        - Filters: q_organization_domains_list[] + person_titles[]
        """
        if not role_keywords:
            return []

        if self._is_linkedin_url(website_url):
            # For LinkedIn URLs, get all employees by org name then filter locally
            slug = self._extract_linkedin_slug(website_url)
            org_name = self._find_best_org_name(slug)
            all_emp = self._search_people_by_org_name(org_name, max_pages=3)
            return [e for e in all_emp if e.matches_role(role_keywords)]

        domain = self._extract_domain(website_url)
        all_employees: list[Employee] = []
        seen_ids: set[str] = set()

        # Fetch up to 3 pages (300 results max)
        for page in range(1, 4):
            payload = {
                "q_organization_domains_list": [domain],
                "person_titles": role_keywords,
                "include_similar_titles": True,
                "page": page,
                "per_page": 100,
            }

            resp = self._session.post(
                f"{self.BASE_URL}/mixed_people/api_search",
                json=payload,
                timeout=30,
            )
            resp.raise_for_status()
            data = resp.json()

            people = data.get("people", [])
            if not people:
                break

            for person in people:
                person_id = person.get("id", "")
                if person_id in seen_ids:
                    continue
                seen_ids.add(person_id)

                first_name = person.get("first_name", "")
                # last_name is obfuscated in search results
                last_name_obf = person.get("last_name_obfuscated", "")
                name = f"{first_name} {last_name_obf}".strip() or "Unknown"

                title = person.get("title", "") or ""
                org = person.get("organization", {}) or {}
                employer = org.get("name", "")

                # Location info from boolean flags
                location_parts = []
                if person.get("city"):
                    location_parts.append(person["city"])
                elif person.get("state"):
                    location_parts.append(person["state"])
                if person.get("country"):
                    location_parts.append(person["country"])

                all_employees.append(Employee(
                    name=name,
                    title=title,
                    profile_url=person.get("linkedin_url", ""),
                    location=", ".join(location_parts),
                    employer=employer,
                    apollo_id=person_id,
                    has_email=person.get("has_email", False),
                ))

            # Check if we've gotten all results
            total = data.get("total_entries", 0)
            if page * 100 >= total:
                break

        return all_employees

    def enrich_employees(self, employees: list[Employee]) -> tuple[list[Employee], list[dict]]:
        """
        Enrich employees with full data using Apollo's people/match endpoint.
        Returns (enriched_employees, raw_responses) — raw_responses is for debug.
        Costs 1 credit per person (only enrich filtered results to save credits).
        Skips already-enriched employees.

        Sends as much identifying info as possible (name, employer, linkedin_url)
        to maximize match quality and data completeness.
        """
        enriched = []
        raw_responses = []
        for emp in employees:
            if emp.enriched:
                enriched.append(emp)
                continue
            if not emp.apollo_id:
                enriched.append(emp)
                continue

            try:
                # Build payload with all available identifying info for better matches
                payload: dict = {
                    "id": emp.apollo_id,
                    "reveal_personal_emails": True,
                }
                # Add name info if we have it (helps Apollo find better match)
                if emp.name and emp.name != "Unknown":
                    name_parts = emp.name.split()
                    if len(name_parts) >= 2:
                        payload["first_name"] = name_parts[0]
                        payload["last_name"] = name_parts[-1]
                    else:
                        payload["name"] = emp.name
                # Add employer for context
                if emp.employer:
                    payload["organization_name"] = emp.employer
                # Add LinkedIn URL if available from search
                if emp.profile_url:
                    payload["linkedin_url"] = emp.profile_url

                resp = self._session.post(
                    f"{self.BASE_URL}/people/match",
                    json=payload,
                    timeout=30,
                )
                resp.raise_for_status()
                data = resp.json()
                person = data.get("person", {}) or {}

                # Log raw response for diagnostics
                raw_responses.append({
                    "input_name": emp.name,
                    "apollo_id": emp.apollo_id,
                    "payload_sent": {k: v for k, v in payload.items() if k != "reveal_personal_emails"},
                    "response_keys": list(person.keys()) if person else [],
                    "email": person.get("email"),
                    "personal_emails": person.get("personal_emails"),
                    "linkedin_url": person.get("linkedin_url"),
                    "headline": person.get("headline"),
                    "seniority": person.get("seniority"),
                    "departments": person.get("departments"),
                    "contact_keys": list((person.get("contact", {}) or {}).keys()) if person.get("contact") else [],
                })
                logger.info(
                    "Enrich response for %s (id=%s): keys=%s, email=%s, personal_emails=%s, linkedin=%s, contact_keys=%s",
                    emp.name, emp.apollo_id,
                    list(person.keys()) if person else "empty",
                    person.get("email", "N/A"),
                    person.get("personal_emails", "N/A"),
                    person.get("linkedin_url", "N/A"),
                    list((person.get("contact", {}) or {}).keys()) if person.get("contact") else "none",
                )

                if person:
                    first = person.get("first_name", "") or ""
                    last = person.get("last_name", "") or ""
                    full_name = f"{first} {last}".strip() or emp.name

                    location_parts = []
                    if person.get("city"):
                        location_parts.append(person["city"])
                    if person.get("state"):
                        location_parts.append(person["state"])
                    if person.get("country"):
                        location_parts.append(person["country"])

                    org = person.get("organization", {}) or {}
                    contact = person.get("contact", {}) or {}

                    # Extract work email — check multiple possible fields
                    work_email = person.get("email", "") or ""

                    # Extract personal email — check multiple paths
                    personal_emails = person.get("personal_emails", []) or []
                    if not personal_emails:
                        # Also check under contact object
                        personal_emails = contact.get("personal_emails", []) or []
                    personal_email = personal_emails[0] if personal_emails else ""

                    # If no work email, try to find any email from contact object
                    if not work_email:
                        contact_email = contact.get("email", "") or ""
                        if contact_email:
                            work_email = contact_email

                    # LinkedIn URL — check person and contact
                    linkedin_url = person.get("linkedin_url", "") or ""
                    if not linkedin_url:
                        linkedin_url = contact.get("linkedin_url", "") or ""
                    if not linkedin_url:
                        linkedin_url = emp.profile_url or ""

                    # Departments/functions from response
                    departments = person.get("departments", []) or []
                    functions = person.get("functions", []) or []
                    dept_str = ", ".join(departments + functions) if (departments or functions) else ""

                    enriched.append(Employee(
                        name=full_name,
                        title=person.get("title", "") or emp.title,
                        profile_url=linkedin_url,
                        location=", ".join(location_parts) if location_parts else emp.location,
                        profile_pic_url=person.get("photo_url", "") or emp.profile_pic_url,
                        employer=org.get("name", "") or emp.employer,
                        apollo_id=emp.apollo_id,
                        has_email=bool(work_email or personal_email),
                        email=work_email,
                        personal_email=personal_email,
                        email_status=person.get("email_status", "") or "",
                        headline=person.get("headline", "") or "",
                        seniority=person.get("seniority", "") or "",
                        enriched=True,
                    ))
                else:
                    enriched.append(emp)
                    raw_responses.append({"input_name": emp.name, "apollo_id": emp.apollo_id, "error": "empty person object"})
            except Exception as e:
                enriched.append(emp)
                raw_responses.append({"input_name": emp.name, "apollo_id": emp.apollo_id, "error": str(e)})

        return enriched, raw_responses
