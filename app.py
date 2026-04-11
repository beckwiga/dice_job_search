import streamlit as st
import requests
import pandas as pd
import time
import random
import concurrent.futures
import logging
from bs4 import BeautifulSoup
from datetime import datetime
from dateutil import parser
from functools import lru_cache
import io

logger = logging.getLogger(__name__)

# Page configuration
st.set_page_config(
    page_title="Dice.com Job Scraper",
    page_icon="💼",
    layout="wide"
)

# List of user agents to rotate through
USER_AGENTS = [
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/96.0.4664.110 Safari/537.36',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/15.1 Safari/605.1.15',
    'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/96.0.4664.93 Safari/537.36',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/97.0.4692.71 Safari/537.36',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/96.0.4664.110 Safari/537.36'
]

@lru_cache(maxsize=128)
def get_soup(url):
    """Fetch and parse HTML with caching for identical URLs"""
    headers = {'User-Agent': random.choice(USER_AGENTS)}
    try:
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        return BeautifulSoup(response.text, 'html.parser')
    except Exception as e:
        logger.error(f"Failed to fetch {url}: {e}")
        st.error(f"Failed to fetch {url}: {e}")
        return None

def extract_date_posted(desc_soup):
    """Extract the date a job was posted"""
    if not desc_soup:
        return 'Posted date not found'
        
    posted_tag = desc_soup.find('dhi-time-ago')
    if posted_tag and posted_tag.has_attr('posted-date'):
        date_str = posted_tag['posted-date']
        try:
            return parser.isoparse(date_str).strftime('%b %d, %Y')
        except (ValueError, OverflowError):
            logger.warning(f"Failed to parse date: {date_str}")
            return date_str
    return 'Posted date not found'

def extract_description(desc_soup):
    """Extract job description"""
    if not desc_soup:
        return 'Description not available'
        
    desc_tag = desc_soup.find('div', class_='description')
    if not desc_tag:
        desc_tag = desc_soup.find('div', class_='job-description') or \
                  desc_soup.find('p', class_='text-sm font-normal text-zinc-900')
    
    return desc_tag.get_text(strip=True) if desc_tag else 'Description not available'

def parse_job_card(card, job_index, easy_apply_filter=True):
    """Parse a job card and return job data"""
    try:
        job_link = card.find('a', {'data-testid': 'job-search-job-card-link'})
        if not job_link or not job_link.has_attr('href'):
            return None
            
        job_link = job_link['href']
        
        # Check for Easy Apply if filter is enabled
        easy_apply = card.find('div', {'aria-labelledby': 'easyApply-label'})
        application_type = 'Easy Apply' if easy_apply else 'External Apply'
        
        # Skip if Easy Apply filter is on and this job is not Easy Apply
        if easy_apply_filter and not easy_apply:
            return None
            
        title_tag = card.find('a', {'data-testid': 'job-search-job-detail-link'})
        company_tag = card.find('p', class_='mb-0')
        location_tag = card.find('p', string=lambda t: t and ('Remote' in t or ',' in t))
        employment_type = card.find('div', {'aria-labelledby': 'employmentType-label'})
        salary = card.find('div', {'aria-labelledby': 'salary-label'})
        
        full_job_url = job_link if job_link.startswith('http') else f'https://www.dice.com{job_link}'
        
        # Basic job data that doesn't require visiting the job page
        job_data = {
            'Job Title': title_tag.get_text(strip=True) if title_tag else 'N/A',
            'Company': company_tag.get_text(strip=True) if company_tag else 'N/A',
            'Position Type': employment_type.get_text(strip=True) if employment_type else 'N/A',
            'Location': location_tag.get_text(strip=True) if location_tag else 'N/A',
            'Compensation': salary.get_text(strip=True) if salary else 'N/A',
            'Job Link': full_job_url,
            'Application': application_type,
            'full_job_url': full_job_url,  # Temporary field for the executor
            'job_index': job_index  # Keep track of original order for sorting later
        }
        
        return job_data
        
    except Exception as e:
        logger.warning(f"Failed to parse job card: {e}")
        st.error(f"Could not parse job card: {e}")
        return None

