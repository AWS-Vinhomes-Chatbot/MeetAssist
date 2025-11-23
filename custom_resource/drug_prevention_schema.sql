-- Drug Use Prevention Database Schema
-- Auto-executed by Custom Resource Lambda during CDK deployment

-- Bảng Role
CREATE TABLE IF NOT EXISTS Role (
    RoleID INT PRIMARY KEY GENERATED ALWAYS AS IDENTITY,
    RoleName VARCHAR(50) NOT NULL UNIQUE
);

-- Bảng Tài khoản
CREATE TABLE IF NOT EXISTS Account (
    AccountID INT PRIMARY KEY GENERATED ALWAYS AS IDENTITY,
    Username VARCHAR(50) NOT NULL UNIQUE,
    Email VARCHAR(100) NOT NULL UNIQUE,
    Password VARCHAR(512) NOT NULL,
    FullName VARCHAR(100) NOT NULL,
    RoleID INT NOT NULL,
    DateOfBirth DATE,
    CreatedAt TIMESTAMP NOT NULL,
    IsDisabled BOOLEAN NOT NULL DEFAULT false,
    ResetToken VARCHAR(255) NULL,
    ResetTokenExpiry TIMESTAMP NULL,
    ProfilePicture VARCHAR(500) NULL,
    FOREIGN KEY (RoleID) REFERENCES Role(RoleID)
);

-- Bảng Danh mục
CREATE TABLE IF NOT EXISTS Category (
    CategoryID INT PRIMARY KEY GENERATED ALWAYS AS IDENTITY,
    CategoryName VARCHAR(100) NOT NULL
);

-- Bảng Khóa học
CREATE TABLE IF NOT EXISTS Course(
    CourseID INT PRIMARY KEY GENERATED ALWAYS AS IDENTITY, 
    CourseName VARCHAR(255) NOT NULL,
    Risk VARCHAR(50) NOT NULL,
    Duration INT,
    Description VARCHAR(1000),
    EnrollCount INT NULL CHECK (EnrollCount >= 0),
    ImageUrl VARCHAR(300),
    Status VARCHAR(40) NOT NULL,
    IsDisabled BOOLEAN NOT NULL DEFAULT false
);

-- Bảng Danh mục khóa học
CREATE TABLE IF NOT EXISTS CourseCategory (
    CategoryID INT NOT NULL,
    CourseID INT NOT NULL,
    PRIMARY KEY (CategoryID, CourseID),
    FOREIGN KEY (CategoryID) REFERENCES Category(CategoryID),
    FOREIGN KEY (CourseID) REFERENCES Course(CourseID)
);

-- Bảng Bài học
CREATE TABLE IF NOT EXISTS Lesson(
    LessonID INT PRIMARY KEY GENERATED ALWAYS AS IDENTITY,
    CourseID INT NOT NULL,
    Title VARCHAR(255) NOT NULL,
    BriefDescription VARCHAR(200),
    Content TEXT,
    Duration INT, 
    VideoUrl VARCHAR(500),
    Status VARCHAR(40),
    IsDisabled BOOLEAN NOT NULL DEFAULT false,
    FOREIGN KEY (CourseID) REFERENCES Course(CourseID)
);

CREATE TABLE IF NOT EXISTS LessonProgress (
    LessonID INT NOT NULL,
    AccountID INT NOT NULL,
    CompletionPercentage FLOAT DEFAULT 0,
    IsCompleted BOOLEAN DEFAULT false,
    LastUpdatedAt TIMESTAMP,
    LastValidTime TIMESTAMP,
    PRIMARY KEY (LessonID, AccountID),
    FOREIGN KEY (LessonID) REFERENCES Lesson(LessonID),
    FOREIGN KEY (AccountID) REFERENCES Account(AccountID)
);

