# Greenplum Database Query Replay & Replicate utility

## Prepare source database system
### Export source Database DDL

Backup all schemas and tables from the source database, including the global Greenplum Database system objects and query statistics, as shown [below](https://gist.github.com/cantzakas/bbdd6d30cec88bdcbf00850fc1a3a7a0):

```sh
#!/bin/sh

# Make sure gpbackup utility is in the execution path by sourcing greenplum_path.sh file
source /usr/local/greenplum-db/greenplum_path.sh

# Update GPBACKUP_DATABASE_NAME parameter value to match the name of the database you want to export
export GPBACKUP_DATABASE_NAME='update_to_match_your_database_name'

# Backup all schemas and tables in the database defined with the $GPBACKUP_DATABASE_NAME parameter, 
# including global Greenplum Database system objects and query statistics
gpbackup --dbname $GPBACKUP_DATABASE_NAME --metadata-only --with-stats

```

Metadata files are created on the Greenplum Database master host in the `$MASTER_DATA_DIRECTORY/backups/YYYYMMDD/YYYYMMDDhhmmss/` directory. 

### Update logging level in source database system

For the Query Replay & Replicate utility to operate properly, it needs to process at the targer database the same queries that are executed in the source, so the full query statement needs to be captured into the log files. This requires the `log_min_messages` parameter be set to '__warning__' and the `log_statement` parameter be set to '__all__'.

Fist, connect into the source database and check the active values set for the `log_min_messages` and `log_statement` parameters in the cluster. i.e. you can use the `psql` utility as shown below:

```sql
$ psql -d template1 -c "SHOW log_min_messages;"

 log_min_messages 
------------------
 warning
(1 row)
```
```sql
$ psql -d template1 -c "SHOW log_statement;"

 log_statement 
---------------
 all
(1 row)

```

If the parameter values don't match the expected values, update them and then reload the new configuration settings to the database, as shown below: 

```sql
$ gpconfig -c log_min_messages -v warning
$ gpconfig -c log_statement -v all
$ gpstop -u
```

### Compress source database daily log files
Updating logging levels to '__all__' has the side-effect that database log file grows very large. This can be difficult to manage in clusters where there are limited disk resources or large/many transactions on the database (or both). In such clusters, it is highly recommended that database log files gets compressed, preferably on a daily basis. i.e.

```sh
$ YYYY=`date --date="yesterday" '+%Y'` 
$ MM=`date --date="today" '+%m'` 
$ DD=`date --date="today" '+%d'` 
$ tar -cvjf /tmp/gpdb-logs-${YYYY}${MM}${DD}.tbz2 $MASTER_DATA_DIRECTORY/pg_log/gpdb-${YYYY}-${MM}-${DD}*.csv &> /dev/null
```

This script

## 2 - Prepare target database system

### 2.1 - Setup Query Replicate utility in the target system

### 2.2 - Import Database DDL

### 2.3 - Import source database log files into the target system

## 3 - Run Replay & Replicate Utility

### 3.1 - Setup the utility config file

### 3.2 - Run the utility



