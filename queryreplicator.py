# -*- coding: utf-8 -*-
import datetime, time
import sys
import pygresql
from pygresql import pg
import os
import string
from multiprocessing import Process, Queue
import ConfigParser, argparse
import io
import re
import commands, subprocess 

current_path = os.path.dirname(os.path.abspath(__file__))
start_time = datetime.datetime.now().strftime("%Y%m%d  %H:%M:%S")

def update_progress(progress,queue_num):
    barLength = 40 # Modify this to change the length of the progress bar
    status = ""
    if isinstance(progress, int):
        progress = float(progress)

    block = int(round(barLength*progress))
    text = "\r\tQueue: "+ str(queue_num).rjust(2) + " - Percent: [{0}] {1}% {2}".format( "#"*block + "-"*(barLength-block), progress*100, status)
    #sys.stdout.write(text)
    #sys.stdout.flush()
    print text


def replaceChars(statement):
    statement = statement.replace("\"","\"\"")
    return statement


def Write_copyFile(copyFile, user_name, db, statement, query_length, Success, output, timestamp_start, timestamp_end):

    output = replaceChars(output)
    statement = replaceChars(statement)
    line = '' + start_time + '~"' +user_name + '"~"' + db + '"~"' + statement + '"~' + str(query_length) \
            + '~"' + str(Success) + '"~"' + output + '"~' + timestamp_start + '~' + timestamp_end +'\n'
    copyFile.write(line)


def checkAndRemovingComment(query):
    startComment = '/*'
    endComment = '*/'
    start = query.find(startComment)
    end = query.find(endComment)
    if (start == -1) or (end == -1):
        return query
    if start != 0:
        newquery = query[:start-1]
    else:
        newquery = ""
    newquery = newquery + query[end+2:]

    return newquery

def checkEventDetails(event_detail):

    parameters = None
    if(event_detail != None):
        parameters = re.findall(r'= \'(.*?)\'', event_detail)

    return parameters

def replacePrepareStatement(query, list_params):

    i = 1
    for param in list_params:

        tmpstring = "$" + str(i)

        query = query.replace(tmpstring, '\'' +param+ '\'')
        i = i+1

    return query



def checkParticularConditions(query, event_detail):

    list_params = checkEventDetails(event_detail)
    if(event_detail != None):
        query = replacePrepareStatement(query, list_params)

    return query



def Replay_Queue_Thread(queue,queue_num):
    ## Read from the queue
    # connect to the log database
    counter=0
    db_Result = pg.connect(dbname=ResultDatabaseName, host=ResultDatabaseIPAddress, port=ResultDatabasePort, user=ResultDatabaseUsername)
    db_Replay = pg.connect(dbname=ReplayDatabase, host=ReplayDatabaseIPAddress, port=ReplayDatabasePort, user=ReplayDatabaseUsername)
    set_Replay_Database_GUC(db_Replay)
    
    #open a temporary file to write the results for then use the copy command and copy in batch
    file_name= current_path + '/copy/copy' + str(os.getpid()) +'.txt'
    # open with in locking mode
    copyFile = open(file_name, 'w+')
    
    while True:
        entry = queue.get()         # Read from the queue and do nothing
        # we received the terminated signal there are no more stuff to consume
        if (entry == None):
            break

        # taking current database parameters (username, database and statement)
        user_name = entry[0]
        statement = entry[2]
        event_detail = entry[3]
        query_length = entry[7]
        thread_nb_queries = entry[8]

        statement = checkParticularConditions(statement, event_detail)
        statement = checkAndRemovingComment(statement)
        if statement.strip():
           type_qry=statement.split()[0].lower()
        list_qry_explain= ['select','update','insert']
        if ReplayRunExplain == True and type_qry in list_qry_explain:
           statement = "EXPLAIN " + statement
        timestamp_start = datetime.datetime.now().strftime("%Y%m%d %H:%M:%S")
        Success, output = Check_Query(entry, statement, db_Replay)
        timestamp_end = datetime.datetime.now().strftime("%Y%m%d %H:%M:%S")
        counter = counter +1
        step = max(1, thread_nb_queries / 40)
        if counter%step == 0:
            update_progress(counter/(thread_nb_queries * 1.0), queue_num)
        #copy to file
        Write_copyFile(copyFile, user_name, ReplayDatabase, statement, query_length, Success, output, timestamp_start, timestamp_end)
        

    update_progress(counter/(thread_nb_queries * 1.0), queue_num)
    copyFile.close()
    Load_Copy_Files(db_Result, file_name)

    try:
        os.remove(file_name)
    except OSError:
        pass
    
    # we are terminating close all
    db_Replay.close()

