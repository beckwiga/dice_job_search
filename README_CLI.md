COMPILE:
pyinstaller --onefile "\dice_job_search\run_scraper_cli.py" --clean

USAGE:
run_scraper_cli.exe --query "Data Engineer" --limit 500 --easy --output _Data_Engineer_jobs --json

