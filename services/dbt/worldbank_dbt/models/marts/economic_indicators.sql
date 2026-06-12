with pivoted as (

    select * from {{ ref('int_indicators_pivoted') }}

),

with_growth as (

    select
        *,
        lag(gdp_usd) over (
            partition by country_code
            order by year
        ) as prev_year_gdp

    from pivoted

),

countries as (

    select
        country_code,
        country_name,
        region,
        income_group,
        capital

    from {{ ref('country_metadata') }}

),

final as (

    select
        w.country_code,
        c.country_name,
        c.region,
        c.income_group,
        c.capital,
        w.year,

        -- raw indicators
        w.gdp_usd,
        w.inflation_rate,
        w.unemployment_rate,
        w.exports_pct_gdp,
        w.population,

        -- derived: GDP growth rate (YoY %)
        case
            when w.prev_year_gdp is null or w.prev_year_gdp = 0 then null
            else ((w.gdp_usd - w.prev_year_gdp) / w.prev_year_gdp) * 100
        end as gdp_growth_rate,

        -- derived: log GDP (for regression)
        case
            when w.gdp_usd > 0 then ln(w.gdp_usd)
            else null
        end as log_gdp,

        -- derived: crisis flag (three-way: 1/0/null)
        case
            when w.inflation_rate is null or w.unemployment_rate is null then null
            when w.inflation_rate > 10 and w.unemployment_rate > 8 then 1
            else 0
        end as crisis_flag,

        -- derived: extreme inflation flag (three-way: 1/0/null)
        case
            when w.inflation_rate is null then null
            when w.inflation_rate > 100 then 1
            else 0
        end as is_extreme_inflation,

        -- derived: income group ordinal encoding
        case c.income_group
            when 'Low income' then 0
            when 'Lower middle income' then 1
            when 'Upper middle income' then 2
            when 'High income' then 3
        end as income_group_enc

    from with_growth w
    inner join countries c
        on w.country_code = c.country_code

)

select * from final
