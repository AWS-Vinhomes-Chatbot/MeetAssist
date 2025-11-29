# /*
#  * Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
#  * SPDX-License-Identifier: MIT-0
#  *
#  * Permission is hereby granted, free of charge, to any person obtaining a copy of this
#  * software and associated documentation files (the "Software"), to deal in the Software
#  * without restriction, including without limitation the rights to use, copy, modify,
#  * merge, publish, distribute, sublicense, and/or sell copies of the Software, and to
#  * permit persons to whom the Software is furnished to do so.
#  *
#  * THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED,
#  * INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A
#  * PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT
#  * HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION
#  * OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE
#  * SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.
#  */

import json
import os
import csv
import io

import boto3
import psycopg
from psycopg import sql

secrets_client = boto3.client("secretsmanager")
s3_client = boto3.client("s3")

# ============================================
# CAREER COUNSELING SCHEMA - HARDCODED
# ============================================
CAREER_COUNSELING_SCHEMA = """
-- Bảng Customer (Khách hàng)
CREATE TABLE IF NOT EXISTS Customer (
    CustomerID INT PRIMARY KEY GENERATED ALWAYS AS IDENTITY,
    FullName VARCHAR(100) NOT NULL,
    Email VARCHAR(100) NOT NULL UNIQUE,
    PhoneNumber VARCHAR(20),
    DateOfBirth DATE,
    CreatedAt TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    IsDisabled BOOLEAN NOT NULL DEFAULT false,
    Notes TEXT
);

-- Bảng Tư vấn viên
CREATE TABLE IF NOT EXISTS Consultant (
    ConsultantID INT PRIMARY KEY GENERATED ALWAYS AS IDENTITY,
    FullName VARCHAR(100) NOT NULL,
    Email VARCHAR(100) NOT NULL UNIQUE,
    PhoneNumber VARCHAR(20),
    ImageUrl VARCHAR(255),
    Specialties TEXT,
    Qualifications TEXT,
    JoinDate DATE NOT NULL,
    CreatedAt TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    IsDisabled BOOLEAN NOT NULL DEFAULT false
);

-- Bảng Lịch tư vấn
CREATE TABLE IF NOT EXISTS ConsultantSchedule (
    ScheduleID INT PRIMARY KEY GENERATED ALWAYS AS IDENTITY,
    ConsultantID INT NOT NULL,
    Date DATE NOT NULL,
    StartTime TIME NOT NULL,
    EndTime TIME NOT NULL,
    IsAvailable BOOLEAN NOT NULL DEFAULT true,
    FOREIGN KEY (ConsultantID) REFERENCES Consultant(ConsultantID),
    CONSTRAINT UQ_Consultant_Schedule UNIQUE (ConsultantID, Date, StartTime)
);

-- Bảng Cuộc hẹn
CREATE TABLE IF NOT EXISTS Appointment (
    AppointmentID INT PRIMARY KEY GENERATED ALWAYS AS IDENTITY,
    ConsultantID INT NOT NULL,
    CustomerID INT NOT NULL,
    Date DATE NOT NULL,
    Time TIME NOT NULL,
    Duration INT NOT NULL DEFAULT 60,
    MeetingURL VARCHAR(255),
    Status VARCHAR(20) NOT NULL DEFAULT 'pending',
    Description TEXT,
    CreatedAt TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UpdatedAt TIMESTAMP,
    FOREIGN KEY (ConsultantID) REFERENCES Consultant(ConsultantID),
    FOREIGN KEY (CustomerID) REFERENCES Customer(CustomerID),
    CONSTRAINT UQ_Appointment_DateTime UNIQUE (ConsultantID, Date, Time),
    CONSTRAINT CHK_AppointmentStatus CHECK (Status IN ('pending', 'confirmed', 'completed', 'cancelled'))
);

-- Bảng Đánh giá cuộc hẹn
CREATE TABLE IF NOT EXISTS AppointmentFeedback (
    AppointmentID INT PRIMARY KEY,
    Rating FLOAT NOT NULL CHECK (Rating >= 0 AND Rating <= 5),
    CustomerFeedback TEXT,
    CreatedAt TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (AppointmentID) REFERENCES Appointment(AppointmentID) ON DELETE CASCADE
);

-- Bảng Chương trình cộng đồng
CREATE TABLE IF NOT EXISTS CommunityProgram (
    ProgramID INT PRIMARY KEY GENERATED ALWAYS AS IDENTITY,
    ProgramName VARCHAR(100) NOT NULL,
    Date DATE NOT NULL,
    Description VARCHAR(255),
    Content TEXT,
    Organizer VARCHAR(100),
    Url VARCHAR(300),
    IsDisabled BOOLEAN NOT NULL DEFAULT false,
    Status VARCHAR(20) NOT NULL DEFAULT 'upcoming',
    CreatedAt TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT CHK_ProgramStatus CHECK (Status IN ('upcoming', 'ongoing', 'completed'))
);

-- Bảng Người tham gia chương trình cộng đồng
CREATE TABLE IF NOT EXISTS ProgramParticipant (
    ProgramID INT NOT NULL,
    CustomerID INT NOT NULL,
    RegisteredTime TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    Status VARCHAR(20) NOT NULL DEFAULT 'registered',
    FOREIGN KEY (ProgramID) REFERENCES CommunityProgram(ProgramID) ON DELETE CASCADE,
    FOREIGN KEY (CustomerID) REFERENCES Customer(CustomerID) ON DELETE CASCADE,
    CONSTRAINT PK_ProgramParticipant PRIMARY KEY (ProgramID, CustomerID),
    CONSTRAINT CHK_ParticipantStatus CHECK (Status IN ('registered', 'attended', 'cancelled'))
);
"""

