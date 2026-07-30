using System.Runtime.InteropServices;

namespace RaphaelHybrid;

/// <summary>
/// Checks actual mute/volume state of playback and recording devices
/// using the Windows Core Audio API.
/// </summary>
public static class AudioDeviceState
{
    private static readonly Guid CLSID_MMDeviceEnumerator = new Guid("BCDE0395-E52F-467C-8E3D-C4579291692E");
    private static readonly Guid IID_IAudioEndpointVolume = new Guid("5CDF2C82-841E-4546-9722-0CF74078229A");

    [ComImport, Guid("BCDE0395-E52F-467C-8E3D-C4579291692E")]
    private class MMDeviceEnumerator
    {
    }

    [ComImport, Guid("886D8EEB-8CF2-4446-8D02-CDBA1DBDCF99"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
    private interface IMMDeviceEnumerator
    {
        int EnumAudioEndpoints(int dataFlow, uint dwStateMask, out IntPtr ppDevices);
        int GetDefaultAudioEndpoint(int dataFlow, int role, out IMMDevice ppDevice);
    }

    [ComImport, Guid("D666063F-1587-4E43-81F1-BB948D3F3B68"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
    private interface IMMDevice
    {
        int Activate([MarshalAs(UnmanagedType.LPStruct)] Guid iid, uint dwClsCtx, IntPtr pActivationParams, [MarshalAs(UnmanagedType.Interface)] out IAudioEndpointVolume ppInterface);
    }

    [ComImport, Guid("5CDF2C82-841E-4546-9722-0CF74078229A"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
    private interface IAudioEndpointVolume
    {
        int RegisterControlChangeNotify(IntPtr pNotify);
        int UnregisterControlChangeNotify(IntPtr pNotify);
        int GetChannelCount(out uint pnChannelCount);
        int SetMasterVolumeLevel(float fLevel, Guid pguidEventContext);
        int SetMasterVolumeLevelScalar(float fLevel, Guid pguidEventContext);
        int GetMasterVolumeLevel(out float pfLevel);
        int GetMasterVolumeLevelScalar(out float pfLevel);
        int SetChannelVolumeLevel(uint nChannel, float fLevel, Guid pguidEventContext);
        int SetChannelVolumeLevelScalar(uint nChannel, float fLevel, Guid pguidEventContext);
        int GetChannelVolumeLevel(uint nChannel, out float pfLevel);
        int GetChannelVolumeLevelScalar(uint nChannel, out float pfLevel);
        int SetMute([MarshalAs(UnmanagedType.Bool)] bool bMute, Guid pguidEventContext);
        int GetMute(out bool pbMute);
        int GetVolumeStepInfo(out uint pnStep, out uint pnStepCount);
        int VolumeStepUp(Guid pguidEventContext);
        int VolumeStepDown(Guid pguidEventContext);
        int QueryHardwareSupport(out uint pdwHardwareSupportMask);
        int GetVolumeRange(out float pflVolumeMindB, out float pflVolumeMaxdB, out float pflVolumeIncrementdB);
    }

    public const int EDataFlowRender = 0;
    public const int EDataFlowCapture = 1;
    public const int ERoleConsole = 0;
    public const int ERoleCommunications = 2;

    public static DeviceState? GetDefaultPlaybackState()
    {
        return GetEndpointState(EDataFlowRender, ERoleConsole);
    }

    public static DeviceState? GetDefaultRecordingState()
    {
        return GetEndpointState(EDataFlowCapture, ERoleCommunications);
    }

    public static AudioDeviceInfo GetAudioState()
    {
        // Core Audio API requires STA thread
        AudioDeviceInfo? result = null;
        var thread = new Thread(() =>
        {
            result = new AudioDeviceInfo
            {
                Playback = GetEndpointState(EDataFlowRender, ERoleConsole),
                Recording = GetEndpointState(EDataFlowCapture, ERoleCommunications)
            };
        });
        thread.SetApartmentState(ApartmentState.STA);
        thread.Start();
        thread.Join();
        return result ?? new AudioDeviceInfo();
    }

    private static DeviceState? GetEndpointState(int dataFlow, int role)
    {
        IMMDeviceEnumerator? enumerator = null;
        IMMDevice? device = null;
        IAudioEndpointVolume? endpointVol = null;

        try
        {
            var devEnumeratorType = Type.GetTypeFromCLSID(CLSID_MMDeviceEnumerator);
            if (devEnumeratorType == null)
                throw new InvalidOperationException("MMDeviceEnumerator CLSID not found");

            enumerator = (IMMDeviceEnumerator)Activator.CreateInstance(devEnumeratorType)!;

            int hr = enumerator.GetDefaultAudioEndpoint(dataFlow, role, out device);
            if (hr != 0 || device == null)
                return null;

            hr = device.Activate(IID_IAudioEndpointVolume, 0, IntPtr.Zero, out endpointVol);
            if (hr != 0 || endpointVol == null)
                return null;

            bool muted = false;
            float volume = 0f;
            endpointVol.GetMute(out muted);
            endpointVol.GetMasterVolumeLevelScalar(out volume);

            return new DeviceState
            {
                Muted = muted,
                VolumePercent = (int)Math.Round(volume * 100)
            };
        }
        catch (Exception ex)
        {
            System.Console.Error.WriteLine($"AudioDeviceState error: {ex.Message}");
            return null;
        }
        finally
        {
            if (endpointVol != null) Marshal.ReleaseComObject(endpointVol);
            if (device != null) Marshal.ReleaseComObject(device);
            if (enumerator != null) Marshal.ReleaseComObject(enumerator);
        }
    }
}

public class AudioDeviceInfo
{
    public DeviceState? Playback { get; set; }
    public DeviceState? Recording { get; set; }
}

public class DeviceState
{
    public bool Muted { get; set; }
    public int VolumePercent { get; set; }
}
