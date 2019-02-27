drop table if exists :v_excludedQueryTable;
create table :v_excludedQueryTable (query_pattern text);

COPY :v_excludedQueryTable from :v_excludedQueryFile WITH CSV;