-- Bảng Bài thi khóa học
CREATE TABLE IF NOT EXISTS CourseExam (
    ExamID INT PRIMARY KEY GENERATED ALWAYS AS IDENTITY,
    CourseID INT NOT NULL UNIQUE,
    ExamTitle VARCHAR(255) NOT NULL,
    ExamDescription VARCHAR(500),
    PassingScore INT NOT NULL DEFAULT 80,
    IsDisabled BOOLEAN NOT NULL DEFAULT false,
    FOREIGN KEY (CourseID) REFERENCES Course(CourseID)
);

-- Bảng Câu hỏi thi
CREATE TABLE IF NOT EXISTS ExamQuestion (
    QuestionID INT PRIMARY KEY GENERATED ALWAYS AS IDENTITY,
    ExamID INT NOT NULL,
    QuestionText VARCHAR(1000) NOT NULL,
    Type VARCHAR(20) NOT NULL DEFAULT 'multiple',
    IsDisabled BOOLEAN NOT NULL DEFAULT false,
    FOREIGN KEY (ExamID) REFERENCES CourseExam(ExamID)
);

-- Bảng Đáp án thi
CREATE TABLE IF NOT EXISTS ExamAnswer (
    AnswerID INT PRIMARY KEY GENERATED ALWAYS AS IDENTITY,
    QuestionID INT NOT NULL,
    AnswerText VARCHAR(1000) NOT NULL,
    IsCorrect BOOLEAN NOT NULL DEFAULT false,
    IsDisabled BOOLEAN NOT NULL DEFAULT false,
    FOREIGN KEY (QuestionID) REFERENCES ExamQuestion(QuestionID)
);

-- Bảng Đăng ký khóa học
CREATE TABLE IF NOT EXISTS Enrollment (
    EnrollmentID INT PRIMARY KEY GENERATED ALWAYS AS IDENTITY,
    CourseID INT NOT NULL,
    AccountID INT NOT NULL,
    EnrollmentDate TIMESTAMP NOT NULL,
    CompletedDate TIMESTAMP,
    Status VARCHAR(20) NOT NULL,
    FOREIGN KEY (CourseID) REFERENCES Course(CourseID),
    FOREIGN KEY (AccountID) REFERENCES Account(AccountID)
);

-- Bảng Kết quả thi
CREATE TABLE IF NOT EXISTS ExamResult (
    ResultID INT PRIMARY KEY GENERATED ALWAYS AS IDENTITY,
    ExamID INT NOT NULL,
    AccountID INT NOT NULL,
    CorrectAnswers INT NOT NULL,
    IsPassed BOOLEAN NOT NULL DEFAULT false,
    AnswerData TEXT,
    FOREIGN KEY (ExamID) REFERENCES CourseExam(ExamID),
    FOREIGN KEY (AccountID) REFERENCES Account(AccountID)
);

-- Bảng Tư vấn viên
CREATE TABLE IF NOT EXISTS Consultant (
    AccountID INT NOT NULL UNIQUE,
    Name VARCHAR(100) NOT NULL,
    Bio TEXT,
    Title VARCHAR(100),
    ImageUrl VARCHAR(255),
    IsDisabled BOOLEAN NOT NULL DEFAULT false,
    FOREIGN KEY (AccountID) REFERENCES Account(AccountID)
);

-- Bảng Lịch tư vấn
CREATE TABLE IF NOT EXISTS ConsultantSchedule (
    ScheduleID INT PRIMARY KEY GENERATED ALWAYS AS IDENTITY,
    AccountID INT NOT NULL,
    Date DATE NOT NULL,
    StartTime TIME NOT NULL,
    EndTime TIME NOT NULL,
    FOREIGN KEY (AccountID) REFERENCES Consultant(AccountID),
    CONSTRAINT UQ_Consultant_Schedule UNIQUE (AccountID, Date, StartTime)
);

