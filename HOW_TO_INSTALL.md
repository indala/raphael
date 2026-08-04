# Raphael Standalone Installation Guide (v0.0.1)

Because this is a developer/tester preview release of Raphael, it is signed with a self-signed developer certificate rather than a commercial CA certificate.

To install and run Raphael on your Windows machine, choose one of the options below:

---

## Option A: Simple Bypass (Recommended)

1. Run **`Raphael_Setup.exe`**.
2. When Windows Defender / SmartScreen blocks the screen saying *"Windows protected your PC"*:
   * Click on the **"More info"** link text.
   * Verify the publisher name displays as: **`Raphael Developer`**.
   * Click the **"Run anyway"** button.

---

## Option B: Full Installation & Trust (No Warning Prompts)

To completely trust the developer signature on this system and prevent any warning popups:

1. Right-click the file **`raphael_public.cer`** in this folder.
2. Select **"Install Certificate"**.
3. Choose **Local Machine** as the store location and click **Next**.
4. Select **"Place all certificates in the following store"**.
5. Click **"Browse..."** and select **"Trusted Root Certification Authorities"**, then click **OK**.
6. Click **Next**, then **Finish**.
7. Now double-click **`Raphael_Setup.exe`**. It will launch and install cleanly with zero warning screens!

> [!NOTE]
> Alternatively, you can trust the certificate quickly by opening PowerShell as Administrator and running:
> ```powershell
> Import-Certificate -FilePath "raphael_public.cer" -CertStoreLocation "Cert:\LocalMachine\Root"
> ```

---

*Raphael Project Contributors*
