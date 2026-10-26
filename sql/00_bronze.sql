create schema if not exists bronze;

create table if not exists bronze.livros (
    id            bigserial primary key,
    fonte_url     text,
    payload       jsonb,
    _execucao_id  text,
    _ingestao_em  timestamptz default now()
);