# ============================================
# TABLE IMPORT ORDER (theo thứ tự foreign key dependencies)
# ============================================
TABLE_IMPORT_ORDER = [
    "customer",           # Không có FK dependency
    "consultant",         # Không có FK dependency  
    "consultantschedule", # FK -> Consultant
    "communityprogram",   # Không có FK dependency
    "appointment",        # FK -> Consultant, Customer
    "appointmentfeedback",# FK -> Appointment
    "programparticipant", # FK -> CommunityProgram, Customer
]

# Mapping từ tên file CSV (lowercase) sang tên table thực tế trong DB
TABLE_NAME_MAPPING = {
    "customer": "customer",
    "consultant": "consultant",
    "consultantschedule": "consultantschedule",
    "communityprogram": "communityprogram",
    "appointment": "appointment",
    "appointmentfeedback": "appointmentfeedback",
    "programparticipant": "programparticipant",
}


def handler(event, context):
    print(event)
    request_type = event["RequestType"]
    if request_type == "Create":
        return on_create(event)
    if request_type == "Update":
        return on_update(event)
    if request_type == "Delete":
        return on_delete(event)
    raise Exception(f"Invalid request type: {request_type}")


def get_csv_files_from_s3(bucket_name):
    """Lấy danh sách file CSV từ S3 bucket (trong folder 'data/')"""
    csv_files = {}
    try:
        response = s3_client.list_objects_v2(Bucket=bucket_name, Prefix="data/")
        
        if "Contents" not in response:
            print(f"No files found in s3://{bucket_name}/data/")
            return csv_files
            
        for obj in response["Contents"]:
            key = obj["Key"]
            if key.endswith(".csv"):
                # Lấy tên file không có extension và folder
                # Ví dụ: "data/customer.csv" -> "customer"
                file_name = key.split("/")[-1].replace(".csv", "").lower()
                csv_files[file_name] = key
                print(f"Found CSV file: {key} -> table: {file_name}")
                
    except Exception as e:
        print(f"Error listing S3 objects: {e}")
        
    return csv_files