def Check_Query(input, statement, db_Replay):
    user_name = input[0]
    output = 'No error'
    query_output=[]

    Success = True
    # check the query result
    try:
        query_results = db_Replay.query(statement)

        if query_results != None and type(query_results) is not str:
           query_output = query_results.getresult()
           output = '\n'.join(str(item[0]) for item in query_output)
           
    except (pg.ProgrammingError, ValueError) as exception:
        #print('FAILURE')
        Success = False
        output = str(exception)
    except pg.InternalError as exception:
        #print('FAILURE')
        Success = False
        output = str(exception)
    # success or other exceptions
    else:
        #print('SUCCESS')
        Success = True
        

    return Success, output


def Create_Reset_Result_Table(db,quiet):
    print "\n### Create of the result table " + ResultTableName

    try:
        flag_Table_Exist=False
        query_results=db.query("SELECT c.oid::regclass from pg_class c \
          inner join pg_namespace n  on c.relnamespace = n.oid \
          where (case when split_part('" + ResultTableName + "','.',2) = '' then split_part(\'"+ ResultTableName +"',\'.\',1) \
             else split_part('" + ResultTableName + "','.',2) end) = c.relname \
          and (case when split_part('"+ ResultTableName + "','.',2) = '' then 'public' \
              else split_part('"+ ResultTableName + "','.',1) end) = n.nspname ")
        if len(query_results.getresult()) == 1:
            flag_Table_Exist=True

    except Exception as exception:
        print('\tERROR: System error' + str(exception))
        sys.exit(-1)

    if flag_Table_Exist == False:
       question="Do you want to create the result table " +  ResultTableName + "? (y/n) [y]" 
    else:
       question="The table " +  ResultTableName + " already exists.\nDo you want to erase it? (y/n) [n]"
    
    if quiet == False:
        print "\n" + question
        while True:
            choice = raw_input().lower()
            if choice == 'y' or (flag_Table_Exist == False and choice == ''):
                break
            elif choice == 'n' or (flag_Table_Exist == True and choice == ''):
                return True
            else:
                print "\n" + question
                print("Please respond with y, Y, n or N")

    try:
       query_results=db.query('DROP table if exists ' + ResultTableName)
       query_results=db.query('CREATE TABLE ' + ResultTableName + ' (sequence serial , Run_Timestamp timestamp, userQuery text, database text, \
                       statement text, query_length integer, success text, output text, timestamp_start timestamp, timestamp_end timestamp)')
       print('\tResult table ' + ResultTableName + ' created')

       return True
    except Exception as exception:
       print('\tERROR: Unable to create result table: System error' + str(exception))
       return True
                
# This function creates the external table in order to read the log file (defined in the config file)
def Create_ExtTable_On_Log(db_Connect_String):
    if (logFlagCompress == False):
        str_Ext_Table_Command='\'cat ' + logFileName + ' 2> /dev/null || true\''
    else:
        str_Ext_Table_Command='\'zcat ' + logFileName + ' 2> /dev/null || true\''
    print "\n### Create of external table on the file" + logFileName
    
    runenv = os.environ
    # Run the query
    runcmd = ['psql',
              '-d', db_Connect_String,
              '-v', 'ON_ERROR_STOP=1',
              '-v', 'v_ext_table_name=' + logExternalTable,
              '-v', 'v_read_file=' + str_Ext_Table_Command ,
              '-f', './scripts/GPDB_read_master_log_template.sql']

    p= subprocess.Popen(runcmd, env=runenv, stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE)

    std, err = p.communicate()
    rc = p.returncode
    if rc <> 0:
        print ("\tSQL command failed: " \
                "\n\t\tSQL: ./scripts/GPDB_read_master_log_template.sql'" + \
                "\n\t\tERROR:" + err)
        raise Exception
    else:
        print('\tExternal table on log file %s created') % logExternalTable

