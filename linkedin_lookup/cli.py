"""Command-line interface for Company Employee Lookup."""

import argparse
import sys
from dotenv import load_dotenv

from linkedin_lookup.providers.apollo_provider import ApolloProvider
from linkedin_lookup.search import search_company, ROLE_ALIASES
from linkedin_lookup.exporters.csv_export import export_csv
from linkedin_lookup.cache import list_cached_companies, get_cache_age_days


def main():
    load_dotenv()

    parser = argparse.ArgumentParser(
        description="Company Employee Lookup — find people by role at any company. Powered by Apollo.io.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=f"""
Examples:
  python -m linkedin_lookup.cli --url stripe.com --role qa
  python -m linkedin_lookup.cli --url google.com --role "Data Scientist" --export
  python -m linkedin_lookup.cli --url stripe.com --role dev --refresh
  python -m linkedin_lookup.cli --list-cache

Built-in role aliases: {', '.join(ROLE_ALIASES.keys())}

Cache: Company data is saved locally in cache/ folder.
       Future searches on the same company use cached data (no API calls).
       Use --refresh to force a fresh fetch from Apollo.
        """,
    )
    parser.add_argument("--url", help="Company website or domain (e.g. stripe.com)")
    parser.add_argument("--role", help='Role to search for (e.g. "QA", "qa", "Software Engineer")')
    parser.add_argument("--export", action="store_true", help="Export results to CSV")
    parser.add_argument("--output-dir", default="output", help="Output directory for CSV export")
    parser.add_argument("--refresh", action="store_true", help="Force fresh fetch from Apollo (ignore cache)")
    parser.add_argument("--no-cache", action="store_true", help="Don't use or save cache")
    parser.add_argument("--list-cache", action="store_true", help="List all cached companies and exit")

    args = parser.parse_args()

    # --- List cache mode ---
    if args.list_cache:
        companies = list_cached_companies()
        if not companies:
            print("No cached companies found. Run a search first.")
            sys.exit(0)
        print(f"\nCached companies ({len(companies)}):\n")
        print(f"{'Domain':<30} {'Company':<25} {'Employees':<12} {'Fetched At'}")
        print("-" * 90)
        for c in companies:
            fetched = c['fetched_at'][:10] if c['fetched_at'] else 'N/A'
            print(f"{c['domain']:<30} {c['company_name']:<25} {c['total_employees']:<12} {fetched}")
        sys.exit(0)

    # --- Search mode ---
    if not args.url or not args.role:
        parser.error("--url and --role are required (unless using --list-cache)")

    # Initialize provider
    try:
        provider = ApolloProvider()
    except ValueError as e:
        print(f"Error: {e}")
        sys.exit(1)

    # Check cache status
    domain = ApolloProvider._extract_domain(args.url)
    cache_age = get_cache_age_days(domain)
    if cache_age is not None and not args.refresh and not args.no_cache:
        print(f"\n[CACHE] Using cached data for {domain} ({cache_age:.0f} days old). Use --refresh to re-fetch.")
    elif args.refresh:
        print(f"\n[REFRESH] Forcing fresh fetch from Apollo for {domain}...")
    else:
        print(f"\n[FETCH] No cache for {domain}. Fetching from Apollo (people search is FREE)...")

    print(f"Searching for '{args.role}' roles...\n")

    try:
        result = search_company(
            provider, args.url, args.role,
            use_cache=not args.no_cache,
            force_refresh=args.refresh,
        )
    except Exception as e:
        print(f"Error fetching data: {e}")
        sys.exit(1)

    # Display company info
    print(f"Company: {result.company.name}")
    print(f"Industry: {result.company.industry}")
    print(f"Size: ~{result.company.employee_count} employees")
    if result.company.linkedin_url:
        print(f"LinkedIn: {result.company.linkedin_url}")
    print(f"Keywords used: {', '.join(result.role_keywords)}")
    print(f"Total people in cache: {result.total_matches}")
    print(f"Filtered matches: {len(result.filtered_employees)}")
    source = "CACHE" if getattr(result, 'from_cache', False) else "API"
    print(f"Data source: {source}")
    print(f"\n{'Name':<30} {'Title':<40} {'Location':<25} {'Employer':<20}")
    print("-" * 115)

    for emp in result.filtered_employees:
        loc = emp.location or "N/A"
        print(f"{emp.name:<30} {emp.title:<40} {loc:<25} {emp.employer:<20}")
        if emp.profile_url:
            print(f"  LinkedIn: {emp.profile_url}")

    if not result.filtered_employees:
        print("  (No employees matched the given role keywords)")

    # Export
    if args.export:
        path = export_csv(result, output_dir=args.output_dir)
        print(f"\nResults exported to: {path}")


if __name__ == "__main__":
    main()
