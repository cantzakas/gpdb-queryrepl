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

### 1.2 - Update the logging level of the source Database cluster

### 1.3 - Compress source database daily log files

## 2 - Prepare target database system

### 2.1 - Setup Query Replicate utility in the target system

### 2.2 - Import Database DDL

### 2.3 - Import source database log files into the target system

## 3 - Run Replay & Replicate Utility

### 3.1 - Setup the utility config file

### 3.2 - Run the utility



