with source as (

    select * from {{ source('worldbank_raw', 'indicator_records') }}

),

cleaned as (

    select
        country_code,
        indicator_code,
        indicator_name,
        year,
        value,
        ingested_at

    from source

    -- defensive filtering, even though ingestion already does this
    where country_code is not null
      and length(country_code) = 3
      and year between 2000 and 2023
      and value is not null

)

select * from cleaned
