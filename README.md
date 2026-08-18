# Stock Monitor - ADANIENSOL and BEL

A real-time stock monitoring tool that alerts you when ADANIENSOL or BEL stocks experience significant price movements (>2%) or volume spikes (>30%).

## Features

✅ **Real-time Monitoring**: Checks stocks every 30 seconds
✅ **Price Alerts**: Notifies when price changes exceed 2%
✅ **Volume Alerts**: Notifies when volume spikes exceed 30%
✅ **Desktop Notifications**: Instant alerts with all relevant details
✅ **Robust Error Handling**: Gracefully handles API failures
✅ **Logging**: Detailed logs for monitoring and debugging
✅ **Continuous Operation**: Runs in background until manually stopped

## Installation

### Prerequisites
- Python 3.7+
- pip package manager

### Install Dependencies

```bash
pip install -r requirements.txt
```

## Usage

### Quick Start

```bash
python stock_monitor.py
```

### Running in Background (Windows)

```bash
# Run in background using Pythonw
pythonw stock_monitor.py

# Or use start command
start /B python stock_monitor.py
```

### Stopping the Monitor

Press `Ctrl+C` in the terminal where the script is running to stop monitoring.

## Configuration

You can easily modify the script to monitor different stocks or change the thresholds:

### Change Stocks
Edit the `tickers` list in the `main()` function:

```python
# Change this line in stock_monitor.py
tickers = ['ADANIENSOL.NS', 'BEL.NS']
```

### Adjust Thresholds
Modify the condition checks in the `check_conditions()` method:

```python
# Change these values to adjust sensitivity
price_condition = abs(current_data['price_change_pct']) > 2.0  # 2% threshold
volume_condition = current_data['volume_change_pct'] > 30.0    # 30% threshold
```

### Change Check Interval
Modify the `check_interval` parameter when creating the StockMonitor:

```python
monitor = StockMonitor(tickers=tickers, check_interval=30)  # 30 seconds
```

## Alert Information

When an alert is triggered, you'll receive a desktop notification with:

- **Stock Name**: ADANIENSOL or BEL
- **Movement Type**: Price or Volume
- **Percentage Change**: The exact percentage change
- **Current Price**: Latest stock price
- **Current Volume**: Latest trading volume
- **Timestamp**: When the alert occurred

## Logs

The script creates a `stock_monitor.log` file that records:
- Monitoring start/stop times
- Data fetch attempts
- Alert triggers
- Errors and exceptions

## Troubleshooting

### Common Issues

**1. No data being fetched**
- Check your internet connection
- Verify Yahoo Finance is accessible
- Ensure the ticker symbols are correct

**2. Notifications not appearing**
- Make sure you have notification permissions enabled
- Check if other notification apps are blocking the alerts
- Try restarting the script

**3. High CPU usage**
- The script is lightweight and shouldn't cause high CPU usage
- If it does, try increasing the check interval

### Viewing Logs

```bash
# View the log file
type stock_monitor.log

# Or tail the log file
Get-Content stock_monitor.log -Wait -Tail 20
```

## Technical Details

### Libraries Used

- **yfinance**: Fetches stock data from Yahoo Finance API
- **plyer**: Provides cross-platform desktop notifications
- **logging**: Handles application logging
- **time**: Manages delays between checks
- **datetime**: Handles timestamps

### Error Handling

The script includes comprehensive error handling for:
- API failures and rate limits
- Network connectivity issues
- Invalid data responses
- Notification system failures

## License

This project is open-source and free to use.

## Support

For issues or questions, check the logs or modify the script as needed.

---

**Note**: This script uses Yahoo Finance data which may have limitations. For critical trading decisions, use official financial data sources.
