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

import boto3
import psycopg
from psycopg import sql

secrets_client = boto3.client("secretsmanager")

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


def on_create(event):
    request_id = event["RequestId"]
    props = event["ResourceProperties"]
    print(f"create new resource with props {props}")

    # Get database credentials
    db_secret = secrets_client.get_secret_value(SecretId=os.environ["DB_SECRET_NAME"])
    db_secret_dict = json.loads(db_secret["SecretString"])

    read_only_secret = secrets_client.get_secret_value(SecretId=os.environ["READ_ONLY_SECRET_NAME"])
    read_only_secret_dict = json.loads(read_only_secret["SecretString"])

    # Connect to the database
    conn = psycopg.connect(host=db_secret_dict["host"], port=db_secret_dict["port"], dbname="postgres",
        user=db_secret_dict["username"], password=db_secret_dict["password"], )
    try:
        with conn.cursor() as cur:
            # Execute hardcoded schema
            print("Executing Career Counseling schema...")
            cur.execute(CAREER_COUNSELING_SCHEMA)
            print("Career Counseling schema created successfully")
            
            # Enable pg_vector for embeddings (optional, for future AI features)
            cur.execute("CREATE EXTENSION IF NOT EXISTS vector")
            cur.execute("""
                CREATE TABLE IF NOT EXISTS embeddings (
                    id SERIAL PRIMARY KEY,
                    embedding VECTOR(1536),
                    database_name VARCHAR(255) NOT NULL,
                    schema_name VARCHAR(255) NOT NULL,
                    table_name VARCHAR(255) NOT NULL,
                    embedding_text TEXT NOT NULL,
                    embedding_hash VARCHAR(64) NOT NULL,
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE (database_name, schema_name, table_name, embedding_hash)
                )
            """)

            # Check if role exists
            cur.execute("""
            SELECT 1 FROM pg_catalog.pg_roles WHERE rolname = 'readonly_user'
            """)
            role_exists = cur.fetchone() is not None

            if not role_exists:
                # Create role with parameterized password
                # semgrep seems to be flagging as a false positive
                create_role_query = sql.SQL("CREATE ROLE readonly_user WITH LOGIN PASSWORD {}").format(
                    sql.Literal(read_only_secret_dict["password"]))
                cur.execute(create_role_query) # nosemgrep
                # Grant permissions
                cur.execute("""
                GRANT CONNECT ON DATABASE postgres TO readonly_user;
                GRANT USAGE ON SCHEMA public TO readonly_user;
                GRANT SELECT ON ALL TABLES IN SCHEMA public TO readonly_user;
                ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO readonly_user;
                """)

        conn.commit()
        return {"PhysicalResourceId": request_id}
    except Exception as e:
        raise e
    finally:
        conn.close()


def on_update(event):
    physical_id = event["PhysicalResourceId"]
    props = event["ResourceProperties"]
    print(f"update resource {physical_id} with props {props}")
    return {"PhysicalResourceId": physical_id}


def on_delete(event):
    physical_id = event["PhysicalResourceId"]
    print(f"delete resource {physical_id}")
    return {"PhysicalResourceId": physical_id}
