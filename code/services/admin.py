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
            
            # Total feedbacks
            cur.execute("SELECT COUNT(*) FROM appointmentfeedback")
            stats['total_feedbacks'] = cur.fetchone()[0]
        
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
        status: Optional[str] = None,
        consultant_id: Optional[int] = None,
        customer_id: Optional[int] = None,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
        search: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Get appointments with optional filters
        
        Args:
            limit: Max number of records to return
            offset: Number of records to skip
            status: Filter by status (pending, confirmed, completed, cancelled)
            consultant_id: Filter by consultant ID
            customer_id: Filter by customer ID
            date_from: Filter appointments from this date (YYYY-MM-DD)
            date_to: Filter appointments to this date (YYYY-MM-DD)
            search: Search by customer name, consultant name, or description
            
        Returns:
            Dict with appointments list and pagination info
        """
        query = """
            SELECT 
                a.appointmentid, a.customerid, a.consultantid,
                a.date, a.time, a.duration, a.meetingurl,
                a.status, a.description, a.createdat, a.updatedat,
                c.fullname as customer_name, c.email as customer_email, c.phonenumber as customer_phone,
                cs.fullname as consultant_name, cs.email as consultant_email, cs.phonenumber as consultant_phone
            FROM appointment a
            JOIN customer c ON a.customerid = c.customerid
            JOIN consultant cs ON a.consultantid = cs.consultantid
            WHERE 1=1
        """
        params = []
        
        if status:
            query += " AND a.status = %s"
            params.append(status)
        
        if consultant_id:
            query += " AND a.consultantid = %s"
            params.append(consultant_id)
        
        if customer_id:
            query += " AND a.customerid = %s"
            params.append(customer_id)
        
        if date_from:
            query += " AND a.date >= %s"
            params.append(date_from)
        
        if date_to:
            query += " AND a.date <= %s"
            params.append(date_to)
        
        if search:
            query += " AND (c.fullname ILIKE %s OR cs.fullname ILIKE %s OR a.description ILIKE %s)"
            search_term = f'%{search}%'
            params.extend([search_term, search_term, search_term])
        
        query += " ORDER BY a.date DESC, a.time DESC LIMIT %s OFFSET %s"
        params.extend([limit, offset])
        
        with self.conn.cursor() as cur:
            cur.execute(query, params)
            rows = cur.fetchall()
            columns = [desc[0] for desc in cur.description]
            
            # Build count query with same filters
            count_query = """
                SELECT COUNT(*) FROM appointment a
                JOIN customer c ON a.customerid = c.customerid
                JOIN consultant cs ON a.consultantid = cs.consultantid
                WHERE 1=1
            """
            count_params = []
            
            if status:
                count_query += " AND a.status = %s"
                count_params.append(status)
            if consultant_id:
                count_query += " AND a.consultantid = %s"
                count_params.append(consultant_id)
            if customer_id:
                count_query += " AND a.customerid = %s"
                count_params.append(customer_id)
            if date_from:
                count_query += " AND a.date >= %s"
                count_params.append(date_from)
            if date_to:
                count_query += " AND a.date <= %s"
                count_params.append(date_to)
            if search:
                count_query += " AND (c.fullname ILIKE %s OR cs.fullname ILIKE %s OR a.description ILIKE %s)"
                count_params.extend([search_term, search_term, search_term])
            
            cur.execute(count_query, count_params)
            total = cur.fetchone()[0]
        
        appointments = [dict(zip(columns, row)) for row in rows]
        self._log_info(f"Retrieved {len(appointments)} appointments")
        
        return {
            "appointments": appointments,
            "total": total,
            "limit": limit,
            "offset": offset
        }
    
    def get_appointment_by_id(self, appointmentid: int) -> Dict[str, Any]:
        """
        Get a single appointment by ID with full details
        
        Args:
            appointmentid: ID of the appointment
            
        Returns:
            Dict with appointment data or error
        """
        query = """
            SELECT 
                a.appointmentid, a.customerid, a.consultantid,
                a.date, a.time, a.duration, a.meetingurl,
                a.status, a.description, a.createdat, a.updatedat,
                c.fullname as customer_name, c.email as customer_email, c.phonenumber as customer_phone,
                cs.fullname as consultant_name, cs.email as consultant_email, cs.phonenumber as consultant_phone,
                f.rating, f.customerfeedback
            FROM appointment a
            JOIN customer c ON a.customerid = c.customerid
            JOIN consultant cs ON a.consultantid = cs.consultantid
            LEFT JOIN appointmentfeedback f ON a.appointmentid = f.appointmentid
            WHERE a.appointmentid = %s
        """
        
        with self.conn.cursor() as cur:
            cur.execute(query, (appointmentid,))
            row = cur.fetchone()
            
            if not row:
                return {"success": False, "error": "Appointment not found"}
            
            columns = [desc[0] for desc in cur.description]
        
        appointment = dict(zip(columns, row))
        self._log_info(f"Retrieved appointment: {appointmentid}")
        
        return {"success": True, "data": appointment}

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

    # ==================== CONSULTANT CRUD ====================
    
    def create_consultant(
        self,
        fullname: str,
        email: str,
        phonenumber: str = None,
        imageurl: str = None,
        specialties: str = None,
        qualifications: str = None,
        joindate: str = None
    ) -> Dict[str, Any]:
        """
        Create a new consultant
        
        Args:
            fullname: Consultant's full name
            email: Consultant's email (unique)
            phonenumber: Phone number
            imageurl: URL to consultant's image
            specialties: Areas of expertise
            qualifications: Educational/professional qualifications
            joindate: Date consultant joined
            
        Returns:
            Dict with created consultant data
        """
        query = """
            INSERT INTO consultant 
            (fullname, email, phonenumber, imageurl, specialties, qualifications, joindate)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            RETURNING consultantid, fullname, email, phonenumber, imageurl, 
                      specialties, qualifications, joindate, createdat, isdisabled
        """
        
        try:
            with self.conn.cursor() as cur:
                cur.execute(query, (
                    fullname, email, phonenumber, imageurl, 
                    specialties, qualifications, joindate
                ))
                result = cur.fetchone()
                self.conn.commit()
            
            consultant = {
                "consultantid": result[0],
                "fullname": result[1],
                "email": result[2],
                "phonenumber": result[3],
                "imageurl": result[4],
                "specialties": result[5],
                "qualifications": result[6],
                "joindate": result[7],
                "createdat": result[8],
                "isdisabled": result[9]
            }
            
            self._log_info(f"Created consultant: {consultant['consultantid']}")
            return {"success": True, "data": consultant}
            
        except Exception as e:
            self.conn.rollback()
            error_msg = str(e)
            # Check for duplicate email error
            if "consultant_email_key" in error_msg or "duplicate key" in error_msg.lower():
                self._log_error(f"Duplicate email: {email}")
                return {"success": False, "error": f"Email '{email}' already exists"}
            self._log_error(f"Error creating consultant: {error_msg}")
            return {"success": False, "error": error_msg}
    
    def update_consultant(
        self,
        consultantid: int,
        fullname: str = None,
        email: str = None,
        phonenumber: str = None,
        imageurl: str = None,
        specialties: str = None,
        qualifications: str = None,
        joindate: str = None,
        isdisabled: bool = None
    ) -> Dict[str, Any]:
        """
        Update an existing consultant
        
        Args:
            consultantid: ID of consultant to update
            (other params): Fields to update (only provided fields will be updated)
            
        Returns:
            Dict with updated consultant data
        """
        # Build dynamic UPDATE query based on provided fields
        update_fields = []
        params = []
        
        if fullname is not None:
            update_fields.append("fullname = %s")
            params.append(fullname)
        if email is not None:
            update_fields.append("email = %s")
            params.append(email)
        if phonenumber is not None:
            update_fields.append("phonenumber = %s")
            params.append(phonenumber)
        if imageurl is not None:
            update_fields.append("imageurl = %s")
            params.append(imageurl)
        if specialties is not None:
            update_fields.append("specialties = %s")
            params.append(specialties)
        if qualifications is not None:
            update_fields.append("qualifications = %s")
            params.append(qualifications)
        if joindate is not None:
            update_fields.append("joindate = %s")
            params.append(joindate)
        if isdisabled is not None:
            update_fields.append("isdisabled = %s")
            params.append(isdisabled)
        
        if not update_fields:
            return {"success": False, "error": "No fields to update"}
        
        params.append(consultantid)
        query = f"""
            UPDATE consultant 
            SET {', '.join(update_fields)}
            WHERE consultantid = %s
            RETURNING consultantid, fullname, email, phonenumber, imageurl,
                      specialties, qualifications, joindate, createdat, isdisabled
        """
        
        with self.conn.cursor() as cur:
            cur.execute(query, params)
            result = cur.fetchone()
            self.conn.commit()
            
            if not result:
                return {"success": False, "error": "Consultant not found"}
        
        consultant = {
            "consultantid": result[0],
            "fullname": result[1],
            "email": result[2],
            "phonenumber": result[3],
            "imageurl": result[4],
            "specialties": result[5],
            "qualifications": result[6],
            "joindate": result[7],
            "createdat": result[8],
            "isdisabled": result[9]
        }
        
        self._log_info(f"Updated consultant: {consultantid}")
        return {"success": True, "data": consultant}
    
    def delete_consultant(self, consultantid: int) -> Dict[str, Any]:
        """
        Soft delete a consultant (set isdisabled = true)
        Only allowed if consultant has NO active appointments (pending/confirmed)
        
        Args:
            consultantid: ID of consultant to delete
            
        Returns:
            Dict with success status or error if has active appointments
        """
        try:
            with self.conn.cursor() as cur:
                # Check if consultant exists
                cur.execute(
                    "SELECT consultantid, fullname FROM consultant WHERE consultantid = %s",
                    (consultantid,)
                )
                consultant = cur.fetchone()
                if not consultant:
                    return {"success": False, "error": "Consultant not found"}
                
                # Check for active appointments (pending or confirmed, not past)
                cur.execute("""
                    SELECT COUNT(*) as active_count
                    FROM appointment 
                    WHERE consultantid = %s 
                    AND status IN ('pending', 'confirmed')
                    AND date >= CURRENT_DATE
                """, (consultantid,))
                
                active_count = cur.fetchone()[0]
                
                if active_count > 0:
                    self._log_info(
                        f"Cannot delete consultant {consultantid}: has {active_count} active appointments"
                    )
                    return {
                        "success": False,
                        "error": "Cannot delete consultant with active appointments",
                        "active_appointments": active_count,
                        "message": f"This consultant has {active_count} active appointment(s). "
                                   f"Please cancel or complete these appointments before deleting."
                    }
                
                # Proceed with soft delete
                cur.execute("""
                    UPDATE consultant 
                    SET isdisabled = true
                    WHERE consultantid = %s
                    RETURNING consultantid
                """, (consultantid,))
                
                deleted = cur.fetchone()
                if not deleted:
                    self.conn.rollback()
                    return {"success": False, "error": "Failed to delete consultant"}
                
                self.conn.commit()
                
            self._log_info(f"Successfully deleted consultant: {consultantid}")
            return {"success": True, "message": "Consultant deleted successfully"}
            
        except Exception as e:
            self.conn.rollback()
            self._log_error(f"Error deleting consultant {consultantid}: {str(e)}")
            return {"success": False, "error": str(e)}

    # ==================== APPOINTMENT CRUD ====================
    
    def create_appointment(
        self,
        consultantid: int,
        customerid: int,
        date: str,
        time: str,
        duration: int = 60,
        meetingurl: str = None,
        status: str = 'pending',
        description: str = None
    ) -> Dict[str, Any]:
        """
        Create a new appointment
        
        Args:
            consultantid: ID of consultant
            customerid: ID of customer
            date: Appointment date (YYYY-MM-DD)
            time: Appointment time (HH:MM:SS)
            duration: Duration in minutes
            meetingurl: Online meeting URL
            status: Appointment status (pending/confirmed/completed/cancelled)
            description: Additional notes
            
        Returns:
            Dict with created appointment data
        """
        query = """
            INSERT INTO appointment 
            (consultantid, customerid, date, time, duration, meetingurl, status, description)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING appointmentid, consultantid, customerid, date, time, duration,
                      meetingurl, status, description, createdat, updatedat
        """
        
        try:
            with self.conn.cursor() as cur:
                cur.execute(query, (
                    consultantid, customerid, date, time, duration,
                    meetingurl, status, description
                ))
                result = cur.fetchone()
                self.conn.commit()
            
            appointment = {
                "appointmentid": result[0],
                "consultantid": result[1],
                "customerid": result[2],
                "date": result[3],
                "time": result[4],
                "duration": result[5],
                "meetingurl": result[6],
                "status": result[7],
                "description": result[8],
                "createdat": result[9],
                "updatedat": result[10]
            }
            
            self._log_info(f"Created appointment: {appointment['appointmentid']}")
            return {"success": True, "data": appointment}
            
        except Exception as e:
            self.conn.rollback()
            error_msg = str(e)
            # Check for duplicate appointment error
            if "uq_appointment_datetime" in error_msg.lower() or "duplicate key" in error_msg.lower():
                self._log_error(f"Duplicate appointment: {date} {time}")
                return {"success": False, "error": f"Appointment already exists at {date} {time}"}
            # Check for foreign key errors
            if "foreign key" in error_msg.lower():
                self._log_error("Invalid consultant or customer ID")
                return {"success": False, "error": "Invalid consultant or customer ID"}
            self._log_error(f"Error creating appointment: {error_msg}")
            return {"success": False, "error": error_msg}
    
    def update_appointment(
        self,
        appointmentid: int,
        consultantid: int = None,
        customerid: int = None,
        date: str = None,
        time: str = None,
        duration: int = None,
        meetingurl: str = None,
        status: str = None,
        description: str = None
    ) -> Dict[str, Any]:
        """
        Update an existing appointment
        
        Args:
            appointmentid: ID of appointment to update
            (other params): Fields to update
            
        Returns:
            Dict with updated appointment data
        """
        update_fields = ["updatedat = CURRENT_TIMESTAMP"]
        params = []
        
        if consultantid is not None:
            update_fields.append("consultantid = %s")
            params.append(consultantid)
        if customerid is not None:
            update_fields.append("customerid = %s")
            params.append(customerid)
        if date is not None:
            update_fields.append("date = %s")
            params.append(date)
        if time is not None:
            update_fields.append("time = %s")
            params.append(time)
        if duration is not None:
            update_fields.append("duration = %s")
            params.append(duration)
        if meetingurl is not None:
            update_fields.append("meetingurl = %s")
            params.append(meetingurl)
        if status is not None:
            update_fields.append("status = %s")
            params.append(status)
        if description is not None:
            update_fields.append("description = %s")
            params.append(description)
        
        if len(params) == 0:
            return {"success": False, "error": "No fields to update"}
        
        params.append(appointmentid)
        query = f"""
            UPDATE appointment 
            SET {', '.join(update_fields)}
            WHERE appointmentid = %s
            RETURNING appointmentid, consultantid, customerid, date, time, duration,
                      meetingurl, status, description, createdat, updatedat
        """
        
        with self.conn.cursor() as cur:
            cur.execute(query, params)
            result = cur.fetchone()
            self.conn.commit()
            
            if not result:
                return {"success": False, "error": "Appointment not found"}
        
        appointment = {
            "appointmentid": result[0],
            "consultantid": result[1],
            "customerid": result[2],
            "date": result[3],
            "time": result[4],
            "duration": result[5],
            "meetingurl": result[6],
            "status": result[7],
            "description": result[8],
            "createdat": result[9],
            "updatedat": result[10]
        }
        
        self._log_info(f"Updated appointment: {appointmentid}")
        return {"success": True, "data": appointment}
    
    def delete_appointment(self, appointmentid: int) -> Dict[str, Any]:
        """
        Delete an appointment (hard delete)
        
        Args:
            appointmentid: ID of appointment to delete
            
        Returns:
            Dict with success status
        """
        query = "DELETE FROM appointment WHERE appointmentid = %s RETURNING appointmentid"
        
        with self.conn.cursor() as cur:
            cur.execute(query, (appointmentid,))
            result = cur.fetchone()
            self.conn.commit()
            
            if not result:
                return {"success": False, "error": "Appointment not found"}
        
        self._log_info(f"Deleted appointment: {appointmentid}")
        return {"success": True, "message": "Appointment deleted successfully"}

    # ==================== CONSULTANT SCHEDULE ====================
    
    def get_consultant_schedules(
        self,
        limit: int = 100,
        offset: int = 0,
        consultant_id: Optional[int] = None,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
        is_available: Optional[bool] = None
    ) -> Dict[str, Any]:
        """
        Get consultant schedules with optional filters
        
        Args:
            limit: Max number of records to return
            offset: Number of records to skip
            consultant_id: Filter by consultant ID
            date_from: Filter schedules from this date (YYYY-MM-DD)
            date_to: Filter schedules to this date (YYYY-MM-DD)
            is_available: Filter by availability status
            
        Returns:
            Dict with schedules list and pagination info
        """
        query = """
            SELECT 
                s.scheduleid, s.consultantid, s.date, s.starttime, s.endtime, s.isavailable,
                c.fullname as consultant_name, c.email as consultant_email
            FROM consultantschedule s
            JOIN consultant c ON s.consultantid = c.consultantid
            WHERE c.isdisabled = false
        """
        params = []
        
        if consultant_id:
            query += " AND s.consultantid = %s"
            params.append(consultant_id)
        
        if date_from:
            query += " AND s.date >= %s"
            params.append(date_from)
        
        if date_to:
            query += " AND s.date <= %s"
            params.append(date_to)
        
        if is_available is not None:
            query += " AND s.isavailable = %s"
            params.append(is_available)
        
        query += " ORDER BY s.date ASC, s.starttime ASC LIMIT %s OFFSET %s"
        params.extend([limit, offset])
        
        with self.conn.cursor() as cur:
            cur.execute(query, params)
            rows = cur.fetchall()
            columns = [desc[0] for desc in cur.description]
            
            # Build count query with same filters
            count_query = """
                SELECT COUNT(*) FROM consultantschedule s
                JOIN consultant c ON s.consultantid = c.consultantid
                WHERE c.isdisabled = false
            """
            count_params = []
            
            if consultant_id:
                count_query += " AND s.consultantid = %s"
                count_params.append(consultant_id)
            if date_from:
                count_query += " AND s.date >= %s"
                count_params.append(date_from)
            if date_to:
                count_query += " AND s.date <= %s"
                count_params.append(date_to)
            if is_available is not None:
                count_query += " AND s.isavailable = %s"
                count_params.append(is_available)
            
            cur.execute(count_query, count_params)
            total = cur.fetchone()[0]
        
        schedules = [dict(zip(columns, row)) for row in rows]
        self._log_info(f"Retrieved {len(schedules)} consultant schedules")
        
        return {
            "schedules": schedules,
            "total": total,
            "limit": limit,
            "offset": offset
        }
    
    def get_schedule_by_consultant(
        self,
        consultant_id: int,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Get all schedules for a specific consultant
        
        Args:
            consultant_id: ID of the consultant
            date_from: Filter from date
            date_to: Filter to date
            
        Returns:
            Dict with consultant info and their schedules
        """
        # First get consultant info
        with self.conn.cursor() as cur:
            cur.execute("""
                SELECT consultantid, fullname, email, phonenumber, specialties
                FROM consultant
                WHERE consultantid = %s AND isdisabled = false
            """, (consultant_id,))
            
            consultant_row = cur.fetchone()
            if not consultant_row:
                return {"success": False, "error": "Consultant not found"}
            
            consultant = {
                "consultantid": consultant_row[0],
                "fullname": consultant_row[1],
                "email": consultant_row[2],
                "phonenumber": consultant_row[3],
                "specialties": consultant_row[4]
            }
            
            # Get schedules
            schedule_query = """
                SELECT scheduleid, date, starttime, endtime, isavailable
                FROM consultantschedule
                WHERE consultantid = %s
            """
            params = [consultant_id]
            
            if date_from:
                schedule_query += " AND date >= %s"
                params.append(date_from)
            if date_to:
                schedule_query += " AND date <= %s"
                params.append(date_to)
            
            schedule_query += " ORDER BY date ASC, starttime ASC"
            
            cur.execute(schedule_query, params)
            schedule_rows = cur.fetchall()
            
            schedules = [{
                "scheduleid": row[0],
                "date": row[1],
                "starttime": row[2],
                "endtime": row[3],
                "isavailable": row[4]
            } for row in schedule_rows]
        
        self._log_info(f"Retrieved {len(schedules)} schedules for consultant {consultant_id}")
        
        return {
            "success": True,
            "consultant": consultant,
            "schedules": schedules,
            "total": len(schedules)
        }

    def create_consultant_schedule(
        self,
        consultant_id: int,
        date: str,
        start_time: str,
        end_time: str,
        is_available: bool = True
    ) -> Dict[str, Any]:
        """
        Create a new schedule slot for a consultant
        
        Args:
            consultant_id: ID of the consultant
            date: Schedule date (YYYY-MM-DD)
            start_time: Start time (HH:MM or HH:MM:SS)
            end_time: End time (HH:MM or HH:MM:SS)
            is_available: Availability status
            
        Returns:
            Dict with created schedule data
        """
        query = """
            INSERT INTO consultantschedule (consultantid, date, starttime, endtime, isavailable)
            VALUES (%s, %s, %s, %s, %s)
            RETURNING scheduleid, consultantid, date, starttime, endtime, isavailable
        """
        
        try:
            with self.conn.cursor() as cur:
                cur.execute(query, (consultant_id, date, start_time, end_time, is_available))
                result = cur.fetchone()
                self.conn.commit()
            
            schedule = {
                "scheduleid": result[0],
                "consultantid": result[1],
                "date": result[2],
                "starttime": result[3],
                "endtime": result[4],
                "isavailable": result[5]
            }
            
            self._log_info(f"Created schedule slot: {schedule['scheduleid']}")
            return {"success": True, "data": schedule}
            
        except Exception as e:
            self.conn.rollback()
            error_msg = str(e)
            if "uq_consultant_schedule" in error_msg.lower() or "duplicate key" in error_msg.lower():
                return {"success": False, "error": "Schedule slot already exists for this time"}
            if "foreign key" in error_msg.lower():
                return {"success": False, "error": "Consultant not found"}
            self._log_error(f"Error creating schedule: {error_msg}")
            return {"success": False, "error": error_msg}

    def update_consultant_schedule(
        self,
        schedule_id: int,
        date: Optional[str] = None,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
        is_available: Optional[bool] = None
    ) -> Dict[str, Any]:
        """
        Update an existing schedule slot
        
        Args:
            schedule_id: ID of schedule to update
            date: New date
            start_time: New start time
            end_time: New end time
            is_available: New availability status
            
        Returns:
            Dict with updated schedule data
        """
        update_fields = []
        params = []
        
        if date is not None:
            update_fields.append("date = %s")
            params.append(date)
        if start_time is not None:
            update_fields.append("starttime = %s")
            params.append(start_time)
        if end_time is not None:
            update_fields.append("endtime = %s")
            params.append(end_time)
        if is_available is not None:
            update_fields.append("isavailable = %s")
            params.append(is_available)
        
        if not update_fields:
            return {"success": False, "error": "No fields to update"}
        
        params.append(schedule_id)
        query = f"""
            UPDATE consultantschedule
            SET {', '.join(update_fields)}
            WHERE scheduleid = %s
            RETURNING scheduleid, consultantid, date, starttime, endtime, isavailable
        """
        
        try:
            with self.conn.cursor() as cur:
                cur.execute(query, params)
                result = cur.fetchone()
                self.conn.commit()
                
                if not result:
                    return {"success": False, "error": "Schedule not found"}
            
            schedule = {
                "scheduleid": result[0],
                "consultantid": result[1],
                "date": result[2],
                "starttime": result[3],
                "endtime": result[4],
                "isavailable": result[5]
            }
            
            self._log_info(f"Updated schedule: {schedule_id}")
            return {"success": True, "data": schedule}
            
        except Exception as e:
            self.conn.rollback()
            error_msg = str(e)
            if "uq_consultant_schedule" in error_msg.lower() or "duplicate key" in error_msg.lower():
                return {"success": False, "error": "Schedule slot already exists for this time"}
            self._log_error(f"Error updating schedule: {error_msg}")
            return {"success": False, "error": error_msg}

    def delete_consultant_schedule(self, schedule_id: int) -> Dict[str, Any]:
        """
        Delete a schedule slot
        
        Args:
            schedule_id: ID of schedule to delete
            
        Returns:
            Dict with success status
        """
        query = "DELETE FROM consultantschedule WHERE scheduleid = %s RETURNING scheduleid"
        
        with self.conn.cursor() as cur:
            cur.execute(query, (schedule_id,))
            result = cur.fetchone()
            self.conn.commit()
            
            if not result:
                return {"success": False, "error": "Schedule not found"}
        
        self._log_info(f"Deleted schedule: {schedule_id}")
        return {"success": True, "message": "Schedule deleted successfully"}

    def generate_consultant_schedule(
        self,
        consultant_id: int,
        date_from: str,
        date_to: str,
        work_start: str = "09:00",
        work_end: str = "18:00",
        slot_duration: int = 60,
        exclude_weekends: bool = True
    ) -> Dict[str, Any]:
        """
        Generate schedule slots automatically for a consultant
        
        Args:
            consultant_id: ID of the consultant
            date_from: Start date (YYYY-MM-DD)
            date_to: End date (YYYY-MM-DD)
            work_start: Work start time (HH:MM), default 09:00
            work_end: Work end time (HH:MM), default 18:00
            slot_duration: Duration of each slot in minutes, default 60
            exclude_weekends: Skip Saturday and Sunday if True
            
        Returns:
            Dict with count of created slots
        """
        from datetime import datetime, timedelta
        
        # Validate consultant exists
        with self.conn.cursor() as cur:
            cur.execute(
                "SELECT consultantid FROM consultant WHERE consultantid = %s AND isdisabled = false",
                (consultant_id,)
            )
            if not cur.fetchone():
                return {"success": False, "error": "Consultant not found or disabled"}
        
        # Parse dates
        try:
            start_date = datetime.strptime(date_from, "%Y-%m-%d").date()
            end_date = datetime.strptime(date_to, "%Y-%m-%d").date()
        except ValueError:
            return {"success": False, "error": "Invalid date format. Use YYYY-MM-DD"}
        
        if start_date > end_date:
            return {"success": False, "error": "Start date must be before end date"}
        
        # Parse work hours
        try:
            work_start_time = datetime.strptime(work_start, "%H:%M").time()
            work_end_time = datetime.strptime(work_end, "%H:%M").time()
        except ValueError:
            return {"success": False, "error": "Invalid time format. Use HH:MM"}
        
        if work_start_time >= work_end_time:
            return {"success": False, "error": "Work start time must be before end time"}
        
        # Generate slots
        slots_created = 0
        slots_skipped = 0
        current_date = start_date
        
        insert_query = """
            INSERT INTO consultantschedule (consultantid, date, starttime, endtime, isavailable)
            VALUES (%s, %s, %s, %s, true)
            ON CONFLICT DO NOTHING
        """
        
        try:
            with self.conn.cursor() as cur:
                while current_date <= end_date:
                    # Skip weekends if configured
                    if exclude_weekends and current_date.weekday() >= 5:  # 5=Sat, 6=Sun
                        current_date += timedelta(days=1)
                        continue
                    
                    # Generate time slots for this date
                    slot_start = datetime.combine(current_date, work_start_time)
                    day_end = datetime.combine(current_date, work_end_time)
                    
                    while slot_start + timedelta(minutes=slot_duration) <= day_end:
                        slot_end = slot_start + timedelta(minutes=slot_duration)
                        
                        cur.execute(insert_query, (
                            consultant_id,
                            current_date.isoformat(),
                            slot_start.strftime("%H:%M"),
                            slot_end.strftime("%H:%M")
                        ))
                        
                        if cur.rowcount > 0:
                            slots_created += 1
                        else:
                            slots_skipped += 1
                        
                        slot_start = slot_end
                    
                    current_date += timedelta(days=1)
                
                self.conn.commit()
            
            self._log_info(
                f"Generated schedule for consultant {consultant_id}: "
                f"{slots_created} created, {slots_skipped} skipped (duplicates)"
            )
            
            return {
                "success": True,
                "slots_created": slots_created,
                "slots_skipped": slots_skipped,
                "message": f"Created {slots_created} slots, skipped {slots_skipped} existing slots"
            }
            
        except Exception as e:
            self.conn.rollback()
            self._log_error(f"Error generating schedule: {str(e)}")
            return {"success": False, "error": str(e)}
