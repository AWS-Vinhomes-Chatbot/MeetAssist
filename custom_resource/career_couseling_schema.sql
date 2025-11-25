-- Career Counseling Management Database Schema
-- Auto-executed by Custom Resource Lambda during CDK deployment
-- Admin authentication managed via AWS Cognito
-- Consultants and Customers (students, high school students, parents) receive email notifications only

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
    Specialties TEXT, -- JSON array: ["Tâm lý học", "Tư vấn gia đình", "Nghiện ma túy"]
    Qualifications TEXT, -- JSON array: ["Thạc sĩ Tâm lý học", "Chứng chỉ hành nghề"]
    JoinDate DATE NOT NULL, -- Ngày gia nhập làm việc
    CreatedAt TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP, -- Ngày tạo bản ghi
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

-- ============================================
-- COMMUNITY PROGRAM MANAGEMENT
-- ============================================

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
    CONSTRAINT CHK_ProgramStatus CHECK (Status IN ('upcoming', 'ongoing', 'completed')),
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
