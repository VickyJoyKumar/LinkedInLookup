"""Streamlit web UI for Company Employee Lookup."""

import streamlit as st
import pandas as pd
from dotenv import load_dotenv

from linkedin_lookup.providers.apollo_provider import ApolloProvider
from linkedin_lookup.search import search_company, enrich_filtered, expand_keywords, ROLE_ALIASES
from linkedin_lookup.exporters.csv_export import export_csv
from linkedin_lookup.cache import list_cached_companies, get_cache_age_days, load_from_cache, rebuild_from_cache

load_dotenv()

st.set_page_config(page_title="Company Employee Lookup", page_icon="🔍", layout="wide")

# --- Password Protection ---
def _check_password() -> bool:
    """Return True if the user has entered the correct password."""
    # If no password is configured, skip the gate
    app_password = st.secrets.get("APP_PASSWORD", "") if hasattr(st, "secrets") else ""
    if not app_password:
        return True

    if "authenticated" not in st.session_state:
        st.session_state["authenticated"] = False

    if st.session_state["authenticated"]:
        return True

    st.title("🔒 Company Employee Lookup")
    st.markdown("Enter the shared password to access the app.")
    pwd = st.text_input("Password", type="password", key="pwd_input")
    if st.button("Login", type="primary"):
        if pwd == app_password:
            st.session_state["authenticated"] = True
            st.rerun()
        else:
            st.error("Incorrect password.")
    return False

if not _check_password():
    st.stop()

# --- Helper: get Apollo API key from secrets or sidebar ---
def _get_default_api_key() -> str:
    """Try to get Apollo API key from Streamlit secrets."""
    try:
        return st.secrets.get("APOLLO_API_KEY", "")
    except Exception:
        return ""

st.title("🔍 Company Employee Lookup")
st.markdown("Find talent by role at any company. Get LinkedIn profiles and emails to accelerate your hiring outreach.")

# --- Sidebar ---
with st.sidebar:
    st.header("⚙️ Settings")
    default_key = _get_default_api_key()
    api_key = st.text_input(
        "Apollo API Key" + (" (using secrets)" if default_key else " (enter or use .env)"),
        type="password",
        value=default_key,
        help="Your Apollo.io API key. If deployed on Streamlit Cloud, set it in Settings > Secrets.",
    )

    st.divider()
    st.header("📦 Cache")
    force_refresh = st.checkbox("Force refresh (ignore cache)", value=False,
                                 help="Re-fetch from Apollo even if data is cached locally.")

    # Show cached companies
    cached = list_cached_companies()
    if cached:
        st.markdown(f"**{len(cached)} cached companies:**")
        for c in cached:
            age = c.get('cache_age_days', 0)
            st.markdown(f"- **{c['company_name']}** ({c['domain']}) — {c['total_employees']} people, {age:.0f}d ago")
    else:
        st.caption("No cached companies yet. Run a search first.")

    st.divider()
    st.markdown("**Built-in role aliases:**")
    for alias, keywords in ROLE_ALIASES.items():
        st.markdown(f"- `{alias}` → {', '.join(keywords[:3])}...")
    st.divider()
    st.markdown("**Note:** People Search is FREE. Enrichment costs ~1 credit/person and reveals full names, emails, and LinkedIn URLs.")

# --- Helper: build employee dataframe ---
def _employee_df(employees):
    """Build a DataFrame from a list of Employee objects."""
    rows = []
    for e in employees:
        row = {
            "Name": e.name,
            "Title": e.title,
            "Employer": e.employer,
            "LinkedIn": e.profile_url,
            "Work Email": e.email,
            "Personal Email": getattr(e, 'personal_email', ''),
            "Email Status": getattr(e, 'email_status', ''),
            "Location": e.location,
            "Headline": getattr(e, 'headline', ''),
            "Seniority": getattr(e, 'seniority', ''),
            "Enriched": "✅" if e.enriched else "—",
        }
        rows.append(row)
    return pd.DataFrame(rows)


