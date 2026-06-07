-- Create additional databases
CREATE DATABASE airflow;
CREATE DATABASE mlflow;

-- Grant permissions
GRANT ALL PRIVILEGES ON DATABASE worldbank TO de;
GRANT ALL PRIVILEGES ON DATABASE airflow TO de;
GRANT ALL PRIVILEGES ON DATABASE mlflow TO de;
