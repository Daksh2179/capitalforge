"""Asset directory: a cached, searchable list of tradable US equities
(symbol + company name), used for fuzzy company-name search. Fetched
once from Alpaca's Trading API, not a per-request lookup.
"""