import os
QUERY = os.getenv("QUERY", "coffee shops in Austin, TX")
MAX_RESULTS = int(os.getenv("MAX_RESULTS", "200"))
OUTFILE = os.getenv("OUTFILE", "/app/out/businesses.csv")
