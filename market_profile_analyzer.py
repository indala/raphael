"""
Market Profile Analyzer - Daily Automated Analysis System
Runs at 9:00 AM IST and 4:00 PM IST for comprehensive market analysis
"""

import os
import sys
import json
import logging
import smtplib
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
import requests
import schedule
import time
from typing import Dict, List, Optional, Tuple
import matplotlib.pyplot as plt
import seaborn as sns
from io import BytesIO
import warnings

# Suppress warnings for cleaner output
warnings.filterwarnings('ignore')

# Configuration
CONFIG = {
    "api_endpoints": {
        "portfolio": "https://api.marketprofile.com/portfolio/summary",
        "quotes": "https://api.marketprofile.com/market/quotes",
        "sector_performance": "https://api.marketprofile.com/market/sector",
        "top_movers": "https://api.marketprofile.com/market/movers",
        "pnl_report": "https://api.marketprofile.com/reports/pnl"
    },
    "email": {
        "smtp_server": "smtp.gmail.com",
        "smtp_port": 587,
        "sender_email": "your_email@gmail.com",
        "sender_password": "your_app_password",
        "receiver_emails": ["receiver1@gmail.com", "receiver2@gmail.com"],
        "subject_prefix": "[Market Profile] Daily Analysis - "
    },
    "logging": {
        "log_file": "market_profile_analyzer.log",
        "log_level": logging.INFO
    },
    "timezone": "Asia/Kolkata",
    "market_hours": {
        "morning": "09:00",
        "evening": "16:00"
    }
}

