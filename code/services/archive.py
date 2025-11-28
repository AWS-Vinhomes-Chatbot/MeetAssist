"""
Archive Service - Business logic for archiving RDS data to S3

This service handles:
- Exporting table data from RDS to CSV format
- Uploading CSV files to S3
- Managing archive metadata (archive_info.json)

IMPORTANT: CSV format must match what index.py expects when restoring:
- Column names: lowercase (PostgreSQL default)
- IDENTITY columns: INCLUDED (index.py will skip them when inserting)
- Empty values: empty string ""
- Datetime: ISO format (YYYY-MM-DDTHH:MM:SS)
- Boolean: True/False (Python string)
- Encoding: UTF-8 (no BOM needed, index.py uses utf-8-sig to handle both)
"""

import json
import csv
import io
import hashlib
from datetime import datetime, timezone, date, time as dt_time
from typing import Dict, Any, List, Optional, Tuple
from decimal import Decimal


class ArchiveService:
    """Service class for archiving database data to S3"""
    
    # Table configuration - maps table names to CSV file names and ordering
    TABLE_CONFIG = {
        "consultant": {
            "db_table": "consultant",
            "csv_file": "Consultant.csv",
            "order_by": "consultantid"
        },
        "customer": {
            "db_table": "customer",
            "csv_file": "Customer.csv",
            "order_by": "customerid"
        },
        "appointment": {
            "db_table": "appointment",
            "csv_file": "Appointment.csv",
            "order_by": "appointmentid"
        },
        "appointmentfeedback": {
            "db_table": "appointmentfeedback",
            "csv_file": "AppointmentFeedback.csv",
            "order_by": "appointmentid"
        },
        "communityprogram": {
            "db_table": "communityprogram",
            "csv_file": "CommunityProgram.csv",
            "order_by": "programid"
        },
        "consultantschedule": {
            "db_table": "consultantschedule",
            "csv_file": "ConsultantSchedule.csv",
            "order_by": "scheduleid"
        },
        "programparticipant": {
            "db_table": "programparticipant",
            "csv_file": "ProgramParticipant.csv",
            "order_by": "programid, customerid"
        }
    }
    
    def __init__(self, s3_client, bucket_name: str, data_prefix: str = "data", logger=None):
        """
        Initialize ArchiveService
        
        Args:
            s3_client: Boto3 S3 client
            bucket_name: S3 bucket name for storing archives
            data_prefix: S3 prefix/folder for CSV files (default: "data")
            logger: Optional logger instance
        """
        self.s3 = s3_client
        self.bucket_name = bucket_name
        self.data_prefix = data_prefix
        self.log = logger
    
    def _log_info(self, message: str):
        if self.log:
            self.log.info(message)
    
    def _log_error(self, message: str):
        if self.log:
            self.log.error(message)
    
    def _log_warning(self, message: str):
        if self.log:
            self.log.warning(message)

    def get_table_config(self, table_name: str) -> Optional[Dict]:
        """
        Get configuration for a table
        
        Args:
            table_name: Name of the table
            
        Returns:
            Table config dict or None if not found
        """
        return self.TABLE_CONFIG.get(table_name.lower())
    
    def is_valid_table(self, table_name: str) -> bool:
        """Check if table name is valid for archiving"""
        return table_name.lower() in self.TABLE_CONFIG

    def get_all_tables(self) -> List[str]:
        """
        Get list of all configured table names for archiving
        
        Returns:
            List of table names
        """
        return list(self.TABLE_CONFIG.keys())

    def export_table_to_csv(self, conn, table_name: str) -> tuple[str, int]:
        """
        Export a table from database to CSV string
        
        Args:
            conn: Database connection
            table_name: Name of the table to export
            
        Returns:
            Tuple of (csv_content, record_count)
        """
        config = self.get_table_config(table_name)
        if not config:
            raise ValueError(f"Unknown table: {table_name}")
        
        db_table = config["db_table"]
        order_by = config["order_by"]
        
        self._log_info(f"Exporting table {db_table}")
        
        # Query all data from table
        query = f"SELECT * FROM {db_table} ORDER BY {order_by}"
        
        with conn.cursor() as cur:
            cur.execute(query)
            rows = cur.fetchall()
            columns = [desc[0] for desc in cur.description]
        
        record_count = len(rows)
        self._log_info(f"Fetched {record_count} records from {db_table}")
        
        # Convert to CSV
        csv_content = self._rows_to_csv(columns, rows)
        
        return csv_content, record_count

    def _rows_to_csv(self, columns: List[str], rows: List[tuple]) -> str:
        """
        Convert database rows to CSV string
        
        Format matches what index.py expects:
        - Column names: lowercase
        - Empty values: empty string ""
        - Datetime/Date/Time: ISO format string
        - Boolean: true/false (lowercase for PostgreSQL compatibility)
        - Decimal: string representation
        
        Args:
            columns: List of column names
            rows: List of row tuples
            
        Returns:
            CSV content as string (UTF-8, no BOM)
        """
        csv_buffer = io.StringIO()
        writer = csv.writer(csv_buffer)
        
        # Write header (lowercase column names)
        writer.writerow([col.lower() for col in columns])
        
        # Write data rows
        for row in rows:
            csv_row = []
            for value in row:
                csv_row.append(self._format_value_for_csv(value))
            writer.writerow(csv_row)
        
        return csv_buffer.getvalue()

    def _format_value_for_csv(self, value: Any) -> str:
        """
        Format a single value for CSV export
        
        Handles:
        - None -> empty string
        - datetime -> ISO format
        - date -> ISO format (YYYY-MM-DD)
        - time -> ISO format (HH:MM:SS)
        - bool -> true/false (lowercase)
        - Decimal -> string
        - Other -> str()
        """
        if value is None:
            return ""
        elif isinstance(value, datetime):
            return value.isoformat()
        elif isinstance(value, date):
            return value.isoformat()
        elif isinstance(value, dt_time):
            return value.isoformat()
        elif isinstance(value, bool):
            return "true" if value else "false"
        elif isinstance(value, Decimal):
            return str(value)
        else:
            return str(value)

    def _calculate_checksum(self, content: str) -> str:
        """
        Calculate MD5 checksum of content
        
        Args:
            content: String content to hash
            
        Returns:
            MD5 hex digest
        """
        return hashlib.md5(content.encode('utf-8')).hexdigest()

    def upload_to_s3(self, table_name: str, csv_content: str) -> str:
        """
        Upload CSV content to S3
        
        Args:
            table_name: Name of the table (used to get CSV filename)
            csv_content: CSV content to upload
            
        Returns:
            S3 key of uploaded file
        """
        config = self.get_table_config(table_name)
        if not config:
            raise ValueError(f"Unknown table: {table_name}")
        
        csv_file = config["csv_file"]
        s3_key = f"{self.data_prefix}/{csv_file}"
        
        self.s3.put_object(
            Bucket=self.bucket_name,
            Key=s3_key,
            Body=csv_content.encode('utf-8'),
            ContentType='text/csv'
        )
        
        self._log_info(f"Uploaded {s3_key} to S3 ({len(csv_content)} bytes)")
        
        return s3_key

    def archive_table(self, conn, table_name: str, checksums: Dict[str, str] = None) -> Tuple[int, str, bool]:
        """
        Archive a single table: export from RDS and upload to S3
        Skips upload if data hasn't changed (checksum match)
        
        Args:
            conn: Database connection
            table_name: Name of the table to archive
            checksums: Dict of existing checksums from metadata (optional)
            
        Returns:
            Tuple of (record_count, new_checksum, was_uploaded)
            - record_count: Number of records in table
            - new_checksum: MD5 checksum of current data
            - was_uploaded: True if uploaded, False if skipped (unchanged)
        """
        # Export to CSV
        csv_content, record_count = self.export_table_to_csv(conn, table_name)
        
        # Calculate checksum
        new_checksum = self._calculate_checksum(csv_content)
        
        # Check if data changed
        old_checksum = checksums.get(table_name) if checksums else None
        
        if old_checksum and old_checksum == new_checksum:
            self._log_info(f"Skipping {table_name}: data unchanged (checksum match)")
            return record_count, new_checksum, False
        
        # Upload to S3 (data changed or first time)
        self.upload_to_s3(table_name, csv_content)
        
        if old_checksum:
            self._log_info(f"Uploaded {table_name}: data changed")
        else:
            self._log_info(f"Uploaded {table_name}: first archive")
        
        return record_count, new_checksum, True

    def archive_all_tables(self, conn) -> Dict[str, int]:
        """
        Archive all configured tables
        
        Args:
            conn: Database connection
            
        Returns:
            Dict mapping table names to record counts (-1 if failed)
        """
        results = {}
        
        for table_name in self.TABLE_CONFIG.keys():
            try:
                record_count = self.archive_table(conn, table_name)
                results[table_name] = record_count
                self._log_info(f"Archived {table_name}: {record_count} records")
            except Exception as e:
                self._log_error(f"Failed to archive {table_name}: {str(e)}")
                results[table_name] = -1
        
        return results

    # ==================== METADATA MANAGEMENT ====================

    def get_metadata(self) -> Dict:
        """
        Get current archive metadata from S3
        
        Returns:
            Metadata dict (empty structure if not exists)
        """
        metadata_key = "metadata/archive_info.json"
        
        try:
            response = self.s3.get_object(Bucket=self.bucket_name, Key=metadata_key)
            metadata = json.loads(response['Body'].read().decode('utf-8'))
            self._log_info("Loaded existing archive metadata")
            return metadata
        except self.s3.exceptions.NoSuchKey:
            self._log_info("No existing metadata, will create new")
            return self._create_empty_metadata()
        except Exception as e:
            self._log_warning(f"Error reading metadata, creating new: {str(e)}")
            return self._create_empty_metadata()

    def _create_empty_metadata(self) -> Dict:
        """Create empty metadata structure"""
        return {
            "created_at": datetime.now(timezone.utc).isoformat(),
            "tables": {},
            "archive_history": []
        }

    def update_metadata(
        self, 
        table_name: str, 
        action: str, 
        record_id: Any, 
        record_count: int
    ):
        """
        Update archive metadata after archiving a table
        
        Args:
            table_name: Name of the archived table
            action: CRUD action that triggered archive (create/update/delete)
            record_id: ID of the affected record
            record_count: Total records in the table after archive
        """
        metadata_key = "metadata/archive_info.json"
        current_time = datetime.now(timezone.utc).isoformat()
        
        # Get existing metadata
        metadata = self.get_metadata()
        
        # Update table info
        metadata["last_updated"] = current_time
        metadata["tables"][table_name] = {
            "record_count": record_count,
            "last_archived": current_time,
            "last_action": action,
            "last_record_id": record_id
        }
        
        # Add to history (keep last 100 entries)
        history_entry = {
            "timestamp": current_time,
            "table": table_name,
            "action": action,
            "record_id": record_id,
            "record_count": record_count
        }
        
        if "archive_history" not in metadata:
            metadata["archive_history"] = []
        
        metadata["archive_history"].insert(0, history_entry)
        metadata["archive_history"] = metadata["archive_history"][:100]  # Keep only last 100
        
        # Upload updated metadata
        self.s3.put_object(
            Bucket=self.bucket_name,
            Key=metadata_key,
            Body=json.dumps(metadata, indent=2, default=str).encode('utf-8'),
            ContentType='application/json'
        )
        
        self._log_info(f"Updated archive metadata for {table_name}")

    def update_metadata_full(self, results: Dict[str, Dict], total_records: int, checksums: Dict[str, str] = None):
        """
        Update archive metadata after archiving ALL tables (schedule-based)
        
        Args:
            results: Dict mapping table names to {"status": str, "record_count": int, "uploaded": bool, "error"?: str}
            total_records: Total records archived across all tables
            checksums: Dict mapping table names to MD5 checksums (optional)
        """
        metadata_key = "metadata/archive_info.json"
        current_time = datetime.now(timezone.utc).isoformat()
        
        # Get existing metadata
        metadata = self.get_metadata()
        
        # Update metadata
        metadata["last_updated"] = current_time
        metadata["last_full_archive"] = current_time
        metadata["total_records"] = total_records
        
        # Count uploads vs skips
        uploaded_count = sum(1 for r in results.values() if r.get("uploaded", False))
        skipped_count = sum(1 for r in results.values() if r.get("status") == "success" and not r.get("uploaded", True))
        
        # Update table info for all tables
        for table_name, result in results.items():
            if result.get("status") == "success":
                table_info = {
                    "record_count": result.get("record_count", 0),
                    "last_archived": current_time,
                    "last_action": "schedule",
                    "status": "success"
                }
                # Add checksum if provided
                if checksums and table_name in checksums:
                    table_info["checksum"] = checksums[table_name]
                # Mark if was skipped (unchanged)
                if not result.get("uploaded", True):
                    table_info["last_upload_skipped"] = True
                    table_info["skip_reason"] = "data_unchanged"
                else:
                    table_info["last_upload_skipped"] = False
                    
                metadata["tables"][table_name] = table_info
            else:
                # Keep previous info but mark error
                if table_name not in metadata["tables"]:
                    metadata["tables"][table_name] = {}
                metadata["tables"][table_name]["last_error"] = result.get("error", "Unknown error")
                metadata["tables"][table_name]["last_error_time"] = current_time
        
        # Add to history (keep last 100 entries)
        history_entry = {
            "timestamp": current_time,
            "type": "full_archive",
            "tables_count": len(results),
            "total_records": total_records,
            "success_count": sum(1 for r in results.values() if r.get("status") == "success"),
            "error_count": sum(1 for r in results.values() if r.get("status") == "error"),
            "uploaded_count": uploaded_count,
            "skipped_count": skipped_count
        }
        
        if "archive_history" not in metadata:
            metadata["archive_history"] = []
        
        metadata["archive_history"].insert(0, history_entry)
        metadata["archive_history"] = metadata["archive_history"][:100]  # Keep only last 100
        
        # Upload updated metadata
        self.s3.put_object(
            Bucket=self.bucket_name,
            Key=metadata_key,
            Body=json.dumps(metadata, indent=2, default=str).encode('utf-8'),
            ContentType='application/json'
        )
        
        self._log_info(f"Updated archive metadata: {len(results)} tables, {total_records} records ({uploaded_count} uploaded, {skipped_count} skipped)")

    def get_archive_history(self, table_name: str = None, limit: int = 20) -> List[Dict]:
        """
        Get archive history, optionally filtered by table
        
        Args:
            table_name: Optional table name to filter by
            limit: Max number of history entries to return
            
        Returns:
            List of history entries
        """
        metadata = self.get_metadata()
        history = metadata.get("archive_history", [])
        
        if table_name:
            history = [h for h in history if h.get("table") == table_name.lower()]
        
        return history[:limit]

    def get_table_status(self, table_name: str) -> Optional[Dict]:
        """
        Get current status of a table's archive
        
        Args:
            table_name: Name of the table
            
        Returns:
            Table status dict or None if never archived
        """
        metadata = self.get_metadata()
        return metadata.get("tables", {}).get(table_name.lower())
