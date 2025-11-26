"""
Admin Service - Business logic for Admin Dashboard

This service handles all database queries and CRUD operations for the admin dashboard.
Separating logic from Lambda handler makes code cleaner and more testable.
"""

from typing import Dict, List, Any, Optional


class Admin:
    """Service class for admin-related database operations (queries + CRUD)"""
    
    def __init__(self, connection, logger=None):
        """
        Initialize AdminService
        
        Args:
            connection: PostgreSQL database connection
            logger: Optional logger instance
        """
        self.conn = connection
        self.log = logger
    
    def _log_info(self, message: str):
        if self.log:
            self.log.info(message)
    
    def _log_error(self, message: str):
        if self.log:
            self.log.error(message)

    # ==================== OVERVIEW STATS ====================
    
    def get_overview_stats(self) -> Dict[str, Any]:
        """
        Get overview statistics for dashboard
        
        Returns:
            Dict containing various statistics
        """
        stats = {}
        
        with self.conn.cursor() as cur:
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
            stats['pending_appointments'] = status_counts.get('pending', 0)
            stats['completed_appointments'] = status_counts.get('completed', 0)
            
            # Programs
            cur.execute("SELECT COUNT(*) FROM communityprogram WHERE status = 'upcoming' AND isdisabled = false")
            stats['active_programs'] = cur.fetchone()[0]
            
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
            
            # Total participants
            cur.execute("SELECT COUNT(*) FROM programparticipant")
            stats['total_participants'] = cur.fetchone()[0]
        
        self._log_info(f"Overview stats retrieved: {stats}")
        return stats

    # ==================== CUSTOMERS ====================
    
    def get_customers(
        self, 
        limit: int = 100, 
        offset: int = 0, 
        search: str = ''
    ) -> Dict[str, Any]:
        """
        Get customers with optional search filter
        
        Args:
            limit: Max number of records to return
            offset: Number of records to skip
            search: Search term for name/email
            
        Returns:
            Dict with customers list and pagination info
        """
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
        
        with self.conn.cursor() as cur:
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
        self._log_info(f"Retrieved {len(customers)} customers")
        
        return {
            "customers": customers,
            "total": total,
            "limit": limit,
            "offset": offset
        }

    # ==================== CONSULTANTS ====================
    
    def get_consultants(
        self, 
        limit: int = 100, 
        offset: int = 0
    ) -> Dict[str, Any]:
        """
        Get consultants list
        
        Args:
            limit: Max number of records to return
            offset: Number of records to skip
            
        Returns:
            Dict with consultants list and pagination info
        """
        query = """
            SELECT consultantid, fullname, email, phonenumber, imageurl,
                   specialties, qualifications, joindate, createdat, isdisabled
            FROM consultant
            WHERE isdisabled = false
            ORDER BY createdat DESC
            LIMIT %s OFFSET %s
        """
        
        with self.conn.cursor() as cur:
            cur.execute(query, [limit, offset])
            rows = cur.fetchall()
            columns = [desc[0] for desc in cur.description]
            
            cur.execute("SELECT COUNT(*) FROM consultant WHERE isdisabled = false")
            total = cur.fetchone()[0]
        
        consultants = [dict(zip(columns, row)) for row in rows]
        self._log_info(f"Retrieved {len(consultants)} consultants")
        
        return {
            "consultants": consultants,
            "total": total,
            "limit": limit,
            "offset": offset
        }

    # ==================== APPOINTMENTS ====================
    
    def get_appointments(
        self, 
        limit: int = 100, 
        offset: int = 0, 
        status: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Get appointments with optional status filter
        
        Args:
            limit: Max number of records to return
            offset: Number of records to skip
            status: Filter by status (pending, confirmed, completed, cancelled)
            
        Returns:
            Dict with appointments list and pagination info
        """
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
        
        with self.conn.cursor() as cur:
            cur.execute(query, params)
            rows = cur.fetchall()
            columns = [desc[0] for desc in cur.description]
            
            count_query = "SELECT COUNT(*) FROM appointment"
            if status:
                count_query += " WHERE status = %s"
                cur.execute(count_query, [status])
            else:
                cur.execute(count_query)
            total = cur.fetchone()[0]
        
        appointments = [dict(zip(columns, row)) for row in rows]
        self._log_info(f"Retrieved {len(appointments)} appointments")
        
        return {
            "appointments": appointments,
            "total": total,
            "limit": limit,
            "offset": offset
        }

    # ==================== PROGRAMS ====================
    
    def get_programs(
        self, 
        limit: int = 100, 
        offset: int = 0, 
        status: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Get community programs with optional status filter
        
        Args:
            limit: Max number of records to return
            offset: Number of records to skip
            status: Filter by status (upcoming, ongoing, completed)
            
        Returns:
            Dict with programs list and pagination info
        """
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
        
        with self.conn.cursor() as cur:
            cur.execute(query, params)
            rows = cur.fetchall()
            columns = [desc[0] for desc in cur.description]
            
            count_query = "SELECT COUNT(*) FROM communityprogram WHERE isdisabled = false"
            if status:
                count_query += " AND status = %s"
                cur.execute(count_query, [status])
            else:
                cur.execute(count_query)
            total = cur.fetchone()[0]
        
        programs = [dict(zip(columns, row)) for row in rows]
        self._log_info(f"Retrieved {len(programs)} programs")
        
        return {
            "programs": programs,
            "total": total,
            "limit": limit,
            "offset": offset
        }

    # ==================== DATABASE ADMIN ====================
    
    def get_tables(self) -> Dict[str, Any]:
        """
        Get list of all tables in the database
        
        Returns:
            Dict with tables list and count
        """
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
        
        with self.conn.cursor() as cur:
            cur.execute(query)
            rows = cur.fetchall()
        
        tables = [{"table_name": row[0], "column_count": row[1]} for row in rows]
        self._log_info(f"Retrieved {len(tables)} tables")
        
        return {
            "tables": tables,
            "total_tables": len(tables)
        }
    
    def get_table_schema(self, table_name: str) -> Dict[str, Any]:
        """
        Get schema information for a specific table
        
        Args:
            table_name: Name of the table
            
        Returns:
            Dict with table schema details
            
        Raises:
            ValueError: If table not found
        """
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
        
        with self.conn.cursor() as cur:
            cur.execute(query, (table_name,))
            rows = cur.fetchall()
        
        if not rows:
            raise ValueError(f"Table '{table_name}' not found")
        
        columns = [{
            "column_name": row[0],
            "data_type": row[1],
            "max_length": row[2],
            "nullable": row[3] == 'YES',
            "default": row[4]
        } for row in rows]
        
        self._log_info(f"Retrieved schema for table '{table_name}' with {len(columns)} columns")
        
        return {
            "table_name": table_name,
            "columns": columns,
            "total_columns": len(columns)
        }
    
    def get_database_stats(self) -> Dict[str, Any]:
        """
        Get database statistics (table counts, row counts)
        
        Returns:
            Dict with database statistics
        """
        query = """
            SELECT 
                schemaname,
                tablename,
                n_live_tup as row_count
            FROM pg_stat_user_tables
            WHERE schemaname = 'public'
            ORDER BY n_live_tup DESC
        """
        
        with self.conn.cursor() as cur:
            cur.execute(query)
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
        
        self._log_info(f"Database stats retrieved: {stats}")
        return stats
