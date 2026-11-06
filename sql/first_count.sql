-- LESSON 1: first count query (written by Claude at James's request, 1 Nov 2026).
-- Table: companies(company_number, category, status, inc_date_text, postcode, sic1)
--   inc_date_text is text like '01/07/2026' (day/month/year).
-- Returns one row per (year, quarter, category): year, quarter, category, companies

SELECT
    year(inc_date)    AS year,
    quarter(inc_date) AS quarter,
    category,
    count(*)          AS companies
FROM (
    -- Turn the text into a real date once, so year() and quarter() can use it.
    SELECT strptime(inc_date_text, '%d/%m/%Y') AS inc_date, category
    FROM companies
)
GROUP BY year, quarter, category
ORDER BY year, quarter, category;
