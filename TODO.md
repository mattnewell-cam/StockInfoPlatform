Finish getting basic company info: python manage.py backfill_company_data
We have 2000 companies uploaded to DB out of ~4000. DB is 270 MB full out of 500 max. So we need to slightly compress data. Maybe just by deleting very small / zero revenue US companies tbh. 
Financials are now in random order on website - need to define a structure. 
Still some companies with bad data e.g. missing income statements that will need rescraping. But only a few dozen prolly.