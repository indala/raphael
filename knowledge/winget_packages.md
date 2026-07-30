# Windows Package Manager (winget) Reference

Always use winget in non-interactive mode. Background tasks or CLI prompts will hang indefinitely if they try to show interactive user prompts.

---

## 1. Silent Installation Command
To install a package silently without any user prompts or dialog popups, always use this flag combination:

```powershell
winget install --id <PackageID> --silent --accept-package-agreements --accept-source-agreements --disable-interactivity
```

### Parameters
* **`--silent`**: Suppresses the GUI installer popup (runs in the background).
* **`--accept-package-agreements`**: Accepts the package's license agreements.
* **`--accept-source-agreements`**: Accepts Microsoft source agreements at first run.
* **`--disable-interactivity`**: Tells winget to abort rather than prompting the user for any input.

---

## 2. Common Package IDs
Here is a list of standardized package IDs for common software:

| Application | Winget Package ID |
| :--- | :--- |
| **Visual Studio Code** | `Microsoft.VisualStudioCode` |
| **Git** | `Git.Git` |
| **Python 3** | `Python.Python.3` |
| **Google Chrome** | `Google.Chrome` |
| **Mozilla Firefox** | `Mozilla.Firefox` |
| **Node.js** | `OpenJS.NodeJS` |
| **Docker Desktop** | `Docker.DockerDesktop` |
| **Notepad++** | `Notepad++.Notepad++` |
| **7-Zip** | `7zip.7zip` |
| **VLC Media Player** | `VideoLAN.VLC` |

---

## 3. Useful winget Commands

### Search for a package
```powershell
winget search <query>
```

### Upgrade all packages to their latest version silently
```powershell
winget upgrade --all --silent --accept-package-agreements --accept-source-agreements --disable-interactivity
```

### List installed packages
```powershell
winget list
```
