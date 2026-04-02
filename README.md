# LinkedIn Company Employee Lookup

Find people by role/position at any company using their LinkedIn company profile URL.

## Features

- Paste a LinkedIn company URL → get a list of employees matching a role
- Built-in role aliases: `qa`, `dev`, `devops`, `pm`, `design`, `data`, `hr`, `sales`, `marketing`
- Two data provider options: **Proxycurl** (recommended) or **RapidAPI**
- Export results to CSV
- Web UI (Streamlit) + CLI interface

## Project Structure

```
LinkedInLookup/
├── app.py                          # Streamlit web UI
├── requirements.txt
├── .env.example
├── linkedin_lookup/
│   ├── cli.py                      # Command-line interface
│   ├── models.py                   # Data models
│   ├── search.py                   # Core search engine + keyword expansion
│   ├── providers/
│   │   ├── base.py                 # Abstract provider interface
│   │   ├── proxycurl_provider.py   # Proxycurl API integration
│   │   └── rapidapi_provider.py    # RapidAPI integration
│   └── exporters/
│       └── csv_export.py           # CSV export
```

## Setup

### 1. Install Python dependencies

```bash
cd LinkedInLookup
pip install -r requirements.txt
```

### 2. Get an API key

You need ONE of these (Proxycurl recommended):

| Provider | Sign up | Free tier |
|---|---|---|
| **Proxycurl** | https://nubela.co/proxycurl/ | 10 free credits on signup |
| **RapidAPI** | https://rapidapi.com/freshdata-freshdata-default/api/fresh-linkedin-profile-data | Freemium |

### 3. Configure your API key

```bash
# Copy the example env file
copy .env.example .env

# Edit .env and paste your key
PROXYCURL_API_KEY=your_key_here
```

## Usage

### Web UI (recommended)

```bash
streamlit run app.py
```

This opens a browser with a form where you can:
1. Paste the LinkedIn company URL
2. Type a role (e.g. "QA" or "Software Engineer")
3. Click Search
4. Download results as CSV

### Command Line

```bash
# Basic search
python -m linkedin_lookup.cli --url https://www.linkedin.com/company/google --role "QA, QC"

# Using a built-in alias
python -m linkedin_lookup.cli --url https://www.linkedin.com/company/microsoft --role qa

# With CSV export
python -m linkedin_lookup.cli --url https://www.linkedin.com/company/amazon --role "Data Scientist" --export

# Using RapidAPI instead
python -m linkedin_lookup.cli --url https://www.linkedin.com/company/google --role dev --provider rapidapi
```

### Built-in Role Aliases

Type any of these shortcuts instead of full titles:

| Alias | Expands to |
|---|---|
| `qa` | QA, QC, Quality Assurance, Quality Control, Test Engineer, SDET |
| `dev` | Software Engineer, Developer, SDE, Full Stack, Backend, Frontend |
| `devops` | DevOps, SRE, Site Reliability, Platform Engineer |
| `pm` | Product Manager, Program Manager, Project Manager, Scrum Master |
| `design` | Designer, UX, UI, User Experience |
| `data` | Data Engineer, Data Scientist, Data Analyst, ML Engineer |
| `hr` | HR, Human Resources, Recruiter, Talent Acquisition |
| `sales` | Sales, Account Executive, Business Development |
| `marketing` | Marketing, Growth, Content, SEO, Brand |

You can also mix aliases and custom terms: `--role "qa, Automation Lead"`

## How It Works

1. **URL input** — You provide a LinkedIn company page URL
2. **Company lookup** — The tool fetches company metadata via the API
3. **Employee search** — The API returns employees associated with that company
4. **Keyword filtering** — Results are filtered server-side (regex) and client-side (title matching)
5. **Display/Export** — Matching employees are displayed in a table or exported to CSV

## Cost Considerations

- **Proxycurl**: ~$0.01 per company lookup, ~$0.03 per employee search page. A typical search costs ~$0.10-$0.30.
- **RapidAPI**: Varies by plan, some offer free tiers with limited requests.

## Adding a New Provider

1. Create a new file in `linkedin_lookup/providers/`
2. Inherit from `BaseProvider` and implement `get_company_info()` and `get_employees()`
3. Add it as an option in `cli.py` and `app.py`
