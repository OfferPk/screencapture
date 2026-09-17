from datetime import datetime
OUTFILE = os.getenv(
    "OUTFILE",
    f"/app/out/businesses_{datetime.now():%Y%m%d_%H%M}.csv",
)
