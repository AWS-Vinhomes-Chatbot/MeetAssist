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
                a.appointmentid, a.customerid, a.consultantid,
                a.date, a.time, a.duration, a.meetingurl,
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
        
        Args:
            consultantid: ID of consultant to delete
            
        Returns:
            Dict with success status
        """
        query = """
            UPDATE consultant 
            SET isdisabled = true
            WHERE consultantid = %s
            RETURNING consultantid
        """
        
        with self.conn.cursor() as cur:
            cur.execute(query, (consultantid,))
            result = cur.fetchone()
            self.conn.commit()
            
            if not result:
                return {"success": False, "error": "Consultant not found"}
        
        self._log_info(f"Deleted consultant: {consultantid}")
        return {"success": True, "message": "Consultant deleted successfully"}

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

    # ==================== COMMUNITY PROGRAM CRUD ====================
    
    def create_program(
        self,
        programname: str,
        date: str,
        description: str = None,
        content: str = None,
        organizer: str = None,
        url: str = None,
        status: str = 'upcoming'
    ) -> Dict[str, Any]:
        """
        Create a new community program
        
        Args:
            programname: Program name
            date: Program date (YYYY-MM-DD)
            description: Short description
            content: Detailed content
            organizer: Organizer name
            url: Program URL
            status: Program status (upcoming/ongoing/completed)
            
        Returns:
            Dict with created program data
        """
        query = """
            INSERT INTO communityprogram 
            (programname, date, description, content, organizer, url, status)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            RETURNING programid, programname, date, description, content,
                      organizer, url, isdisabled, status, createdat
        """
        
        with self.conn.cursor() as cur:
            cur.execute(query, (
                programname, date, description, content,
                organizer, url, status
            ))
            result = cur.fetchone()
            self.conn.commit()
        
        program = {
            "programid": result[0],
            "programname": result[1],
            "date": result[2],
            "description": result[3],
            "content": result[4],
            "organizer": result[5],
            "url": result[6],
            "isdisabled": result[7],
            "status": result[8],
            "createdat": result[9]
        }
        
        self._log_info(f"Created program: {program['programid']}")
        return {"success": True, "data": program}
    
    def update_program(
        self,
        programid: int,
        programname: str = None,
        date: str = None,
        description: str = None,
        content: str = None,
        organizer: str = None,
        url: str = None,
        status: str = None,
        isdisabled: bool = None
    ) -> Dict[str, Any]:
        """
        Update an existing community program
        
        Args:
            programid: ID of program to update
            (other params): Fields to update
            
        Returns:
            Dict with updated program data
        """
        update_fields = []
        params = []
        
        if programname is not None:
            update_fields.append("programname = %s")
            params.append(programname)
        if date is not None:
            update_fields.append("date = %s")
            params.append(date)
        if description is not None:
            update_fields.append("description = %s")
            params.append(description)
        if content is not None:
            update_fields.append("content = %s")
            params.append(content)
        if organizer is not None:
            update_fields.append("organizer = %s")
            params.append(organizer)
        if url is not None:
            update_fields.append("url = %s")
            params.append(url)
        if status is not None:
            update_fields.append("status = %s")
            params.append(status)
        if isdisabled is not None:
            update_fields.append("isdisabled = %s")
            params.append(isdisabled)
        
        if not update_fields:
            return {"success": False, "error": "No fields to update"}
        
        params.append(programid)
        query = f"""
            UPDATE communityprogram 
            SET {', '.join(update_fields)}
            WHERE programid = %s
            RETURNING programid, programname, date, description, content,
                      organizer, url, isdisabled, status, createdat
        """
        
        with self.conn.cursor() as cur:
            cur.execute(query, params)
            result = cur.fetchone()
            self.conn.commit()
            
            if not result:
                return {"success": False, "error": "Program not found"}
        
        program = {
            "programid": result[0],
            "programname": result[1],
            "date": result[2],
            "description": result[3],
            "content": result[4],
            "organizer": result[5],
            "url": result[6],
            "isdisabled": result[7],
            "status": result[8],
            "createdat": result[9]
        }
        
        self._log_info(f"Updated program: {programid}")
        return {"success": True, "data": program}
    
    def delete_program(self, programid: int) -> Dict[str, Any]:
        """
        Soft delete a community program (set isdisabled = true)
        
        Args:
            programid: ID of program to delete
            
        Returns:
            Dict with success status
        """
        query = """
            UPDATE communityprogram 
            SET isdisabled = true
            WHERE programid = %s
            RETURNING programid
        """
        
        with self.conn.cursor() as cur:
            cur.execute(query, (programid,))
            result = cur.fetchone()
            self.conn.commit()
            
            if not result:
                return {"success": False, "error": "Program not found"}
        
        self._log_info(f"Deleted program: {programid}")
        return {"success": True, "message": "Program deleted successfully"}
