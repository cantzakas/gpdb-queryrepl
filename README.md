# Greenplum Database Query Replay & Replicate utility

## 1 - Prepare source database system
### 1.1 - Export source Database DDL using gpbackup utility
### 1.2 - Update the logging level of the source Database cluster
### 1.3 - Compress source database daily log files

## 2 - Prepare target database system
### 2.1 - Setup Query Replicate utility in the target system
### 2.2 - Import Database DDL
### 2.3 - Import source database log files into the target system

## 3 - Run Replay & Replicate Utility
### 3.1 - Setup the utility config file
### 3.2 - Run the utility



