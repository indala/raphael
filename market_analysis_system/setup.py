# Market Analysis System Setup
# This script sets up the required dependencies and directory structure

import os
import sys
import subprocess
from pathlib import Path

def create_directory_structure():
    """Create the required directory structure"""
    directories = [
        "market_analysis_system",
        "market_analysis_system/config",
        "market_analysis_system/reports",
        "market_analysis_system/logs",
        "market_analysis_system/src",
        "market_analysis_system/src/notifications",
        "market_analysis_system/src/reporting",
        "market_analysis_system/src/scheduler",
        "market_analysis_system/src/system_tray",
        "market_analysis_system/src/utils",
        "market_analysis_system/tests"
    ]
    
    for directory in directories:
        Path(directory).mkdir(parents=True, exist_ok=True)
        print(f"Created directory: {directory}")

def install_dependencies():
    """Install required Python packages"""
    required_packages = [
        "schedule",
        "pandas",
        "matplotlib", 
        "python-dotenv",
        "pywin32",
        "psutil",
        "jinja2",
        "weasyprint",
        "send2trash",
        "pynotifier",
        "pytz",
        "python-dateutil"
    ]
    
    print("Installing required packages...")
    for package in required_packages:
        try:
            subprocess.check_call([sys.executable, "-m", "pip", "install", package])
            print(f"Installed: {package}")
        except subprocess.CalledProcessError:
            print(f"Failed to install: {package}")

def create_main_files():
    """Create main Python files for the system"""
    
    # Main entry point
    main_content = '''#!/usr/bin/env python3
# Market Analysis System - Main Entry Point

import sys
import os
import logging
from pathlib import Path

# Add src to Python path
sys.path.append(str(Path(__file__).parent / "src"))

from scheduler.scheduler import MarketAnalysisScheduler
from reporting.report_generator import ReportGenerator
from notifications.notification_manager import NotificationManager
from utils.config_manager import ConfigManager
from utils.logger import setup_logging
from system_tray.tray_icon import SystemTrayApp

class MarketAnalysisSystem:
    def __init__(self):
        self.config = ConfigManager()
        self.logger = setup_logging(self.config.get_log_level())
        self.notification_manager = NotificationManager(self.config)
        self.report_generator = ReportGenerator(self.config, self.notification_manager)
        self.scheduler = MarketAnalysisScheduler(
            config=self.config,
            report_generator=self.report_generator,
            notification_manager=self.notification_manager
        )
        
    def run(self):
        """Start the market analysis system"""
        try:
            self.logger.info("Starting Market Analysis System")
            self.notification_manager.show_system_tray_notification(
                "Market Analysis System", 
                "System starting up..."
            )
            
            # Start the scheduler
            self.scheduler.start()
            
            # Start system tray application
            tray_app = SystemTrayApp(self)
            tray_app.run()
            
        except Exception as e:
            self.logger.error(f"System failed to start: {e}")
            self.notification_manager.show_error_notification(
                "System Error", 
                f"Failed to start system: {str(e)}"
            )
            sys.exit(1)

if __name__ == "__main__":
    system = MarketAnalysisSystem()
    system.run()
'''
    
    with open("market_analysis_system/src/main.py", "w") as f:
        f.write(main_content)
    
    print("Created main.py")

def main():
    print("Setting up Market Analysis System...")
    create_directory_structure()
    install_dependencies()
    create_main_files()
    print("\nSetup completed successfully!")
    print("Next steps:")
    print("1. Configure settings in config/settings.ini")
    print("2. Set up email notifications in config/email_config.ini")
    print("3. Configure Windows Task Scheduler integration")
    print("4. Run the system with: python market_analysis_system/src/main.py")

if __name__ == "__main__":
    main()