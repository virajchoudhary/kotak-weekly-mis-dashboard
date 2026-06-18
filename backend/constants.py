from __future__ import annotations

RAW_SHEET_NAME = "Brokerwise Data (67)"

RAW_COLUMN_ALIASES = {
    "MAIN ARN CODE": "arn_code",
    "BROKER NAME": "broker_name",
    "Category": "category",
    "Sub Category": "sub_category",
    "Scheme Group": "sch_group",
    "Scheme Type": "asset_class",
    "K (AUM)": "kotak_aum",
    "I (AUM)": "cams_aum",
    "K (GS)": "kotak_gross_sales",
    "I (GS)": "cams_gross_sales",
    "K (NS)": "kotak_net_sales",
    "I (NS)": "cams_net_sales",
    "K SIP Count": "kotak_sip_count",
    "I Sip Count": "cams_sip_count",
    "K SIP BOOK": "kotak_sip_book",
    "I SIP BOOK": "cams_sip_book",
}

TEXT_COLUMNS = [
    "category",
    "sub_category",
    "arn_code",
    "broker_name",
    "sch_group",
    "asset_class",
]

NUMERIC_COLUMNS = [
    "kotak_aum",
    "cams_aum",
    "kotak_gross_sales",
    "cams_gross_sales",
    "kotak_net_sales",
    "cams_net_sales",
    "kotak_sip_count",
    "cams_sip_count",
    "kotak_sip_book",
    "cams_sip_book",
]

MARKET_SHARE_COLUMNS = {
    "ms_aum": ("kotak_aum", "cams_aum"),
    "ms_gross_sales": ("kotak_gross_sales", "cams_gross_sales"),
    "ms_net_sales": ("kotak_net_sales", "cams_net_sales"),
    "ms_sip_count": ("kotak_sip_count", "cams_sip_count"),
    "ms_sip_book": ("kotak_sip_book", "cams_sip_book"),
}

DB_ROW_COLUMNS = TEXT_COLUMNS + NUMERIC_COLUMNS + list(MARKET_SHARE_COLUMNS)

# Order is taken directly from the supplied weekly Summary.xlsx template.
SCHEME_MASTER = [
    ("Arbitrage Fund", "Equity"),
    ("Balanced Hybrid Fund/Aggressive Hybrid Fund", "Equity"),
    ("Banking and PSU Fund", "Debt"),
    ("Capital Protection Oriented Schemes", "Debt"),
    ("CHILDRENS FUND", "Equity"),
    ("Conservative Hybrid Fund", "Debt"),
    ("Corporate Bond Fund", "Debt"),
    ("Credit Risk Fund", "Debt"),
    ("DIVIDEND YIELD FUND", "Equity"),
    ("Dynamic Asset Allocation/Balanced Advantage", "Equity"),
    ("Dynamic Bond Fund", "Debt"),
    ("ELSS", "Equity"),
    ("ELSS(C)", "Equity"),
    ("Equity Others (C)", "Equity"),
    ("Equity Savings Fund", "Equity"),
    ("Fixed Term Plan", "Debt"),
    ("Flexi Cap Fund", "Equity"),
    ("Floater Fund", "Debt"),
    ("Focused Fund", "Equity"),
    ("Fund of Fund - Domestic", "Debt"),
    ("Fund of Fund - Overseas", "Debt"),
    ("Gilt Fund", "Debt"),
    ("GILT FUND WITH 10 YEAR CONSTANT DURATION", "Debt"),
    ("INCOME/DEBT (INTERVAL)", "Debt"),
    ("Index Funds - Debt", "Debt"),
    ("Index Funds - EQUITY", "Equity"),
    ("Large & Mid Cap Fund", "Equity"),
    ("Large Cap Fund", "Equity"),
    ("Liquid Fund", "Debt"),
    ("Long Duration Fund", "Debt"),
    ("Low Duration Fund", "Debt"),
    ("Medium Duration Fund", "Debt"),
    ("Medium to Long Duration Fund", "Debt"),
    ("Mid Cap Fund", "Equity"),
    ("Money Market Fund", "Debt"),
    ("Multi Asset Allocation", "Equity"),
    ("Multi Cap Fund", "Equity"),
    ("OTHER DEBT (C)", "Debt"),
    ("Overnight Fund", "Debt"),
    ("RETIREMENT FUND", "Equity"),
    ("Sectoral/Thematic Funds", "Equity"),
    ("Short Duration Fund", "Debt"),
    ("Small cap Fund", "Equity"),
    ("Ultra Short Duration Fund", "Debt"),
    ("Value Fund/Contra Fund", "Equity"),
]

FINTECH_EXCLUSIONS = {
    "Capital Protection Oriented Schemes",
    "INCOME/DEBT (INTERVAL)",
    "OTHER DEBT (C)",
}

SUMMARY_METRICS = [
    ("kotak_aum", "cams_aum", "ms_aum"),
    ("kotak_gross_sales", "cams_gross_sales", "ms_gross_sales"),
    ("kotak_net_sales", "cams_net_sales", "ms_net_sales"),
    ("kotak_sip_count", "cams_sip_count", "ms_sip_count"),
    ("kotak_sip_book", "cams_sip_book", "ms_sip_book"),
]