def import_csv_to_table(conn, bucket_name, s3_key, table_name):
    """Import data từ CSV file trong S3 vào table RDS"""
    try:
        print(f"Importing {s3_key} to table {table_name}...")
        
        # Đọc CSV từ S3 và xử lý BOM (UTF-8 with BOM)
        response = s3_client.get_object(Bucket=bucket_name, Key=s3_key)
        csv_content = response["Body"].read().decode("utf-8-sig")  # utf-8-sig tự động bỏ BOM
        
        # Parse CSV (comma delimiter)
        csv_reader = csv.DictReader(io.StringIO(csv_content))
        rows = list(csv_reader)
        
        if not rows:
            print(f"No data in {s3_key}")
            return 0
            
        # Lấy column names từ CSV header (lowercase để match với PostgreSQL)
        columns = list(rows[0].keys())
        
        # CHỈ loại bỏ các cột PRIMARY KEY IDENTITY (không loại bỏ FK columns)
        # Các bảng có PK tự động: customer(customerid), consultant(consultantid), 
        # consultantschedule(scheduleid), appointment(appointmentid), communityprogram(programid)
        # KHÔNG loại bỏ: consultantid, customerid, programid khi chúng là FK
        pk_identity_columns = {
            "customer": ["customerid"],
            "consultant": ["consultantid"],
            "consultantschedule": ["scheduleid"],
            "appointment": ["appointmentid"],
            "communityprogram": ["programid"],
            "appointmentfeedback": [],  # appointmentid là PK nhưng không phải IDENTITY
            "programparticipant": [],   # composite PK, không có IDENTITY
        }
        
        identity_cols_for_table = pk_identity_columns.get(table_name.lower(), [])
        columns_to_insert = [col for col in columns 
                           if col.lower() not in identity_cols_for_table]
        
        if not columns_to_insert:
            print(f"No columns to insert for {table_name}")
            return 0
        
        # Tạo INSERT statement - dùng lowercase column names
        col_names = ", ".join([col.lower() for col in columns_to_insert])
        placeholders = ", ".join(["%s"] * len(columns_to_insert))
        
        insert_sql = f"""
            INSERT INTO {table_name} ({col_names}) 
            VALUES ({placeholders})
            ON CONFLICT DO NOTHING
        """
        
        print(f"SQL: INSERT INTO {table_name} ({col_names}) VALUES (...)")
        
        # Insert từng row với separate transaction
        inserted_count = 0
        error_count = 0
        
        for row in rows:
            values = []
            for col in columns_to_insert:
                value = row.get(col, "")
                # Xử lý giá trị rỗng
                if value == "" or value is None:
                    values.append(None)
                else:
                    values.append(value)
            
            try:
                with conn.cursor() as cur:
                    cur.execute(insert_sql, values)
                conn.commit()
                inserted_count += 1
            except Exception as e:
                conn.rollback()  # Rollback chỉ row này
                error_count += 1
                if error_count <= 3:  # Chỉ log 3 errors đầu
                    print(f"Error inserting row: {e}")
                continue
        
        if error_count > 3:
            print(f"... and {error_count - 3} more errors")
                
        print(f"Imported {inserted_count} rows to {table_name} ({error_count} errors)")
        return inserted_count
        
    except Exception as e:
        print(f"Error importing {s3_key}: {e}")
        return 0


