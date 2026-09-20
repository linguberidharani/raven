# RAVEN lab

Safe telemetry-generation scripts and the Sysmon configuration of the isolated Windows 11 lab VM.
Everything here is harmless by design: small text files and one local connection. No real ransomware,
no encryption of data, no credential access, no connection to external systems.

## Files

- `sysmon-config.xml` the Sysmon configuration running in the VM (byte-exact copy, SHA256 8AB64C55DAD6EF7D1B89000F4FC6B4D48E815A9E346BE8AB21F6A329133D2410)
- `Invoke-RavenBurst.ps1` one child process creates 60 small `.raventest` files over 30 seconds in `C:\RavenLab\burst` (telemetry for rules R001 and R003)
- `Invoke-RavenStager.ps1` one child process makes one connection to a test listener, then creates 5 small files in `C:\RavenLab\stager` (telemetry for rule R002)
- `Invoke-RavenCleanup.ps1` removes only `.raventest` files from those two folders

## Running (inside the VM only)

The VM sees this folder read-only as `\\VBoxSvr\raven_lab`.

    powershell -NoProfile -ExecutionPolicy Bypass -File \\VBoxSvr\raven_lab\Invoke-RavenBurst.ps1
    powershell -NoProfile -ExecutionPolicy Bypass -File \\VBoxSvr\raven_lab\Invoke-RavenStager.ps1
    powershell -NoProfile -ExecutionPolicy Bypass -File \\VBoxSvr\raven_lab\Invoke-RavenCleanup.ps1

Each script refuses to run when the VirtualBox Guest Additions service or the Sysmon service is missing,
so it does nothing on the host.

## Notes

- The test listener of the stager script runs inside the VM on 127.0.0.1 (only loopback or private
  addresses are accepted). The spec mentions a listener on the host-only network; loopback avoids
  changing the host firewall and keeps the connection inside the VM.
- Sysmon records the SHA256 hash in process creation events (event 1). File creation (event 11) and
  network connection (event 3) events do not carry a hash.
- Take a VM snapshot before each test session.