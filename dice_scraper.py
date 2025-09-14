import requests
import pandas as pd
import time
import random
import concurrent.futures
from bs4 import BeautifulSoup
from datetime import datetime
from dateutil import parser
from functools import lru_cache

USER_AGENTS = [
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64)...',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)...',
    # Add others as needed
]

@lru_cache(maxsize=128)
def get_soup(url):
    headers = {'User-Agent': random.choice(USER_AGENTS)}
    try:
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        return BeautifulSoup(response.text, 'html.parser')
    except Exception as e:
        print(f"Failed to fetch {url}: {e}")
        return None

def extract_date_posted(desc_soup):
    if not desc_soup:
        return 'Posted date not found'
    posted_tag = desc_soup.find('dhi-time-ago')
    if posted_tag and posted_tag.has_attr('posted-date'):
        date_str = posted_tag['posted-date']
        try:
            return parser.isoparse(date_str).strftime('%b %d, %Y')
        except:
            return date_str
    return 'Posted date not found'

def extract_description(desc_soup):
    if not desc_soup:
        return 'Description not available'
    desc_tag = desc_soup.find('div', class_='description') or \
               desc_soup.find('div', class_='job-description') or \
               desc_soup.find('p', class_='text-sm font-normal text-zinc-900')
    return desc_tag.get_text(strip=True) if desc_tag else 'Description not available'

def parse_job_card(card, job_index, easy_apply_filter=True):
    try:
        job_link = card.find('a', {'data-testid': 'job-search-job-card-link'})
        if not job_link or not job_link.has_attr('href'):
            return None
        job_link = job_link['href']
        easy_apply = card.find('div', {'aria-labelledby': 'easyApply-label'})
        application_type = 'Easy Apply' if easy_apply else 'External Apply'
        if easy_apply_filter and not easy_apply:
            return None
        title_tag = card.find('a', {'data-testid': 'job-search-job-detail-link'})
        company_tag = card.find('p', class_='mb-0')
        location_tag = card.find('p', string=lambda t: t and ('Remote' in t or ',' in t))
        employment_type = card.find('div', {'aria-labelledby': 'employmentType-label'})
        salary = card.find('div', {'aria-labelledby': 'salary-label'})
        full_job_url = job_link if job_link.startswith('http') else f'https://www.dice.com{job_link}'
        return {
            'Job Title': title_tag.get_text(strip=True) if title_tag else 'N/A',
            'Company': company_tag.get_text(strip=True) if company_tag else 'N/A',
            'Position Type': employment_type.get_text(strip=True) if employment_type else 'N/A',
            'Location': location_tag.get_text(strip=True) if location_tag else 'N/A',
            'Compensation': salary.get_text(strip=True) if salary else 'N/A',
            'Job Link': full_job_url,
            'Application': application_type,
            'full_job_url': full_job_url,
            'job_index': job_index
        }
    except Exception as e:
        print(f"Could not parse job card: {e}")
        return None

def fetch_job_details(job_data):
    try:
        if not job_data:
            return None
        full_job_url = job_data.pop('full_job_url')
        desc_soup = get_soup(full_job_url)
        job_data['Date Posted'] = extract_date_posted(desc_soup)
        job_data['Job Description'] = extract_description(desc_soup)
        return job_data
    except Exception as e:
        print(f"Failed to fetch job details: {e}")
        return job_data if 'job_index' in job_data else None

def scrape_dice_jobs(query, limit=20, easy_apply_filter=True, max_workers=10):
    jobs = []
    job_details_to_fetch = []
    page = 1
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        while len(job_details_to_fetch) < limit:
            base_url = f"https://www.dice.com/jobs?filters.postedDate=ONE&filters.employmentType=CONTRACTS&q={query}&page={page}"
            if easy_apply_filter:
                base_url += "&filters.easyApply=true"
            soup = get_soup(base_url)
            if not soup:
                break
            job_cards = soup.find_all('div', class_='flex flex-col gap-6 overflow-hidden rounded-lg border bg-surface-primary p-6 relative mx-auto h-full w-full border-transparent shadow-none transition duration-300 ease-in-out sm:border-zinc-100 sm:shadow')
            if not job_cards:
                break
            job_index = 0
            for card in job_cards:
                if len(job_details_to_fetch) >= limit:
                    break
                job_data = parse_job_card(card, job_index, easy_apply_filter)
                job_index += 1
                if job_data:
                    job_details_to_fetch.append(job_data)
            page += 1
            time.sleep(random.uniform(0.5, 1.5))
        job_details_to_fetch = job_details_to_fetch[:limit]
        future_to_job = {executor.submit(fetch_job_details, job_data): job_data for job_data in job_details_to_fetch}
        for future in concurrent.futures.as_completed(future_to_job):
            job_data = future.result()
            if job_data:
                jobs.append(job_data)
    jobs.sort(key=lambda x: x.pop('job_index') if 'job_index' in x else 999999)
    return jobs