def Init_Excluded_Queries_Table(db_Connect_String,quiet):
    print "\n### Init the table that contains the excluded queries"

    if quiet == False:
        question="Do you want to (re)init the table " + excludedQueryTable + " containing the excluded queries"+ \
                "\nfrom the file " + excludedQueryFile + "? (y/n) [n]" 
        print "\n" + question
        while True:
            choice = raw_input().lower()
            if choice == 'y':
                break
            elif choice == 'n' or choice == '':
                return True
            else:
                print "\n" + question
                print("Please respond with y, Y, n or N")
    
    runenv = os.environ
    # Run the query
    runcmd = ['psql',
              '-d', db_Connect_String,
              '-1', '',
              '-v', 'ON_ERROR_STOP=1',
              '-v', 'v_excludedQueryTable=' + excludedQueryTable,
              '-v', 'v_excludedQueryFile=\'' + current_path + '/scripts/' + excludedQueryFile  + '\'',
              '-f', './scripts/GPDB_t_list_excluded_query.sql']

    p= subprocess.Popen(runcmd, env=runenv, stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE)

    std, err = p.communicate()
    rc = p.returncode
    if rc <> 0:
        print ("\tSQL command failed: " \
                "\n\t\tSQL: './scripts/GPDB_t_list_excluded_query.sql'" + \
                "\n\t\tFile: "+ current_path + "/scripts/" + excludedQueryFile + \
                "\n\t\tERROR:" + err)
        raise Exception
    else:
        print('\tTable for excluded queries %s created and loaded') % excludedQueryTable
            

# select query from log file
# statement is a variable which show the sql operation to search
# limit in case we want to limit the number of rows
def Identify_Queries_To_Replay(db):
    print "\n### Identify the queries to replay from the log " + logFileName

    if (ReplayTypeExecution == 'session'):
       query = 'create temp table tmp_query_replay as (select user_name, database_name, debug_query_string, event_detail,gp_session_id,thread,gp_command_count,query_length \n' \
            + 'from ( select user_name, database_name, debug_query_string, event_time \n' \
            + ', substr(gp_session_id,4) as  gp_session_id,mod(substr(gp_session_id,4)::integer,'+ str(ReplayNumThreads)+') as thread\n' \
            + ', substr(gp_command_count,4)::integer as gp_command_count\n' \
            + ', length(debug_query_string) as query_length\n' \
            + ', max(case when event_detail like \'parameters: $1 = %\' then event_detail else null end) ' \
            + 'over (partition by session_start_time,gp_session_id,process_id,gp_command_count) as event_detail\n' \
            + ', rank() over (partition by session_start_time,gp_session_id,process_id,gp_command_count order by event_time) as rank \n' \
            + 'from ' +logExternalTable + '\n' \
            + 'where event_message not like \'duration:%\' and event_message not ilike \'execute %: insert%values%(%)%\'' \
            + ' and debug_query_string not ilike \'%BEGIN%\' and debug_query_string not ilike \'%COMMIT%\'' \
            + 'and database_name=' + '\'' + ReplayDatabase + '\'' \
            + ') T where rank = 1) distributed randomly;\n' \
            + 'analyze tmp_query_replay;\n' \
            + 'select *, count(*) over (partition by thread) as thread_nb_queries\n' \
            + 'from tmp_query_replay \n' \
            + 'where not exists (select 1 from ' + excludedQueryTable + ' where lower(debug_query_string) similar to lower(query_pattern)) '\
            + ' order by gp_session_id,gp_command_count;\n'
    else:
        query = 'create temp table tmp_query_replay as (select user_name, database_name, debug_query_string\n' \
            + ', max(case when event_detail like \'parameters: $1 = %\' then event_detail else null end) as event_detail\n' \
            + ' from ' + logExternalTable + '\n' \
            + 'where event_message not like \'duration:%\' and event_message not ilike \'execute %: insert%values%(%)%\'' \
            + ' and debug_query_string not ilike \'%BEGIN%\' and debug_query_string not ilike \'%COMMIT%\'' \
            + ' and database_name=' + '\'' + ReplayDatabase + '\'' \
            + 'group by 1,2,3) distributed randomly;\n' \
            + 'analyze tmp_query_replay;\n' \
            + 'select *, count(*) over (partition by thread) as thread_nb_queries\n' \
            + 'from (select *,null as gp_session_id' \
            + ',mod((row_number() over())::integer,'+ str(ReplayNumThreads)+') as thread\n' \
            + ',0 as gp_command_count, length(debug_query_string) as query_length \n' \
            + 'from tmp_query_replay\n' \
            + ' where not exists (select 1 from ' + excludedQueryTable + ' where lower(debug_query_string) similar to lower(query_pattern))) T;\n'
    query_results=db.query(query).getresult()
    return query_results

            
