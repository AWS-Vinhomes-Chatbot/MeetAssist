import json
import os
from typing import Dict, Any
import boto3
from services.postgres import PostgreSQLService
from util.lambda_logger import create_logger

# Get the Lambda function name from the environment
lambda_function_name = os.environ.get("AWS_LAMBDA_FUNCTION_NAME", "AdminHandler")

# Setup logging
logger = create_logger(lambda_function_name)

# Initialize AWS clients
session = boto3.session.Session()
sm_client = session.client(service_name="secretsmanager")

# Environment variables
RDS_HOST = os.getenv("RDS_HOST")
RDS_PORT = os.getenv("RDS_PORT", "5432")
RDS_DATABASE = os.getenv("RDS_DATABASE", "postgres")
SECRET_NAME = os.getenv("SECRET_NAME")

# Initialize PostgreSQL service
pg = PostgreSQLService(secret_client=sm_client, db_host=RDS_HOST, db_name=RDS_DATABASE, log=logger)


def lambda_handler(event: Dict[str, Any], context: Any) -> Dict:
    """
    Admin Lambda Handler - Xử lý các request từ Admin Dashboard
    
    Supported actions:
    - execute_sql: Execute raw SQL statements (INSERT/UPDATE/DELETE/SELECT)
    - get_tables: Get list of all tables in database
    - get_table_schema: Get schema information for a specific table
    - get_stats: Get database statistics
    """
    logger.info(f"Event received: {json.dumps(event)}")
    
    try:
        # Parse request body
        body = event.get('body', {})
        if isinstance(body, str):
            body = json.loads(body)
        
        action = body.get('action')
        
        if not action:
            return error_response("Missing 'action' in request body", 400)
        
        # Connect to database
        pg.set_secret(SECRET_NAME)
        conn = pg.connect_to_db()
        
        if not conn:
            return error_response("Failed to connect to database", 500)
        
        try:
            # Route to appropriate handler
            if action == 'execute_sql':
                result = handle_execute_sql(conn, body)
            elif action == 'get_tables':
                result = handle_get_tables(conn)
            elif action == 'get_table_schema':
                result = handle_get_table_schema(conn, body)
            elif action == 'get_stats':
                result = handle_get_stats(conn)
            else:
                result = error_response(f"Unknown action: {action}", 400)
            
            return result
            
        finally:
            conn.close()
            logger.info("Database connection closed")
    
    except Exception as e:
        logger.error(f"Error processing request: {str(e)}", exc_info=True)
        return error_response(f"Internal server error: {str(e)}", 500)


def handle_execute_sql(conn, body: Dict) -> Dict:
    """
    Execute raw SQL statements from admin
    Supports: INSERT, UPDATE, DELETE, SELECT
    Blocks: DROP, TRUNCATE, ALTER (for safety)
    """
    try:
        sql_query = body.get('sql', '').strip()
        
        if not sql_query:
            return error_response("Missing 'sql' in request body", 400)
        
        # Validate SQL - block dangerous operations
        dangerous_keywords = ['DROP', 'TRUNCATE', 'ALTER', 'CREATE DATABASE', 'DROP DATABASE']
        sql_upper = sql_query.upper()
        
        for keyword in dangerous_keywords:
            if keyword in sql_upper:
                return error_response(f"Operation '{keyword}' is not allowed for safety reasons", 403)
        
        # Check if it's a SELECT query
        is_select = sql_upper.strip().startswith('SELECT')
        
        # Execute the query
        with conn.cursor() as cur:
            cur.execute(sql_query)
            
            if is_select:
                # Fetch results for SELECT queries
                rows = cur.fetchall()
                columns = [desc[0] for desc in cur.description] if cur.description else []
                
                # Convert rows to list of dicts
                result_data = []
                for row in rows:
                    result_data.append(dict(zip(columns, row)))
                
                logger.info(f"SELECT query executed successfully. Rows returned: {len(result_data)}")
                
                return success_response({
                    "message": "SELECT query executed successfully",
                    "rows_returned": len(result_data),
                    "data": result_data
                })
            else:
                # For INSERT/UPDATE/DELETE, commit and return affected rows
                conn.commit()
                rows_affected = cur.rowcount
                
                logger.info(f"SQL executed successfully. Rows affected: {rows_affected}")
                
                return success_response({
                    "message": "SQL executed successfully",
                    "rows_affected": rows_affected
                })
        
    except Exception as e:
        conn.rollback()
        logger.error(f"Error executing SQL: {str(e)}", exc_info=True)
        return error_response(f"Failed to execute SQL: {str(e)}", 500)


