# Greenplum Database Query Replay & Replicate utility

## Prepare source database system
### Export source Database DDL

Backup all schemas and tables from the source database, including the global Greenplum Database system objects and query statistics, as shown [below](https://gist.github.com/cantzakas/bbdd6d30cec88bdcbf00850fc1a3a7a0). Backup set files are created on the Greenplum Database master host in the `$MASTER_DATA_DIRECTORY/backups/YYYYMMDD/YYYYMMDDhhmmss/` directory, which we will also package in a compressed file, in preparation for transfering to the target system:

```sh
#!/bin/bash

# Make sure gpbackup utility is in the execution path by sourcing greenplum_path.sh file
source /usr/local/greenplum-db/greenplum_path.sh

# Update GPBACKUP_DATABASE_NAME parameter value to match the name of the database you want to export
export GPBACKUP_DATABASE_NAME='update_to_match_your_database_name'

# Backup all schemas and tables in the database defined with the $GPBACKUP_DATABASE_NAME parameter, 
# including global Greenplum Database system objects and query statistics
gpbackup --dbname $GPBACKUP_DATABASE_NAME --metadata-only --with-stats

# Package backup set into a compressed file in preparation for transfering it to the target system
tar -cvzf $MASTER_DATA_DIRECTORY/backups/YYYYMMDD/YYYYMMDDhhmmss/gpbackup_YYYYMMDDhhmmss.tar.gz / 
	$MASTER_DATA_DIRECTORY/backups/YYYYMMDD/YYYYMMDDhhmmss/gpbackup_YYYYMMDDhhmmss_*.*
```

***Note***: *Don't forget to update the `YYYYMMDD`, `YYYYMMDDhhmmss` values to match your backup set timestamp.*

### Update logging level in source database system

For the Query Replay & Replicate utility to operate properly, it needs to process at the targer database the same queries that are executed in the source, so the full query statement needs to be captured into the log files. This requires the `log_min_messages` parameter be set to '__warning__' and the `log_statement` parameter be set to '__all__'.

Fist, connect into the source database and check the active values set for the `log_min_messages` and `log_statement` parameters in the cluster. i.e. you can use the `psql` utility as shown below:

```sql
$ psql -d template1
psql (8.3.23)
Type "help" for help.

template1=# SHOW log_min_messages;

log_min_messages 
------------------
warning
(1 row)
```

```sql
$ psql -d template1
psql (8.3.23)
Type "help" for help.

template1=# SHOW log_statement;

log_statement 
---------------
all
(1 row)
```

If the parameter values don't match the expected values, update them and then reload the new configuration settings to the database, as shown below: 

```sh
#!/bin/bash

gpconfig -c log_min_messages -v warning
gpconfig -c log_statement -v all
gpstop -u
```

### Compress source database daily log files
Updating logging levels to '__all__' has the side-effect that database log file grows very large. This can be difficult to manage in clusters where there are limited disk resources or large/many transactions on the database (or both). In such clusters, it is highly recommended that database log files gets compressed, preferably on a daily basis. i.e.

```sh
#!/bin/bash

YYYY=`date --date="yesterday" '+%Y'`; \
MM=`date --date="today" '+%m'`; \
DD=`date --date="today" '+%d'`; \
tar -cvjf /tmp/gpdb-logs-${YYYY}${MM}${DD}.tbz2 \
  $MASTER_DATA_DIRECTORY/pg_log/gpdb-${YYYY}-${MM}-${DD}*.csv &> /dev/null
```

### Schedule log files compression
TBD

## Prepare target database system

### Setup Query Replicate utility in the target system

There are a couple of different options on how to setup the Query replicate utility into your target Greenplum cluster system:

- Clone the utility code directly from its [Github repo](https://github.com/cantzakas/gpdb-queryrepl), if your target system has access to the internet and you already have (or the `gpadmin` user is allowed to install) the `git` utility on the host machine:

  ```sh
  #!/bin/bash
  
  pip install git --upgrade
  git clone https://github.com/cantzakas/gpdb-queryrepl.git
  cd gpdb-queryrepl
  ```

- Alternatively, you can download the [utility package](missing url for .tar file or similar) from the Github repo, transfer it over to the host machine and uncompress into a new folder.

  ```sh
  #!/bin/bash
  
  wget https://github.com/cantzakas/QueryReplicator_vx.y.tar
  scp QueryReplicator_vx.y.tar user@host:directory/QueryReplicator_vx.y.tar
  tar -xvf QueryReplicator_vx.y.tar
  ```

In both cases, the utility should be installed on the master of the cluster in which the target version of Greenplum is installed.

### Import Database DDL

Use the metadata and query statistics files previously created in the [Export Source Database DDL](https://github.com/cantzakas/gpdb-queryrepl#export-source-database-ddl)step on the Greenplum Database master host. Move the files located in the `$MASTER_DATA_DIRECTORY/backups/YYYYMMDD/YYYYMMDDhhmmss/` directory on the source system to the target system, i.e.

```sh
#!/bin/bash

# Update YYYYMMDD and YYYYMMDDhhmmss values to match your backup set timestamp  
cd $MASTER_DATA_DIRECTORY/backups/YYYYMMDD/YYYYMMDDhhmmss/

# Update the `user`, `target-host` and `directory` values to match your cluster information
scp gpbackup_YYYYMMDDhhmmss.tar.gz \
  user@target-host:directory/gpbackup_YYYYMMDDhhmmss.tar.gz
tar -xzvf gpbackup_YYYYMMDDhhmmss.tar.gz

```

, then login into the target host system, navigate into the directory where you previously moved the backupset files and uncompress:

```sh
#!/bin/bash

# Update directory value to match the location where you previously uncompressed the backup set package 
cd directory

# Update YYYYMMDDhhmmss value to match your backup set timestamp
tar -xzvf gpbackup_YYYYMMDDhhmmss.tar.gz
```

If the target database has been previously created then drop it, re-create it and finally restore all schemas and tables in the backup set for the indicated timestamp (without the data) , the global Greenplum Database metadata and query plan statistics:

```sh
#!/bin/bash
  
# Update GPBACKUP_DATABASE_NAME parameter value to match the name of the database you want to export
$ export GPBACKUP_DATABASE_NAME='update_to_match_your_database_name'

$ dropdb $GPBACKUP_DATABASE_NAME

# Update YYYYMMDDhhmmss value to match your backup set timestamp
$ gprestore --timestamp YYYYMMDDhhmmss --create-db --metadata-only --with-globals --with-stats
```

***Note***: *Don't forget to update the `YYYYMMDD`, `YYYYMMDDhhmmss` values to match your backup set timestamp. Also, update the `user`, `target-host` and `directory` values to match your target host environment.

### 2.3 - Import source database log files into the target system

## 3 - Run Replay & Replicate Utility

### 3.1 - Setup the utility config file

### 3.2 - Run the utility
