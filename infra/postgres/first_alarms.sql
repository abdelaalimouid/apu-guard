-- First sustained alarm in the 24 hours before each failure report
SELECT f.id AS failure,
       f.report_time,
       a.first_alarm,
       round(extract(epoch FROM f.report_time - a.first_alarm)::numeric / 3600, 1) AS hours_before
FROM failures f
LEFT JOIN LATERAL (
    SELECT min(window_start) AS first_alarm
    FROM alarms
    WHERE alarm AND window_start BETWEEN f.report_time - interval '24 hours' AND f.report_time
) a ON true
ORDER BY f.id;