#Query output table
def Load_Copy_Files(db, filePath):
    statement = 'COPY ' + ResultTableName + '(run_timestamp, userQuery, database, statement,query_length, success, output, timestamp_start, timestamp_end) FROM \'' + filePath + '\''
    statement = statement + ' WITH CSV DELIMITER \'~\' LOG ERRORS SEGMENT REJECT LIMIT 100 PERCENT;'
    db.query(statement)

def get_LogFileName_Ext_Table(db):
    query_results=db.query('select split_part(command,\' \',2) from pg_exttable where reloid = \'' + logExternalTable + '\'::regclass;').getresult()
    line = query_results[0]
    return line[0]

#Query output table
def count_ResultTable(db):
    query= 'SELECT count(*) from ' + ResultTableName + \
           ' where run_timestamp = \'' + start_time + '\';'
    query_results=db.query(query).getresult()
    line = query_results[0]
    return line[0]

def count_ResultTable_Success(db):
    query= 'SELECT count(*) from ' + ResultTableName + \
            ' where success=\'True\' \
            and run_timestamp = \'' + start_time + '\';'
    query_results=db.query(query).getresult()
    line = query_results[0]
    return line[0]

def extract_Error_Summary(db):
    statement = "COPY (select arr_error[1] || coalesce (arr_error[3],'') \
                ,count(*) from (select output \
                ,string_to_array(split_part(output,E'\\n',1),'\"') as arr_error \
                from " + ResultTableName + \
                " where success = 'False' \
                and run_timestamp = \'" + start_time + "\') T \
                group by 1 \
                order by 2 desc) TO '"+ current_path + "/log/" + ResultTableName +"_Error_Summary.csv' WITH CSV;"
    db.query(statement)


def set_Replay_Database_GUC(db):
    try:
        query_results=db.query("set optimizer=" + Optimizer + ";")
        query_results=db.query("set statement_timeout='" + StatementTimeout + "';")
        query_results=db.query("set application_name='replay';")
        query_results=db.query("set standard_conforming_strings=" + Standard_Conforming_Strings + ";")

    except Exception as exception:
         print('ERROR: System error' + str(exception))
         sys.exit(-1)
         
def Replay_Queries(db_Result):

    # main query to get all queries from log
    query_results = Identify_Queries_To_Replay(db_Result)
    
    print "\n### Replay queries on DB " +  ReplayDatabase + " using "  + str(ReplayNumThreads) + " threads"

    # create a pool of processes synchronized by queues
    processes = []
    queues = []

    for i in range(0, int(ReplayNumThreads)):
        queue = Queue()
        queues.append(queue)
        proc = Process(target=Replay_Queue_Thread, args=((queue),i))
        proc.start()
        processes.append(proc)

    if(query_results):
        # sends every query to the queue of a specific thread
        for entry in query_results:
            queues[entry[5]].put(entry, False)

        #sends a None to all thread queues to terminate and close the queues
        for queue in queues:
            queue.put(None, False)
            queue.close()

        #join all processe before terminating
        for proc in processes:
            proc.join()


