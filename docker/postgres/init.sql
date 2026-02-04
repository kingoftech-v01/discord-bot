-- PostgreSQL initialization script
-- This script runs when the container is first created

-- Create extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Grant privileges
GRANT ALL PRIVILEGES ON DATABASE discord_bot TO discord_bot;

-- Create schema for better organization (optional)
-- CREATE SCHEMA IF NOT EXISTS bot;
-- SET search_path TO bot, public;

-- Note: Tables will be created by Django migrations and bot initialization
-- This file is for any PostgreSQL-specific setup needed before the app starts
