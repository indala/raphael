#!/usr/bin/env python3
# Configuration Manager for Market Analysis System

import configparser
import os
import json
from pathlib import Path
from typing import Dict, Any, Optional
import logging
from datetime import datetime

class ConfigManager:
    """Manages all configuration settings for the market analysis system"""
    
    def __init__(self, config_dir: str = "config"):
        self.config_dir = Path(config_dir)
        self.config = configparser.ConfigParser()
        self.settings = {}
        self._ensure_config_directory()
        self._load_default_configs()
        
    def _ensure_config_directory(self):
        """Ensure config directory exists"""
        self.config_dir.mkdir(parents=True, exist_ok=True)
    
    def _load_default_configs(self):
        """Load default configuration files"""
        # Load main settings
        self._load_settings_file("settings.ini")
        
        # Load email configuration if exists
        email_config_path = self.config_dir / "email_config.ini"
        if email_config_path.exists():
            self._load_email_config(email_config_path)
        
        # Load notification preferences
        self._load_notification_prefs()
        
    def _load_settings_file(self, filename: str):
        """Load a settings file"""
        config_path = self.config_dir / filename
        
        if not config_path.exists():
            self._create_default_settings()
        
        self.config.read(config_path)
        
        # Convert to dictionary for easier access
        self.settings = {}
        for section in self.config.sections():
            self.settings[section] = dict(self.config[section])
    
    def _create_default_settings(self):
        """Create default settings file"""
        default_config = configparser.ConfigParser()
        
        # Main settings
        default_config["System"] = {
            "log_level": "INFO",
            "max_log_size_mb": "10",
            "max_log_files": "5",
            "retry_attempts": "3",
            "retry_delay_seconds": "60",
            "timezone": "Asia/Kolkata",  # IST
            "report_format": "html,pdf",
            "cleanup_old_reports_days": "30"
        }
        
        default_config["Scheduler"] = {
            "enable_9am_task": "true",
            "enable_4pm_task": "true",
            "task_execution_timeout_minutes": "120",
            "startup_check_delay_seconds": "30"
        }
        
        default_config["Paths"] = {
            "reports_dir": "reports",
            "logs_dir": "logs",
            "config_dir": "config",
            "backup_dir": "backups"
        }
        
        default_config["MarketData"] = {
            "default_market_data_source": "yahoo",
            "data_refresh_interval_hours": "1",
            "max_data_points": "1000"
        }
        
        config_path = self.config_dir / "settings.ini"
        with open(config_path, 'w') as f:
            default_config.write(f)
    
    def _load_email_config(self, config_path: Path):
        """Load email configuration"""
        email_config = configparser.ConfigParser()
        email_config.read(config_path)
        
        if "Email" in email_config:
            self.settings["Email"] = dict(email_config["Email"])
    
    def _load_notification_prefs(self):
        """Load notification preferences"""
        prefs_path = self.config_dir / "notification_prefs.json"
        
        default_prefs = {
            "email_notifications": True,
            "desktop_notifications": True,
            "whatsapp_notifications": False,
            "notification_recipients": [],
            "notification_levels": ["info", "warning", "error"]
        }
        
        if prefs_path.exists():
            try:
                with open(prefs_path, 'r') as f:
                    prefs = json.load(f)
                    default_prefs.update(prefs)
            except Exception as e:
                logging.warning(f"Failed to load notification prefs: {e}")
        
        self.settings["NotificationPrefs"] = default_prefs
        
        # Save updated preferences
        with open(prefs_path, 'w') as f:
            json.dump(default_prefs, f, indent=2)
    
    def get(self, section: str, key: str, default: Any = None) -> Any:
        """Get a configuration value"""
        try:
            return self.settings.get(section, {}).get(key, default)
        except Exception:
            return default
    
    def get_log_level(self) -> str:
        """Get log level"""
        return self.get("System", "log_level", "INFO")
    
    def get_reports_dir(self) -> Path:
        """Get reports directory path"""
        reports_dir = self.get("Paths", "reports_dir", "reports")
        return Path(reports_dir)
    
    def get_logs_dir(self) -> Path:
        """Get logs directory path"""
        logs_dir = self.get("Paths", "logs_dir", "logs")
        return Path(logs_dir)
    
    def get_retry_attempts(self) -> int:
        """Get maximum retry attempts"""
        return int(self.get("System", "retry_attempts", 3))
    
    def get_retry_delay(self) -> int:
        """Get retry delay in seconds"""
        return int(self.get("System", "retry_delay_seconds", 60))
    
    def get_timezone(self) -> str:
        """Get timezone"""
        return self.get("System", "timezone", "Asia/Kolkata")
    
    def get_report_formats(self) -> list:
        """Get report formats"""
        formats = self.get("System", "report_format", "html,pdf")
        return [fmt.strip().lower() for fmt in formats.split(",")]
    
    def get_smtp_config(self) -> Optional[Dict]:
        """Get SMTP configuration if available"""
        if "Email" in self.settings:
            return self.settings["Email"]
        return None
    
    def get_notification_prefs(self) -> Dict:
        """Get notification preferences"""
        return self.settings.get("NotificationPrefs", {})
    
    def save_notification_prefs(self, prefs: Dict):
        """Save notification preferences"""
        prefs_path = self.config_dir / "notification_prefs.json"
        with open(prefs_path, 'w') as f:
            json.dump(prefs, f, indent=2)
        self.settings["NotificationPrefs"] = prefs
    
    def get_cleanup_days(self) -> int:
        """Get number of days to keep old reports"""
        return int(self.get("System", "cleanup_old_reports_days", 30))
    
    def get_task_timeout_minutes(self) -> int:
        """Get task execution timeout in minutes"""
        return int(self.get("Scheduler", "task_execution_timeout_minutes", 120))
    
    def get_startup_check_delay(self) -> int:
        """Get startup check delay in seconds"""
        return int(self.get("Scheduler", "startup_check_delay_seconds", 30))