# --- Helper: display results ---
def _display_results(company, all_employees, filtered_employees, keywords, source_label, tab_key=""):
    """Render company info, filtered results, and full employee table."""
    st.divider()
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Company", company.name)
    c2.metric("Industry", company.industry or "N/A")
    c3.metric("Company Size", f"~{company.employee_count:,}")
    c4.metric("Filtered / Total", f"{len(filtered_employees)} / {len(all_employees)}")

    enriched_count = sum(1 for e in filtered_employees if e.enriched)
    not_enriched = len(filtered_employees) - enriched_count
    keyword_label = ', '.join(keywords) if keywords else "(all employees)"
    st.caption(f"Keywords: {keyword_label} | Source: {source_label} | Enriched: {enriched_count}/{len(filtered_employees)}")
    if company.linkedin_url:
        st.caption(f"LinkedIn: {company.linkedin_url}")
    if not_enriched > 0:
        st.info(f"💡 {not_enriched} results have limited data (obfuscated names, no email/LinkedIn). "
                f"**Enrich** below to get full names, work emails, personal emails, and LinkedIn URLs for outreach.")

    tab_filtered, tab_full = st.tabs(["🎯 Filtered Results", "📋 All Cached Employees"])

    with tab_filtered:
        if filtered_employees:
            df_filtered = _employee_df(filtered_employees)

            # --- Selective enrichment: let users pick who to enrich ---
            not_enriched = [e for e in filtered_employees if not e.enriched]
            if not_enriched:
                st.markdown("##### Select employees to enrich")
                st.caption("Only selected employees will use credits (1 credit each). Already-enriched employees are skipped.")

                select_all = st.checkbox("Select all unenriched", key=f"sel_all_{tab_key}")

                selected_indices = []
                for i, emp in enumerate(filtered_employees):
                    if emp.enriched:
                        continue
                    label = f"{emp.name} — {emp.title}" + (f" @ {emp.employer}" if emp.employer else "")
                    checked = st.checkbox(label, value=select_all, key=f"sel_{tab_key}_{i}")
                    if checked:
                        selected_indices.append(i)

                if selected_indices:
                    st.info(f"**{len(selected_indices)}** employee(s) selected — will use ~{len(selected_indices)} credit(s)")
                    if st.button(f"🔓 Enrich {len(selected_indices)} selected", key=f"enrich_sel_{tab_key}"):
                        to_enrich = [filtered_employees[i] for i in selected_indices]
                        st.session_state[f"_enrich_sel_{tab_key}"] = to_enrich
                        st.rerun()

                st.divider()

            # Show outreach summary
            enriched_list = [e for e in filtered_employees if e.enriched]
            with_email = [e for e in filtered_employees if e.email or getattr(e, 'personal_email', '')]
            with_linkedin = [e for e in filtered_employees if e.profile_url]
            st.markdown(f"📊 **Outreach ready:** {len(with_email)} with email · {len(with_linkedin)} with LinkedIn · {len(enriched_list)} enriched")

            st.dataframe(
                df_filtered,
                column_config={
                    "LinkedIn": st.column_config.LinkColumn("LinkedIn", display_text="Open Profile"),
                    "Work Email": st.column_config.TextColumn("Work Email"),
                    "Personal Email": st.column_config.TextColumn("Personal Email"),
                },
                use_container_width=True,
                hide_index=True,
            )

            csv_filtered = df_filtered.to_csv(index=False).encode("utf-8")
            st.download_button(
                "📥 Download Filtered CSV",
                data=csv_filtered,
                file_name=f"{company.name}_filtered.csv",
                mime="text/csv",
                key=f"dl_filtered_{tab_key}",
            )
        else:
            st.warning("No employees matched the given role keywords.")

    with tab_full:
        if all_employees:
            df_full = _employee_df(all_employees)

            st.dataframe(
                df_full,
                column_config={
                    "LinkedIn": st.column_config.LinkColumn("LinkedIn", display_text="Open Profile"),
                    "Work Email": st.column_config.TextColumn("Work Email"),
                    "Personal Email": st.column_config.TextColumn("Personal Email"),
                },
                use_container_width=True,
                hide_index=True,
            )

            csv_full = df_full.to_csv(index=False).encode("utf-8")
            st.download_button(
                "📥 Download All Employees CSV",
                data=csv_full,
                file_name=f"{company.name}_all_employees.csv",
                mime="text/csv",
                key=f"dl_full_{tab_key}",
            )
        else:
            st.info("No full employee data available.")


# --- Main form ---
col1, col2 = st.columns([2, 1])

with col1:
    company_url = st.text_input(
        "Company Website, Domain, or LinkedIn URL",
        placeholder="stripe.com or https://www.linkedin.com/company/stripe/",
    )

with col2:
    role_query = st.text_input(
        "Role / Position (optional)",
        placeholder="Leave blank to fetch all, or: QA, dev, manager",
    )

search_clicked = st.button("🔎 Search", type="primary", use_container_width=True)