def fetch_job_details(job_data):
    """Fetch additional job details from the job page"""
    try:
        if not job_data:
            return None
            
        full_job_url = job_data.pop('full_job_url')  # Remove temporary field
        
        # Get the job description page
        desc_soup = get_soup(full_job_url)
        
        # Add additional details
        job_data['Date Posted'] = extract_date_posted(desc_soup)
        job_data['Job Description'] = extract_description(desc_soup)
        
        return job_data
        
    except Exception as e:
        logger.error(f"Failed to fetch job details: {e}")
        st.error(f"Failed to fetch job details: {e}")
        return job_data if 'job_index' in job_data else None

def scrape_dice_jobs(query, limit, easy_apply_filter=True, max_workers=10, progress_bar=None, status_text=None):
    """Scrape jobs from Dice.com with parallel processing"""
    jobs = []
    job_details_to_fetch = []
    page = 1
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        while len(job_details_to_fetch) < limit:
            # Build URL based on Easy Apply filter
            if easy_apply_filter:
                base_url = f"https://www.dice.com/jobs?filters.easyApply=true&q={query}&radius=30&radiusUnit=mi&page={page}"
            else:
                base_url = f"https://www.dice.com/jobs?q={query}&radius=30&radiusUnit=mi&page={page}"
            
            if status_text:
                status_text.text(f"Fetching page {page}...")
            
            soup = get_soup(base_url)
            
            if not soup:
                st.error(f"Failed to fetch page {page}")
                break
                
            job_cards = soup.find_all(
                'div',
                class_='flex flex-col gap-6 overflow-hidden rounded-lg border bg-surface-primary p-6 relative mx-auto h-full w-full border-transparent shadow-none transition duration-300 ease-in-out sm:border-zinc-100 sm:shadow'
            )
            
            if not job_cards:
                if status_text:
                    status_text.text(f"No more job cards found on page {page}.")
                break
            
            if status_text:
                status_text.text(f"Page {page}: Found {len(job_cards)} jobs. Processing...")
            
            # First pass: extract basic job data from the search results page
            job_index = 0
            for card in job_cards:
                if len(job_details_to_fetch) >= limit:
                    break
                    
                job_data = parse_job_card(card, job_index, easy_apply_filter)
                job_index += 1
                
                if job_data:
                    job_details_to_fetch.append(job_data)
            
            if len(job_details_to_fetch) >= limit or len(job_details_to_fetch) == 0:
                break
                
            page += 1
            time.sleep(random.uniform(0.5, 1.5))  # Respect the site with a small delay between pages
        
        # Second pass: fetch job details in parallel
        job_details_to_fetch = job_details_to_fetch[:limit]  # Ensure we don't exceed the limit
        
        if status_text:
            status_text.text(f"Fetching detailed information for {len(job_details_to_fetch)} jobs...")
        
        # Submit all jobs to the executor
        future_to_job = {executor.submit(fetch_job_details, job_data): job_data for job_data in job_details_to_fetch}
        
        # Collect results as they complete
        completed_jobs = 0
        for future in concurrent.futures.as_completed(future_to_job):
            job_data = future.result()
            if job_data:
                jobs.append(job_data)
            completed_jobs += 1
            
            if progress_bar:
                progress_bar.progress(completed_jobs / len(job_details_to_fetch))
    
    # Sort jobs by original index to maintain order
    jobs.sort(key=lambda x: x.pop('job_index') if 'job_index' in x else 999999)
    return jobs

def create_excel_download(df, query):
    """Create Excel file for download"""
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='Jobs')
    processed_data = output.getvalue()
    return processed_data

