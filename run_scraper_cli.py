import argparse
import pandas as pd
import json
from dice_scraper import scrape_dice_jobs

def main():
    parser = argparse.ArgumentParser(
        description="Scrape Dice.com job listings and export to CSV or JSON"
    )
    parser.add_argument(
        "--query", "-q",
        type=str,
        required=True,
        help="Job search query (e.g., 'Data Architect')"
    )
    parser.add_argument(
        "--limit", "-l",
        type=int,
        default=20,
        help="Maximum number of jobs to fetch"
    )
    parser.add_argument(
        "--easy", "-e",
        action="store_true",
        help="Filter for Easy Apply jobs only"
    )
    parser.add_argument(
        "--output", "-o",
        type=str,
        default=None,
        help="Custom output filename (without extension)"
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Export results as JSON instead of CSV"
    )

    args = parser.parse_args()

    print(f"\n🔍 Searching Dice.com for: {args.query}")
    print(f"📦 Limit: {args.limit}")
    print(f"⚙️ Easy Apply Only: {args.easy}")
    print(f"📁 Output Format: {'JSON' if args.json else 'CSV'}\n")

    jobs = scrape_dice_jobs(
        query=args.query,
        limit=args.limit,
        easy_apply_filter=args.easy
    )

    if not jobs:
        print("❌ No jobs found or scraping failed.")
        return

    # Determine output filename
    base_name = args.output if args.output else f"dice_jobs_{args.query.replace(' ', '_')}"
    file_ext = "json" if args.json else "csv"
    full_filename = f"{base_name}.{file_ext}"

    # Export
    if args.json:
        with open(full_filename, "w", encoding="utf-8") as f:
            json.dump(jobs, f, indent=2)
    else:
        df = pd.DataFrame(jobs)
        df.to_csv(full_filename, index=False)

    print(f"✅ Saved {len(jobs)} jobs to {full_filename}")

if __name__ == "__main__":
    main()