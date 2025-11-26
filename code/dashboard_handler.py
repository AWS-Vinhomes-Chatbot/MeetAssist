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
    - get_overview_stats: Get statistics for overview page
    - get_customers: Get all customers
    - get_consultants: Get all consultants
    - get_appointments: Get appointments with filters
    - get_programs: Get community programs
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
            if action == 'get_overview_stats':
                result = handle_get_overview_stats(conn)
            elif action == 'get_customers':
                result = handle_get_customers(conn, body)
            elif action == 'get_consultants':
                result = handle_get_consultants(conn, body)
            elif action == 'get_appointments':
                result = handle_get_appointments(conn, body)
            elif action == 'get_programs':
                result = handle_get_programs(conn, body)
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


def handle_get_overview_stats(conn) -> Dict:
    """Get overview statistics for dashboard"""
    try:
        stats = {}
        
        with conn.cursor() as cur:
            # Total customers
            cur.execute("SELECT COUNT(*) FROM customer WHERE isdisabled = false")
            stats['total_customers'] = cur.fetchone()[0]
            
            # Total consultants
            cur.execute("SELECT COUNT(*) FROM consultant WHERE isdisabled = false")
            stats['total_consultants'] = cur.fetchone()[0]
            
            # Total appointments
            cur.execute("SELECT COUNT(*) FROM appointment")
            stats['total_appointments'] = cur.fetchone()[0]
            
            # Appointments by status
            cur.execute("""
                SELECT status, COUNT(*) 
                FROM appointment 
                GROUP BY status
            """)
            status_counts = {row[0]: row[1] for row in cur.fetchall()}
            stats['appointments_by_status'] = status_counts
            
            # Pending appointments
            stats['pending_appointments'] = status_counts.get('pending', 0)
            
            # Completed appointments
            stats['completed_appointments'] = status_counts.get('completed', 0)
            
            # Active programs (upcoming)
            cur.execute("SELECT COUNT(*) FROM communityprogram WHERE status = 'upcoming' AND isdisabled = false")
            stats['active_programs'] = cur.fetchone()[0]
            
            # Total programs
            cur.execute("SELECT COUNT(*) FROM communityprogram WHERE isdisabled = false")
            stats['total_programs'] = cur.fetchone()[0]
            
            # Average rating
            cur.execute("SELECT AVG(rating) FROM appointmentfeedback")
            avg_rating = cur.fetchone()[0]
            stats['average_rating'] = round(float(avg_rating), 2) if avg_rating else 0
            
            # Recent appointments (last 7 days)
            cur.execute("""
                SELECT COUNT(*) FROM appointment 
                WHERE createdat >= CURRENT_DATE - INTERVAL '7 days'
            """)
            stats['recent_appointments'] = cur.fetchone()[0]
            
            # Total program participants
            cur.execute("SELECT COUNT(*) FROM programparticipant")
            stats['total_participants'] = cur.fetchone()[0]
        
        logger.info(f"Overview stats retrieved: {stats}")
        return success_response(stats)
        
    except Exception as e:
        logger.error(f"Error getting overview stats: {str(e)}", exc_info=True)
        return error_response(f"Failed to get overview stats: {str(e)}", 500)


def handle_get_customers(conn, body: Dict) -> Dict:
    """Get customers with optional filters"""
    try:
        limit = body.get('limit', 100)
        offset = body.get('offset', 0)
        search = body.get('search', '')
        
        query = """
            SELECT customerid, fullname, email, phonenumber, dateofbirth, 
                   createdat, isdisabled, notes
            FROM customer
            WHERE isdisabled = false
        """
        params = []
        
        if search:
            query += " AND (fullname ILIKE %s OR email ILIKE %s)"
            params.extend([f'%{search}%', f'%{search}%'])
        
        query += " ORDER BY createdat DESC LIMIT %s OFFSET %s"
        params.extend([limit, offset])
        
        with conn.cursor() as cur:
            cur.execute(query, params)
            rows = cur.fetchall()
            columns = [desc[0] for desc in cur.description]
            
            # Get total count
            count_query = "SELECT COUNT(*) FROM customer WHERE isdisabled = false"
            if search:
                count_query += " AND (fullname ILIKE %s OR email ILIKE %s)"
                cur.execute(count_query, [f'%{search}%', f'%{search}%'])
            else:
                cur.execute(count_query)
            total = cur.fetchone()[0]
        
        customers = [dict(zip(columns, row)) for row in rows]
        
        logger.info(f"Retrieved {len(customers)} customers")
        return success_response({
            "customers": customers,
            "total": total,
            "limit": limit,
            "offset": offset
        })
        
    except Exception as e:
        logger.error(f"Error getting customers: {str(e)}", exc_info=True)
        return error_response(f"Failed to get customers: {str(e)}", 500)