# Streamlit UI
def main():
    st.title("💼 Dice.com Job Scraper")
    st.markdown("Search and scrape Easy Apply jobs from Dice.com")
    
    # Sidebar for inputs
    with st.sidebar:
        st.header("Search Parameters")
        query = st.text_input("Job Title", placeholder="e.g., Python Developer")
        limit = st.number_input("Number of Jobs", min_value=1, max_value=100, value=10)
        easy_apply_only = st.toggle("Easy Apply Only", value=True, help="Filter jobs to only show Easy Apply positions")
        
        search_button = st.button("🔍 Search Jobs", type="primary")
    
    # Main content area
    if search_button:
        if not query:
            st.error("Please enter a job title to search.")
            return
        
        # Convert query to the format expected by the scraper
        formatted_query = query.strip().lower().replace(' ', '+')
        
        # Progress indicators
        progress_bar = st.progress(0)
        status_text = st.empty()
        
        # Start scraping
        start_time = time.time()
        
        try:
            jobs = scrape_dice_jobs(formatted_query, limit, easy_apply_only, progress_bar=progress_bar, status_text=status_text)
            
            if jobs:
                # Clear progress indicators
                progress_bar.empty()
                status_text.empty()
                
                # Success message
                st.success(f"Successfully scraped {len(jobs)} jobs in {time.time() - start_time:.2f} seconds!")
                
                # Create DataFrame
                df = pd.DataFrame(jobs)
                
                # Reorder columns for better display
                column_order = ['Job Title', 'Company', 'Location', 'Position Type', 'Compensation', 'Date Posted', 'Application', 'Job Link', 'Job Description']
                df = df.reindex(columns=[col for col in column_order if col in df.columns])
                
                # Display results in a table
                st.header("📋 Job Results")
                
                # Make the table interactive with better formatting
                st.dataframe(
                    df,
                    use_container_width=True,
                    height=400,
                    column_config={
                        "Job Link": st.column_config.LinkColumn("Job Link"),
                        "Job Description": st.column_config.TextColumn(
                            "Job Description",
                            width="large",
                            help="Click to expand"
                        )
                    }
                )
                
                # Download button
                st.header("📥 Download Results")
                
                # Create Excel file
                excel_data = create_excel_download(df, formatted_query)
                filename = f"dice_jobs_{formatted_query.replace('+', '_')}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
                
                st.download_button(
                    label="📊 Download Excel File",
                    data=excel_data,
                    file_name=filename,
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    type="primary"
                )
                
                # Display summary statistics
                with st.expander("📊 Summary Statistics"):
                    col1, col2, col3, col4 = st.columns(4)
                    
                    with col1:
                        st.metric("Total Jobs Found", len(jobs))
                    
                    with col2:
                        companies = df['Company'].nunique()
                        st.metric("Unique Companies", companies)
                    
                    with col3:
                        remote_jobs = len(df[df['Location'].str.contains('Remote', case=False, na=False)])
                        st.metric("Remote Jobs", remote_jobs)
                    
                    with col4:
                        easy_apply_jobs = len(df[df['Application'] == 'Easy Apply'])
                        st.metric("Easy Apply Jobs", easy_apply_jobs)
                
            else:
                progress_bar.empty()
                status_text.empty()
                st.warning("No Easy Apply jobs found for your search criteria. Try a different job title.")
                
        except Exception as e:
            logger.exception("Scraping failed")
            progress_bar.empty()
            status_text.empty()
            st.error(f"An error occurred during scraping: {str(e)}")
    
    # Instructions
    with st.expander("ℹ️ How to Use"):
        st.markdown("""
        1. **Enter Job Title**: Type the job position you're looking for (e.g., "Python Developer", "Data Scientist")
        2. **Set Number of Jobs**: Choose how many jobs you want to scrape (1-100)
        3. **Click Search**: The app will scrape Easy Apply jobs from Dice.com
        4. **View Results**: Jobs will be displayed in a table format
        5. **Download**: Click the download button to get an Excel file with all the results
        
        **Note**: Toggle "Easy Apply Only" to filter jobs that can be applied to directly through Dice.com, or turn it off to see all available positions.
        """)

if __name__ == "__main__":
    main()