def Check_Settings(config_file,quiet):
    # Load the configuration file
    with open(config_file) as cfg:
        sample_config = cfg.read()
    config = ConfigParser.RawConfigParser(allow_no_value=True)
    config.optionxform = str 
    config.readfp(io.BytesIO(sample_config))

    # List all contents
    print("\n### Content of config file:" + config_file)
    for section in config.sections():
        print("\n\tSection: %s" % section)
        for options in config.options(section):
            print("\t\t%s:\t%s" % (options.ljust(30),
                                  config.get(section, options)))
    if quiet == False:
        question="Do you want to continue? (y/n) [y]" 
        print "\n" + question
        while True:
            choice = raw_input().lower()
            if choice == 'y' or choice == '':
                break
            elif choice == 'n':
                sys.exit(0)
            else:
                print "\n" + question
                print("Please respond with y, Y, n or N")

    global file_name_summary
    global ResultDatabaseName
    global ResultDatabaseIPAddress
    global ResultDatabaseUsername
    global ResultDatabasePort
    global ResultTableName

    global ReplayDatabase
    global ReplayDatabaseIPAddress
    global ReplayDatabaseUsername
    global ReplayDatabasePort

    global logExternalTable
    global logFileName
    global logFlagCompress

    global excludedQueryTable
    global excludedQueryFile
    
    global StatementTimeout
    global Optimizer
    global Standard_Conforming_Strings
    global ReplayTypeExecution
    global ReplayRunExplain
    global ReplayNumThreads
    
    ResultDatabaseName=config.get("Result_DB", "ResultDatabaseName")
    ResultDatabaseIPAddress=config.get("Result_DB", "ResultDatabaseIPAddress")
    ResultDatabaseUsername=config.get("Result_DB", "ResultDatabaseUsername")
    ResultDatabasePort=config.getint("Result_DB", "ResultDatabasePort")
    ResultTableName=config.get("Result_DB", "ResultTableName")

    ReplayDatabase=config.get("Replay_DB", "ReplayDatabase")
    ReplayDatabaseIPAddress=config.get("Replay_DB", "ReplayDatabaseIPAddress")
    ReplayDatabaseUsername=config.get("Replay_DB", "ReplayDatabaseUsername")
    ReplayDatabasePort = config.getint("Replay_DB", "ReplayDatabasePort")

    logExternalTable=config.get("Log_Source", "logExternalTable")
    logFileName=config.get("Log_Source", "logFileName")
    logFlagCompress=config.get("Log_Source", "logFlagCompress")

    excludedQueryTable=config.get("Excluded_Queries", "excludedQueryTable")
    excludedQueryFile=config.get("Excluded_Queries", "excludedQueryFile")
    
    StatementTimeout=config.get("Run_Settings", "StatementTimeout")
    Optimizer=config.get("Run_Settings", "Optimizer")
    Standard_Conforming_Strings=config.get("Run_Settings", "Standard_Conforming_Strings")
    ReplayTypeExecution=config.get("Run_Settings", "ReplayTypeExecution")
    ReplayRunExplain=config.getboolean("Run_Settings", "ReplayRunExplain")
    ReplayNumThreads=config.getint("Run_Settings", "ReplayNumThreads")

    file_name_summary = current_path + '/log/' + ResultTableName + "_" + datetime.datetime.now().strftime("%Y%m%d") +'.txt'

    f = open(file_name_summary, 'a')
  
    f.write('################################################################################\n')
    f.write('###  Run: ' + start_time.ljust(67) + '###\n')
    f.write('################################################################################\n')
    f.write('### Result database:             ' + ResultDatabaseName.ljust(44) + '###\n')
    f.write('### Result table:                ' + ResultTableName.ljust(44) + '###\n')
    f.write('###                                                                          ###\n')
    f.write('### Replay Database:             ' + ReplayDatabase.ljust(44) + '###\n')
    f.write('### Input log:                   ' + logFileName.ljust(44) + '###\n')
    f.write('###                                                                          ###\n')
    f.write('### Optimizer:                   ' + Optimizer.ljust(44) + '###\n')
    f.write('### Statement_timeout:           ' + StatementTimeout.ljust(44) + '###\n')
    f.write('### Standard_Conforming_Strings: ' + Standard_Conforming_Strings.ljust(44) + '###\n')
    f.write('################################################################################\n')
    f.close

