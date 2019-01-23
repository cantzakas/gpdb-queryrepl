# Greenplum Database Query Replay & Replicate utility

## Pre-start checklist

- Make sure Greenplum Database utilities are in the execution path:

  ```sh
  #!/bin/bash
  
  # Make sure gpbackup utility is in the execution path by sourcing greenplum_path.sh file
  source /usr/local/greenplum-db/greenplum_path.sh
  ```

- Check the status of the source and target Greenplum Database systems:
  
  ```sh
  #!/bin/bash
  
  # Display a brief summary of the state of the Greenplum Database system. Similar to -b (brief status) option
  gpstate
  ```
  
  or 
  
  ```sh
  #!/bin/bash
  
  # Display a detailed status information for the Greenplum Database system
  gpstate -s
  ```
  
- Check the available free space in the host filesystem, i.e. in `$MASTER_DATA_DIRECTORY` (where database data and log files are stored) or `/tmp` (or similar), on both the source and the target Greenplum Database systems.

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
# Update the `YYYYMMDD` and `YYYYMMDDhhmmss` parameter values to match your backup set timestamp
tar -cvzf $MASTER_DATA_DIRECTORY/backups/YYYYMMDD/YYYYMMDDhhmmss/gpbackup_YYYYMMDDhhmmss.tar.gz / 
	$MASTER_DATA_DIRECTORY/backups/YYYYMMDD/YYYYMMDDhhmmss/gpbackup_YYYYMMDDhhmmss_*.*
```

#### Notes

1. `gpbackup` and `gprestore` utilities are available with Greenplum Database software v4.3.18 or later. If you are using Greenplum Database software release earlier than v4.3.18, then you can use the `pg_dump` utility to extract a database into a single script file or other archive file. To restore, you must use the corresponding `pg_restore` utility (if the dump file is in archive format), or you can use a client program such as `psql` (if the dump file is in plain text format). 

  #### Examples ####
  
  - Dump the object definitions of a Greenplum Database in tar file format suitable for input into `pg_restore` utility, including distribution policy information:
  
  ```sh
  pg_dump -Ft --gp-syntax --schema-only mydb > mydb.tar
  ```
  
  - Dump the object definitions of a Greenplum Database into a custom-format archive file suitable for input into `pg_restore` utility, including distribution policy information:
  
  ```sh
  pg_dump -Fc --gp-syntax --schema-only mydb > mydb.dump
  ```
  
  - Reload an archive file into a (freshly created) database named newdb:

  ```sh
  pg_restore -d newdb mydb.dump
  ```
  
2. The dump file produced by `pg_dump` does not contain the statistics used by the optimizer to make query planning decisions. Therefore, it is wise to run `ANALYZE` after restoring from a dump file to ensure good performance.

### Update logging level in source database system

For the Query Replay & Replicate utility to operate properly, it needs to process at the targer database the same queries that are executed in the source, so the full query statement needs to be captured into the log files. This requires the `log_min_messages` parameter be set to '__warning__' and the `log_statement` parameter be set to '__all__'.

Use the `gpconfig` utility to check the active values set for the `log_min_messages` and `log_statement` parameters in the cluster. i.e.

```sh
#!/bin/bash

gpconfig -c log_min_messages -v warning
```

and, 

```sh
#!/bin/bash

gpconfig -c log_statement -v all
```

If the parameter values don't match the expected values, update them and then reload the new configuration settings to the database, as shown below: 

```sh
#!/bin/bash

gpconfig -c log_min_messages -v warning
gpconfig -c log_statement -v all
gpstop -u
```

#### Notes

1. Alternatively, you can also use the `psql` utility to connect to the database cluster and check the active values, using the `SHOW <name>` command:

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

### Compress source database daily log files

Updating logging levels to '__all__' has the side-effect that database log file grows very large. This can be difficult to manage in clusters where there are limited disk resources or large/many transactions on the database (or both). In such clusters, it is highly recommended that database log files gets compressed, preferably on a daily basis. i.e.

```sh
tee -a /tmp/gpdb-logs-compress.sh <<- EOF