-- Bảng Cuộc hẹn
CREATE TABLE IF NOT EXISTS Appointment (
    AppointmentID INT PRIMARY KEY GENERATED ALWAYS AS IDENTITY,
    ConsultantID INT NOT NULL,
    AccountID INT NOT NULL,
    Time TIME NOT NULL,
    Date DATE NOT NULL,
    MeetingURL VARCHAR(255),
    Status VARCHAR(20) NOT NULL,
    Description TEXT,
    Duration INT NOT NULL,
    RejectedReason VARCHAR(500),
    Rating FLOAT,
    FOREIGN KEY (ConsultantID) REFERENCES Consultant(AccountID),
    FOREIGN KEY (AccountID) REFERENCES Account(AccountID),
    CONSTRAINT UQ_Consultant_Date_Time UNIQUE (AccountID, Date, Time)
);

-- Bảng Bài viết
CREATE TABLE IF NOT EXISTS Article (
    BlogID INT PRIMARY KEY GENERATED ALWAYS AS IDENTITY,
    AccountID INT NOT NULL,
    ArticleTitle VARCHAR(200),
    PublishedDate DATE NOT NULL,
    ImageUrl VARCHAR(255),
    Author VARCHAR(100) NOT NULL,
    Status VARCHAR(20) NOT NULL,
    Description VARCHAR(255),
    Content TEXT,
    IsDisabled BOOLEAN NOT NULL DEFAULT false,
    FOREIGN KEY (AccountID) REFERENCES Account(AccountID)
);

-- Bảng Chương trình cộng đồng
CREATE TABLE IF NOT EXISTS CommunityProgram (
    ProgramID INT PRIMARY KEY GENERATED ALWAYS AS IDENTITY,
    ProgramName VARCHAR(100) NOT NULL,
    Type VARCHAR(40) NULL DEFAULT 'online',
    Date DATE NOT NULL,
    Description VARCHAR(255),
    Content TEXT,
    Organizer VARCHAR(100),
    Url VARCHAR(300),
    "Platform" VARCHAR(50) NULL DEFAULT 'Zoom',
    ImageUrl VARCHAR(255),
    IsDisabled BOOLEAN NOT NULL DEFAULT false,
    Status VARCHAR(20) NOT NULL DEFAULT 'upcoming',
    ZoomLink VARCHAR(500) NULL,
    MeetingRoomName VARCHAR(255) NULL,
    CONSTRAINT CHK_ProgramStatus CHECK (Status IN ('upcoming', 'ongoing', 'completed')),
    CONSTRAINT CHK_Platform CHECK ("Platform" IN ('Zoom', NULL))
);

-- Bảng Người tham gia chương trình cộng đồng
CREATE TABLE IF NOT EXISTS CommunityProgramAttendee (
    ProgramID INT NOT NULL,
    AccountID INT NOT NULL,
    RegistrationDate TIMESTAMP NOT NULL,
    Status VARCHAR(20) NOT NULL,
    SurveyBeforeCompleted BOOLEAN NOT NULL DEFAULT false,
    SurveyAfterCompleted BOOLEAN NOT NULL DEFAULT false,
    FOREIGN KEY (ProgramID) REFERENCES CommunityProgram(ProgramID),
    FOREIGN KEY (AccountID) REFERENCES Account(AccountID),
    CONSTRAINT UQ_ProgramAttendee_ProgramID_AccountID UNIQUE (ProgramID, AccountID)
);

-- Bảng Chuyên môn
CREATE TABLE IF NOT EXISTS Specialty (
    SpecialtyID INT PRIMARY KEY GENERATED ALWAYS AS IDENTITY,
    Name VARCHAR(100) UNIQUE NOT NULL
);

-- Bảng Chuyên môn của tư vấn viên
CREATE TABLE IF NOT EXISTS ConsultantSpecialty (
    AccountID INT,
    SpecialtyID INT,
    PRIMARY KEY (AccountID, SpecialtyID),
    FOREIGN KEY (AccountID) REFERENCES Consultant(AccountID),
    FOREIGN KEY (SpecialtyID) REFERENCES Specialty(SpecialtyID)
);