# --- New Search Results ---
if search_clicked:
    if not company_url:
        st.error("Please enter a company website or domain (e.g. stripe.com)")
    else:
        try:
            with st.spinner("Initializing Apollo provider..."):
                provider = ApolloProvider(api_key=api_key or None)

            # Show cache status
            cache_key = provider._cache_key_for_input(company_url)
            cache_age = get_cache_age_days(cache_key)
            if cache_age is not None and not force_refresh:
                st.info(f"📦 Using cached data for **{cache_key}** ({cache_age:.0f} days old). Toggle 'Force refresh' in sidebar to re-fetch.")
            elif force_refresh and cache_age is not None:
                st.info(f"🔄 Force-refreshing data for **{cache_key}**...")
            else:
                st.info(f"🌐 Fetching fresh data from Apollo for **{cache_key}**...")

            spinner_msg = f"Searching for '{role_query}' roles at {company_url}..." if role_query else f"Fetching all employees at {company_url}..."
            with st.spinner(spinner_msg):
                result = search_company(
                    provider, company_url, role_query or "",
                    use_cache=True,
                    force_refresh=force_refresh,
                )

            # Store result in session state for enrichment
            st.session_state["last_result"] = result
            st.session_state["last_cache_key"] = cache_key
            st.session_state["last_provider_key"] = api_key or None

            source_label = "📦 Cache" if getattr(result, 'from_cache', False) else "🌐 Apollo API"
            _display_results(result.company, result.employees, result.filtered_employees, result.role_keywords, source_label, tab_key="search")

        except ValueError as e:
            st.error(f"Configuration error: {e}")
        except Exception as e:
            st.error(f"Error: {e}")

# --- Handle selective enrichment for search results ---
if "_enrich_sel_search" in st.session_state and "last_result" in st.session_state:
    to_enrich = st.session_state.pop("_enrich_sel_search")
    result = st.session_state["last_result"]
    cache_key = st.session_state["last_cache_key"]
    try:
        provider = ApolloProvider(api_key=st.session_state.get("last_provider_key") or api_key or None)
        with st.spinner(f"Enriching {len(to_enrich)} selected people..."):
            enriched, raw_debug = enrich_filtered(provider, cache_key, result.company, result.employees, to_enrich)
        st.success(f"✅ Enriched {len(to_enrich)} people! Data updated.")
        if raw_debug:
            with st.expander("🔍 Debug: Raw Apollo enrichment responses", expanded=False):
                for entry in raw_debug:
                    st.json(entry)
        st.rerun()
    except ValueError as e:
        st.error(f"API key required for enrichment: {e}")
    except Exception as e:
        st.error(f"Enrichment error: {e}")

# --- Search History ---
st.divider()
st.subheader("📜 Search History")

cached_list = list_cached_companies()
if not cached_list:
    st.caption("No search history yet. Run a search to see companies here.")
else:
    # Company selector
    company_options = {
        f"{c['company_name']} ({c['domain']}) — {c['total_employees']} people, {c.get('cache_age_days', 0):.0f}d ago": c['domain']
        for c in cached_list
    }
    selected_label = st.selectbox("Select a company from history", options=list(company_options.keys()))
    selected_domain = company_options[selected_label]

    # Filter input for history
    history_role = st.text_input(
        "Filter by role / keywords",
        placeholder="QA, dev, manager...",
        key="history_role",
    )

    filter_clicked = st.button("🔎 Apply Filter", key="history_filter", use_container_width=True)

    # Load and display cached data
    cached_data = load_from_cache(selected_domain)
    if cached_data:
        company, all_employees = rebuild_from_cache(cached_data)
        cache_age = get_cache_age_days(selected_domain)
        st.info(f"📦 **{company.name}** — {len(all_employees)} employees cached ({cache_age:.0f} days ago)")

        if filter_clicked and history_role:
            keywords = expand_keywords(history_role)
            filtered = [e for e in all_employees if e.matches_role(keywords)]
            _display_results(company, all_employees, filtered, keywords, "📦 Cache (History)", tab_key="history")

        elif filter_clicked and not history_role:
            st.warning("Enter a role or keyword to filter.")
        else:
            # Show all employees by default when a company is selected
            _display_results(company, all_employees, all_employees, ["(all)"], "📦 Cache (History)", tab_key="history_all")

# --- Handle selective enrichment for history results ---
for _enrich_key in ["_enrich_sel_history", "_enrich_sel_history_all"]:
    if _enrich_key in st.session_state:
        to_enrich = st.session_state.pop(_enrich_key)
        try:
            cached_data = load_from_cache(selected_domain)
            if cached_data:
                company, all_employees = rebuild_from_cache(cached_data)
                provider = ApolloProvider(api_key=api_key or None)
                with st.spinner(f"Enriching {len(to_enrich)} selected people..."):
                    enriched, raw_debug = enrich_filtered(provider, selected_domain, company, all_employees, to_enrich)
                st.success(f"✅ Enriched {len(to_enrich)} people! Data updated.")
                if raw_debug:
                    with st.expander("🔍 Debug: Raw Apollo enrichment responses", expanded=False):
                        for entry in raw_debug:
                            st.json(entry)
                st.rerun()
        except ValueError as e:
            st.error(f"API key required for enrichment: {e}")
        except Exception as e:
            st.error(f"Enrichment error: {e}")
