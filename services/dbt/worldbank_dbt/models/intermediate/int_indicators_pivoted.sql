with indicators as (

    select * from {{ ref('stg_indicators') }}

),

countries as (

    select country_code
    from {{ ref('country_metadata') }}

),

pivoted as (

    select
        i.country_code,
        i.year,

        max(case when i.indicator_name = 'gdp_usd'
                 then i.value end)               as gdp_usd,

        max(case when i.indicator_name = 'inflation_rate'
                 then i.value end)               as inflation_rate,

        max(case when i.indicator_name = 'unemployment_rate'
                 then i.value end)               as unemployment_rate,

        max(case when i.indicator_name = 'exports_pct_gdp'
                 then i.value end)               as exports_pct_gdp,

        max(case when i.indicator_name = 'population'
                 then i.value end)               as population

    from indicators i
    inner join countries c
        on i.country_code = c.country_code

    group by i.country_code, i.year

)

select * from pivoted
