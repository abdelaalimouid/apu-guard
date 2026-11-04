-- Runs once, the first time the Postgres volume is created.
-- One server, four databases: Airflow and MLflow metadata, and the apu serving database.

CREATE USER airflow WITH PASSWORD 'airflow';
CREATE DATABASE airflow OWNER airflow;
CREATE USER mlflow WITH PASSWORD 'mlflow';
CREATE DATABASE mlflow OWNER mlflow;
CREATE USER apu WITH PASSWORD 'apu';
CREATE DATABASE apu OWNER apu;
CREATE USER grafana WITH PASSWORD 'grafana';

\connect apu
SET ROLE apu;

-- 10-minute feature windows written by the streaming job (one row per window, upserted)
CREATE TABLE features (
    window_start        timestamp PRIMARY KEY,
    window_end          timestamp NOT NULL,
    n_rows              integer   NOT NULL,   -- 60 when the window is fully recorded (one row every 10 s)
    load_share          double precision,     -- share of the window spent loaded
    tp3_mean            double precision,
    tp3_min             double precision,
    tp3_max             double precision,
    tp3_range           double precision,
    tp2_max             double precision,
    motor_current_mean  double precision,
    oil_temp_mean       double precision,
    h1_mean             double precision,
    dv_pressure_mean    double precision,
    lps_max             double precision,     -- 1 if the 7 bar low-pressure switch fired
    tp3_flat            boolean,              -- TP3 did not move while the motor ran: likely frozen sensor
    ingested_at         timestamptz NOT NULL DEFAULT now()
);

-- Anomaly scores from the champion model
CREATE TABLE scores (
    window_start   timestamp PRIMARY KEY REFERENCES features (window_start),
    score          double precision,
    threshold      double precision,
    is_anomaly     boolean,
    sensor_fault   boolean,
    model_version  text,
    scored_at      timestamptz NOT NULL DEFAULT now()
);

-- Failure reports (maintenance log, Troshin et al. 2026; UCI windows) for dashboard annotations
CREATE TABLE failures (
    id           integer PRIMARY KEY,
    report_time  timestamp NOT NULL,
    uci_start    timestamp,
    uci_end      timestamp,
    label        text
);
INSERT INTO failures VALUES
    (1, '2020-04-18 07:05', '2020-04-18 00:00', '2020-04-18 23:59', 'air leak'),
    (2, '2020-05-30 01:10', '2020-05-29 23:30', '2020-05-30 06:00', 'air leak'),
    (3, '2020-06-05 18:00', '2020-06-05 10:00', '2020-06-07 14:30', 'air leak'),
    (4, '2020-07-15 18:25', '2020-07-15 14:30', '2020-07-15 19:00', 'air leak, pressure below 7 bar'),
    (5, '2020-07-17 05:46', NULL, NULL, 'air leak (maintenance log only)');

-- An alarm needs three anomalous windows in a row (30 min), so single noisy windows don't page anyone
CREATE VIEW alarms AS
SELECT window_start, score, threshold, model_version, is_anomaly, sensor_fault,
       (is_anomaly
        AND COALESCE(LAG(is_anomaly, 1) OVER w, false)
        AND COALESCE(LAG(is_anomaly, 2) OVER w, false)) AS alarm
FROM scores
WINDOW w AS (ORDER BY window_start);

RESET ROLE;
GRANT CONNECT ON DATABASE apu TO grafana;
GRANT USAGE ON SCHEMA public TO grafana;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO grafana;