#!/bin/bash

YYYY=`date --date="yesterday" '+%Y'`; \
MM=`date --date="yesteday" '+%m'`; \
DD=`date --date="yesterday" '+%d'`; \
tar -cvjf /tmp/gpdb-logs-${YYYY}${MM}${DD}.tbz2 \
  $MASTER_DATA_DIRECTORY/pg_log/gpdb-${YYYY}-${MM}-${DD}*.csv &> /dev/null
EOF

chmod +x /tmp/gpdb-logs-compress.sh
```

#### Notes

1. As previously mentioned, database log file can grow very large when logging level is set to '__all__'; before making and throughout such a change is in place, check regurarly for available free space in the host filesystem, i.e. in `$MASTER_DATA_DIRECTORY` (where log files are stored) or `/tmp` (where our script above, stores the compressed log files).

### Schedule log files compression

The `cron` daemon can be used to run tasks in the background at specific times; there are a couple of ways we can update `cron` and schedule the execution of `gpdb-logs-compress.sh` utility which was defined in the previous step:

- Use the `crontab -e` command  to open your user account’s crontab file. Commands in this file run with your user account’s permissions. If you want a command to run with system permissions, use the `sudo crontab -e` command to open the root account’s crontab file or the `su -c “crontab -e”` command if user account is not in the `sudoers` group. At this point, you may be asked to select an editor; select any of the available by typing its number and press Enter. Add the following line into the editor and save:

  ```sh
  # Run gpdb-logs-compress.sh script at 09:00AM, every day 
  # and also disable email output.
  0 9 * * * /tmp/gpdb-logs-compress.sh >/dev/null 2>&1
  ```
  
  *The `cron` utility syntax can be tricky - check online, there are some pretty cool Cron Expression Generators online you can use to update the frequency and time when you want to setup your script execution.*
  
- Alternatively, "export" your existing `crontab` tasks into a file, append the new task at the end of the file and finally, push it back:

  ```sh
  # Update YYYYMMDD parameter value, and export existing crontab tasks
  crontab -l > crontab_YYYYMMDD
  
  # Append new task into list of existing
  tee -a crontab_YYYYMMDD <<- EOF
  0 9 * * * /tmp/gpdb-logs-compress.sh >/dev/null 2>&1
  EOF
  
  # Update cron with updated task list
  crontab crontab_YYYYMMDD
  ```

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
  
  # Update the `user`, `target-host` and `directory` values to match your cluster information
  scp QueryReplicator_vx.y.tar user@host:directory/QueryReplicator_vx.y.tar
  tar -xvf QueryReplicator_vx.y.tar
  ```

In both cases, the utility should be installed on the master of the cluster in which the target version of Greenplum is installed.

### Import Database DDL