def on_create(event):
    request_id = event["RequestId"]
    props = event["ResourceProperties"]
    print(f"create new resource with props {props}")

    # Get database credentials
    db_secret = secrets_client.get_secret_value(SecretId=os.environ["DB_SECRET_NAME"])
    db_secret_dict = json.loads(db_secret["SecretString"])

    read_only_secret = secrets_client.get_secret_value(SecretId=os.environ["READ_ONLY_SECRET_NAME"])
    read_only_secret_dict = json.loads(read_only_secret["SecretString"])
    
    bucket_name = os.environ.get("DATA_BUCKET_NAME", "")

    # Connect to the database
    conn = psycopg.connect(
        host=db_secret_dict["host"], 
        port=db_secret_dict["port"], 
        dbname="postgres",
        user=db_secret_dict["username"], 
        password=db_secret_dict["password"]
    )
    
    try:
        with conn.cursor() as cur:
            # ========== STEP 1: Create Schema ==========
            print("Step 1: Executing Career Counseling schema...")
            cur.execute(CAREER_COUNSELING_SCHEMA)
            print("Career Counseling schema created successfully")
            
            # Enable pg_vector for embeddings (for AI features)
            cur.execute("CREATE EXTENSION IF NOT EXISTS vector")
            cur.execute("""
                CREATE TABLE IF NOT EXISTS embeddings (
                    id SERIAL PRIMARY KEY,
                    embedding VECTOR(1024),
                    database_name VARCHAR(255) NOT NULL,
                    schema_name VARCHAR(255) NOT NULL,
                    table_name VARCHAR(255) NOT NULL,
                    embedding_text TEXT NOT NULL,
                    embedding_hash VARCHAR(64) NOT NULL,
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE (database_name, schema_name, table_name, embedding_hash)
                )
            """)

            # ========== STEP 2: Create readonly user ==========
            cur.execute("""
                SELECT 1 FROM pg_catalog.pg_roles WHERE rolname = 'readonly_user'
            """)
            role_exists = cur.fetchone() is not None

            if not role_exists:
                print("Step 2: Creating readonly_user role...")
                create_role_query = sql.SQL("CREATE ROLE readonly_user WITH LOGIN PASSWORD {}").format(
                    sql.Literal(read_only_secret_dict["password"]))
                cur.execute(create_role_query)  # nosemgrep
                cur.execute("""
                    GRANT CONNECT ON DATABASE postgres TO readonly_user;
                    GRANT USAGE ON SCHEMA public TO readonly_user;
                    GRANT SELECT ON ALL TABLES IN SCHEMA public TO readonly_user;
                    ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO readonly_user;
                """)
                print("readonly_user role created successfully")
            else:
                print("Step 2: readonly_user role already exists, skipping...")

        conn.commit()
        
        # ========== STEP 3: Import CSV data from S3 ==========
        if bucket_name:
            print(f"Step 3: Importing CSV data from S3 bucket: {bucket_name}")
            csv_files = get_csv_files_from_s3(bucket_name)
            
            if csv_files:
                # Import theo thứ tự đúng (respecting FK dependencies)
                for table_key in TABLE_IMPORT_ORDER:
                    if table_key in csv_files:
                        s3_key = csv_files[table_key]
                        table_name = TABLE_NAME_MAPPING.get(table_key, table_key)
                        import_csv_to_table(conn, bucket_name, s3_key, table_name)
                
                # Import các file CSV khác không trong danh sách
                for file_name, s3_key in csv_files.items():
                    if file_name not in TABLE_IMPORT_ORDER:
                        import_csv_to_table(conn, bucket_name, s3_key, file_name)
            else:
                print("No CSV files found in S3, skipping data import")
        else:
            print("Step 3: DATA_BUCKET_NAME not set, skipping CSV import")

        print("Database initialization completed successfully!")
        return {"PhysicalResourceId": request_id}
        
    except Exception as e:
        print(f"Error during database initialization: {e}")
        raise e
    finally:
        conn.close()


def on_update(event):
    physical_id = event["PhysicalResourceId"]
    props = event["ResourceProperties"]
    print(f"update resource {physical_id} with props {props}")
    # Khi update, cũng chạy lại import để cập nhật data mới từ S3
    return on_create(event)


def on_delete(event):
    physical_id = event["PhysicalResourceId"]
    print(f"delete resource {physical_id}")
    return {"PhysicalResourceId": physical_id}