def Trace_End(file_name):

    f = open(file_name, 'a')

    f.write('###  Check any reject during the loading of ' + ResultTableName + ' ####\n')
    f.write('     select * from gp_read_error_log(\'' + ResultTableName + '\')')
    f.write('     where cmdtime >= \'' + start_time + '\'\n')
    f.write('################################################################################\n')
    f.write('###  End: ' + datetime.datetime.now().strftime("%Y%m%d  %H:%M:%S").ljust(67) + '###\n')
    f.write('################################################################################\n')
    f.write('\n')
    f.close

def Extract_Statistics(file_name,db):
    try:
        total_query = count_ResultTable(db)
        success_query = count_ResultTable_Success(db)
        extract_Error_Summary(db)
    except Exception as e:
        print("Sql error:" + str(e))
        sys.exit(-1)
            
    f = open(file_name, 'a')

    f.write('\n')
    f.write('################################################################################\n')
    f.write('### Statistics from the result table: ' + ResultTableName.ljust(39) + '###\n')
    f.write('###                                                                          ###\n')
    f.write('### Executed Queries:      ' + str(total_query).ljust(50)+ '###\n')
    f.write('### Succeeded Queries:     ' + str(success_query).ljust(50)+ '###\n')
    f.write('### Failed Queries:        ' + str(total_query - success_query).ljust(50)+ '###\n')
    f.write('################################################################################\n')
    f.close()


def Argument_Parsing(argv):
    parser = argparse.ArgumentParser()
    parser.add_argument("-f", help="configuration file", required=True)
    parser.add_argument("-a", help="Quiet - useful if executed with nohup",action="store_true")
    parser.add_argument("-r", help="Replay the queries from the logs",action="store_true")
    parser.add_argument("-c", help="Clean the output result table of the Query replicator tool",action="store_true")
    parser.add_argument("-e", help="Create or reset table with excluded queries",action="store_true")
    parser.add_argument("-L", help="Create External table on top of log file",action="store_true")

    args = parser.parse_args()
    return args


def main(argv):
    # Parse the command line parameters
    args = Argument_Parsing(argv)

    if args.a:
        quiet = True
    else:
        quiet = False
    
    # Parse the configuration file
    config_file=args.f
    Check_Settings(config_file,quiet)

    # connect to the Result and Replay database
    db_Result = pg.connect(dbname=ResultDatabaseName, host=ResultDatabaseIPAddress, port=ResultDatabasePort, user=ResultDatabaseUsername)
    db_Result_Connect_String = 'host='+ResultDatabaseIPAddress + ' port=' + str(ResultDatabasePort) + ' user=' + ResultDatabaseUsername + ' dbname=' + ResultDatabaseName
    db_Replay = pg.connect(dbname=ReplayDatabase, host=ReplayDatabaseIPAddress, port=ReplayDatabasePort, user=ReplayDatabaseUsername)
    


    # Output: clean the output result table of the Query replicator tool
    if args.c:
        Create_Reset_Result_Table(db_Result,quiet)

    # Log: Create External table on top of log file
    if args.L:
        Create_ExtTable_On_Log(db_Result_Connect_String)

    # Check the log file read by the external table and the log file in the config file
    Ext_Table_File = get_LogFileName_Ext_Table(db_Result)
    if Ext_Table_File <> logFileName:
       print 'ERROR: difference between file read in external table and file in ' + config_file
       print '    - file read in external table:' + Ext_Table_File
       print '    - file in properties.py:      ' + logFileName
       sys.exit(1)

    # Excluded: Create or reset excluded table
    if args.e:
        Init_Excluded_Queries_Table(db_Result_Connect_String,quiet)

    # If the option -r is not used, the queries are not replayed
    if not args.r:
        sys.exit(0)
        
    Replay_Queries(db_Result)
    
    Extract_Statistics(file_name_summary,db_Result)

    Trace_End(file_name_summary)
    
    db_Result.close()


# start main function
if __name__ == "__main__":
    main(sys.argv)