-- Bảng Bằng cấp
CREATE TABLE IF NOT EXISTS Qualification (
    QualificationID INT PRIMARY KEY GENERATED ALWAYS AS IDENTITY,
    Name VARCHAR(100) UNIQUE NOT NULL
);

-- Bảng Bằng cấp của tư vấn viên
CREATE TABLE IF NOT EXISTS ConsultantQualification (
    AccountID INT,
    QualificationID INT,
    PRIMARY KEY (AccountID, QualificationID),
    FOREIGN KEY (AccountID) REFERENCES Consultant(AccountID),
    FOREIGN KEY (QualificationID) REFERENCES Qualification(QualificationID)
);

-- Bảng Danh mục tư vấn viên
CREATE TABLE IF NOT EXISTS ConsultantCategory (
    AccountID INT, 
    CategoryID INT,
    PRIMARY KEY (AccountID, CategoryID),
    FOREIGN KEY (AccountID) REFERENCES Consultant(AccountID),
    FOREIGN KEY (CategoryID) REFERENCES Category(CategoryID)
);

-- Bảng Danh mục khảo sát
CREATE TABLE IF NOT EXISTS SurveyCategory(
    SurveyCategoryID INT PRIMARY KEY GENERATED ALWAYS AS IDENTITY,
    SurveyCategoryName VARCHAR(200)
);

-- Bảng Khảo sát
CREATE TABLE IF NOT EXISTS Survey(
    SurveyID INT PRIMARY KEY GENERATED ALWAYS AS IDENTITY,
    Description TEXT NOT NULL,
    Type BOOLEAN NOT NULL,
    SurveyCategoryID INT,
    FOREIGN KEY (SurveyCategoryID) REFERENCES SurveyCategory(SurveyCategoryID)
);

-- Bảng Khảo sát chương trình cộng đồng
CREATE TABLE IF NOT EXISTS CommunityProgramSurvey (
    SurveyID INT NOT NULL,
    ProgramID INT NOT NULL,
    Type VARCHAR(20) NOT NULL,
    SurveyType VARCHAR(20) NOT NULL,
    FOREIGN KEY (SurveyID) REFERENCES Survey(SurveyID),
    FOREIGN KEY (ProgramID) REFERENCES CommunityProgram(ProgramID),
    CONSTRAINT PK_CommunityProgramSurvey PRIMARY KEY (ProgramID, SurveyID)
);

-- Bảng Phản hồi khảo sát
CREATE TABLE IF NOT EXISTS SurveyResponse (
    ResponseID INT PRIMARY KEY GENERATED ALWAYS AS IDENTITY,
    AccountID INT NOT NULL,
    ProgramID INT NOT NULL,
    SurveyType VARCHAR(10) NOT NULL CHECK (SurveyType IN ('before', 'after')),
    ResponseData TEXT NOT NULL,
    CreatedAt TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (AccountID) REFERENCES Account(AccountID),
    FOREIGN KEY (ProgramID) REFERENCES CommunityProgram(ProgramID),
    UNIQUE(AccountID, ProgramID, SurveyType)
);

-- Bảng Assessment
CREATE TABLE IF NOT EXISTS AssessmentResults (
    ResultID INT PRIMARY KEY GENERATED ALWAYS AS IDENTITY,
    AccountID INT NOT NULL,
    AssessmentID INT NOT NULL,
    Score INT NOT NULL, 
    RiskLevel VARCHAR(50),
    CreatedAt TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (AccountID) REFERENCES Account(AccountID)
);

-- Insert default roles
INSERT INTO Role (RoleName)
VALUES ('Admin'), ('Manager'), ('Staff'), ('Consultant'), ('Member')
ON CONFLICT (RoleName) DO NOTHING;