def handle_get_tables(conn) -> Dict:
    """Get list of all tables in the database"""
    try:
        query = """
            SELECT 
                table_name,
                (SELECT COUNT(*) FROM information_schema.columns 
                 WHERE table_schema = 'public' AND table_name = t.table_name) as column_count
            FROM information_schema.tables t
            WHERE table_schema = 'public'
            AND table_type = 'BASE TABLE'
            ORDER BY table_name
        """
        
        with conn.cursor() as cur:
            cur.execute(query)
            rows = cur.fetchall()
        
        tables = [{"table_name": row[0], "column_count": row[1]} for row in rows]
        
        logger.info(f"Retrieved {len(tables)} tables")
        
        return success_response({
            "tables": tables,
            "total_tables": len(tables)
        })
        
    except Exception as e:
        logger.error(f"Error getting tables: {str(e)}", exc_info=True)
        return error_response(f"Failed to get tables: {str(e)}", 500)


def handle_get_table_schema(conn, body: Dict) -> Dict:
    """Get schema information for a specific table"""
    try:
        table_name = body.get('table_name')
        
        if not table_name:
            return error_response("Missing 'table_name' in request body", 400)
        
        query = """
            SELECT 
                column_name,
                data_type,
                character_maximum_length,
                is_nullable,
                column_default
            FROM information_schema.columns
            WHERE table_schema = 'public'
            AND table_name = %s
            ORDER BY ordinal_position
        """
        
        with conn.cursor() as cur:
            cur.execute(query, (table_name,))
            rows = cur.fetchall()
        
        if not rows:
            return error_response(f"Table '{table_name}' not found", 404)
        
        columns = []
        for row in rows:
            columns.append({
                "column_name": row[0],
                "data_type": row[1],
                "max_length": row[2],
                "nullable": row[3] == 'YES',
                "default": row[4]
            })
        
        logger.info(f"Retrieved schema for table '{table_name}' with {len(columns)} columns")
        
        return success_response({
            "table_name": table_name,
            "columns": columns,
            "total_columns": len(columns)
        })
        
    except Exception as e:
        logger.error(f"Error getting table schema: {str(e)}", exc_info=True)
        return error_response(f"Failed to get table schema: {str(e)}", 500)


def handle_get_stats(conn) -> Dict:
    """Get database statistics"""
    try:
        # Get table count and row counts
        stats_query = """
            SELECT 
                schemaname,
                tablename,
                n_live_tup as row_count
            FROM pg_stat_user_tables
            WHERE schemaname = 'public'
            ORDER BY n_live_tup DESC
        """
        
        with conn.cursor() as cur:
            cur.execute(stats_query)
            results = cur.fetchall()
        
        table_stats = []
        total_rows = 0
        
        for row in results:
            row_count = row[2] or 0
            table_stats.append({
                "table_name": row[1],
                "row_count": row_count
            })
            total_rows += row_count
        
        stats = {
            "total_tables": len(table_stats),
            "total_rows": total_rows,
            "table_stats": table_stats
        }
        
        logger.info(f"Database stats retrieved: {stats}")
        
        return success_response(stats)
        
    except Exception as e:
        logger.error(f"Error getting stats: {str(e)}", exc_info=True)
        return error_response(f"Failed to get stats: {str(e)}", 500)


def success_response(data: Dict, status_code: int = 200) -> Dict:
    """Build success response"""
    return {
        'statusCode': status_code,
        'headers': {
            'Access-Control-Allow-Origin': '*',
            'Access-Control-Allow-Headers': 'Content-Type,Authorization',
            'Access-Control-Allow-Methods': 'POST,GET,OPTIONS',
            'Content-Type': 'application/json'
        },
        'body': json.dumps(data, default=str)  # default=str for handling datetime
    }


def error_response(message: str, status_code: int = 500) -> Dict:
    """Build error response"""
    return {
        'statusCode': status_code,
        'headers': {
            'Access-Control-Allow-Origin': '*',
            'Access-Control-Allow-Headers': 'Content-Type,Authorization',
            'Access-Control-Allow-Methods': 'POST,GET,OPTIONS',
            'Content-Type': 'application/json'
        },
        'body': json.dumps({
            'error': message
        })
    }