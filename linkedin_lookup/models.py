"""Data models for Company Employee Lookup."""

from dataclasses import dataclass, field


@dataclass
class Employee:
    """Represents a person found at a company."""
    name: str
    title: str
    profile_url: str = ""
    location: str = ""
    profile_pic_url: str = ""
    employer: str = ""
    apollo_id: str = ""
    has_email: bool = False
    email: str = ""
    personal_email: str = ""
    email_status: str = ""
    headline: str = ""
    seniority: str = ""
    employment_history: list = field(default_factory=list)  # list of dicts: org_name, title, start_date, end_date, description, current
    enriched: bool = False

    def matches_role(self, keywords: list[str]) -> bool:
        """Check if this employee's title matches any of the given keywords."""
        title_lower = self.title.lower()
        return any(kw.lower() in title_lower for kw in keywords)


@dataclass
class CompanyInfo:
    """Basic company metadata."""
    name: str
    website: str = ""
    description: str = ""
    industry: str = ""
    employee_count: int = 0
    linkedin_url: str = ""
    founded_year: int = 0


@dataclass
class SearchResult:
    """Result of a company employee search."""
    company: CompanyInfo
    employees: list[Employee] = field(default_factory=list)
    filtered_employees: list[Employee] = field(default_factory=list)
    role_keywords: list[str] = field(default_factory=list)
    total_matches: int = 0
