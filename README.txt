UNIVERSAL PROJECTOR REMOTE — PJLink REAL-CONTROL STARTER

IMPORTANT
- This application sends real PJLink Class 1 commands. It is not a simulator.
- Only use it with projectors and networks you are authorized to control.
- A projector must support PJLink, have network control enabled, and be reachable
  from the computer running this Flask server.
- Default PJLink TCP port: 4352.
- Brand/model alone do not guarantee PJLink support.
- Projector credentials are held in server memory only; restarting the server clears
  saved profiles and credentials. They are never returned by the API.
- Do not expose this development server to the public internet.

INSTALL
1. Extract this ZIP.
2. Open the extracted "projector_control_real" folder in VS Code.
3. Open Terminal in that folder.
4. Run:
      py -m pip install -r requirements.txt
5. Start:
      py server.py
6. Open:
      http://127.0.0.1:5000

USE
1. Obtain the exact model, private IP, PJLink enablement status, and password from
   the projector owner/administrator.
2. Add the profile.
3. Click TEST CONNECTION.
4. Only after the connection is verified, use POWER ON or POWER OFF.
5. Check the returned verified state. If unsupported/unreachable/authentication
   fails, the app reports an error rather than pretending it worked.

PHONE / LAN
The default server listens only on this computer (127.0.0.1).
For a trusted private network only, run:
      py server.py --lan
Then open http://YOUR-LAPTOP-LAN-IP:5000 from the phone, if network policy permits.
Do not use LAN mode on public/untrusted Wi-Fi. Stop the server when finished.

LIMITATIONS
- PJLink Class 1 only in this first version.
- Some projectors use manufacturer-specific APIs, different PJLink classes,
  disabled network control, or administrator-managed settings.
- This version does not discover devices, scan networks, bypass authentication,
  or change projector settings.
