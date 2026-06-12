{% snapshot economic_indicators_snapshot %}

{{
    config(
        target_schema='snapshots',
        unique_key="country_code || '-' || year",
        strategy='check',
        check_cols=[
            'gdp_usd',
            'inflation_rate',
            'unemployment_rate',
            'exports_pct_gdp',
            'population',
            'gdp_growth_rate',
            'crisis_flag'
        ]
    )
}}

select * from {{ ref('economic_indicators') }}

{% endsnapshot %}
