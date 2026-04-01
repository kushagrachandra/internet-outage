-- MySQL 8.x — Internet outage monitor schema
-- Uncomment if you need to create the database on the server:
-- CREATE DATABASE IF NOT EXISTS outage_monitor
--   CHARACTER SET utf8mb4
--   COLLATE utf8mb4_unicode_ci;
-- USE outage_monitor;

-- One row per monitoring cycle (~15s): DNS checks, LAN pings, overall internet flag
CREATE TABLE IF NOT EXISTS connectivity_samples (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  checked_at DATETIME(6) NOT NULL,
  dns_google_ok TINYINT(1) NOT NULL COMMENT '8.8.8.8 resolution ok',
  dns_cloudflare_ok TINYINT(1) NOT NULL COMMENT '1.1.1.1 resolution ok',
  dns_opendns_ok TINYINT(1) NOT NULL COMMENT '208.67.222.222 resolution ok',
  dns_google_ms INT UNSIGNED NULL,
  dns_cloudflare_ms INT UNSIGNED NULL,
  dns_opendns_ms INT UNSIGNED NULL,
  ping_192_168_1_1_ok TINYINT(1) NOT NULL,
  ping_192_168_0_1_ok TINYINT(1) NOT NULL,
  ping_192_168_1_1_ms INT UNSIGNED NULL,
  ping_192_168_0_1_ms INT UNSIGNED NULL,
  internet_ok TINYINT(1) NOT NULL COMMENT '1 if any DNS check succeeded',
  PRIMARY KEY (id),
  KEY idx_connectivity_samples_checked_at (checked_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Outage windows: row inserted when internet_ok goes 1->0; ended_at set when back to 1
CREATE TABLE IF NOT EXISTS outage_events (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  started_at DATETIME(6) NOT NULL,
  ended_at DATETIME(6) NULL,
  is_internet_outage TINYINT(1) NOT NULL DEFAULT 1,
  notes VARCHAR(512) NULL,
  PRIMARY KEY (id),
  KEY idx_outage_events_started_at (started_at),
  KEY idx_outage_events_open (ended_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
