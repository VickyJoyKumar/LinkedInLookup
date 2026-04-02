"""Local JSON cache for company data — fetch once, filter many times."""

import json
import os
from dataclasses import asdict
from datetime import datetime, timezone
from linkedin_lookup.models import CompanyInfo, Employee


CACHE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "cache")


def _domain_key(domain: str) -> str:
    """Sanitize domain into a safe filename key."""
    return domain.lower().replace(".", "_").replace("/", "").replace(":", "")


def _cache_path(domain: str) -> str:
    os.makedirs(CACHE_DIR, exist_ok=True)
    return os.path.join(CACHE_DIR, f"{_domain_key(domain)}.json")


def save_to_cache(domain: str, company: CompanyInfo, all_employees: list[Employee]) -> str:
    """Save full company + all employees to a local JSON file. Returns file path."""
    path = _cache_path(domain)
    data = {
        "domain": domain,
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "company": asdict(company),
        "all_employees": [asdict(e) for e in all_employees],
        "total_employee_count": len(all_employees),
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    return path


def load_from_cache(domain: str) -> dict | None:
    """
    Load cached data for a domain. Returns None if no cache exists.
    Returns dict with keys: domain, fetched_at, company, all_employees, total_employee_count
    """
    path = _cache_path(domain)
    if not os.path.exists(path):
        return None
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def get_cache_age_days(domain: str) -> float | None:
    """Return how many days old the cache is, or None if no cache."""
    cached = load_from_cache(domain)
    if not cached:
        return None
    fetched_at = datetime.fromisoformat(cached["fetched_at"])
    now = datetime.now(timezone.utc)
    return (now - fetched_at).total_seconds() / 86400


def rebuild_from_cache(cached: dict) -> tuple[CompanyInfo, list[Employee]]:
    """Reconstruct CompanyInfo and Employee list from cached dict."""
    c = cached["company"]
    company = CompanyInfo(
        name=c.get("name", ""),
        website=c.get("website", ""),
        description=c.get("description", ""),
        industry=c.get("industry", ""),
        employee_count=c.get("employee_count", 0),
        linkedin_url=c.get("linkedin_url", ""),
        founded_year=c.get("founded_year", 0),
    )
    employees = []
    for e in cached.get("all_employees", []):
        employees.append(Employee(
            name=e.get("name", ""),
            title=e.get("title", ""),
            profile_url=e.get("profile_url", ""),
            location=e.get("location", ""),
            profile_pic_url=e.get("profile_pic_url", ""),
            employer=e.get("employer", ""),
            apollo_id=e.get("apollo_id", ""),
            has_email=e.get("has_email", False),
            email=e.get("email", ""),
            personal_email=e.get("personal_email", ""),
            email_status=e.get("email_status", ""),
            headline=e.get("headline", ""),
            seniority=e.get("seniority", ""),
            enriched=e.get("enriched", False),
        ))
    return company, employees


def list_cached_companies() -> list[dict]:
    """List all cached companies with their domain, name, employee count, and cache date."""
    if not os.path.exists(CACHE_DIR):
        return []
    results = []
    for fname in sorted(os.listdir(CACHE_DIR)):
        if not fname.endswith(".json"):
            continue
        path = os.path.join(CACHE_DIR, fname)
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            results.append({
                "domain": data.get("domain", ""),
                "company_name": data.get("company", {}).get("name", ""),
                "total_employees": data.get("total_employee_count", 0),
                "fetched_at": data.get("fetched_at", ""),
                "cache_age_days": (datetime.now(timezone.utc) - datetime.fromisoformat(data["fetched_at"])).total_seconds() / 86400 if data.get("fetched_at") else 0,
            })
        except (json.JSONDecodeError, KeyError):
            continue
    return results