# Set up logging
logging.basicConfig(
    level=CONFIG["logging"]["log_level"],
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(CONFIG["logging"]["log_file"]),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


class MarketProfileAnalyzer:
    """
    Main class for Market Profile Analysis System
    """
    
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'MarketProfileAnalyzer/1.0',
            'Accept': 'application/json',
            'Content-Type': 'application/json'
        })
        
    def get_portfolio_summary(self) -> Dict:
        """
        Fetch portfolio summary data
        
        Returns:
            Dictionary containing portfolio summary
        """
        try:
            logger.info("Fetching portfolio summary...")
            
            # Mock data for demonstration
            # In production, replace with actual API call
            portfolio_data = {
                "total_investment": 1500000.00,
                "current_value": 1625000.00,
                "total_gain": 125000.00,
                "total_gain_pct": 8.33,
                "portfolio_value": 1625000.00,
                "cash_balance": 50000.00,
                "margin_used": 25000.00,
                "assets_under_management": 1600000.00,
                "portfolio_health": "Good",
                "risk_level": "Moderate",
                "diversification_score": 8.5,
                "holdings": [
                    {"symbol": "RELIANCE", "quantity": 50, "avg_price": 2500.00, "current_price": 2750.00, "gain_pct": 10.0},
                    {"symbol": "TCS", "quantity": 100, "avg_price": 3200.00, "current_price": 3450.00, "gain_pct": 7.81},
                    {"symbol": "HDFCBANK", "quantity": 200, "avg_price": 1500.00, "current_price": 1620.00, "gain_pct": 8.0},
                    {"symbol": "INFY", "quantity": 75, "avg_price": 1800.00, "current_price": 1950.00, "gain_pct": 8.33},
                    {"symbol": "ICICIBANK", "quantity": 150, "avg_price": 900.00, "current_price": 980.00, "gain_pct": 8.89}
                ]
            }
            
            logger.info(f"Successfully fetched portfolio summary. Total value: ₹{portfolio_data['portfolio_value']:,.2f}")
            return portfolio_data
            
        except Exception as e:
            logger.error(f"Failed to fetch portfolio summary: {str(e)}")
            # Return mock data in case of failure
            return {
                "total_investment": 0.00,
                "current_value": 0.00,
                "total_gain": 0.00,
                "total_gain_pct": 0.0,
                "portfolio_value": 0.00,
                "cash_balance": 0.00,
                "margin_used": 0.00,
                "assets_under_management": 0.00,
                "portfolio_health": "Unknown",
                "risk_level": "Unknown",
                "diversification_score": 0.0,
                "holdings": []
            }
    
    def get_market_quotes(self, indices: List[str]) -> Dict:
        """
        Get market quotes for specified indices
        
        Args:
            indices: List of index names (e.g., ['NIFTY 50', 'BANK NIFTY', 'SENSEX'])
            
        Returns:
            Dictionary containing market quotes
        """
        try:
            logger.info(f"Fetching market quotes for {indices}...")
            
            # Mock data for demonstration
            quotes_data = {
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "indices": {}
            }
            
            for index in indices:
                # Generate mock data based on index
                if "NIFTY" in index.upper():
                    quotes_data["indices"][index] = {
                        "last_price": 20500.50 + (np.random.random() * 100 - 50),
                        "change": np.random.uniform(-1.5, 1.5),
                        "change_pct": np.random.uniform(-0.8, 0.8),
                        "high": 20550.00,
                        "low": 20450.00,
                        "open": 20480.00,
                        "volume": int(250000000 + np.random.random() * 10000000),
                        "year_high": 21000.00,
                        "year_low": 18000.00,
                        "trend": "Bullish" if np.random.random() > 0.3 else "Neutral"
                    }
                elif "BANK" in index.upper():
                    quotes_data["indices"][index] = {
                        "last_price": 45500.75 + (np.random.random() * 200 - 100),
                        "change": np.random.uniform(-2.0, 2.0),
                        "change_pct": np.random.uniform(-1.0, 1.0),
                        "high": 45600.00,
                        "low": 45400.00,
                        "open": 45550.00,
                        "volume": int(180000000 + np.random.random() * 5000000),
                        "year_high": 47000.00,
                        "year_low": 40000.00,
                        "trend": "Bullish" if np.random.random() > 0.4 else "Neutral"
                    }
                elif "SENSEX" in index.upper():
                    quotes_data["indices"][index] = {
                        "last_price": 70500.25 + (np.random.random() * 300 - 150),
                        "change": np.random.uniform(-3.0, 3.0),
                        "change_pct": np.random.uniform(-1.5, 1.5),
                        "high": 70650.00,
                        "low": 70350.00,
                        "open": 70550.00,
                        "volume": int(350000000 + np.random.random() * 15000000),
                        "year_high": 72000.00,
                        "year_low": 65000.00,
                        "trend": "Bullish" if np.random.random() > 0.35 else "Neutral"
                    }
            
            logger.info(f"Successfully fetched market quotes for {len(indices)} indices")
            return quotes_data
            
        except Exception as e:
            logger.error(f"Failed to fetch market quotes: {str(e)}")
            # Return mock data in case of failure
            return {
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "indices": {}
            }
    
    def get_sector_performance(self) -> Dict:
        """
        Get sector performance data
        
        Returns:
            Dictionary containing sector performance
        """
        try:
            logger.info("Fetching sector performance data...")
            
            # Mock data for demonstration
            sectors = [
                "IT", "FINANCIAL SERVICES", "ENERGY", "AUTOMOBILE", 
                "PHARMA", "FMCG", "METAL", "REALTY"
            ]
            
            sector_data = {
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "sectors": {}
            }
            
            for sector in sectors:
                sector_data["sectors"][sector] = {
                    "last_price": 10000.00 + (np.random.random() * 5000 - 2500),
                    "change": np.random.uniform(-5.0, 5.0),
                    "change_pct": np.random.uniform(-3.0, 3.0),
                    "top_gainers": ["TCS", "INFY", "HCLTECH"][:int(np.random.random() * 3) + 1],
                    "top_losers": ["WIPRO", "TECHM"][:int(np.random.random() * 2) + 1],
                    "market_cap": f"{int(500000 + np.random.random() * 200000)} Cr",
                    "performance_rating": round(np.random.uniform(6.0, 9.5), 1)
                }
            
            logger.info(f"Successfully fetched sector performance for {len(sectors)} sectors")
            return sector_data
            
        except Exception as e:
            logger.error(f"Failed to fetch sector performance: {str(e)}")
            return {
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "sectors": {}
            }
    
    def get_top_movers(self) -> Dict:
        """
        Get top gainers and losers data
        
        Returns:
            Dictionary containing top movers data
        """
        try:
            logger.info("Fetching top movers data...")
            
            # Mock data for demonstration
            top_movers_data = {
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "top_gainers": [],
                "top_losers": [],
                "most_active": []
            }
            
            # Generate mock top gainers
            stocks = ["RELIANCE", "TCS", "HDFCBANK", "INFY", "ICICIBANK", "BHARTIARTL", 
                     "LT", "HINDUNILVR", "ITC", "KOTAKBANK", "SBIN", "BAJFINANCE"]
            
            for stock in stocks[:10]:
                if np.random.random() > 0.5:
                    top_movers_data["top_gainers"].append({
                        "symbol": stock,
                        "price": round(100 + np.random.random() * 900, 2),
                        "change": round(np.random.uniform(1.0, 10.0), 2),
                        "change_pct": round(np.random.uniform(0.5, 8.0), 2),
                        "volume": int(5000000 + np.random.random() * 20000000)
                    })
                else:
                    top_movers_data["top_losers"].append({
                        "symbol": stock,
                        "price": round(100 + np.random.random() * 900, 2),
                        "change": round(np.random.uniform(-10.0, -1.0), 2),
                        "change_pct": round(np.random.uniform(-8.0, -0.5), 2),
                        "volume": int(5000000 + np.random.random() * 20000000)
                    })
            
            # Most active stocks
            top_movers_data["most_active"] = top_movers_data["top_gainers"][:5] + top_movers_data["top_losers"][:5]
            
            logger.info(f"Successfully fetched top movers data. Gainers: {len(top_movers_data['top_gainers'])}, Losers: {len(top_movers_data['top_losers'])}")
            return top_movers_data
            
        except Exception as e:
            logger.error(f"Failed to fetch top movers data: {str(e)}")
            return {
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "top_gainers": [],
                "top_losers": [],
                "most_active": []
            }
    
    def generate_pnl_report(self, portfolio_data: Dict) -> Dict:
        """
        Generate Profit & Loss report
        
        Args:
            portfolio_data: Portfolio summary data
            
        Returns:
            Dictionary containing P&L report
        """
        try:
            logger.info("Generating P&L report...")
            
            pnl_report = {
                "report_date": datetime.now().strftime("%Y-%m-%d"),
                "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "portfolio_summary": portfolio_data,
                "daily_pnl": portfolio_data.get("total_gain", 0.00),
                "daily_pnl_pct": portfolio_data.get("total_gain_pct", 0.0),
                "weekly_pnl": round(portfolio_data.get("total_gain", 0.00) * 5, 2),  # Simple projection
                "monthly_pnl": round(portfolio_data.get("total_gain", 0.00) * 22, 2),  # Simple projection
                "pnl_breakdown": {
                    "equity_gain": 110000.00,
                    "derivative_gain": 15000.00,
                    "dividend_income": 5000.00,
                    "interest_income": 2000.00,
                    "fees_expenses": -7000.00
                },
                "performance_metrics": {
                    "sharpe_ratio": 1.2,
                    "sortino_ratio": 1.8,
                    "max_drawdown": -4.5,
                    "cagr": 12.5,
                    "volatility": 15.2
                }
            }
            
            logger.info("P&L report generated successfully")
            return pnl_report
            
        except Exception as e:
            logger.error(f"Failed to generate P&L report: {str(e)}")
            return {
                "report_date": datetime.now().strftime("%Y-%m-%d"),
                "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "error": str(e)
            }
    
    def generate_investment_suggestions(self, portfolio_data: Dict, market_data: Dict) -> Dict:
        """
    
        Generate investment suggestions based on current market conditions
        
        Args:
            portfolio_data: Portfolio summary data
            market_data: Market quotes data
            
        Returns:
            Dictionary containing investment suggestions
        """
        try:
            logger.info("Generating investment suggestions...")
            
            suggestions = {
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "overall_sentiment": "Positive" if np.random.random() > 0.3 else "Cautious",
                "suggestions": [],
                "risk_assessment": {
                    "portfolio_risk": portfolio_data.get("risk_level", "Moderate"),
                    "market_risk": "Low" if np.random.random() > 0.4 else "Moderate",
                    "overall_risk": "Moderate"
                },
                "diversification_recommendations": []
            }
            
            # Generate investment suggestions based on portfolio and market conditions
            portfolio_value = portfolio_data.get("portfolio_value", 0)
            diversification_score = portfolio_data.get("diversification_score", 0)
            
            # Sector allocation suggestions
            sectors = ["IT", "FINANCIAL SERVICES", "ENERGY", "AUTOMOBILE", 
                      "PHARMA", "FMCG", "METAL", "REALTY"]
            
            for sector in sectors:
                allocation_pct = np.random.uniform(5.0, 25.0)
                suggestions["diversification_recommendations"].append({
                    "sector": sector,
                    "current_allocation": f"{allocation_pct:.1f}%",
                    "recommended_allocation": f"{allocation_pct + np.random.uniform(-3.0, 3.0):.1f}%",
                    "action": "Hold" if np.random.random() > 0.3 else ("Increase" if np.random.random() > 0.5 else "Reduce")
                })
            
            # Individual stock suggestions
            stocks = ["RELIANCE", "TCS", "HDFCBANK", "INFY", "ICICIBANK", 
                     "BHARTIARTL", "LT", "HINDUNILVR"]
            
            for stock in stocks:
                current_holding = next((h for h in portfolio_data.get("holdings", []) if h["symbol"] == stock), None)
                
                if current_holding:
                    gain_pct = current_holding.get("gain_pct", 0)
                    if gain_pct > 15:
                        action = "Take Profit"
                        reason = "Strong gains achieved"
                    elif gain_pct < -10:
                        action = "Consider Exit"
                        reason = "Significant losses"
                    else:
                        action = "Hold"
                        reason = "Stable performance"
                else:
                    action = "Monitor"
                    reason = "Not currently held"
                
                suggestions["suggestions"].append({
                    "type": "Stock",
                    "symbol": stock,
                    "action": action,
                    "reason": reason,
                    "confidence": round(np.random.uniform(6.0, 9.5), 1)
                })
            
            # Market timing suggestions
            nifty_change = market_data.get("indices", {}).get("NIFTY 50", {}).get("change_pct", 0)
            if nifty_change > 2.0:
                suggestions["suggestions"].append({
                    "type": "Market Timing",
                    "symbol": "NIFTY 50",
                    "action": "Cautious",
                    "reason": "Market showing strong momentum, consider partial profit booking",
                    "confidence": 7.8
                })
            elif nifty_change < -2.0:
                suggestions["suggestions"].append({
                    "type": "Market Timing",
                    "symbol": "NIFTY 50",
                    "action": "Opportunistic",
                    "reason": "Market showing weakness, potential buying opportunity",
                    "confidence": 7.2
                })
            
            logger.info(f"Generated {len(suggestions['suggestions'])} investment suggestions")
            return suggestions
            
        except Exception as e:
            logger.error(f"Failed to generate investment suggestions: {str(e)}")
            return {
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "error": str(e),
                "suggestions": []
            }
    
    def create_risk_alerts(self, portfolio_data: Dict, market_data: Dict, 
                          sector_data: Dict, top_movers_data: Dict) -> Dict:
        """
        Create risk alerts based on current market conditions
        
        Args:
            portfolio_data: Portfolio summary data
            market_data: Market quotes data
            sector_data: Sector performance data
            top_movers_data: Top movers data
            
        Returns:
            Dictionary containing risk alerts
        """
        try:
            logger.info("Creating risk alerts...")
            
            alerts = {
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "high_priority": [],
                "medium_priority": [],
                "low_priority": [],
                "portfolio_health": portfolio_data.get("portfolio_health", "Unknown"),
                "overall_risk_level": "Moderate"
            }
            
            # Check portfolio health
            if portfolio_data.get("portfolio_health") != "Good":
                alerts["high_priority"].append({
                    "type": "Portfolio Health",
                    "message": f"Portfolio health is {portfolio_data.get('portfolio_health')}. Review positions.",
                    "severity": "High",
                    "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                })
            
            # Check diversification
            diversification_score = portfolio_data.get("diversification_score", 0)
            if diversification_score < 6.0:
                alerts["medium_priority"].append({
                    "type": "Diversification",
                    "message": f"Low diversification score: {diversification_score:.1f}/10. Consider diversifying across sectors.",
                    "severity": "Medium",
                    "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                })
            
            # Check market indices
            for index, data in market_data.get("indices", {}).items():
                change_pct = data.get("change_pct", 0)
                if abs(change_pct) > 5.0:
                    severity = "High" if abs(change_pct) > 7.0 else "Medium"
                    alerts[severity.lower() + "_priority"].append({
                        "type": "Market Index",
                        "message": f"{index} moved {change_pct:.2f}% ({'up' if change_pct > 0 else 'down'}).",
                        "severity": severity,
                        "timestamp": data.get("timestamp", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
                    })
            
            # Check sector performance
            for sector, data in sector_data.get("sectors", {}).items():
                change_pct = data.get("change_pct", 0)
                if abs(change_pct) > 4.0:
                    alerts["medium_priority"].append({
                        "type": "Sector Performance",
                        "message": f"{sector} sector moved {change_pct:.2f}%. Review sector exposure.",
                        "severity": "Medium",
                        "timestamp": data.get("timestamp", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
                    })
            
            # Check top losers
            for loser in top_movers_data.get("top_losers", [])[:3]:  # Top 3 losers
                if loser.get("change_pct", 0) < -7.0:
                    alerts["high_priority"].append({
                        "type": "Top Loser",
                        "message": f"{loser['symbol']} down {loser['change_pct']:.2f}%. Consider reviewing position.",
                        "severity": "High",
                        "timestamp": top_movers_data.get("timestamp", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
                    })
            
            # Check top gainers (potential overbought)
            for gainer in top_movers_data.get("top_gainers", [])[:3]:  # Top 3 gainers
                if gainer.get("change_pct", 0) > 8.0:
                    alerts["medium_priority"].append({
                        "type": "Top Gainer",
                        "message": f"{gainer['symbol']} up {gainer['change_pct']:.2f}%. Consider profit booking.",
                        "severity": "Medium",
                        "timestamp": top_movers_data.get("timestamp", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
                    })
            
            # Set overall risk level
            if len(alerts["high_priority"]) > 2:
                alerts["overall_risk_level"] = "High"
            elif len(alerts["high_priority"]) > 0 or len(alerts["medium_priority"]) > 3:
                alerts["overall_risk_level"] = "Moderate"
            else:
                alerts["overall_risk_level"] = "Low"
            
            logger.info(f"Created {len(alerts['high_priority'])} high priority alerts")
            return alerts
            
        except Exception as e:
            logger.error(f"Failed to create risk alerts: {str(e)}")
            return {
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "error": str(e),
                "high_priority": [],
                "medium_priority": [],
                "low_priority": []
            }
    
    def create_visualizations(self, portfolio_data: Dict, market_data: Dict, 
                            sector_data: Dict, output_dir: str = "visualizations") -> List[str]:
        """
        Create visualizations for the report
        
        Args:
            portfolio_data: Portfolio summary data
            market_data: Market quotes data
            sector_data: Sector performance data
            output_dir: Directory to save visualizations
            
        Returns:
            List of paths to created visualizations
        """
        try:
            logger.info("Creating visualizations...")
            
            if not os.path.exists(output_dir):
                os.makedirs(output_dir)
            
            visualization_paths = []
            
            # Set style
            plt.style.use('seaborn-v0_8')
            sns.set_palette("husl")
            
            # 1. Portfolio Allocation Pie Chart
            plt.figure(figsize=(10, 8))
            holdings = portfolio_data.get("holdings", [])
            if holdings:
                symbols = [h["symbol"] for h in holdings]
                values = [h["current_price"] * h["quantity"] for h in holdings]
                
                plt.pie(values, labels=symbols, autopct='%1.1f%%', startangle=140)
                plt.title('Portfolio Allocation', fontsize=16, fontweight='bold')
                plt.tight_layout()
                
                pie_path = os.path.join(output_dir, "portfolio_allocation.png")
                plt.savefig(pie_path, dpi=150, bbox_inches='tight')
                plt.close()
                visualization_paths.append(pie_path)
            
            # 2. Market Indices Performance Bar Chart
            plt.figure(figsize=(12, 6))
            indices = market_data.get("indices", {})
            if indices:
                index_names = list(indices.keys())
                changes = [data.get("change_pct", 0) for data in indices.values()]
                
                bars = plt.bar(index_names, changes, color=['green' if c > 0 else 'red' for c in changes])
                plt.title('Market Indices Performance (% Change)', fontsize=16, fontweight='bold')
                plt.ylabel('Change (%)')
                plt.xticks(rotation=45)
                plt.grid(axis='y', alpha=0.3)
                
                # Add value labels
                for bar in bars:
                    height = bar.get_height()
                    plt.text(bar.get_x() + bar.get_width()/2., height,
                            f'{height:.2f}%', ha='center', va='bottom' if height > 0 else 'top')
                
                plt.tight_layout()
                
                indices_path = os.path.join(output_dir, "market_indices.png")
                plt.savefig(indices_path, dpi=150, bbox_inches='tight')
                plt.close()
                visualization_paths.append(indices_path)
            
            # 3. Sector Performance Heatmap
            plt.figure(figsize=(12, 6))
            sectors = sector_data.get("sectors", {})
            if sectors:
                sector_names = list(sectors.keys())
                changes = [data.get("change_pct", 0) for data in sectors.values()]
                
                # Create heatmap-like bar chart
                colors = ['green' if c > 0 else 'red' for c in changes]
                bars = plt.bar(sector_names, changes, color=colors)
                plt.title('Sector Performance (% Change)', fontsize=16, fontweight='bold')
                plt.ylabel('Change (%)')
                plt.xticks(rotation=45)
                plt.grid(axis='y', alpha=0.3)
                
                # Add value labels
                for bar in bars:
                    height = bar.get_height()
                    plt.text(bar.get_x() + bar.get_width()/2., height,
                            f'{height:.2f}%', ha='center', va='bottom' if height > 0 else 'top')
                
                plt.tight_layout()
                
                sectors_path = os.path.join(output_dir, "sector_performance.png")
                plt.savefig(sectors_path, dpi=150, bbox_inches='tight')
                plt.close()
                visualization_paths.append(sectors_path)
            
            # 4. Portfolio Gain/Loss Waterfall Chart
            plt.figure(figsize=(12, 6))
            holdings = portfolio_data.get("holdings", [])
            if holdings:
                symbols = [h["symbol"] for h in holdings]
                gains = [h.get("gain_pct", 0) for h in holdings]
                
                colors = ['green' if g > 0 else 'red' for g in gains]
                bars = plt.bar(symbols, gains, color=colors)
                plt.title('Individual Stock Gains/Losses (%)', fontsize=16, fontweight='bold')
                plt.ylabel('Gain/Loss (%)')
                plt.xticks(rotation=45)
                plt.grid(axis='y', alpha=0.3)
                
                # Add value labels
                for bar in bars:
                    height = bar.get_height()
                    plt.text(bar.get_x() + bar.get_width()/2., height,
                            f'{height:.2f}%', ha='center', va='bottom' if height > 0 else 'top')
                
                plt.tight_layout()
                
                waterfall_path = os.path.join(output_dir, "portfolio_gains.png")
                plt.savefig(waterfall_path, dpi=150, bbox_inches='tight')
                plt.close()
                visualization_paths.append(waterfall_path)
            
            logger.info(f"Created {len(visualization_paths)} visualizations")
            return visualization_paths
            
        except Exception as e:
            logger.error(f"Failed to create visualizations: {str(e)}")
            return []
    
    def format_report(self, portfolio_data: Dict, market_data: Dict, 
                     sector_data: Dict, top_movers_data: Dict, 
                     pnl_report: Dict, suggestions: Dict, 
                     alerts: Dict, visualizations: List[str]) -> str:
        """
        Format comprehensive report
        
        Args:
            portfolio_data: Portfolio summary data
            market_data: Market quotes data
            sector_data: Sector performance data
            top_movers_data: Top movers data
            pnl_report: P&L report
            suggestions: Investment suggestions
            alerts: Risk alerts
            visualizations: List of visualization paths
            
        Returns:
            Formatted report as HTML string
        """
        try:
            logger.info("Formatting comprehensive report...")
            
            # Generate report timestamp
            report_timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            report_date = datetime.now().strftime("%B %d, %Y")
            
            # Calculate key metrics
            total_investment = portfolio_data.get("total_investment", 0)
            current_value = portfolio_data.get("current_value", 0)
            total_gain = portfolio_data.get("total_gain", 0)
            total_gain_pct = portfolio_data.get("total_gain_pct", 0)
            diversification_score = portfolio_data.get("diversification_score", 0)
            
            # Market indices summary
            indices = market_data.get("indices", {})
            market_summary = {
                "advancers": 0,
                "decliners": 0,
                "unchanged": 0
            }
            
            for index, data in indices.items():
                change_pct = data.get("change_pct", 0)
                if change_pct > 0.5:
                    market_summary["advancers"] += 1
                elif change_pct < -0.5:
                    market_summary["decliners"] += 1
                else:
                    market_summary["unchanged"] += 1
            
            # Create HTML report
            html_report = f"""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Market Profile Analysis Report - {report_date}</title>
    <style>
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}
        
        body {{
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            line-height: 1.6;
            color: #333;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            padding: 20px;
        }}
        
        .container {{
            max-width: 1200px;
            margin: 0 auto;
            background: white;
            border-radius: 15px;
            box-shadow: 0 10px 40px rgba(0,0,0,0.3);
            overflow: hidden;
        }}
        
        .header {{
            background: linear-gradient(135deg, #1e3c72 0%, #2a5298 100%);
            color: white;
            padding: 30px;
            text-align: center;
        }}
        
        .header h1 {{
            font-size: 2.5em;
            margin-bottom: 10px;
            text-shadow: 2px 2px 4px rgba(0,0,0,0.3);
        }}
        
        .header p {{
            font-size: 1.2em;
            opacity: 0.9;
        }}
        
        .report-meta {{
            background: #f8f9fa;
            padding: 20px;
            border-bottom: 2px solid #e9ecef;
            display: flex;
            justify-content: space-between;
            flex-wrap: wrap;
        }}
        
        .meta-item {{
            margin: 10px 0;
        }}
        
        .meta-item strong {{
            color: #1e3c72;
        }}
        
        .summary-section {{
            padding: 30px;
            background: #f8f9fa;
        }}
        
        .summary-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
            gap: 20px;
            margin-top: 20px;
        }}
        
        .summary-card {{
            background: white;
            padding: 20px;
            border-radius: 10px;
            box-shadow: 0 4px 6px rgba(0,0,0,0.1);
            border-left: 5px solid;
        }}
        
        .summary-card.green {{
            border-color: #28a745;
        }}
        
        .summary-card.red {{
            border-color: #dc3545;
        }}
        
        .summary-card.blue {{
            border-color: #007bff;
        }}
        
        .summary-card.orange {{
            border-color: #fd7e14;
        }}
        
        .summary-card h3 {{
            color: #6c757d;
            font-size: 0.9em;
            text-transform: uppercase;
            margin-bottom: 10px;
        }}
        
        .summary-card .value {{
            font-size: 2em;
            font-weight: bold;
            margin-bottom: 5px;
        }}
        
        .summary-card .label {{
            font-size: 0.9em;
            color: #6c757d;
        }}
        
        .section {{
            padding: 30px;
        }}
        
        .section-title {{
            font-size: 1.8em;
            color: #1e3c72;
            margin-bottom: 20px;
            padding-bottom: 10px;
            border-bottom: 3px solid #1e3c72;
        }}
        
        .subsection {{
            margin-bottom: 30px;
        }}
        
        .subsection-title {{
            font-size: 1.4em;
            color: #2c3e50;
            margin-bottom: 15px;
            padding-left: 10px;
            border-left: 4px solid #3498db;
        }}
        
        .table {{
            width: 100%;
            border-collapse: collapse;
            margin: 20px 0;
        }}
        
        .table th {{
            background: #1e3c72;
            color: white;
            padding: 12px;
            text-align: left;
        }}
        
        .table td {{
            padding: 12px;
            border-bottom: 1px solid #e9ecef;
        }}
        
        .table tr:hover {{
            background: #f8f9fa;
        }}
        
        .table tr.positive {{
            background: #d4edda;
        }}
        
        .table tr.negative {{
            background: #f8d7da;
        }}
        
        .alert-box {{
            padding: 15px;
            margin: 15px 0;
            border-radius: 8px;
            border-left: 5px solid;
        }}
        
        .alert-box.high {{
            background: #fff3cd;
            border-color: #ffc107;
        }}
        
        .alert-box.medium {{
            background: #d1ecf1;
            border-color: #17a2b8;
        }}
        
        .alert-box.low {{
            background: #d4edda;
            border-color: #28a745;
        }}
        
        .alert-box h4 {{
            margin-bottom: 10px;
            display: flex;
            align-items: center;
        }}
        
        .alert-box .severity {{
            display: inline-block;
            padding: 3px 10px;
            border-radius: 12px;
            font-size: 0.8em;
            font-weight: bold;
            margin-left: 10px;
        }}
        
        .alert-box.high .severity {{
            background: #ffc107;
            color: #856404;
        }}
        
        .alert-box.medium .severity {{
            background: #17a2b8;
            color: white;
        }}
        
        .alert-box.low .severity {{
            background: #28a745;
            color: white;
        }}
        
        .visualizations {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(400px, 1fr));
            gap: 20px;
            margin: 20px 0;
        }}
        
        .visualization {{
            background: white;
            padding: 15px;
            border-radius: 10px;
            box-shadow: 0 4px 6px rgba(0,0,0,0.1);
        }}
        
        .visualization img {{
            width: 100%;
            height: auto;
            border-radius: 8px;
        }}
        
        .footer {{
            background: #f8f9fa;
            padding: 20px;
            text-align: center;
            color: #6c757d;
            font-size: 0.9em;
            border-top: 2px solid #e9ecef;
        }}
        
        @media (max-width: 768px) {{
            .summary-grid {{
                grid-template-columns: 1fr;
            }}
            
            .visualizations {{
                grid-template-columns: 1fr;
            }}
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>📊 Market Profile Analysis Report</h1>
            <p>{report_date} | Generated at {report_timestamp}</p>
        </div>
        
        <div class="report-meta">
            <div class="meta-item"><strong>Report Type:</strong> Daily Market Analysis</div>
            <div class="meta-item"><strong>Market Hours:</strong> IST</div>
            <div class="meta-item"><strong>Analysis Time:</strong> {report_timestamp}</div>
        </div>
        
        <div class="summary-section">
            <h2 style="color: #1e3c72; margin-bottom: 20px;">📈 Executive Summary</h2>
            <div class="summary-grid">
                <div class="summary-card green">
                    <h3>Portfolio Value</h3>
                    <div class="value">₹{current_value:,.2f}</div>
                    <div class="label">Current Portfolio Value</div>
                </div>
                
                <div class="summary-card blue">
                    <h3>Total Gain</h3>
                    <div class="value">₹{total_gain:,.2f}</div>
                    <div class="label">({total_gain_pct:.2f}%)</div>
                </div>
                
                <div class="summary-card orange">
                    <h3>Diversification</h3>
                    <div class="value">{diversification_score:.1f}/10</div>
                    <div class="label">Diversification Score</div>
                </div>
                
                <div class="summary-card" style="border-color: #6f42c1;">
                    <h3>Risk Level</h3>
                    <div class="value">{alerts.get('overall_risk_level', 'Unknown')}</div>
                    <div class="label">Overall Risk Assessment</div>
                </div>
            </div>
        </div>
        
        <div class="section">
            <h2 class="section-title">💼 Portfolio Analysis</h2>
            
            <div class="subsection">
                <h3 class="subsection-title">Portfolio Holdings</h3>
                <table class="table">
                    <thead>
                        <tr>
                            <th>Symbol</th>
                            <th>Quantity</th>
                            <th>Avg Price</th>
                            <th>Current Price</th>
                            <th>Gain/Loss</th>
                            <th>Gain %</th>
                            <th>Value</th>
                        </tr>
                    </thead>
                    <tbody>
            """
            
            # Add portfolio holdings
            holdings = portfolio_data.get("holdings", [])
            if holdings:
                for holding in holdings:
                    symbol = holding.get("symbol", "N/A")
                    quantity = holding.get("quantity", 0)
                    avg_price = holding.get("avg_price", 0)
                    current_price = holding.get("current_price", 0)
                    gain_pct = holding.get("gain_pct", 0)
                    value = quantity * current_price
                    
                    gain_class = "positive" if gain_pct >= 0 else "negative"
                    gain_sign = "+" if gain_pct >= 0 else ""
                    
                    html_report += f"""
                        <tr class="{gain_class}">
                            <td><strong>{symbol}</strong></td>
                            <td>{quantity:,}</td>
                            <td>₹{avg_price:,.2f}</td>
                            <td>₹{current_price:,.2f}</td>
                            <td><span style="color: {'green' if gain_pct >= 0 else 'red'}">{gain_sign}{gain_pct:.2f}%</span></td>
                            <td><span style="color: {'green' if gain_pct >= 0 else 'red'}">{gain_sign}{gain_pct:.2f}%</span></td>
                            <td>₹{value:,.2f}</td>
                        </tr>
                    """
            else:
                html_report += """
                        <tr>
                            <td colspan="7" style="text-align: center; color: #6c757d;">
                                No holdings data available
                            </td>
                        </tr>
                """
            
            html_report += """
                    </tbody>
                    <tfoot>
                        <tr style="background: #e9ecef; font-weight: bold;">
                            <td colspan="6" style="text-align: right;">Total Investment:</td>
                            <td>₹{total_investment:,.2f}</td>
                        </tr>
                        <tr style="background: #d4edda; font-weight: bold;">
                            <td colspan="6" style="text-align: right;">Current Value:</td>
                            <td>₹{current_value:,.2f}</td>
                        </tr>
                        <tr style="background: #cce5ff; font-weight: bold;">
                            <td colspan="6" style="text-align: right;">Net Gain/Loss:</td>
                            <td style="color: {'green' if total_gain >= 0 else 'red'}">
                                ₹{total_gain:,.2f} ({total_gain_pct:.2f}%)
                            </td>
                        </tr>
                    </tfoot>
                </table>
            </div>
            
            <div class="subsection">
                <h3 class="subsection-title">Portfolio Metrics</h3>
                <table class="table">
                    <tbody>
                        <tr>
                            <td><strong>Total Investment:</strong></td>
                            <td>₹{total_investment:,.2f}</td>
                        </tr>
                        <tr>
                            <td><strong>Current Portfolio Value:</strong></td>
                            <td>₹{current_value:,.2f}</td>
                        </tr>
                        <tr>
                            <td><strong>Net Gain/Loss:</strong></td>
                            <td style="color: {'green' if total_gain >= 0 else 'red'}">
                                ₹{total_gain:,.2f} ({total_gain_pct:.2f}%)
                            </td>
                        </tr>
                        <tr>
                            <td><strong>Cash Balance:</strong></td>
                            <td>₹{portfolio_data.get('cash_balance', 0):,.2f}</td>
                        </tr>
                        <tr>
                            <td><strong>Margin Used:</strong></td>
                            <td>₹{portfolio_data.get('margin_used', 0):,.2f}</td>
                        </tr>
                        <tr>
                            <td><strong>Portfolio Health:</strong></td>
                            <td><span style="color: {'green' if portfolio_data.get('portfolio_health') == 'Good' else 'orange'}">
                                {portfolio_data.get('portfolio_health', 'Unknown')}
                            </span></td>
                        </tr>
                        <tr>
                            <td><strong>Risk Level:</strong></td>
                            <td>{portfolio_data.get('risk_level', 'Unknown')}</td>
                        </tr>
                        <tr>
                            <td><strong>Diversification Score:</strong></td>
                            <td>{diversification_score:.1f}/10</td>
                        </tr>
                    </tbody>
                </table>
            </div>
        </div>
        
        <div class="section">
            <h2 class="section-title">📊 Market Analysis</h2>
            
            <div class="subsection">
                <h3 class="subsection-title">Market Indices Performance</h3>
                <table class="table">
                    <thead>
                        <tr>
                            <th>Index</th>
                            <th>Last Price</th>
                            <th>Change</th>
                            <th>Change %</th>
                            <th>High</th>
                            <th>Low</th>
                            <th>Volume</th>
                            <th>Trend</th>
                        </tr>
                    </thead>
                    <tbody>
            """
            
            # Add market indices
            indices = market_data.get("indices", {})
            if indices:
                for index_name, index_data in indices.items():
                    last_price = index_data.get("last_price", 0)
                    change = index_data.get("change", 0)
                    change_pct = index_data.get("change_pct", 0)
                    high = index_data.get("high", 0)
                    low = index_data.get("low", 0)
                    volume = index_data.get("volume", 0)
                    trend = index_data.get("trend", "Unknown")
                    
                    change_sign = "+" if change >= 0 else ""
                    change_class = "positive" if change >= 0 else "negative"
                    
                    html_report += f"""
                        <tr class="{change_class}">
                            <td><strong>{index_name}</strong></td>
                            <td>₹{last_price:,.2f}</td>
                            <td style="color: {'green' if change >= 0 else 'red'}">{change_sign}{change:.2f}</td>
                            <td style="color: {'green' if change_pct >= 0 else 'red'}">{change_sign}{change_pct:.2f}%</td>
                            <td>₹{high:,.2f}</td>
                            <td>₹{low:,.2f}</td>
                            <td>{volume:,}</td>
                            <td><span style="color: {'green' if trend == 'Bullish' else 'orange' if trend == 'Neutral' else 'red'}">
                                {trend}
                            </span></td>
                        </tr>
                    """
            else:
                html_report += """
                        <tr>
                            <td colspan="8" style="text-align: center; color: #6c757d;">
                                No market data available
                            </td>
                        </tr>
                """
            
            html_report += """
                    </tbody>
                </table>
            </div>
            
            <div class="subsection">
                <h3 class="subsection-title">Market Summary</h3>
                <table class="table">
                    <tbody>
                        <tr>
                            <td><strong>Advancing Indices:</strong></td>
                            <td>{market_summary['advancers']}</td>
                        </tr>
                        <tr>
                            <td><strong>Declining Indices:</strong></td>
                            <td>{market_summary['decliners']}</td>
                        </tr>
                        <tr>
                            <td><strong>Unchanged Indices:</strong></td>
                            <td>{market_summary['unchanged']}</td>
                        </tr>
                        <tr>
                            <td><strong>Overall Market Sentiment:</strong></td>
                            <td>{suggestions.get('overall_sentiment', 'Neutral')}</td>
                        </tr>
                    </tbody>
                </table>
            </div>
        </div>
        
        <div class="section">
            <h2 class="section-title">🏢 Sector Performance</h2>
            
            <div class="subsection">
                <h3 class="subsection-title">Sector-wise Performance</h3>
                <table class="table">
                    <thead>
                        <tr>
                            <th>Sector</th>
                            <th>Last Price</th>
                            <th>Change</th>
                            <th>Change %</th>
                            <th>Top Gainers</th>
                            <th>Top Losers</th>
                            <th>Performance Rating</th>
                        </tr>
                    </thead>
                    <tbody>
            """
            
            # Add sector performance
            sectors = sector_data.get("sectors", {})
            if sectors:
                for sector_name, sector_data_dict in sectors.items():
                    last_price = sector_data_dict.get("last_price", 0)
                    change = sector_data_dict.get("change", 0)
                    change_pct = sector_data_dict.get("change_pct", 0)
                    top_gainers = ", ".join(sector_data_dict.get("top_gainers", []))
                    top_losers = ", ".join(sector_data_dict.get("top_losers", []))
                    rating = sector_data_dict.get("performance_rating", 0)
                    
                    change_sign = "+" if change >= 0 else ""
                    change_class = "positive" if change >= 0 else "negative"
                    
                    html_report += f"""
                        <tr class="{change_class}">
                            <td><strong>{sector_name}</strong></td>
                            <td>₹{last_price:,.2f}</td>
                            <td style="color: {'green' if change >= 0 else 'red'}">{change_sign}{change:.2f}</td>
                            <td style="color: {'green' if change_pct >= 0 else 'red'}">{change_sign}{change_pct:.2f}%</td>
                            <td>{top_gainers if top_gainers else 'N/A'}</td>
                            <td>{top_losers if top_losers else 'N/A'}</td>
                            <td>{rating}/10</td>
                        </tr>
                    """
            else:
                html_report += """
                        <tr>
                            <td colspan="7" style="text-align: center; color: #6c757d;">
                                No sector data available
                            </td>
                        </tr>
                """
            
            html_report += """
                    </tbody>
                </table>
            </div>
        </div>
        
        <div class="section">
            <h2 class="section-title">📈 Top Movers</h2>
            
            <div class="subsection">
                <h3 class="subsection-title">Top Gainers</h3>
                <table class="table">
                    <thead>
                        <tr>
                            <th>Symbol</th>
                            <th>Price</th>
                            <th>Change</th>
                            <th>Change %</th>
                            <th>Volume</th>
                        </tr>
                    </thead>
                    <tbody>
            """
            
            # Add top gainers
            top_gainers = top_movers_data.get("top_gainers", [])
            if top_gainers:
                for mover in top_gainers[:10]:  # Top 10 gainers
                    symbol = mover.get("symbol", "N/A")
                    price = mover.get("price", 0)
                    change = mover.get("change", 0)
                    change_pct = mover.get("change_pct", 0)
                    volume = mover.get("volume", 0)
                    
                    change_sign = "+" if change >= 0 else ""
                    
                    html_report += f"""
                        <tr class="positive">
                            <td><strong>{symbol}</strong></td>
                            <td>₹{price:,.2f}</td>
                            <td style="color: green">{change_sign}{change:.2f}</td>
                            <td style="color: green">{change_sign}{change_pct:.2f}%</td>
                            <td>{volume:,}</td>
                        </tr>
                    """
            else:
                html_report += """
                        <tr>
                            <td colspan="5" style="text-align: center; color: #6c757d;">
                                No top gainers data available
                            </td>
                        </tr>
                """
            
            html_report += """
                    </tbody>
                </table>
            </div>
            
            <div class="subsection">
                <h3 class="subsection-title">Top Losers</h3>
                <table class="table">
                    <thead>
                        <tr>
                            <th>Symbol</th>
                            <th>Price</th>
                            <th>Change</th>
                            <th>Change %</th>
                            <th>Volume</th>
                        </tr>
                    </thead>
                    <tbody>
            """
            
            # Add top losers
            top_losers = top_movers_data.get("top_losers", [])
            if top_losers:
                for mover in top_losers[:10]:  # Top 10 losers
                    symbol = mover.get("symbol", "N/A")
                    price = mover.get("price", 0)
                    change = mover.get("change", 0)
                    change_pct = mover.get("change_pct", 0)
                    volume = mover.get("volume", 0)
                    
                    change_sign = "+" if change >= 0 else ""
                    
                    html_report += f"""
                        <tr class="negative">
                            <td><strong>{symbol}</strong></td>
                            <td>₹{price:,.2f}</td>
                            <td style="color: red">{change_sign}{change:.2f}</td>
                            <td style="color: red">{change_sign}{change_pct:.2f}%</td>
                            <td>{volume:,}</td>
                        </tr>
                    """
            else:
                html_report += """
                        <tr>
                            <td colspan="5" style="text-align: center; color: #6c757d;">
                                No top losers data available
                            </td>
                        </tr>
                """
            
            html_report += """
                    </tbody>
                </table>
            </div>
        </div>
        
        <div class="section">
            <h2 class="section-title">💡 Investment Suggestions</h2>
            
            <div class="subsection">
                <h3 class="subsection-title">Portfolio Recommendations</h3>
                <table class="table">
                    <thead>
                        <tr>
                            <th>Type</th>
                            <th>Symbol/Sector</th>
                            <th>Action</th>
                            <th>Reason</th>
                            <th>Confidence</th>
                        </tr>
                    </thead>
                    <tbody>
            """
            
            # Add investment suggestions
            suggestions_list = suggestions.get("suggestions", [])
            if suggestions_list:
                for suggestion in suggestions_list[:15]:  # Top 15 suggestions
                    suggestion_type = suggestion.get("type", "N/A")
                    symbol = suggestion.get("symbol", "N/A")
                    action = suggestion.get("action", "N/A")
                    reason = suggestion.get("reason", "N/A")
                    confidence = suggestion.get("confidence", 0)
                    
                    action_class = "positive" if action in ["Increase", "Buy", "Opportunistic"] else "negative"
                    action_class = "neutral" if action in ["Hold", "Monitor"] else action_class
                    
                    html_report += f"""
                        <tr class="{action_class}">
                            <td>{suggestion_type}</td>
                            <td><strong>{symbol}</strong></td>
                            <td style="color: {'green' if action in ['Increase', 'Buy', 'Opportunistic'] else 'red' if action in ['Reduce', 'Sell', 'Take Profit'] else 'blue'}">
                                {action}
                            </td>
                            <td>{reason}</td>
                            <td>{confidence}/10</td>
                        </tr>
                    """
            else:
                html_report += """
                        <tr>
                            <td colspan="5" style="text-align: center; color: #6c757d;">
                                No investment suggestions available
                            </td>
                        </tr>
                """
            
            html_report += """
                    </tbody>
                </table>
            </div>
            
            <div class="subsection">
                <h3 class="subsection-title">Diversification Recommendations</h3>
                <table class="table">
                    <thead>
                        <tr>
                            <th>Sector</th>
                            <th>Current Allocation</th>
                            <th>Recommended Allocation</th>
                            <th>Action</th>
                        </tr>
                    </thead>
                    <tbody>
            """
            
            # Add diversification recommendations
            diversification_recs = suggestions.get("diversification_recommendations", [])
            if diversification_recs:
                for rec in diversification_recs[:10]:  # Top 10 recommendations
                    sector = rec.get("sector", "N/A")
                    current_allocation = rec.get("current_allocation", "0%")
                    recommended_allocation = rec.get("recommended_allocation", "0%")
                    action = rec.get("action", "Hold")
                    
                    action_class = "positive" if action == "Increase" else "negative" if action == "Reduce" else "neutral"
                    
                    html_report += f"""
                        <tr class="{action_class}">
                            <td><strong>{sector}</strong></td>
                            <td>{current_allocation}</td>
                            <td>{recommended_allocation}</td>
                            <td style="color: {'green' if action == 'Increase' else 'red' if action == 'Reduce' else 'blue'}">
                                {action}
                            </td>
                        </tr>
                    """
            else:
                html_report += """
                        <tr>
                            <td colspan="4" style="text-align: center; color: #6c757d;">
                                No diversification recommendations available
                            </td>
                        </tr>
                """
            
            html_report += """
                    </tbody>
                </table>
            </div>
        </div>
        
        <div class="section">
            <h2 class="section-title">⚠️ Risk Alerts</h2>
            """
            
            # Add high priority alerts
            high_priority_alerts = alerts.get("high_priority", [])
            if high_priority_alerts:
                html_report += f"""
            <div class="subsection">
                <h3 class="subsection-title">🔴 High Priority Alerts ({len(high_priority_alerts)})</h3>
            """
                for alert in high_priority_alerts:
                    alert_type = alert.get("type", "N/A")
                    message = alert.get("message", "No message")
                    severity = alert.get("severity", "High")
                    timestamp = alert.get("timestamp", "N/A")
                    
                    html_report += f"""
                <div class="alert-box high">
                    <h4>
                        {alert_type}
                        <span class="severity">{severity}</span>
                    </h4>
                    <p>{message}</p>
                    <small style="color: #6c757d;">Generated at: {timestamp}</small>
                </div>
                    """
                html_report += "</div>"
            
            # Add medium priority alerts
            medium_priority_alerts = alerts.get("medium_priority", [])
            if medium_priority_alerts:
                html_report += f"""
            <div class="subsection">
                <h3 class="subsection-title">🟡 Medium Priority Alerts ({len(medium_priority_alerts)})</h3>
            """
                for alert in medium_priority_alerts:
                    alert_type = alert.get("type", "N/A")
                    message = alert.get("message", "No message")
                    severity = alert.get("severity", "Medium")
                    timestamp = alert.get("timestamp", "N/A")
                    
                    html_report += f"""
                <div class="alert-box medium">
                    <h4>
                        {alert_type}
                        <span class="severity">{severity}</span>
                    </h4>
                    <p>{message}</p>
                    <small style="color: #6c757d;">Generated at: {timestamp}</small>
                </div>
                    """
                html_report += "</div>"
            
            # Add low priority alerts
            low_priority_alerts = alerts.get("low_priority", [])
            if low_priority_alerts:
                html_report += f"""
            <div class="subsection">
                <h3 class="subsection-title">🟢 Low Priority Alerts ({len(low_priority_alerts)})</h3>
            """
                for alert in low_priority_alerts:
                    alert_type = alert.get("type", "N/A")
                    message = alert.get("message", "No message")
                    severity = alert.get("severity", "Low")
                    timestamp = alert.get("timestamp", "N/A")
                    
                    html_report += f"""
                <div class="alert-box low">
                    <h4>
                        {alert_type}
                        <span class="severity">{severity}</span>
                    </h4>
                    <p>{message}</p>
                    <small style="color: #6c757d;">Generated at: {timestamp}</small>
                </div>
                    """
                html_report += "</div>"
            
            html_report += """
        </div>
        
        <div class="section">
            <h2 class="section-title">📊 Visualizations</h2>
            <div class="visualizations">
            """
            
            # Add visualizations
            for viz_path in visualizations:
                if os.path.exists(viz_path):
                    html_report += f'                <div class="visualization">\n                    <img src="{viz_path}" alt="Visualization">\n                </div>\n'
            
            html_report += """
            </div>
        </div>
        
        <div class="section">
            <h2 class="section-title">📋 P&L Report</h2>
            
            <div class="subsection">
                <h3 class="subsection-title">Profit & Loss Summary</h3>
                <table class="table">
                    <tbody>
                        <tr>
                            <td><strong>Report Date:</strong></td>
                            <td>{pnl_report.get('report_date', 'N/A')}</td>
                        </tr>
                        <tr>
                            <td><strong>Daily P&L:</strong></td>
                            <td style="color: {'green' if pnl_report.get('daily_pnl', 0) >= 0 else 'red'}">
                                ₹{pnl_report.get('daily_pnl', 0):,.2f} ({pnl_report.get('daily_pnl_pct', 0):.2f}%)
                            </td>
                        </tr>
                        <tr>
                            <td><strong>Weekly P&L (Projected):</strong></td>
                            <td style="color: {'green' if pnl_report.get('weekly_pnl', 0) >= 0 else 'red'}">
                                ₹{pnl_report.get('weekly_pnl', 0):,.2f}
                            </td>
                        </tr>
                        <tr>
                            <td><strong>Monthly P&L (Projected):</strong></td>
                            <td style="color: {'green' if pnl_report.get('monthly_pnl', 0) >= 0 else 'red'}">
                                ₹{pnl_report.get('monthly_pnl', 0):,.2f}
                            </td>
                        </tr>
                        <tr>
                            <td><strong>Portfolio Health:</strong></td>
                            <td>{pnl_report.get('portfolio_summary', {}).get('portfolio_health', 'Unknown')}</td>
                        </tr>
                    </tbody>
                </table>
            </div>
            
            <div class="subsection">
                <h3 class="subsection-title">P&L Breakdown</h3>
                <table class="table">
                    <thead>
                        <tr>
                            <th>Category</th>
                            <th>Amount (₹)</th>
                            <th>Percentage</th>
                        </tr>
                    </thead>
                    <tbody>
                        <tr>
                            <td>Equity Gain/Loss</td>
                            <td>₹{pnl_report.get('pnl_breakdown', {}).get('equity_gain', 0):,.2f}</td>
                            <td>{(pnl_report.get('pnl_breakdown', {}).get('equity_gain', 0) / total_gain * 100):.1f}%</td>
                        </tr>
                        <tr>
                            <td>Derivative Gain/Loss</td>
                            <td>₹{pnl_report.get('pnl_breakdown', {}).get('derivative_gain', 0):,.2f}</td>
                            <td>{(pnl_report.get('pnl_breakdown', {}).get('derivative_gain', 0) / total_gain * 100):.1f}%</td>
                        </tr>
                        <tr>
                            <td>Dividend Income</td>
                            <td>₹{pnl_report.get('pnl_breakdown', {}).get('dividend_income', 0):,.2f}</td>
                            <td>{(pnl_report.get('pnl_breakdown', {}).get('dividend_income', 0) / total_gain * 100):.1f}%</td>
                        </tr>
                        <tr>
                            <td>Interest Income</td>
                            <td>₹{pnl_report.get('pnl_breakdown', {}).get('interest_income', 0):,.2f}</td>
                            <td>{(pnl_report.get('pnl_breakdown', {}).get('interest_income', 0) / total_gain * 100):.1f}%</td>
                        </tr>
                        <tr>
                            <td>Fees & Expenses</td>
                            <td>₹{pnl_report.get('pnl_breakdown', {}).get('fees_expenses', 0):,.2f}</td>
                            <td>{(pnl_report.get('pnl_breakdown', {}).get('fees_expenses', 0) / total_gain * 100):.1f}%</td>
                        </tr>
                        <tr style="background: #e9ecef; font-weight: bold;">
                            <td>Net P&L</td>
                            <td>₹{pnl_report.get('daily_pnl', 0):,.2f}</td>
                            <td>{pnl_report.get('daily_pnl_pct', 0):.2f}%</td>
                        </tr>
                    </tbody>
                </table>
            </div>
            
            <div class="subsection">
                <h3 class="subsection-title">Performance Metrics</h3>
                <table class="table">
                    <tbody>
                        <tr>
                            <td><strong>Sharpe Ratio:</strong></td>
                            <td>{pnl_report.get('performance_metrics', {}).get('sharpe_ratio', 0):.2f}</td>
                        </tr>
                        <tr>
                            <td><strong>Sortino Ratio:</strong></td>
                            <td>{pnl_report.get('performance_metrics', {}).get('sortino_ratio', 0):.2f}</td>
                        </tr>
                        <tr>
                            <td><strong>Max Drawdown:</strong></td>
                            <td style="color: {'green' if pnl_report.get('performance_metrics', {}).get('max_drawdown', 0) < -10 else 'red'}">
                                {pnl_report.get('performance_metrics', {}).get('max_drawdown', 0):.2f}%
                            </td>
                        </tr>
                        <tr>
                            <td><strong>CAGR (3Y):</strong></td>
                            <td>{pnl_report.get('performance_metrics', {}).get('cagr', 0):.2f}%</td>
                        </tr>
                        <tr>
                            <td><strong>Volatility (Annualized):</strong></td>
                            <td>{pnl_report.get('performance_metrics', {}).get('volatility', 0):.2f}%</td>
                        </tr>
                    </tbody>
                </table>
            </div>
        </div>
        
        <div class="footer">
            <p>📊 Market Profile Analysis Report | Generated by Automated System | 
            {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
            <p style="margin-top: 10px; font-size: 0.8em;">
                Disclaimer: This is an automated report. Please verify all information before making investment decisions.
            </p>
        </div>
    </div>
</body>
</html>
            """
            
            logger.info("Report formatted successfully")
            return html_report
    
        except Exception as e:
            logger.error(f"Failed to format report: {str(e)}")
            return f"<html><body><h1>Error generating report</h1><p>{str(e)}</p></body></html>"
    
    def send_email_report(self, html_content: str, subject: str, 
                         attachments: List[str] = None) -> bool:
        """
        Send email report with HTML content and optional attachments
        
        Args:
            html_content: HTML content of the report
            subject: Email subject
            attachments: List of file paths to attach
            
        Returns:
            True if email sent successfully, False otherwise
        """
        try:
            logger.info(f"Sending email report: {subject}")
            
            # Email configuration
            sender_email = CONFIG["email"]["sender_email"]
            sender_password = CONFIG["email"]["sender_password"]
            smtp_server = CONFIG["email"]["smtp_server"]
            smtp_port = CONFIG["email"]["smtp_port"]
            receiver_emails = CONFIG["email"]["receiver_emails"]
            
            # Create message
            msg = MIMEMultipart('alternative')
            msg['From'] = sender_email
            msg['To'] = ", ".join(receiver_emails)
            msg['Subject'] = subject
            
            # Attach HTML content
            msg.attach(MIMEText(html_content, 'html'))
            
            # Attach files if provided
            if attachments:
                for file_path in attachments:
                    if os.path.exists(file_path):
                        try:
                            with open(file_path, 'rb') as attachment:
                                part = MIMEBase('application', 'octet-stream')
                                part.set_payload(attachment.read())
                            
                            encoders.encode_base64(part)
                            part.add_header(
                                'Content-Disposition',
                                f'attachment; filename= {os.path.basename(file_path)}'
                            )
                            msg.attach(part)
                            logger.info(f"Attached file: {file_path}")
                        except Exception as e:
                            logger.error(f"Failed to attach file {file_path}: {str(e)}")
            
            # Send email
            with smtplib.SMTP(smtp_server, smtp_port) as server:
                server.starttls()
                server.login(sender_email, sender_password)
                server.sendmail(sender_email, receiver_emails, msg.as_string())
            
            logger.info(f"Email report sent successfully to {len(receiver_emails)} recipients")
            return True
            
        except Exception as e:
            logger.error(f"Failed to send email: {str(e)}")
            return False
    
    def run_daily_analysis(self, analysis_time: str):
        """
        Run complete daily analysis workflow
        
        Args:
            analysis_time: Time of analysis (morning/evening)
        """
        try:
            logger.info(f"=== Starting {analysis_time} analysis ===")
            
            # Step 1: Fetch portfolio data
            portfolio_data = self.get_portfolio_summary()
            logger.info(f"Portfolio value: ₹{portfolio_data.get('portfolio_value', 0):,.2f}")
            
            # Step 2: Get market quotes
            indices = ["NIFTY 50", "BANK NIFTY", "SENSEX"]
            market_data = self.get_market_quotes(indices)
            logger.info(f"Fetched quotes for {len(market_data.get('indices', {}))} indices")
            
            # Step 3: Get sector performance
            sector_data = self.get_sector_performance()
            logger.info(f"Fetched sector performance for {len(sector_data.get('sectors', {}))} sectors")
            
            # Step 4: Get top movers
            top_movers_data = self.get_top_movers()
            logger.info(f"Top gainers: {len(top_movers_data.get('top_gainers', []))}, "
                       f"Top losers: {len(top_movers_data.get('top_losers', []))}")
            
            # Step 5: Generate P&L report
            pnl_report = self.generate_pnl_report(portfolio_data)
            logger.info(f"P&L report generated. Daily gain: ₹{pnl_report.get('daily_pnl', 0):,.2f}")
            
            # Step 6: Generate investment suggestions
            suggestions = self.generate_investment_suggestions(portfolio_data, market_data)
            logger.info(f"Generated {len(suggestions.get('suggestions', []))} investment suggestions")
            
            # Step 7: Create risk alerts
            alerts = self.create_risk_alerts(portfolio_data, market_data, sector_data, top_movers_data)
            logger.info(f"Created {len(alerts.get('high_priority', []))} high priority alerts")
            
            # Step 8: Create visualizations
            visualizations = self.create_visualizations(portfolio_data, market_data, sector_data)
            logger.info(f"Created {len(visualizations)} visualizations")
            
            # Step 9: Format comprehensive report
            report_html = self.format_report(
                portfolio_data=portfolio_data,
                market_data=market_data,
                sector_data=sector_data,
                top_movers_data=top_movers_data,
                pnl_report=pnl_report,
                suggestions=suggestions,
                alerts=alerts,
                visualizations=visualizations
            )
            
            # Step 10: Send email report
            analysis_type = "Morning" if analysis_time == "morning" else "Evening"
            subject = f"{CONFIG['email']['subject_prefix']}{analysis_type} Market Analysis - {datetime.now().strftime('%Y-%m-%d')}"
            
            # Save HTML report to file
            report_filename = f"market_analysis_{analysis_time}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.html"
            with open(report_filename, 'w', encoding='utf-8') as f:
                f.write(report_html)
            
            # Send email with HTML report and visualizations as attachments
            email_success = self.send_email_report(
                html_content=report_html,
                subject=subject,
                attachments=[report_filename] + visualizations
            )
            
            if email_success:
                logger.info(f"{analysis_type} analysis completed successfully and email sent")
            else:
                logger.warning(f"{analysis_time} analysis completed but email sending failed")
            
            # Clean up temporary files
            try:
                os.remove(report_filename)
                for viz_path in visualizations:
                    if os.path.exists(viz_path):
                        os.remove(viz_path)
                logger.info("Temporary files cleaned up")
            except Exception as e:
                logger.error(f"Error cleaning up temporary files: {str(e)}")
            
        except Exception as e:
            logger.error(f"Error in {analysis_time} analysis: {str(e)}")
            # Send error notification
            error_subject = f"{CONFIG['email']['subject_prefix']}ERROR - {analysis_time} Analysis Failed"
            error_message = f"<html><body><h1>Analysis Failed</h1><p>{str(e)}</p></body></html>"
            self.send_email_report(error_message, error_subject)


def setup_scheduling():
    """
    Set up cron jobs for morning and evening analysis
    """
    try:
        logger.info("Setting up scheduling...")
        
        # Create analyzer instance
        analyzer = MarketProfileAnalyzer()
        
        # Schedule morning analysis (9:00 AM IST)
        schedule.every().day.at("09:00", "Asia/Kolkata").do(
            analyzer.run_daily_analysis, analysis_time="morning"
        )
        
        # Schedule evening analysis (4:00 PM IST)
        schedule.every().day.at("16:00", "Asia/Kolkata").do(
            analyzer.run_daily_analysis, analysis_time="evening"
        )
        
        logger.info("Scheduling configured successfully")
        logger.info("Morning analysis: 9:00 AM IST")
        logger.info("Evening analysis: 4:00 PM IST")
        
        return analyzer
        
    except Exception as e:
        logger.error(f"Failed to set up scheduling: {str(e)}")
        return None


def main():
    """
    Main function to run the market profile analyzer
    """
    try:
        logger.info("=== Market Profile Analyzer Starting ===")
        logger.info(f"Current time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        
        # Set up scheduling
        analyzer = setup_scheduling()
        
        if not analyzer:
            logger.error("Failed to set up analyzer. Exiting.")
            return
        
        # Run initial analysis immediately for testing
        logger.info("Running initial test analysis...")
        analyzer.run_daily_analysis(analysis_time="test")
        
        # Main loop for scheduled jobs
        logger.info("Market Profile Analyzer is running. Waiting for scheduled jobs...")
        
        while True:
            schedule.run_pending()
            time.sleep(60)  # Check every minute
            
    except KeyboardInterrupt:
        logger.info("Market Profile Analyzer stopped by user")
    except Exception as e:
        logger.error(f"Unexpected error in main loop: {str(e)}")
    finally:
        logger.info("Market Profile Analyzer shutdown complete")


if __name__ == "__main__":
    main()
