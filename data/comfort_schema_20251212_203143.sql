CREATE TABLE IF NOT EXISTS comfort_logs (
  id               INTEGER PRIMARY KEY AUTOINCREMENT,
  timestamp_local  TEXT    NOT NULL,   -- ISO-8601 local datetime when YOU felt it
  source           TEXT    NOT NULL,   -- 'cli', 'discord', 'web_ui', etc.
  context          TEXT    NOT NULL,   -- 'morning_commute', 'afternoon_commute', 'midday_walk', ...
  leg              TEXT,               -- 'am', 'pm', 'none', 'n/a'
  location         TEXT,               -- 'home', 'work', 'other'
  wore             TEXT,               -- free-text description of layers/outfit
  comfort          TEXT,               -- 'too_cold', 'a_bit_cold', 'comfortable', 'a_bit_hot', 'too_hot'
  activity         TEXT,               -- 'walking', 'standing', 'laps', etc.

  temp_f           REAL,               -- forecast/observed temp at that moment
  feels_like_f     REAL,               -- windchill/heat index
  wind_speed_mph   REAL,
  wind_gust_mph    REAL,
  humidity_pct     REAL,
  pop_pct          REAL,               -- precip probability 0–100, if available

  raw_weather_json TEXT,               -- optional blob for debugging future tuning
  created_at       TEXT    NOT NULL DEFAULT (datetime('now')) -- UTC timestamp row was logged
);

CREATE INDEX IF NOT EXISTS idx_comfort_logs_timestamp
  ON comfort_logs(timestamp_local);

CREATE INDEX IF NOT EXISTS idx_comfort_logs_context
  ON comfort_logs(context);

CREATE INDEX IF NOT EXISTS idx_comfort_logs_comfort
  ON comfort_logs(comfort);
