# Windows CLI Command Reference (CMD & PowerShell)

Use this guide to find the exact, safe syntax for standard Windows CLI tasks. Always use relative paths (`outputs/`) when saving files.

---

## 1. Audio and Recording Devices
To locate, list, and verify microphones or recording audio endpoints:

### Querying PNP Audio Endpoints (Fastest, Native)
Returns all active audio capture and render devices.
```powershell
Get-PnpDevice -Class AudioEndpoint | Select-Object Status, Class, FriendlyName, InstanceId
```

### Querying Hardware Sound Devices
Queries the sound card hardware level.
```powershell
Get-CimInstance Win32_SoundDevice | Select-Object Name, Manufacturer, ProductName, Status
```

### Registry Check (For Active Endpoints)
Finds active audio endpoints registered in Windows MMDevices:
```powershell
Get-ChildItem 'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\MMDevices\Audio\Capture' | ForEach-Object { $p = Get-ItemProperty ($_.PSPath + '\Properties'); $_ | Add-Member -NotePropertyName 'Name' -NotePropertyValue ($p.'{a45c254e-df1c-4efd-8020-67d146a850e0},2') -PassThru } | Select-Object PSChildName, Name
```

---

## 2. Registry Management
Always read registry keys safely using query commands (never execute modifications unless explicitly requested).

### Reading registry values (PowerShell)
```powershell
Get-ItemProperty -Path "HKCU:\Software\Microsoft\Windows\CurrentVersion\Explorer" -Name "Logon User Name"
```

### Reading registry values (CMD)
```cmd
reg query "HKCU\Software\Microsoft\Windows\CurrentVersion\Explorer" /v "Logon User Name"
```

---

## 3. Process and Service Management
To check system states or list active tasks:

### List running processes matching a name
```powershell
Get-Process | Where-Object { $_.Name -like "*raphael*" }
```

### List services and their status
```powershell
Get-Service | Where-Object { $_.Status -eq "Running" }
```

---

## 4. File and Directory Operations
Always use relative paths (`outputs/`) when running workspace operations.

### List files in a folder
```powershell
Get-ChildItem -Path .\outputs\
```

### Create a new folder
```cmd
mkdir outputs\logs
```

---

## 5. Networking
To inspect network settings or verify connectivity:

### Show IP configuration
```cmd
ipconfig /all
```

### Test connectivity
```cmd
ping www.microsoft.com
```

---

## 6. System Information
To check system details or hardware information:

### Quick system overview
```powershell
Get-ComputerInfo | Select-Object CsName, OsName, OsArchitecture, WindowsVersion
```

### Check disk space
```powershell
Get-PSDrive -PSProvider FileSystem
```

---

## 7. Task Scheduling
To list active background schedules:

### List scheduled tasks
```powershell
Get-ScheduledTask | Select-Object TaskName, State
```

---

## 8. User and Security
To audit privileges or active users:

### Current logged-in user
```cmd
whoami
```

### List local users
```powershell
Get-LocalUser
```
