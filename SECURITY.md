# Security Policy

## Reporting a Vulnerability

If you discover a security vulnerability in this project, please report it by opening an issue on GitHub.

## Supported Versions

Only the latest version on the `main` branch is supported.

## Security Considerations

This application scrapes public job listings from Dice.com. Keep in mind:

- **No authentication data is stored.** The app does not collect or store user credentials.
- **Network requests go to dice.com only.** The scraper fetches pages from `dice.com` and does not follow external redirects.
- **Rate limiting.** The app includes delays between requests to avoid overwhelming the target site.
- **Dependencies.** Run `pip-audit -r requirements.txt` periodically to check for known vulnerabilities.
- **No secrets in source.** This project contains no API keys, tokens, or credentials.
