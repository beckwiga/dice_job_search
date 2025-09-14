from dice_scraper import scrape_dice_jobs
import pandas as pd

if __name__ == "__main__":
    query = "Data Architect"
    limit = 25
    easy_apply_only = True

    jobs = scrape_dice_jobs(query, limit=limit, easy_apply_filter=easy_apply_only)
    df = pd.DataFrame(jobs)

    print(df.head())  # Preview results
    df.to_csv("dice_jobs_output.csv", index=False)
    print("Saved to dice_jobs_output.csv")