def handle_get_consultants(conn, body: Dict) -> Dict:
    """Get consultants with optional filters"""
    try:
        limit = body.get('limit', 100)
        offset = body.get('offset', 0)
        
        query = """
            SELECT consultantid, fullname, email, phonenumber, imageurl,
                   specialties, qualifications, joindate, createdat, isdisabled
            FROM consultant
            WHERE isdisabled = false
            ORDER BY createdat DESC
            LIMIT %s OFFSET %s
        """
        
        with conn.cursor() as cur:
            cur.execute(query, [limit, offset])
            rows = cur.fetchall()
            columns = [desc[0] for desc in cur.description]
            
            # Get total count
            cur.execute("SELECT COUNT(*) FROM consultant WHERE isdisabled = false")
            total = cur.fetchone()[0]
        
        consultants = [dict(zip(columns, row)) for row in rows]
        
        logger.info(f"Retrieved {len(consultants)} consultants")
        return success_response({
            "consultants": consultants,
            "total": total,
            "limit": limit,
            "offset": offset
        })
        
    except Exception as e:
        logger.error(f"Error getting consultants: {str(e)}", exc_info=True)
        return error_response(f"Failed to get consultants: {str(e)}", 500)


def handle_get_appointments(conn, body: Dict) -> Dict:
    """Get appointments with optional filters"""
    try:
        limit = body.get('limit', 100)
        offset = body.get('offset', 0)
        status = body.get('status')  # Optional: pending, confirmed, completed, cancelled
        
        query = """
            SELECT 
                a.appointmentid, a.date, a.time, a.duration, a.meetingurl,
                a.status, a.description, a.createdat, a.updatedat,
                c.fullname as customer_name, c.email as customer_email,
                cs.fullname as consultant_name, cs.email as consultant_email
            FROM appointment a
            JOIN customer c ON a.customerid = c.customerid
            JOIN consultant cs ON a.consultantid = cs.consultantid
        """
        params = []
        
        if status:
            query += " WHERE a.status = %s"
            params.append(status)
        
        query += " ORDER BY a.date DESC, a.time DESC LIMIT %s OFFSET %s"
        params.extend([limit, offset])
        
        with conn.cursor() as cur:
            cur.execute(query, params)
            rows = cur.fetchall()
            columns = [desc[0] for desc in cur.description]
            
            # Get total count
            count_query = "SELECT COUNT(*) FROM appointment"
            if status:
                count_query += " WHERE status = %s"
                cur.execute(count_query, [status])
            else:
                cur.execute(count_query)
            total = cur.fetchone()[0]
        
        appointments = [dict(zip(columns, row)) for row in rows]
        
        logger.info(f"Retrieved {len(appointments)} appointments")
        return success_response({
            "appointments": appointments,
            "total": total,
            "limit": limit,
            "offset": offset
        })
        
    except Exception as e:
        logger.error(f"Error getting appointments: {str(e)}", exc_info=True)
        return error_response(f"Failed to get appointments: {str(e)}", 500)


def handle_get_programs(conn, body: Dict) -> Dict:
    """Get community programs with optional filters"""
    try:
        limit = body.get('limit', 100)
        offset = body.get('offset', 0)
        status = body.get('status')  # Optional: upcoming, ongoing, completed
        
        query = """
            SELECT programid, programname, date, description, content,
                   organizer, url, isdisabled, status, createdat,
                   (SELECT COUNT(*) FROM programparticipant pp 
                    WHERE pp.programid = cp.programid) as participant_count
            FROM communityprogram cp
            WHERE isdisabled = false
        """
        params = []
        
        if status:
            query += " AND status = %s"
            params.append(status)
        
        query += " ORDER BY date DESC LIMIT %s OFFSET %s"
        params.extend([limit, offset])
        
        with conn.cursor() as cur:
            cur.execute(query, params)
            rows = cur.fetchall()
            columns = [desc[0] for desc in cur.description]
            
            # Get total count
            count_query = "SELECT COUNT(*) FROM communityprogram WHERE isdisabled = false"
            if status:
                count_query += " AND status = %s"
                cur.execute(count_query, [status])
            else:
                cur.execute(count_query)
            total = cur.fetchone()[0]
        
        programs = [dict(zip(columns, row)) for row in rows]
        
        logger.info(f"Retrieved {len(programs)} programs")
        return success_response({
            "programs": programs,
            "total": total,
            "limit": limit,
            "offset": offset
        })
        
    except Exception as e:
        logger.error(f"Error getting programs: {str(e)}", exc_info=True)
        return error_response(f"Failed to get programs: {str(e)}", 500)


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