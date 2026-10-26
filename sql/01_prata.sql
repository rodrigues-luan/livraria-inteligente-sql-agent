create schema if not exists prata;

create or replace view prata.livros as
with ultima as (
    select
        payload,
        _ingestao_em,
        row_number() over (
            partition by trim(payload->>'upc')                                        -- R1
            order by _ingestao_em desc, id desc                                       -- R1
        ) as ordem
    from bronze.livros
)
select
    trim(payload->>'upc')                                                             as upc,           -- R1 R7
    trim(payload->>'titulo')                                                          as titulo,        -- R7
    case
        when trim(payload->>'categoria_raw') in ('Default', 'Add a comment')          -- R6
            then 'Sem categoria'                                                      -- R6
        else trim(payload->>'categoria_raw')                                          -- R7
    end                                                                               as categoria,
    substring(payload->>'preco_raw' from '[0-9]+(?:\.[0-9]+)?')::numeric(10,2)        as preco_gbp,     -- R2
    case split_part(trim(payload->>'rating_raw'), ' ', 2)                             -- R3
        when 'One'   then 1                                                           -- R3
        when 'Two'   then 2                                                           -- R3
        when 'Three' then 3                                                           -- R3
        when 'Four'  then 4                                                           -- R3
        when 'Five'  then 5                                                           -- R3
    end                                                                               as rating,
    coalesce(substring(payload->>'estoque_raw' from '([0-9]+)')::int, 0)              as estoque_qtd,   -- R4
    trim(payload->>'n_reviews_raw')::int                                              as n_reviews,     -- R5 R7
    trim(payload->>'url')                                                             as url,           -- R7
    _ingestao_em
from ultima
where ordem = 1;                                                                      -- R1
