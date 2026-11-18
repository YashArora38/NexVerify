from . import company, listing, news, rbi, sebi

# All five run at the same time; the ones that need the page's claims wait for
# the listing checker (it is usually done in a few seconds).
AGENTS = {
    "listing": listing.run,
    "rbi": rbi.run,
    "sebi": sebi.run,
    "company": company.run,
    "news": news.run,
}
