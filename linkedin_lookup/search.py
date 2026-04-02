"""Core search engine that ties providers, filtering, cache, and export together."""

import re
from linkedin_lookup.models import SearchResult
from linkedin_lookup.providers.base import BaseProvider
from linkedin_lookup.cache import (
    load_from_cache, save_to_cache, rebuild_from_cache, get_cache_age_days,
)
from linkedin_lookup.providers.apollo_provider import ApolloProvider


# Common role keyword mappings for convenience
ROLE_ALIASES: dict[str, list[str]] = {
    "qa": ["QA", "QC", "Quality Assurance", "Quality Control", "Test Engineer", "SDET", "QA Engineer", "QC Engineer"],
    "dev": ["Software Engineer", "Developer", "SDE", "Programmer", "Full Stack", "Backend", "Frontend"],
    "devops": ["DevOps", "SRE", "Site Reliability", "Platform Engineer", "Infrastructure"],
    "pm": ["Product Manager", "Program Manager", "Project Manager", "Scrum Master"],
    "design": ["Designer", "UX", "UI", "User Experience", "User Interface", "Graphic Designer"],
    "data": ["Data Engineer", "Data Scientist", "Data Analyst", "ML Engineer", "Machine Learning"],
    "hr": ["HR", "Human Resources", "Recruiter", "Talent Acquisition", "People Operations"],
    "sales": ["Sales", "Account Executive", "Business Development", "BDR", "SDR"],
    "marketing": ["Marketing", "Growth", "Content", "SEO", "Brand"],
}


def expand_keywords(user_input: str) -> list[str]:
    """
    Expand user input into a list of search keywords.
    Supports aliases (e.g. 'qa' -> multiple QA-related titles)
    and comma-separated custom keywords.
    """
    terms = [t.strip() for t in re.split(r"[,;]+", user_input) if t.strip()]
    expanded: list[str] = []

    for term in terms:
        alias_match = ROLE_ALIASES.get(term.lower())
        if alias_match:
            expanded.extend(alias_match)
        else:
            expanded.append(term)

    return expanded


def _filter_employees(all_employees, keywords):
    """Filter employee list by role keywords (case-insensitive substring match)."""
    return [e for e in all_employees if e.matches_role(keywords)]


def search_company(
    provider: BaseProvider,
    website_url: str,
    role_query: str,
    use_cache: bool = True,
    force_refresh: bool = False,
) -> SearchResult:
    """
    Main search function with local caching:

    1. Check if we have cached data for this domain
    2. If cached (and not force_refresh): load full data, filter locally — NO API calls
    3. If not cached (or force_refresh): fetch company + ALL employees, save to cache, then filter
    4. Return both full + filtered results
    """
    # Extract cache key — LinkedIn slug for LinkedIn URLs, domain otherwise
    cache_key = website_url.strip().lower()
    if hasattr(provider, '_cache_key_for_input'):
        cache_key = provider._cache_key_for_input(website_url)
    elif hasattr(provider, '_extract_domain'):
        cache_key = provider._extract_domain(website_url)

    keywords = expand_keywords(role_query) if role_query.strip() else []

    # --- Try cache first ---
    cached = None
    if use_cache and not force_refresh:
        cached = load_from_cache(cache_key)

    if cached:
        company, all_employees = rebuild_from_cache(cached)
        cache_age = get_cache_age_days(cache_key)
        filtered = _filter_employees(all_employees, keywords) if keywords else all_employees
        result = SearchResult(
            company=company,
            employees=all_employees,
            filtered_employees=filtered,
            role_keywords=keywords,
            total_matches=len(all_employees),
        )
        result.from_cache = True
        result.cache_age_days = round(cache_age or 0, 1)
        return result

    # --- Fetch fresh from API ---
    company = provider.get_company_info(website_url)

    # Fetch ALL employees (no role filter) — this is FREE on Apollo
    if isinstance(provider, ApolloProvider):
        all_employees = provider.get_all_employees(website_url, max_pages=5)
    else:
        all_employees = provider.get_employees(website_url, role_keywords=keywords)

    # Save full data to local cache
    save_to_cache(cache_key, company, all_employees)

    # Filter for the requested role (if any)
    filtered = _filter_employees(all_employees, keywords) if keywords else all_employees

    result = SearchResult(
        company=company,
        employees=all_employees,
        filtered_employees=filtered,
        role_keywords=keywords,
        total_matches=len(all_employees),
    )
    result.from_cache = False
    result.cache_age_days = 0
    return result


def enrich_filtered(
    provider,
    cache_key: str,
    company,
    all_employees: list,
    filtered_employees: list,
) -> tuple[list, list[dict]]:
    """
    Enrich filtered employees with full data (costs credits).
    Updates the cache with enriched data so future lookups are free.
    Returns (enriched_employees, raw_debug_responses).
    """
    if not hasattr(provider, 'enrich_employees'):
        return filtered_employees, []

    enriched, raw_responses = provider.enrich_employees(filtered_employees)

    # Merge enriched data back into the full employee list and update cache
    enriched_by_id = {e.apollo_id: e for e in enriched if e.apollo_id}
    updated_all = []
    for emp in all_employees:
        if emp.apollo_id in enriched_by_id:
            updated_all.append(enriched_by_id[emp.apollo_id])
        else:
            updated_all.append(emp)

    save_to_cache(cache_key, company, updated_all)
    return enriched, raw_responses