- Use the metadata and query statistics files previously created in the [Export Source Database DDL](https://github.com/cantzakas/gpdb-queryrepl#export-source-database-ddl)step on the Greenplum Database master host. Move the files located in the `$MASTER_DATA_DIRECTORY/backups/YYYYMMDD/YYYYMMDDhhmmss/` directory on the source system to the target system, i.e.

  ```sh
  #!/bin/bash

  # Update the `YYYYMMDD` and `YYYYMMDDhhmmss` parameter values to match your backup set timestamp
  cd $MASTER_DATA_DIRECTORY/backups/YYYYMMDD/YYYYMMDDhhmmss/

  # Update the `user`, `target-host` and `directory` values to match your cluster information
  scp gpbackup_YYYYMMDDhhmmss.tar.gz \
    user@target-host:directory/gpbackup_YYYYMMDDhhmmss.tar.gz
  tar -xzvf gpbackup_YYYYMMDDhhmmss.tar.gz
  ```

- Login into the target host system and navigate into the directory where you previously moved the backupset files and uncompress:

  ```sh
  #!/bin/bash
  
  # Update directory value to match the location where you previously uncompressed the backup set package 
  cd directory. 
  # Update the `YYYYMMDDhhmmss` parameter value to match your backup set timestamp.
  # Uncompress the backup set file in place
  tar -xzvf gpbackup_YYYYMMDDhhmmss.tar.gz
  ```

- If the target database has been previously created then drop and re-create it (or create it for the first time). Finally restore all schemas and tables in the backup set for the indicated timestamp (without the data), the global Greenplum Database metadata and query plan statistics using the `gprestore` utility:

  ```sh
  #!/bin/bash
  
  # Update GPBACKUP_DATABASE_NAME parameter value to match the name of the database you want to export
  $ export GPBACKUP_DATABASE_NAME='update_to_match_your_database_name'

  $ dropdb $GPBACKUP_DATABASE_NAME

  # Update the `YYYYMMDDhhmmss` parameter value to match your backup set timestamp
  $ gprestore --timestamp YYYYMMDDhhmmss --create-db --metadata-only --with-globals --with-stats
  ```

### Import source database log files into the target system

- Use `scp` or `sftp` or any similar utility to tranfer the database log files from the source to the target system:

  ```sh
  # Update the `user`, `target-host` and `directory` values to match your cluster information
  scp -r /tmp/gpdb-logs-*.tbz2 user@target-host:directory
  ```

- Login into the target host system and navigate into the directory where you previously moved the backupset files (no need to uncompress)

## Run Replay & Replicate Utility

### Setup the utility config file

The configuration file has the following structure:

```
[Result_DB]
# Information about database in which the results, the external table and the excluded queries are stored
ResultDatabaseIPAddress=00.00.00.00
ResultDatabaseUsername=login_user
ResultDatabasePort=5432
ResultDatabaseName=target_db
# name of the table where you want to store the results of the Query replicator tool computation
ResultTableName=results_table_name

[Replay_DB]
# Information about database in which the queries will be executed
ReplayDatabaseIPAddress=00.00.00.00
ReplayDatabaseUsername=******
ReplayDatabasePort=5432
ReplayDatabase=source_db

[Log_Source]
# Definition of the external table that reads the Greenplum log files
logExternalTable=public.test_20180423
logFileName=/home/gpadmin/Customer/logs/gpdb-2018-04-23_000000.csv.gz
logFlagCompress=True

[Excluded_Queries]
excludedQueryTable= public.t_list_excluded_query
excludedQueryFile= GPDB_t_list_excluded_query.csv

[Run_Settings]
# Database Settings
StatementTimeout=15s
Optimizer=on
Standard_Conforming_Strings=on

#Type of Execution
#  - session ==> the queries are executed in session as in the original DB
#               (useful in case of temp tables)
#  - distinct ==> the queries are deduplicated (faster because less queries to run)
ReplayTypeExecution=session

# Flag to know if the SELECT, INSERT and UPDATE must be executed as EXPLAIN
ReplayRunExplain=True

# Number of concurrent threads
ReplayNumThreads = 10
```

Make sure you check all parameter values defined in the configuration file and update accordingly, before running the utility.

### Run the utility

The syntax for the `queryreplicator.py` utility command is:

```shell
python queryreplicator.py -f config.ini [-rLeca]
```

#### Required parameters

- The location of the [utility configuration file](https://github.com/cantzakas/gpdb-queryrepl#setup-the-utility-config-file) is specified with the `-f` parameter

#### Optional parameters
- To replay the queries, use the `-r` parameter
- To create (or recreate) the external table which reads the input database log file(s), use the `-L` parameter
- To create (or recreate) and load the table `t_list_excluded_query` that stores the patterns of the queries you want not to replay, use the `-e` parameter
- To create (or recreate) the target table that stores the result of each replayed query, user the `-c` parameter