-- Digital Seettu Management System - MySQL schema
-- Run once to create a fresh database:
--   mysql -u root -p < database/schema.sql
-- WARNING: this script drops the Digital Seettu tables. Do not run it on a database that holds data you need.

CREATE DATABASE IF NOT EXISTS digital_seettu
    CHARACTER SET utf8mb4
    COLLATE utf8mb4_unicode_ci;

USE digital_seettu;

SET FOREIGN_KEY_CHECKS = 0;
DROP TABLE IF EXISTS reminders;
DROP TABLE IF EXISTS payments;
DROP TABLE IF EXISTS rounds;
DROP TABLE IF EXISTS group_members;
DROP TABLE IF EXISTS seettu_groups;
DROP TABLE IF EXISTS users;
SET FOREIGN_KEY_CHECKS = 1;

CREATE TABLE users (
    id            INT AUTO_INCREMENT PRIMARY KEY,
    full_name     VARCHAR(100) NOT NULL,
    email         VARCHAR(120) NOT NULL,
    phone         VARCHAR(25)  NULL,
    password_hash VARCHAR(255) NOT NULL,
    role          ENUM('organiser', 'member') NOT NULL DEFAULT 'member',
    created_at    DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_users_email (email)
) ENGINE=InnoDB;

CREATE TABLE seettu_groups (
    id                  INT AUTO_INCREMENT PRIMARY KEY,
    name                VARCHAR(100) NOT NULL,
    description         VARCHAR(255) NULL,
    organiser_id        INT NOT NULL,
    contribution_amount DECIMAL(12, 2) NOT NULL,
    frequency           ENUM('weekly', 'biweekly', 'monthly') NOT NULL,
    start_date          DATE NOT NULL,
    invite_code         CHAR(6) NOT NULL,
    status              ENUM('draft', 'active', 'completed') NOT NULL DEFAULT 'draft',
    created_at          DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_groups_invite_code (invite_code),
    KEY idx_groups_organiser (organiser_id),
    CONSTRAINT fk_groups_organiser FOREIGN KEY (organiser_id)
        REFERENCES users (id) ON DELETE CASCADE
) ENGINE=InnoDB;

CREATE TABLE group_members (
    id          INT AUTO_INCREMENT PRIMARY KEY,
    group_id    INT NOT NULL,
    user_id     INT NOT NULL,
    turn_order  INT NULL,
    joined_at   DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_members_group_user (group_id, user_id),
    UNIQUE KEY uq_members_group_turn (group_id, turn_order),
    KEY idx_members_user (user_id),
    CONSTRAINT fk_members_group FOREIGN KEY (group_id)
        REFERENCES seettu_groups (id) ON DELETE CASCADE,
    CONSTRAINT fk_members_user FOREIGN KEY (user_id)
        REFERENCES users (id) ON DELETE CASCADE
) ENGINE=InnoDB;

CREATE TABLE rounds (
    id                 INT AUTO_INCREMENT PRIMARY KEY,
    group_id           INT NOT NULL,
    round_no           INT NOT NULL,
    due_date           DATE NOT NULL,
    beneficiary_member INT NOT NULL,
    status             ENUM('pending', 'completed') NOT NULL DEFAULT 'pending',
    payout_date        DATE NULL,
    UNIQUE KEY uq_rounds_group_no (group_id, round_no),
    KEY idx_rounds_beneficiary (beneficiary_member),
    CONSTRAINT fk_rounds_group FOREIGN KEY (group_id)
        REFERENCES seettu_groups (id) ON DELETE CASCADE,
    CONSTRAINT fk_rounds_beneficiary FOREIGN KEY (beneficiary_member)
        REFERENCES group_members (id) ON DELETE CASCADE
) ENGINE=InnoDB;

CREATE TABLE payments (
    id          INT AUTO_INCREMENT PRIMARY KEY,
    round_id    INT NOT NULL,
    member_id   INT NOT NULL,
    amount      DECIMAL(12, 2) NOT NULL,
    status      ENUM('pending', 'paid') NOT NULL DEFAULT 'pending',
    paid_date   DATE NULL,
    method      ENUM('cash', 'bank', 'other') NULL,
    notes       VARCHAR(255) NULL,
    recorded_by INT NULL,
    updated_at  DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uq_payments_round_member (round_id, member_id),
    KEY idx_payments_member (member_id),
    KEY idx_payments_status (status),
    CONSTRAINT fk_payments_round FOREIGN KEY (round_id)
        REFERENCES rounds (id) ON DELETE CASCADE,
    CONSTRAINT fk_payments_member FOREIGN KEY (member_id)
        REFERENCES group_members (id) ON DELETE CASCADE,
    CONSTRAINT fk_payments_recorded_by FOREIGN KEY (recorded_by)
        REFERENCES users (id) ON DELETE SET NULL
) ENGINE=InnoDB;

CREATE TABLE reminders (
    id         INT AUTO_INCREMENT PRIMARY KEY,
    payment_id INT NOT NULL,
    member_id  INT NOT NULL,
    message    VARCHAR(255) NOT NULL,
    channel    ENUM('in_app', 'email') NOT NULL DEFAULT 'in_app',
    is_read    TINYINT(1) NOT NULL DEFAULT 0,
    sent_date  DATE NOT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_reminders_payment_day (payment_id, sent_date),
    KEY idx_reminders_member (member_id),
    CONSTRAINT fk_reminders_payment FOREIGN KEY (payment_id)
        REFERENCES payments (id) ON DELETE CASCADE,
    CONSTRAINT fk_reminders_member FOREIGN KEY (member_id)
        REFERENCES group_members (id) ON DELETE CASCADE
) ENGINE=InnoDB;
