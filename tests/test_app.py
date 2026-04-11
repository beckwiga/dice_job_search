"""Tests for Dice.com Job Scraper app functions."""

import sys
from unittest.mock import MagicMock

# Mock streamlit before importing app, since app.py calls st.set_page_config()
# at module level (line 14).
mock_st = MagicMock()
sys.modules["streamlit"] = mock_st

import pandas as pd
import pytest
from bs4 import BeautifulSoup

from app import (
    create_excel_download,
    extract_date_posted,
    extract_description,
    fetch_job_details,
    get_soup,
    parse_job_card,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_soup(html: str) -> BeautifulSoup:
    return BeautifulSoup(html, "html.parser")


# ---------------------------------------------------------------------------
# Fixtures: realistic HTML fragments
# ---------------------------------------------------------------------------

JOB_CARD_HTML = """
<div class="flex flex-col gap-6 overflow-hidden rounded-lg border bg-surface-primary p-6 relative mx-auto h-full w-full border-transparent shadow-none transition duration-300 ease-in-out sm:border-zinc-100 sm:shadow">
  <a data-testid="job-search-job-card-link" href="/job-detail/abc123">View</a>
  <a data-testid="job-search-job-detail-link">Senior Python Developer</a>
  <p class="mb-0">Acme Corp</p>
  <p>Remote, USA</p>
  <div aria-labelledby="employmentType-label">Full-time</div>
  <div aria-labelledby="salary-label">$120k - $150k</div>
  <div aria-labelledby="easyApply-label">Easy Apply</div>
</div>
"""

JOB_CARD_NO_EASY_APPLY_HTML = """
<div>
  <a data-testid="job-search-job-card-link" href="/job-detail/xyz789">View</a>
  <a data-testid="job-search-job-detail-link">Data Engineer</a>
  <p class="mb-0">BigCo</p>
  <p>New York, NY</p>
  <div aria-labelledby="employmentType-label">Contract</div>
  <div aria-labelledby="salary-label">$100/hr</div>
</div>
"""

JOB_CARD_ABSOLUTE_LINK_HTML = """
<div>
  <a data-testid="job-search-job-card-link" href="https://www.dice.com/job-detail/full-url">View</a>
  <a data-testid="job-search-job-detail-link">DevOps Lead</a>
  <p class="mb-0">CloudInc</p>
  <div aria-labelledby="easyApply-label">Easy Apply</div>
</div>
"""

JOB_CARD_MISSING_LINK_HTML = """
<div>
  <p class="mb-0">NoLink Corp</p>
</div>
"""

JOB_DETAIL_HTML = """
<html>
<body>
  <dhi-time-ago posted-date="2026-03-15T12:00:00Z"></dhi-time-ago>
  <div class="description">We are looking for a talented Python developer...</div>
</body>
</html>
"""


# ===========================================================================
# extract_date_posted
# ===========================================================================

class TestExtractDatePosted:
    def test_valid_iso_date(self):
        soup = make_soup('<dhi-time-ago posted-date="2026-03-15T12:00:00Z"></dhi-time-ago>')
        assert extract_date_posted(soup) == "Mar 15, 2026"

    def test_different_date(self):
        soup = make_soup('<dhi-time-ago posted-date="2025-12-01T08:30:00Z"></dhi-time-ago>')
        assert extract_date_posted(soup) == "Dec 01, 2025"

    def test_no_tag_returns_not_found(self):
        soup = make_soup("<div>No date here</div>")
        assert extract_date_posted(soup) == "Posted date not found"

    def test_none_input(self):
        assert extract_date_posted(None) == "Posted date not found"

    def test_tag_without_posted_date_attr(self):
        soup = make_soup("<dhi-time-ago></dhi-time-ago>")
        assert extract_date_posted(soup) == "Posted date not found"

    def test_unparseable_date_returns_raw_string(self):
        soup = make_soup('<dhi-time-ago posted-date="not-a-date"></dhi-time-ago>')
        assert extract_date_posted(soup) == "not-a-date"

    def test_partial_date_string(self):
        # dateutil.parser.isoparse cannot handle plain "March 2026"
        soup = make_soup('<dhi-time-ago posted-date="March 2026"></dhi-time-ago>')
        result = extract_date_posted(soup)
        # Should fall through to the bare except and return raw string
        assert result == "March 2026"


# ===========================================================================
# extract_description
# ===========================================================================

class TestExtractDescription:
    def test_div_description_class(self):
        soup = make_soup('<div class="description">Great job opportunity.</div>')
        assert extract_description(soup) == "Great job opportunity."

    def test_div_job_description_class(self):
        soup = make_soup('<div class="job-description">Backend role.</div>')
        assert extract_description(soup) == "Backend role."

    def test_p_with_specific_class(self):
        soup = make_soup(
            '<p class="text-sm font-normal text-zinc-900">Short description.</p>'
        )
        assert extract_description(soup) == "Short description."

    def test_fallback_to_job_description_when_no_description_div(self):
        html = '<div><div class="job-description">Fallback desc.</div></div>'
        soup = make_soup(html)
        assert extract_description(soup) == "Fallback desc."

    def test_no_description_found(self):
        soup = make_soup("<div><span>Nothing relevant</span></div>")
        assert extract_description(soup) == "Description not available"

    def test_none_input(self):
        assert extract_description(None) == "Description not available"

    def test_strips_whitespace(self):
        soup = make_soup('<div class="description">   Spaced out   </div>')
        assert extract_description(soup) == "Spaced out"


# ===========================================================================
# parse_job_card
# ===========================================================================

class TestParseJobCard:
    def test_full_card_easy_apply(self):
        card = make_soup(JOB_CARD_HTML)
        result = parse_job_card(card, job_index=0, easy_apply_filter=True)
        assert result is not None
        assert result["Job Title"] == "Senior Python Developer"
        assert result["Company"] == "Acme Corp"
        assert result["Position Type"] == "Full-time"
        assert result["Compensation"] == "$120k - $150k"
        assert result["Application"] == "Easy Apply"
        assert result["Job Link"].startswith("https://www.dice.com")
        assert result["full_job_url"] == result["Job Link"]
        assert result["job_index"] == 0

    def test_no_easy_apply_filtered_out(self):
        card = make_soup(JOB_CARD_NO_EASY_APPLY_HTML)
        result = parse_job_card(card, job_index=1, easy_apply_filter=True)
        assert result is None

    def test_no_easy_apply_filter_disabled(self):
        card = make_soup(JOB_CARD_NO_EASY_APPLY_HTML)
        result = parse_job_card(card, job_index=1, easy_apply_filter=False)
        assert result is not None
        assert result["Application"] == "External Apply"
        assert result["Job Title"] == "Data Engineer"
        assert result["Company"] == "BigCo"

    def test_absolute_link_not_doubled(self):
        card = make_soup(JOB_CARD_ABSOLUTE_LINK_HTML)
        result = parse_job_card(card, job_index=2, easy_apply_filter=True)
        assert result is not None
        assert result["Job Link"] == "https://www.dice.com/job-detail/full-url"
        # Should NOT be "https://www.dice.comhttps://..."

    def test_relative_link_gets_prefix(self):
        card = make_soup(JOB_CARD_HTML)
        result = parse_job_card(card, job_index=0, easy_apply_filter=True)
        assert result["Job Link"] == "https://www.dice.com/job-detail/abc123"

    def test_missing_link_returns_none(self):
        card = make_soup(JOB_CARD_MISSING_LINK_HTML)
        result = parse_job_card(card, job_index=0, easy_apply_filter=False)
        assert result is None

    def test_missing_optional_fields_default_to_na(self):
        # Card with link + easy apply but no title/company/location/salary/employment
        html = """
        <div>
          <a data-testid="job-search-job-card-link" href="/job/minimal">Go</a>
          <div aria-labelledby="easyApply-label">Easy Apply</div>
        </div>
        """
        card = make_soup(html)
        result = parse_job_card(card, job_index=5, easy_apply_filter=True)
        assert result is not None
        assert result["Job Title"] == "N/A"
        assert result["Company"] == "N/A"
        assert result["Location"] == "N/A"
        assert result["Position Type"] == "N/A"
        assert result["Compensation"] == "N/A"

    def test_job_index_preserved(self):
        card = make_soup(JOB_CARD_HTML)
        result = parse_job_card(card, job_index=42, easy_apply_filter=True)
        assert result["job_index"] == 42


# ===========================================================================
# fetch_job_details
# ===========================================================================

class TestFetchJobDetails:
    def setup_method(self):
        # Clear lru_cache between tests to avoid cross-test contamination
        get_soup.cache_clear()

    def test_none_input(self):
        assert fetch_job_details(None) is None

    def test_adds_date_and_description(self, mocker):
        detail_soup = make_soup(JOB_DETAIL_HTML)
        mocker.patch("app.get_soup", return_value=detail_soup)

        job_data = {
            "Job Title": "Python Dev",
            "full_job_url": "https://www.dice.com/job-detail/abc123",
            "job_index": 0,
        }

        result = fetch_job_details(job_data)
        assert result is not None
        assert result["Date Posted"] == "Mar 15, 2026"
        assert "talented Python developer" in result["Job Description"]
        # full_job_url should be popped
        assert "full_job_url" not in result

    def test_get_soup_returns_none(self, mocker):
        mocker.patch("app.get_soup", return_value=None)

        job_data = {
            "Job Title": "Tester",
            "full_job_url": "https://www.dice.com/job-detail/fail",
            "job_index": 1,
        }

        result = fetch_job_details(job_data)
        assert result is not None
        assert result["Date Posted"] == "Posted date not found"
        assert result["Job Description"] == "Description not available"

    def test_pops_full_job_url(self, mocker):
        mocker.patch("app.get_soup", return_value=make_soup("<div></div>"))
        job_data = {
            "full_job_url": "https://example.com/job/1",
            "job_index": 0,
        }
        fetch_job_details(job_data)
        assert "full_job_url" not in job_data


# ===========================================================================
# create_excel_download
# ===========================================================================

class TestCreateExcelDownload:
    def test_returns_bytes(self):
        df = pd.DataFrame({"Job Title": ["Dev"], "Company": ["Acme"]})
        result = create_excel_download(df, "python+developer")
        assert isinstance(result, bytes)
        assert len(result) > 0

    def test_excel_is_valid(self):
        df = pd.DataFrame(
            {
                "Job Title": ["Dev", "Tester"],
                "Company": ["Acme", "BigCo"],
                "Location": ["Remote", "NYC"],
            }
        )
        result = create_excel_download(df, "test")
        # Read back the Excel file and verify contents
        import io
        read_back = pd.read_excel(io.BytesIO(result), sheet_name="Jobs")
        assert len(read_back) == 2
        assert list(read_back.columns) == ["Job Title", "Company", "Location"]
        assert read_back.iloc[0]["Job Title"] == "Dev"

    def test_empty_dataframe(self):
        df = pd.DataFrame(columns=["Job Title", "Company"])
        result = create_excel_download(df, "empty")
        assert isinstance(result, bytes)
        import io
        read_back = pd.read_excel(io.BytesIO(result), sheet_name="Jobs")
        assert len(read_back) == 0


# ===========================================================================
# Query formatting logic (extracted from main, line 239)
# ===========================================================================

class TestQueryFormatting:
    """Test the query formatting logic: query.strip().lower().replace(' ', '+')"""

    @staticmethod
    def format_query(query: str) -> str:
        return query.strip().lower().replace(" ", "+")

    def test_simple_query(self):
        assert self.format_query("Python Developer") == "python+developer"

    def test_leading_trailing_spaces(self):
        assert self.format_query("  Data Scientist  ") == "data+scientist"

    def test_already_lowercase(self):
        assert self.format_query("devops") == "devops"

    def test_multiple_spaces(self):
        assert self.format_query("machine  learning  engineer") == "machine++learning++engineer"

    def test_single_word(self):
        assert self.format_query("Java") == "java"

    def test_mixed_case(self):
        assert self.format_query("SeNiOr DaTa EnGiNeEr") == "senior+data+engineer"

    def test_empty_string(self):
        assert self.format_query("") == ""

    def test_only_spaces(self):
        assert self.format_query("   ") == ""
