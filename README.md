# anycubic-lan

Talk to an Anycubic 3D printer in **LAN Mode**, directly on your network: no
Anycubic account, no cloud.

A printer with LAN Mode switched on runs its own MQTT broker. This library
performs the printer's handshake to get the broker credentials, connects,
asks for state, parses the reports into typed objects, and sends the commands
the printer accepts locally. It is fully async and has no cloud code and no
bundled certificates or keys.

Tested on a Kobra S1 (firmware 2.7.2.7). Reports from a Kobra X (firmware
2.0.2.2) informed the parser.

## Status

The specification in [`docs/`](docs/) comes first; the implementation follows
it. See [`docs/CLEAN-ROOM.md`](docs/CLEAN-ROOM.md) for how this library was
written and by whom.

## Licence

MIT.
