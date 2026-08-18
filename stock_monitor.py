"""
Stock Price and Volume Monitor for ADANIENSOL and BEL

This script continuously monitors ADANIENSOL and BEL stocks for:
- Price movements greater than 2%
- Volume spikes greater than 30%

When conditions are met, it sends desktop notifications with relevant details.

Requirements:
- yfinance: For fetching stock data
- plyer: For desktop notifications
- time: For delays between checks
- datetime: For timestamps
"""

import yfinance as yf
from plyer import notification
import time
from datetime import datetime
import logging
from typing import Dict, Optional, Tuple

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('stock_monitor.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

class StockMonitor:
    """
    A class to monitor stock price and volume movements.
    """
    
    def __init__(self, tickers: list, check_interval: int = 30):
        """
        Initialize the stock monitor.
        
        Args:
            tickers: List of stock tickers to monitor
            check_interval: Time between checks in seconds (default: 30)
        """
        self.tickers = tickers
        self.check_interval = check_interval
        self.previous_data: Dict[str, Dict] = {}
        
    def fetch_stock_data(self, ticker: str) -> Optional[Dict]:
        """
        Fetch current stock data from Yahoo Finance.
        
        Args:
            ticker: Stock ticker symbol
            
        Returns:
            Dictionary with stock data or None if failed
        """
        try:
            stock = yf.Ticker(ticker)
            
            # Get historical data for price calculation
            hist = stock.history(period="1d", interval="1d")
            if hist.empty:
                hist = stock.history(period="5d", interval="1d")
            
            # Get current data
            info = stock.info
            
            # Calculate price change percentage
            if len(hist) >= 2:
                prev_close = hist['Close'].iloc[-2]
                current_price = hist['Close'].iloc[-1]
                price_change_pct = ((current_price - prev_close) / prev_close) * 100
            else:
                # If not enough historical data, use regular price change
                prev_close = info.get('regularMarketPreviousClose', info.get('previousClose', 0))
                current_price = info.get('currentPrice', info.get('regularMarketPrice', 0))
                if prev_close > 0:
                    price_change_pct = ((current_price - prev_close) / prev_close) * 100
                else:
                    price_change_pct = 0
            
            # Get volume data
            current_volume = info.get('volume', 0)
            avg_volume = info.get('averageVolume', 0)
            
            # Calculate volume change percentage
            if avg_volume > 0:
                volume_change_pct = ((current_volume - avg_volume) / avg_volume) * 100
            else:
                volume_change_pct = 0
            
            return {
                'ticker': ticker,
                'price': current_price,
                'price_change_pct': price_change_pct,
                'volume': current_volume,
                'avg_volume': avg_volume,
                'volume_change_pct': volume_change_pct,
                'timestamp': datetime.now()
            }
            
        except Exception as e:
            logger.error(f"Error fetching data for {ticker}: {e}")
            return None
    
    def check_conditions(self, current_data: Dict, ticker: str) -> bool:
        """
        Check if price or volume conditions are met.
        
        Args:
            current_data: Current stock data
            ticker: Stock ticker
            
        Returns:
            True if conditions are met, False otherwise
        """
        try:
            # Check price movement > 2%
            price_condition = abs(current_data['price_change_pct']) > 2.0
            
            # Check volume spike > 30%
            volume_condition = current_data['volume_change_pct'] > 30.0
            
            if price_condition or volume_condition:
                movement_type = "price" if price_condition else "volume"
                change_pct = current_data['price_change_pct'] if price_condition else current_data['volume_change_pct']
                
                logger.info(f"Alert triggered for {ticker} - {movement_type} movement of {abs(change_pct):.2f}%")
                
                # Send desktop notification
                self.send_notification(
                    ticker=ticker,
                    movement_type=movement_type,
                    change_pct=abs(change_pct),
                    current_price=current_data['price'],
                    current_volume=current_data['volume'],
                    timestamp=current_data['timestamp']
                )
                
                return True
            
            return False
            
        except Exception as e:
            logger.error(f"Error checking conditions for {ticker}: {e}")
            return False
    
    def send_notification(self, ticker: str, movement_type: str, change_pct: float,
                         current_price: float, current_volume: int, timestamp: datetime):
        """
        Send desktop notification with stock alert.
        
        Args:
            ticker: Stock ticker symbol
            movement_type: Type of movement ('price' or 'volume')
            change_pct: Percentage change
            current_price: Current stock price
            current_volume: Current volume
            timestamp: Timestamp of the alert
        """
        try:
            # Format message
            message = (
                f"Stock Alert: {ticker}\n"
                f"Type: {movement_type.upper()} Movement\n"
                f"Change: {change_pct:.2f}%\n"
                f"Price: ₹{current_price:.2f}\n"
                f"Volume: {current_volume:,}\n"
                f"Time: {timestamp.strftime('%Y-%m-%d %H:%M:%S')}"
            )
            
            # Send notification
            notification.notify(
                title=f"🚨 {ticker} Alert",
                message=message,
                app_name="Stock Monitor",
                timeout=10  # Notification stays for 10 seconds
            )
            
            logger.info(f"Notification sent for {ticker}")
            
        except Exception as e:
            logger.error(f"Error sending notification for {ticker}: {e}")
    
    def run(self):
        """
        Main monitoring loop.
        """
        logger.info("Starting stock monitoring...")
        logger.info(f"Monitoring tickers: {', '.join(self.tickers)}")
        logger.info(f"Check interval: {self.check_interval} seconds")
        logger.info("Press Ctrl+C to stop the monitor")
        
        try:
            while True:
                for ticker in self.tickers:
                    logger.info(f"Checking {ticker}...")
                    
                    # Fetch current data
                    current_data = self.fetch_stock_data(ticker)
                    
                    if current_data:
                        # Check conditions
                        self.check_conditions(current_data, ticker)
                    
                    # Wait before next check
                    time.sleep(1)
                
                # Wait for next monitoring cycle
                logger.info(f"Waiting {self.check_interval} seconds for next check...")
                time.sleep(self.check_interval)
                
        except KeyboardInterrupt:
            logger.info("Monitoring stopped by user")
        except Exception as e:
            logger.error(f"Unexpected error in monitoring loop: {e}")
            logger.info("Restarting monitoring...")
            # Restart the monitoring loop
            self.run()


def main():
    """
    Main function to start the stock monitor.
    """
    # Stock tickers to monitor
    tickers = ['ADANIENSOL.NS', 'BEL.NS']
    
    # Create and run the monitor
    monitor = StockMonitor(tickers=tickers, check_interval=30)
    monitor.run()


if __name__ == "__main__":
    main()
